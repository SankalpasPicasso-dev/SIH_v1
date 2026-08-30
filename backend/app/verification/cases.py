"""Persistent case state, authorization, and manual-review helpers."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import CaseCrossVerification, CaseDocument, CaseEvent, VerificationCase
from app.risk.engine import level_for
from app.verification.case_service import cross_verify


def _pin_hash(pin: str) -> str:
    salt = os.getenv("CASE_PIN_SALT", "govdoc-synthetic-demo")
    return hashlib.sha256(f"{salt}:{pin}".encode()).hexdigest()


def event(db: Session, case_id: str, event_type: str, message: str) -> None:
    db.add(CaseEvent(case_id=case_id, event_type=event_type, message=message))


def create_case(db: Session) -> tuple[VerificationCase, str]:
    year = datetime.utcnow().year
    count = db.query(VerificationCase).count() + 1
    case_id = f"CASE-{year}-{count:05d}"
    while db.get(VerificationCase, case_id):
        count += 1
        case_id = f"CASE-{year}-{count:05d}"
    pin = f"{secrets.randbelow(1_000_000):06d}"
    case = VerificationCase(id=case_id, pin_hash=_pin_hash(pin), status="SUBMITTED")
    db.add(case)
    event(db, case_id, "CASE_CREATED", "Verification case created.")
    db.commit()
    db.refresh(case)
    return case, pin


def require_case(db: Session, case_id: str, pin: str) -> VerificationCase:
    case = db.get(VerificationCase, case_id.upper())
    if not case or not secrets.compare_digest(case.pin_hash, _pin_hash(pin)):
        raise HTTPException(401, "Invalid Case ID or access PIN")
    return case


def status_for_document(item: dict) -> str:
    state = item.get("state")
    if state == "VERIFIED_IN_SYNTHETIC_DATA":
        return "VERIFIED"
    if state == "DOCUMENT_TYPE_MISMATCH":
        return "NEEDS_INSPECTION"
    if state in {"UNABLE_TO_VERIFY", "UNABLE_TO_DETERMINE_DOCUMENT_TYPE"}:
        return "UNVERIFIABLE"
    if state in {"INFORMATION_MISMATCH", "TAMPERING_DETECTED", "NOT_FOUND"}:
        return "PENDING_OFFICER_REVIEW"
    return "NEEDS_INSPECTION"


def manual_verification_required(db: Session, case: VerificationCase, row: CaseDocument) -> tuple[bool, str | None]:
    """The final human gate is opened only by persisted automated evidence."""
    if row.status in {"MANUALLY_VERIFIED", "MANUALLY_REJECTED"}:
        return False, None
    payload = json.loads(row.payload_json)
    risk = payload.get("risk", {})
    automated_state = payload.get("state")
    if risk.get("level") in {"HIGH", "CRITICAL"}:
        return True, (risk.get("reasons") or ["High automated risk"])[0]
    if automated_state in {"DOCUMENT_TYPE_MISMATCH", "INFORMATION_MISMATCH", "TAMPERING_DETECTED", "NOT_FOUND", "UNABLE_TO_VERIFY", "UNABLE_TO_DETERMINE_DOCUMENT_TYPE"}:
        return True, payload.get("message")
    if payload.get("forensics", {}).get("indicator_score", 0) > 25:
        return True, "Suspicious forensic indicators"
    cross = db.get(CaseCrossVerification, case.id)
    if cross and json.loads(cross.result_json).get("state") == "CROSS_DOCUMENT_MISMATCH":
        return True, "Cross-document mismatch"
    return False, None


def refresh_case_status(db: Session, case: VerificationCase) -> str:
    # SessionLocal deliberately disables autoflush; make pending document rows
    # visible before deriving the case's persisted aggregate status.
    db.flush()
    docs = db.query(CaseDocument).filter_by(case_id=case.id).all()
    statuses = [doc.status for doc in docs]
    if not docs:
        case.status = "SUBMITTED"
        return case.status
    cross = db.get(CaseCrossVerification, case.id)
    cross_result = json.loads(cross.result_json) if cross else None
    required_types = {"aadhaar", "pan", "passport"}
    if any(state == "MANUALLY_REJECTED" for state in statuses):
        value = "REJECTED"
    elif any(manual_verification_required(db, case, row)[0] for row in docs):
        value = "NEEDS_VERIFICATION"
    elif set(doc.document_type for doc in docs) != required_types or not cross_result:
        value = "PROCESSING"
    elif all(state in {"VERIFIED", "MANUALLY_VERIFIED"} for state in statuses):
        value = "VERIFIED"
    else:
        value = "PROCESSING"
    case.status = value
    return value


def run_cross_verification(db: Session, case: VerificationCase) -> dict:
    rows = db.query(CaseDocument).filter_by(case_id=case.id).all()
    by_type = {row.document_type: json.loads(row.payload_json) for row in rows}
    required = {"aadhaar", "pan", "passport"}
    if set(by_type) != required:
        raise HTTPException(409, "Upload all 3 documents to enable Cross Verification")
    result = cross_verify(db, by_type)
    individual_score = max((item.get("risk", {}).get("score", 0) for item in by_type.values()), default=0)
    final_score = min(100, individual_score + result.get("score", 0))
    result["case_risk"] = {"score": final_score, "level": level_for(final_score), "reasons": result.get("reasons", [])}
    stored = db.get(CaseCrossVerification, case.id)
    if stored: stored.result_json, stored.created_at = json.dumps(result), datetime.utcnow()
    else: db.add(CaseCrossVerification(case_id=case.id, result_json=json.dumps(result)))
    event(db, case.id, "CROSS_VERIFICATION_COMPLETED", "Cross Verification completed" + (" with mismatches found." if result["state"] == "CROSS_DOCUMENT_MISMATCH" else "."))
    db.flush(); refresh_case_status(db, case); db.commit()
    return result


def replace_case_document(db: Session, case: VerificationCase, document_type: str, payload: dict) -> CaseDocument:
    row = db.query(CaseDocument).filter_by(case_id=case.id, document_type=document_type).first()
    status = status_for_document(payload)
    if row is None:
        row = CaseDocument(id=secrets.token_hex(16), case_id=case.id, document_type=document_type,
                           status=status, automated_status=status, payload_json=json.dumps(payload))
        db.add(row)
    else:
        row.status, row.automated_status, row.payload_json = status, status, json.dumps(payload)
        row.officer_decision = row.officer_reason = row.officer_decided_at = None
    event(db, case.id, "DOCUMENT_UPLOADED", f"{document_type.title()} uploaded.")
    event(db, case.id, "OCR_COMPLETED", f"OCR completed for {document_type.title()}.")
    event(db, case.id, "DATABASE_VERIFICATION_COMPLETED", f"Database verification completed for {document_type.title()}.")
    event(db, case.id, "FORENSICS_COMPLETED", f"Forensic analysis completed for {document_type.title()}.")
    if status in {"PENDING_OFFICER_REVIEW", "NEEDS_INSPECTION", "UNVERIFIABLE"}:
        event(db, case.id, "MANUAL_REVIEW_REQUESTED", f"{document_type.title()} requires officer review.")
    # A changed document invalidates the prior second-stage comparison.
    prior_cross = db.get(CaseCrossVerification, case.id)
    if prior_cross:
        db.delete(prior_cross)
        event(db, case.id, "CROSS_VERIFICATION_INVALIDATED", "A document changed; Cross Verification must be run again.")
    refresh_case_status(db, case)
    db.commit()
    db.refresh(row)
    return row


def serialise_case(db: Session, case: VerificationCase, include_evidence: bool) -> dict:
    documents = []
    for row in db.query(CaseDocument).filter_by(case_id=case.id).order_by(CaseDocument.created_at.desc()).all():
        payload = json.loads(row.payload_json)
        documents.append({
            "id": row.id, "document_type": row.document_type, "status": row.status,
            "automated_status": row.automated_status, "officer_decision": row.officer_decision,
            "officer_reason": row.officer_reason, "updated_at": row.updated_at.isoformat(),
            **({"evidence": payload} if include_evidence else {"message": payload.get("message"), "risk": payload.get("risk")}),
        })
    history = [{"type": item.event_type, "message": item.message, "timestamp": item.created_at.isoformat()}
               for item in db.query(CaseEvent).filter_by(case_id=case.id).order_by(CaseEvent.created_at).all()]
    cross = db.get(CaseCrossVerification, case.id)
    return {"case_id": case.id, "status": case.status, "created_at": case.created_at.isoformat(),
            "updated_at": case.updated_at.isoformat(), "documents": documents, "history": history,
            "cross_verification": json.loads(cross.result_json) if cross else None}
