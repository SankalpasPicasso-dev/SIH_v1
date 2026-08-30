"""Creates visually labelled, synthetic test cards for local OCR evaluation."""
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session
from app.models.entities import Document

SAMPLE_DIR = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "documents"
COLORS={"aadhaar":"#0b1f3a","pan":"#6b3c14","passport":"#185c46"}
FIXTURE_VERSION = "3"
def _fonts():
    for candidate in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf"):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, 29), ImageFont.truetype(candidate, 34)
    return ImageFont.load_default(), ImageFont.load_default()
def make_documents(db: Session):
    SAMPLE_DIR.mkdir(parents=True,exist_ok=True)
    version_file = SAMPLE_DIR / ".fixture_version"
    if len(list(SAMPLE_DIR.glob("*.png"))) == 19 and version_file.exists() and version_file.read_text() == FIXTURE_VERSION: return
    for old in SAMPLE_DIR.glob("*.png"): old.unlink()
    font, heading_font = _fonts()
    for doc in db.query(Document).all():
        fields=json.loads(doc.fields_json); im=Image.new("RGB",(1400,900),"#fafafa"); draw=ImageDraw.Draw(im)
        draw.rectangle((0,0,1400,120),fill=COLORS[doc.document_type]); draw.text((50,38),"GOVDOC VERIFY — SYNTHETIC %s-LIKE DEMO" % doc.document_type.upper(),fill="white",font=heading_font)
        draw.text((50,155),"NOT A GOVERNMENT DOCUMENT · FICTIONAL TEST DATA",fill="#b42318",font=font)
        y=220
        for key,value in fields.items():
            draw.text((60,y),"%s: %s" % (key.replace("_"," ").title(),value),fill="#172033",font=font); y+=58
        draw.text((60,810),"Synthetic OCR evaluation fixture",fill="#475569",font=font)
        im.save(SAMPLE_DIR / ("%s_%s.png" % (doc.document_type,doc.identifier)))
    # Deliberate, visibly labelled demo variants. They never represent real documents.
    variants = [
      ("aadhaar", "DEM-IRA-1004", "DOB_MISMATCH", {"date_of_birth":"1998-04-05"}),
      ("pan", "DEMKRA005X", "TAMPERED", {"name":"Demo Karan Roe"}),
      ("aadhaar", "DEM-UNK-9999", "UNKNOWN", {"name":"Unknown Synthetic Person","date_of_birth":"1990-01-01","gender":"Male","aadhaar_number":"DEM-UNK-9999","address":"Unknown Demo Address"}),
      ("aadhaar", "DEM-NAI-1002", "LOW_QUALITY", {}),
    ]
    for kind,identifier,variant,overrides in variants:
        doc=db.query(Document).filter_by(document_type=kind,identifier=identifier).first()
        fields=dict(overrides) if variant=="UNKNOWN" else dict(json.loads(doc.fields_json))
        fields.update(overrides); im=Image.new("RGB",(1400,900),"#fafafa"); draw=ImageDraw.Draw(im)
        draw.rectangle((0,0,1400,120),fill=COLORS[kind]); draw.text((50,38),"SYNTHETIC %s DEMO — %s CASE" % (kind.upper(),variant.replace("_"," ")),fill="white",font=heading_font)
        draw.text((50,155),"NOT A GOVERNMENT DOCUMENT · TEST CASE",fill="#b42318",font=font); y=220
        for key,value in fields.items(): draw.text((60,y),"%s: %s" % (key.replace("_"," ").title(),value),fill="#172033",font=font); y+=58
        draw.text((60,810),"Synthetic OCR evaluation fixture",fill="#475569",font=font)
        if variant=="TAMPERED": draw.rectangle((55,250,660,300),fill="#fff200"); draw.text((60,252),"Name: Demo Karan Roe",fill="#111111",font=font)
        if variant=="LOW_QUALITY": im=im.resize((220,140),Image.Resampling.BILINEAR)
        im.save(SAMPLE_DIR / ("case_%s_%s.png" % (variant.lower(),kind)))
    version_file.write_text(FIXTURE_VERSION)
