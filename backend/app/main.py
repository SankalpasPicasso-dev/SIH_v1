import json, os, secrets, uuid
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from app.database.session import get_db, engine, Base, SessionLocal
from app.database.seed import seed
from app.database.demo_documents import make_documents, SAMPLE_DIR
from app.models.entities import VerificationResult, Citizen, Document, VerificationCase, CaseDocument
from app.verification.config import DOCUMENTS
from app.verification.service import verify_fields
from app.preprocessing.service import preprocess, UPLOAD_DIR
from app.ocr.service import LocalOCR
from app.forensics.analyzer import analyze
from app.risk.engine import calculate
from app.reports.pdf import build_report
from app.verification.case_service import evaluate_document, cross_verify
from app.verification.cases import create_case, event, manual_verification_required, require_case, replace_case_document, refresh_case_status, run_cross_verification, serialise_case

app=FastAPI(title="GovDoc Verify — Synthetic Demo", version="1.0.0")
app.mount("/files",StaticFiles(directory=str(UPLOAD_DIR)),name="files")
app.mount("/samples",StaticFiles(directory=str(SAMPLE_DIR)),name="samples")
@app.on_event("startup")
def startup():
 Base.metadata.create_all(engine); seed(); db=SessionLocal(); make_documents(db); db.close()
def save_upload(file: UploadFile):
 if not file.content_type or not (file.content_type.startswith("image/") or file.content_type=="application/pdf"): raise HTTPException(415,"Only PNG, JPEG, and PDF uploads are supported")
 content=file.file.read()
 if len(content)>10*1024*1024: raise HTTPException(413,"File must be under 10 MB")
 suffix=Path(file.filename or "upload.png").suffix.lower() or ".png"; name=f"{uuid.uuid4()}{suffix}"; path=UPLOAD_DIR/name
 path.write_bytes(content); return str(path),name

def as_image(path: str) -> str:
 """Render the first PDF page locally; image uploads pass through unchanged."""
 if Path(path).suffix.lower() != ".pdf": return path
 try:
  import fitz
  pdf=fitz.open(path); page=pdf.load_page(0); pix=page.get_pixmap(matrix=fitz.Matrix(2,2), alpha=False)
  output=UPLOAD_DIR/f"{Path(path).stem}_page1.png"; pix.save(str(output)); pdf.close(); return str(output)
 except Exception as exc: raise HTTPException(422, f"PDF could not be processed: {exc}")

OFFICER_ID=os.getenv("OFFICER_ID", "OFFICER")
# Demo-only universal PIN. Set OFFICER_ACCESS_PIN in the backend environment.
OFFICER_ACCESS_PIN=os.getenv("OFFICER_ACCESS_PIN", "OFFICER2026")
_officer_tokens:set[str]=set()
def require_officer(authorization: str | None = Header(default=None)):
 token=(authorization or "").removeprefix("Bearer ").strip()
 if token not in _officer_tokens: raise HTTPException(401,"Officer authentication required")
 return token
@app.get("/api/health")
def health(): return {"status":"ok","data_scope":"synthetic/demo only"}
@app.get("/api/document-types")
def types(): return [{"id":k,"label":v["label"],"fields":v["fields"]} for k,v in DOCUMENTS.items()]
@app.get("/api/demo-cases")
def demo_cases(db:Session=Depends(get_db)):
 """A small selection of downloadable, generated synthetic three-document fixtures."""
 rows=[]
 for citizen in db.query(Citizen).limit(8):
  docs=db.query(Document).filter_by(citizen_id=citizen.id).all()
  rows.append({"citizen":"Synthetic fixture: "+citizen.name,"documents":{d.document_type:f"/samples/{d.document_type}_{d.identifier}.png" for d in docs}})
 return rows
@app.post("/api/enhance")
def enhance(file:UploadFile=File(...)):
 path,name=save_upload(file); image_path=as_image(path); result=preprocess(image_path); return {"original_url":f"/files/{name}","enhanced_url":f"/files/{Path(result['enhanced_path']).name}",**result}
@app.post("/api/ocr")
def ocr(document_type:str=Form(...), file:UploadFile=File(...)):
 if document_type not in DOCUMENTS: raise HTTPException(404,"Unsupported document type")
 path,_=save_upload(file); data=preprocess(as_image(path)); evidence=LocalOCR().extract(data["ocr_paths"],document_type)
 return {"fields":evidence["fields"],"confidence":evidence["confidence"],"raw_text":evidence["raw_text"],"boxes":evidence["boxes"],"engine":evidence["engine"],"message":"Fields are extracted from the visible document image only."}
@app.post("/api/forensics")
def forensics(file:UploadFile=File(...)):
 path,_=save_upload(file); return analyze(as_image(path), artifact_dir=UPLOAD_DIR)
