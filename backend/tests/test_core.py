import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.database.demo_documents import SAMPLE_DIR, make_documents
from app.database.seed import seed
from app.database.session import SessionLocal
from app.models.entities import Document
from app.models.entities import CaseDocument
from app.ocr.service import LocalOCR
from app.preprocessing.service import preprocess
from app.risk.engine import calculate
from app.schemas.contracts import FieldResult
from app.verification.case_service import cross_verify, evaluate_document
from app.verification.config import DOCUMENTS
from app.verification.service import normalise
from app.verification.cases import create_case, require_case, replace_case_document, refresh_case_status, run_cross_verification, serialise_case
from app.verification.case_service import detect_document_type
from fastapi import HTTPException
from fastapi.testclient import TestClient
import cv2
import numpy as np
from app.forensics.analyzer import analyze


def test_normalise(): assert normalise("Aarav-Mehta ") == "AARAVMEHTA"


def test_demo_patterns():
    assert __import__('re').match(DOCUMENTS['aadhaar']['pattern'], 'DEM-AAR-1024')
    assert __import__('re').match(DOCUMENTS['pan']['pattern'], 'TESTV1234K')
    assert not __import__('re').match(DOCUMENTS['pan']['pattern'], 'TEST1234')


def test_risk_is_transparent():
    field = [FieldResult(field='date_of_birth', extracted_value='1999', expected_value='1998', status='MISMATCH', severity='high')]
    assert calculate(field, {"indicator_score": 0})['score'] == 25


def test_optional_forensic_detectors_are_evidence_only_and_keep_artifacts_scoped(tmp_path, monkeypatch):
    image = np.full((160, 240, 3), 220, dtype=np.uint8)
    cv2.rectangle(image, (30, 30), (90, 90), (20, 20, 20), -1)
    path = tmp_path / "document.png"; cv2.imwrite(str(path), image)
    result = analyze(str(path), artifact_dir=tmp_path)
    assert {"localized_ela", "copy_move", "resampling", "jpeg_blocks", "edge_inconsistency"} <= set(result["advanced"])
    assert 0.5 <= result["confidence"] <= 1
    assert "not proof" in result["note"]
    monkeypatch.setenv("FORENSICS_COPY_MOVE_ENABLED", "false")
    disabled = analyze(str(path), artifact_dir=tmp_path)
    assert disabled["advanced"]["copy_move"]["enabled"] is False


def test_case_evidence_uses_existing_upload_storage_for_forensic_overlays(tmp_path):
    image = np.full((180, 260, 3), 200, dtype=np.uint8)
    path = tmp_path / "case-upload.png"; cv2.imwrite(str(path), image)
    result = analyze(str(path), artifact_dir=tmp_path)
    assert all(url.startswith("/files/") for url in result["artifact_urls"])


def test_real_ocr_pipeline():
    """Fixture evaluation uses the same local OCR pipeline as an upload."""
    seed(); db = SessionLocal(); make_documents(db); ocr = LocalOCR(); checks = {}
    for doc in db.query(Document).filter_by(citizen_id=1).all():
        source = SAMPLE_DIR / f"{doc.document_type}_{doc.identifier}.png"
        processed = preprocess(str(source))
        evidence = ocr.extract(processed['ocr_paths'], doc.document_type)
        assert evidence['raw_text'] and evidence['fields'][DOCUMENTS[doc.document_type]['identifier']] == doc.identifier
        checks[doc.document_type] = evaluate_document(db, doc.document_type, str(source), '/original', '/enhanced', 'adequate', evidence)
        assert checks[doc.document_type]['state'] == 'VERIFIED_IN_SYNTHETIC_DATA'
    assert cross_verify(db, checks)['state'] == 'CONSISTENT'
    db.close()


