"""Verification orchestration driven exclusively by OCR-extracted fields."""
from app.forensics.analyzer import analyze
from app.preprocessing.service import UPLOAD_DIR
from app.risk.engine import calculate
from app.verification.service import normalise, verify_fields


def evaluate_document(db, kind: str, path: str, original_url: str, enhanced_url: str, quality: str, ocr: dict):
    forensic = analyze(path, artifact_dir=UPLOAD_DIR)
    extracted, confidence = ocr["fields"], ocr["confidence"]
    base = {"document_type": kind, "citizen_id": None, "extracted_fields": extracted, "ocr": {key: ocr.get(key) for key in ("raw_text", "confidence", "boxes", "engine", "error")}, "forensics": forensic, "image": {"original_url": original_url, "enhanced_url": enhanced_url, "quality": quality}}
    raw = (ocr.get("raw_text") or "").upper()
    detected_type = detect_document_type(raw)
    base["detected_document_type"] = detected_type
    if detected_type and detected_type != kind:
        risk = calculate([], forensic, None, confidence, document_type_mismatch=True)
        return {**base, "state": "DOCUMENT_TYPE_MISMATCH", "message": f"Document type mismatch: expected {kind.title()}, detected {detected_type.title()}.", "fields": [], "risk": risk}
    if raw and not detected_type:
        return {**base, "state": "UNABLE_TO_DETERMINE_DOCUMENT_TYPE", "message": "Unable to determine document type.", "fields": [], "risk": calculate([], forensic, None, confidence)}
    identifier = extracted.get(__import__("app.verification.config", fromlist=["DOCUMENTS"]).DOCUMENTS[kind]["identifier"])
    if not extracted or not identifier or confidence < .35:
        return {**base, "state": "UNABLE_TO_VERIFY", "message": "Unable to reliably extract the document number from visible text.", "fields": [], "risk": calculate([], forensic, None, confidence)}
    fields, doc = verify_fields(db, kind, extracted, confidence)
    risk = calculate(fields, forensic, doc.status if doc else None, confidence)
    if not doc:
        state, message = "NOT_FOUND", "Document not found in the local synthetic database."
    elif any(field.status in ("MISMATCH", "INVALID_FORMAT") for field in fields):
        state, message = "INFORMATION_MISMATCH", "Document found but information mismatch detected."
    elif forensic["indicator_score"] >= 60:
        state, message = "TAMPERING_DETECTED", "Strong forensic indicators require manual review for possible tampering."
    else:
        state, message = "VERIFIED_IN_SYNTHETIC_DATA", "Document verified against the approved local reference data."
    return {**base, "state": state, "message": message, "citizen_id": doc.citizen_id if doc else None, "data_source": doc.source if doc else None, "fields": [field.model_dump() for field in fields], "risk": risk, "expired": bool(doc and doc.status == "expired")}


def detect_document_type(raw: str) -> str | None:
    """Content-based type detection independent of the selected parser."""
    hits = {
        "aadhaar": bool(__import__("re").search(r"AADHAAR|AADHAR|DEM[-\s]?[A-Z]{3}[-\s]?\d{4}|\b\d{4}\s?\d{4}\s?\d{4}\b", raw)),
        "pan": bool(__import__("re").search(r"\bPAN\b|INCOM\w{0,3}\s*TAX|PERMANENT\s+ACCOUNT|DEM[A-Z]{3}\d{3}X|\b[A-Z]{5}\d{4}[A-Z]\b", raw)),
        "passport": bool(__import__("re").search(r"PASSPORT|DMP\d{6}|\b[A-Z]\d{7}\b", raw)),
    }
    found = [kind for kind, matched in hits.items() if matched]
    return found[0] if len(found) == 1 else None


def _same_name(left: str | None, right: str | None) -> bool:
    if not left or not right: return False
    return set(left.upper().split()) == set(right.upper().split())


def _person_name(item: dict) -> str | None:
    values = item["extracted_fields"]
    return f"{values.get('given_name', '')} {values.get('surname', '')}".strip() if item["document_type"] == "passport" else values.get("name")


def cross_verify(_db, checks: dict):
    unavailable = [kind for kind, item in checks.items() if item["state"] == "UNABLE_TO_VERIFY"]
    if unavailable:
        return {"state": "UNABLE_TO_VERIFY", "score": None, "level": None, "reasons": [f"{', '.join(unavailable)} could not be OCR-extracted reliably"], "checks": []}
    checks_out, mismatches = [], []
    names = [_person_name(item) for item in checks.values()]
    if all(names) and all(_same_name(names[0], name) for name in names[1:]):
        checks_out.append({"field": "name", "status": "MATCH", "values": names, "note": "OCR-extracted names agree after order/case normalization."})
    else:
        mismatches.append("name"); checks_out.append({"field": "name", "status": "MISMATCH", "values": names, "note": "OCR-extracted names conflict."})
    dobs = [item["extracted_fields"].get("date_of_birth") for item in checks.values()]
    if all(dobs) and len(set(dobs)) == 1:
        checks_out.append({"field": "date_of_birth", "status": "MATCH", "values": dobs, "note": "OCR-extracted dates of birth agree."})
    else:
        mismatches.append("date_of_birth"); checks_out.append({"field": "date_of_birth", "status": "MISMATCH", "values": dobs, "note": "OCR-extracted dates of birth conflict or are missing."})
    gender = checks["aadhaar"]["extracted_fields"].get("gender", "").upper()[:1]
    sex = checks["passport"]["extracted_fields"].get("sex", "").upper()[:1]
    status = "MATCH" if gender and gender == sex else "MISMATCH"
    if status == "MISMATCH": mismatches.append("gender_sex")
    checks_out.append({"field": "gender_sex", "status": status, "values": [gender, sex], "note": "Aadhaar-like gender and passport-like sex are compared from OCR."})
    if mismatches:
        score = min(60, 25 * len(mismatches))
        level = "HIGH" if score > 40 else "MODERATE"
        return {"state": "CROSS_DOCUMENT_MISMATCH", "score": score, "level": level, "reasons": [f"Cross-document mismatch: {', '.join(mismatches)} +{score}"], "checks": checks_out}
    expired = checks["passport"].get("expired", False)
    return {"state": "NEEDS_MANUAL_REVIEW" if expired else "CONSISTENT", "score": 7 if expired else 0, "level": "MODERATE" if expired else "LOW", "reasons": ["OCR-extracted fields are cross-document consistent."] + (["Passport is expired +7"] if expired else []), "checks": checks_out}