@app.post("/api/verify/{document_type}")
def verify(document_type:str, file:UploadFile=File(...), db:Session=Depends(get_db)):
 if document_type not in DOCUMENTS: raise HTTPException(404,"Unsupported document type")
 path,name=save_upload(file); image_path=as_image(path); image=preprocess(image_path); evidence=LocalOCR().extract(image["ocr_paths"],document_type); extracted,confidence=evidence["fields"],evidence["confidence"]
 fields,doc=verify_fields(db,document_type,extracted,confidence); forensic=analyze(image_path, artifact_dir=UPLOAD_DIR)
 risk=calculate(fields,forensic,doc.status if doc else None,confidence)
 result={"id":str(uuid.uuid4()),"document_type":document_type,"data_source":doc.source if doc else None,"extracted_fields":extracted,"fields":[f.model_dump() for f in fields],"ocr":evidence,"forensics":forensic,"risk":risk,"image":{"original_url":f"/files/{name}","enhanced_url":f"/files/{Path(image['enhanced_path']).name}","quality":image["quality"],"ocr_confidence":confidence},"disclaimer":"Synthetic/demo data only. OCR and forensic indicators are decision support, not proof of fraud."}
 db.add(VerificationResult(id=result["id"],document_type=document_type,score=risk["score"],level=risk["level"],payload_json=json.dumps(result)));db.commit()
 return result

@app.post("/api/cases")
def new_case(db:Session=Depends(get_db)):
 case,pin=create_case(db)
 return {"case_id":case.id,"access_pin":pin,"status":case.status,"message":"Save this Case ID and Access PIN to track your verification."}

@app.post("/api/cases/access")
def access_case(case_id:str=Form(...), access_pin:str=Form(...), db:Session=Depends(get_db)):
 case=require_case(db,case_id,access_pin)
 return serialise_case(db,case,include_evidence=False)

@app.post("/api/cases/{case_id}/documents")
def upload_case_document(case_id:str, document_type:str=Form(...), access_pin:str=Form(...), file:UploadFile=File(...), db:Session=Depends(get_db)):
 if document_type not in DOCUMENTS: raise HTTPException(404,"Unsupported document type")
 case=require_case(db,case_id,access_pin)
 path,name=save_upload(file); image_path=as_image(path); image=preprocess(image_path)
 evidence=LocalOCR().extract(image["ocr_paths"],document_type)
 payload=evaluate_document(db,document_type,image_path,f"/files/{name}",f"/files/{Path(image['enhanced_path']).name}",image["quality"],evidence)
 payload["image"].update({"original_file_type": Path(path).suffix.lower(), "original_preview_url": f"/files/{Path(image_path).name}"})
 row=replace_case_document(db,case,document_type,payload)
 return {"case":serialise_case(db,case,include_evidence=False),"document":{"id":row.id,"status":row.status,"automated_status":row.automated_status}}

@app.post("/api/cases/{case_id}/cross-verification")
def cross_verification(case_id:str, access_pin:str=Form(...), db:Session=Depends(get_db)):
 case=require_case(db,case_id,access_pin)
 result=run_cross_verification(db,case)
 return {"case":serialise_case(db,case,include_evidence=False),"cross_verification":result}

@app.post("/api/officer/login")
def officer_login(officer_id:str=Form(...), access_pin:str=Form(...)):
 if not (secrets.compare_digest(officer_id,OFFICER_ID) and secrets.compare_digest(access_pin,OFFICER_ACCESS_PIN)):
  raise HTTPException(401,"Invalid officer credentials")
 token=secrets.token_urlsafe(32); _officer_tokens.add(token); return {"token":token}

@app.post("/api/officer/logout")
def officer_logout(authorization: str | None = Header(default=None)):
 token=(authorization or "").removeprefix("Bearer ").strip(); _officer_tokens.discard(token); return {"ok":True}