def test_sanitized_repo_b_format_fixtures_use_the_same_pipeline_and_cross_verify():
    seed(); db = SessionLocal(); make_documents(db); ocr = LocalOCR(); checks = {}
    for doc in db.query(Document).filter_by(source="repo_b").all():
        source = SAMPLE_DIR / f"{doc.document_type}_{doc.identifier}.png"
        evidence = ocr.extract(preprocess(str(source))["ocr_paths"], doc.document_type)
        assert evidence["raw_text"] and evidence["fields"][DOCUMENTS[doc.document_type]["identifier"]] == doc.identifier
        result = evaluate_document(db, doc.document_type, str(source), "/original", "/enhanced", "adequate", evidence)
        assert result["state"] == "VERIFIED_IN_SYNTHETIC_DATA"
        assert result["data_source"] == "repo_b"
        assert result["forensics"]["advanced"] and result["risk"]["level"] == "LOW"
        checks[doc.document_type] = result
    assert cross_verify(db, checks)["state"] == "CONSISTENT"
    db.close()


def test_persistent_case_requires_pin_and_keeps_automated_result():
    db = SessionLocal()
    case, pin = create_case(db)
    assert require_case(db, case.id, pin).id == case.id
    try:
        require_case(db, case.id, "000000")
        assert False, "a wrong PIN must not grant access"
    except HTTPException as exc:
        assert exc.status_code == 401
    payload = {"state": "INFORMATION_MISMATCH", "message": "Mismatch detected", "risk": {"score": 40, "level": "MODERATE"}}
    row = replace_case_document(db, case, "aadhaar", payload)
    assert row.automated_status == "PENDING_OFFICER_REVIEW"
    assert serialise_case(db, case, include_evidence=False)["status"] == "NEEDS_VERIFICATION"
    db.close()


def test_case_api_user_to_officer_review_flow():
    from app.main import app
    with TestClient(app) as client:
        created = client.post("/api/cases").json()
        case_id, pin = created["case_id"], created["access_pin"]
        assert client.post("/api/cases/access", data={"case_id": case_id, "access_pin": "wrong"}).status_code == 401
        source = SAMPLE_DIR / "passport_DMP100001.png"
        with source.open("rb") as upload:
            response = client.post(f"/api/cases/{case_id}/documents", data={"document_type": "pan", "access_pin": pin}, files={"file": (source.name, upload, "image/png")})
        assert response.status_code == 200
        login = client.post("/api/officer/login", data={"officer_id": "OFFICER", "access_pin": "OFFICER2026"})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['token']}"}
        detail = client.get(f"/api/officer/cases/{case_id}", headers=headers)
        assert detail.status_code == 200
        forensic_evidence = detail.json()["documents"][0]["evidence"]["forensics"]
        assert "advanced" in forensic_evidence
        assert forensic_evidence["advanced"]["copy_move"]["enabled"] is True
        original_url = detail.json()["documents"][0]["evidence"]["image"]["original_url"]
        assert client.get(original_url).status_code == 200
        document_id = detail.json()["documents"][0]["id"]
        assert detail.json()["documents"][0]["evidence"]["state"] == "DOCUMENT_TYPE_MISMATCH"
        final = client.post(f"/api/officer/cases/{case_id}/documents/{document_id}/decision", data={"action": "MARK_VERIFIED", "reason": "Visible synthetic fields reviewed."}, headers=headers)
        assert final.status_code == 200
        assert final.json()["documents"][0]["status"] == "MANUALLY_VERIFIED"
        assert final.json()["documents"][0]["evidence"]["risk"]["level"] == "HIGH"


def test_clean_document_cannot_bypass_manual_verification_gate():
    from app.main import app
    with TestClient(app) as client:
        created = client.post("/api/cases").json()
        source = SAMPLE_DIR / "aadhaar_DEM-AAR-1001.png"
        with source.open("rb") as upload:
            response = client.post(f"/api/cases/{created['case_id']}/documents", data={"document_type": "aadhaar", "access_pin": created["access_pin"]}, files={"file": (source.name, upload, "image/png")})
        assert response.status_code == 200
        token = client.post("/api/officer/login", data={"officer_id": "OFFICER", "access_pin": "OFFICER2026"}).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        detail = client.get(f"/api/officer/cases/{created['case_id']}", headers=headers).json()
        decision = client.post(f"/api/officer/cases/{created['case_id']}/documents/{detail['documents'][0]['id']}/decision", data={"action": "MARK_VERIFIED"}, headers=headers)
        assert decision.status_code == 409


