"""Single configurable, evidence-led risk scoring policy."""

WEIGHTS = {
    "database_dob_mismatch": 25, "database_other_mismatch": 15,
    "invalid_identifier": 25, "not_found": 12, "low_ocr": 8,
    "forensic_cap": 18, "expired": 7, "document_type_mismatch": 45,
}

def level_for(score: int) -> str:
    return "LOW" if score <= 20 else "MODERATE" if score <= 40 else "HIGH" if score <= 70 else "CRITICAL"

def calculate(fields, forensics, doc_status=None, confidence=.83, document_type_mismatch=False):
    score=0; reasons=[]
    if document_type_mismatch:
        score += WEIGHTS["document_type_mismatch"]; reasons.append(f"Detected document type differs from selected type +{WEIGHTS['document_type_mismatch']}")
    for f in fields:
      if f.status=="MISMATCH":
        points=WEIGHTS["database_dob_mismatch"] if f.field=="date_of_birth" else WEIGHTS["database_other_mismatch"]
        score+=points; reasons.append(f"{f.field.replace('_',' ').title()} mismatch +{points}")
      elif f.status=="INVALID_FORMAT": score+=WEIGHTS["invalid_identifier"]; reasons.append(f"Invalid document-number format +{WEIGHTS['invalid_identifier']}")
      elif f.status=="NOT_FOUND": score+=WEIGHTS["not_found"]; reasons.append(f"No matching synthetic record +{WEIGHTS['not_found']}")
      elif f.status=="LOW_CONFIDENCE": score+=WEIGHTS["low_ocr"]; reasons.append(f"Low OCR confidence +{WEIGHTS['low_ocr']}")
    if confidence < .55 and not any(f.status=="LOW_CONFIDENCE" for f in fields): score+=WEIGHTS["low_ocr"]; reasons.append(f"Low OCR confidence +{WEIGHTS['low_ocr']}")
    forensic_score=forensics.get("indicator_score",0)
    if forensic_score>25:
        points=min(WEIGHTS["forensic_cap"],round(forensic_score*.35)); score+=points; reasons.append(f"Forensic risk indicator +{points}")
    if doc_status=="expired": score+=WEIGHTS["expired"]; reasons.append(f"Document is expired +{WEIGHTS['expired']}")
    score=min(100,score)
    return {"score":score,"level":level_for(score),"reasons":reasons or ["No significant verification issues detected."],"note":"This is a transparent demo heuristic, not a fraud determination."}