@app.get("/api/officer/dashboard")
def officer_dashboard(_token:str=Depends(require_officer), db:Session=Depends(get_db)):
 docs=db.query(CaseDocument).order_by(CaseDocument.created_at.desc()).all()
 document_queue=[]
 for d in docs:
  case=db.get(VerificationCase,d.case_id); payload=json.loads(d.payload_json); required,reason=manual_verification_required(db,case,d)
  document_queue.append({"id":d.id,"case_id":d.case_id,"document_type":d.document_type,"status":d.status,"submitted_at":d.created_at.isoformat(),"risk":payload.get("risk") or {"score":0,"level":"LOW"},"manual_verification_required":required,"review_reason":reason})
 case_summaries=[]
 for case in db.query(VerificationCase).order_by(VerificationCase.updated_at.desc()).all():
  detail=serialise_case(db,case,include_evidence=False)
  document_risks=[(item.get("risk") or {}).get("score",0) for item in detail["documents"]]
  cross_risk=(detail.get("cross_verification") or {}).get("case_risk",{}).get("score",0)
  score=max([cross_risk,*document_risks],default=0)
  level=(detail.get("cross_verification") or {}).get("case_risk",{}).get("level")
  if not level: level="LOW" if score<=20 else "MODERATE" if score<=40 else "HIGH" if score<=70 else "CRITICAL"
  case_summaries.append({"case_id":case.id,"status":case.status,"updated_at":case.updated_at.isoformat(),"document_count":len(detail["documents"]),"risk":{"score":score,"level":level},"documents":detail["documents"]})
 return {"low_risk":sum((json.loads(d.payload_json).get("risk") or {}).get("level")=="LOW" for d in docs),
  "high_risk":sum((json.loads(d.payload_json).get("risk") or {}).get("level") in {"HIGH","CRITICAL"} for d in docs),
  "needs_inspection":sum(d["manual_verification_required"] for d in document_queue),"all_documents":len(docs), "documents":document_queue,
  "cases":case_summaries}

@app.get("/api/officer/cases/{case_id}")
def officer_case(case_id:str, _token:str=Depends(require_officer), db:Session=Depends(get_db)):
 case=db.get(VerificationCase,case_id.upper())
 if not case: raise HTTPException(404,"Case not found")
 return serialise_case(db,case,include_evidence=True)

@app.post("/api/officer/cases/{case_id}/documents/{document_id}/decision")
def officer_decision(case_id:str,document_id:str, action:str=Form(...), reason:str=Form(""), _token:str=Depends(require_officer), db:Session=Depends(get_db)):
 if action not in {"MARK_VERIFIED","MARK_REJECTED","KEEP_NEEDS_INSPECTION"}: raise HTTPException(422,"Unsupported officer action")
 if action=="MARK_REJECTED" and not reason.strip(): raise HTTPException(422,"A reason is required when rejecting")
 case=db.get(VerificationCase,case_id.upper()); row=db.get(CaseDocument,document_id)
 if not case or not row or row.case_id!=case.id: raise HTTPException(404,"Case document not found")
 required,_reason=manual_verification_required(db,case,row)
 if not required: raise HTTPException(409,"Manual verification is not required for this document")
 status={"MARK_VERIFIED":"MANUALLY_VERIFIED","MARK_REJECTED":"MANUALLY_REJECTED","KEEP_NEEDS_INSPECTION":"NEEDS_INSPECTION"}[action]
 row.status=status; row.officer_decision=action; row.officer_reason=reason.strip() or None; row.officer_decided_at=__import__('datetime').datetime.utcnow()
 event(db,case.id,"OFFICER_DECISION",f"Officer action for {row.document_type.title()}: {action}.")
 refresh_case_status(db,case); db.commit()
 return serialise_case(db,case,include_evidence=True)
@app.post("/api/verify-case")
def verify_case(aadhaar:UploadFile=File(...), pan:UploadFile=File(...), passport:UploadFile=File(...), db:Session=Depends(get_db)):
 uploaded={"aadhaar":aadhaar,"pan":pan,"passport":passport}; checks={}
 for kind,file in uploaded.items():
  path,name=save_upload(file); image=preprocess(path)
  evidence=LocalOCR().extract(image["ocr_paths"],kind)
  checks[kind]=evaluate_document(db,kind,path,f"/files/{name}",f"/files/{Path(image['enhanced_path']).name}",image["quality"],evidence)
 cross=cross_verify(db,checks); result={"id":str(uuid.uuid4()),"documents":checks,"cross_verification":cross,"disclaimer":"Synthetic/demo data only. A consistent result only means the three generated demo cards resolve to one fictional local record; it is not government verification."}
 score=cross["score"] if cross["score"] is not None else 0; level=cross["level"] or "UNVERIFIABLE"
 db.add(VerificationResult(id=result["id"],document_type="three_document_case",score=score,level=level,payload_json=json.dumps(result)));db.commit()
 return result
@app.get("/api/results/{result_id}")
def result(result_id:str,db:Session=Depends(get_db)):
 row=db.get(VerificationResult,result_id)
 if not row: raise HTTPException(404,"Result not found")
 return json.loads(row.payload_json)
@app.get("/api/report/{result_id}")
def report(result_id:str,db:Session=Depends(get_db)):
 row=db.get(VerificationResult,result_id)
 if not row: raise HTTPException(404,"Result not found")
 return StreamingResponse(build_report(json.loads(row.payload_json)),media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="govdoc-demo-{result_id}.pdf"'})