def test_uploaded_pdf_original_and_rendered_preview_are_served_to_officer():
    from reportlab.pdfgen import canvas
    from app.main import app
    buffer = BytesIO(); page = canvas.Canvas(buffer); page.drawString(72, 720, "SYNTHETIC PASSPORT DMP100001"); page.save()
    with TestClient(app) as client:
        created = client.post("/api/cases").json()
        response = client.post(f"/api/cases/{created['case_id']}/documents", data={"document_type": "passport", "access_pin": created["access_pin"]}, files={"file": ("synthetic.pdf", buffer.getvalue(), "application/pdf")})
        assert response.status_code == 200
        token = client.post("/api/officer/login", data={"officer_id": "OFFICER", "access_pin": "OFFICER2026"}).json()["token"]
        detail = client.get(f"/api/officer/cases/{created['case_id']}", headers={"Authorization": f"Bearer {token}"}).json()
        image = detail["documents"][0]["evidence"]["image"]
        assert image["original_file_type"] == ".pdf"
        assert client.get(image["original_url"]).status_code == 200
        assert client.get(image["original_preview_url"]).status_code == 200


def test_cross_verification_is_an_explicit_persisted_gate():
    db = SessionLocal(); case, _pin = create_case(db)
    base = {"state": "VERIFIED_IN_SYNTHETIC_DATA", "risk": {"score": 0, "level": "LOW"}}
    replace_case_document(db, case, "aadhaar", {**base, "document_type": "aadhaar", "extracted_fields": {"name": "Demo Aarav Mehta", "date_of_birth": "1994-02-14", "gender": "Male"}})
    try:
        run_cross_verification(db, case)
        assert False, "cross verification must be disabled until all three documents exist"
    except HTTPException as exc:
        assert exc.status_code == 409
    replace_case_document(db, case, "pan", {**base, "document_type": "pan", "extracted_fields": {"name": "Demo Aarav Mehta", "date_of_birth": "1994-02-14"}})
    replace_case_document(db, case, "passport", {**base, "document_type": "passport", "extracted_fields": {"given_name": "Demo Aarav", "surname": "Mehta", "date_of_birth": "1994-02-14", "sex": "M"}})
    result = run_cross_verification(db, case)
    assert result["state"] == "CONSISTENT"
    assert serialise_case(db, case, include_evidence=False)["cross_verification"]["state"] == "CONSISTENT"
    db.close()


def test_cross_mismatch_increases_case_risk_and_requires_review():
    db = SessionLocal(); case, _pin = create_case(db)
    base = {"state": "VERIFIED_IN_SYNTHETIC_DATA", "risk": {"score": 20, "level": "LOW"}}
    replace_case_document(db, case, "aadhaar", {**base, "document_type": "aadhaar", "extracted_fields": {"name": "Demo Aarav Mehta", "date_of_birth": "1994-02-14", "gender": "Male"}})
    replace_case_document(db, case, "pan", {**base, "document_type": "pan", "extracted_fields": {"name": "Demo Aarav Mehta", "date_of_birth": "1994-02-14"}})
    replace_case_document(db, case, "passport", {**base, "document_type": "passport", "extracted_fields": {"given_name": "Demo Aarav", "surname": "Mehta", "date_of_birth": "1990-02-14", "sex": "M"}})
    assert refresh_case_status(db, case) == "PROCESSING"
    result = run_cross_verification(db, case)
    assert result["state"] == "CROSS_DOCUMENT_MISMATCH"
    assert result["case_risk"]["score"] >= 45
    assert result["case_risk"]["level"] == "HIGH"
    assert case.status == "NEEDS_VERIFICATION"
    db.close()


