import json, re
from typing import Optional
from sqlalchemy.orm import Session
from app.models.entities import Document
from app.schemas.contracts import FieldResult
from app.verification.config import DOCUMENTS

def normalise(value: Optional[str]) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())

def verify_fields(db: Session, kind: str, extracted: dict, confidence: float = .83):
    cfg = DOCUMENTS[kind]; identifier = extracted.get(cfg["identifier"], "")
    doc = db.query(Document).filter_by(document_type=kind, identifier=identifier).first()
    expected = json.loads(doc.fields_json) if doc else {}
    results=[]
    for field in cfg["fields"]:
        actual = extracted.get(field)
        if field == cfg["identifier"] and actual and not re.match(cfg["pattern"], actual.upper()):
            status, sev = "INVALID_FORMAT", "high"
        elif confidence < .55: status, sev = "LOW_CONFIDENCE", "medium"
        elif not doc: status, sev = "NOT_FOUND", "medium"
        elif field not in expected: status, sev = "NOT_AVAILABLE", "info"
        elif normalise(actual) == normalise(expected.get(field)): status, sev = "MATCH", "info"
        else: status, sev = "MISMATCH", "high" if field in ("date_of_birth", cfg["identifier"]) else "medium"
        results.append(FieldResult(field=field, extracted_value=actual, expected_value=expected.get(field), status=status, severity=sev, confidence=round(confidence,2)))
    return results, doc