def test_detect_document_type_independently_of_selected_parser():
    assert detect_document_type("SYNTHETIC PASSPORT DMP100001") == "passport"
    assert detect_document_type("AADHAAR DEM-AAR-1001") == "aadhaar"
    assert detect_document_type("PAN DEMAME001X") == "pan"


def test_wrong_document_type_is_explicit_and_routed_to_inspection():
    db = SessionLocal(); source = SAMPLE_DIR / "passport_DMP100001.png"
    evidence = LocalOCR().extract(preprocess(str(source))["ocr_paths"], "pan")
    result = evaluate_document(db, "pan", str(source), "/original", "/enhanced", "adequate", evidence)
    assert result["state"] == "DOCUMENT_TYPE_MISMATCH"
    assert result["detected_document_type"] == "passport"
    assert "expected Pan, detected Passport" in result["message"]
    case, _pin = create_case(db)
    assert replace_case_document(db, case, "pan", result).status == "NEEDS_INSPECTION"
    db.close()


def test_case_status_is_verified_only_after_all_documents_and_cross_check():
    db = SessionLocal(); case, _pin = create_case(db)
    base = {"state": "VERIFIED_IN_SYNTHETIC_DATA", "risk": {"score": 0, "level": "LOW"}}
    replace_case_document(db, case, "aadhaar", {**base, "document_type": "aadhaar", "extracted_fields": {"name": "Demo Aarav Mehta", "date_of_birth": "1994-02-14", "gender": "Male"}})
    assert case.status == "PROCESSING"
    replace_case_document(db, case, "pan", {**base, "document_type": "pan", "extracted_fields": {"name": "Demo Aarav Mehta", "date_of_birth": "1994-02-14"}})
    replace_case_document(db, case, "passport", {**base, "document_type": "passport", "extracted_fields": {"given_name": "Demo Aarav", "surname": "Mehta", "date_of_birth": "1994-02-14", "sex": "M"}})
    assert case.status == "PROCESSING"
    run_cross_verification(db, case)
    assert case.status == "VERIFIED"
    db.close()


def test_rejection_wins_case_status_and_universal_pin_is_not_returned():
    from app.main import app
    with TestClient(app) as client:
        created = client.post("/api/cases").json()
        source = SAMPLE_DIR / "passport_DMP100001.png"
        with source.open("rb") as upload:
            client.post(f"/api/cases/{created['case_id']}/documents", data={"document_type": "pan", "access_pin": created["access_pin"]}, files={"file": (source.name, upload, "image/png")})
        assert client.post("/api/officer/login", data={"officer_id": "OFFICER", "access_pin": "wrong"}).status_code == 401
        login = client.post("/api/officer/login", data={"officer_id": "OFFICER", "access_pin": "OFFICER2026"})
        assert "access_pin" not in login.json()
        headers = {"Authorization": f"Bearer {login.json()['token']}"}
        dashboard = client.get("/api/officer/dashboard", headers=headers).json()
        assert "OFFICER2026" not in str(dashboard)
        detail = client.get(f"/api/officer/cases/{created['case_id']}", headers=headers).json()
        row_id = detail["documents"][0]["id"]
        rejected = client.post(f"/api/officer/cases/{created['case_id']}/documents/{row_id}/decision", data={"action": "MARK_REJECTED", "reason": "Synthetic mismatch confirmed."}, headers=headers)
        assert rejected.status_code == 200
        assert rejected.json()["status"] == "REJECTED"


def test_officer_dashboard_orders_documents_newest_first():
    from app.main import app
    with TestClient(app) as client:
        token = client.post("/api/officer/login", data={"officer_id": "OFFICER", "access_pin": "OFFICER2026"}).json()["token"]
        dashboard = client.get("/api/officer/dashboard", headers={"Authorization": f"Bearer {token}"}).json()
        stamps = [item["submitted_at"] for item in dashboard["documents"]]
        assert stamps == sorted(stamps, reverse=True)
