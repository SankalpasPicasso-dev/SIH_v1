from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
def build_report(result):
 b=BytesIO(); c=canvas.Canvas(b,pagesize=A4); _,h=A4
 c.setFillColor("#0b1f3a"); c.rect(0,h-80,595,80,fill=1,stroke=0); c.setFillColor("white"); c.setFont("Helvetica-Bold",20); c.drawString(40,h-48,"GovDoc Verify — Demo Report")
 c.setFillColor("#111827"); y=h-120; c.setFont("Helvetica-Bold",13); c.drawString(40,y,f"THREE-DOCUMENT CASE | {result['cross_verification']['state']}"); y-=32
 c.setFont("Helvetica",10); c.drawString(40,y,"SYNTHETIC / DEMO DATA ONLY — Not government verification."); y-=28
 c.setFont("Helvetica-Bold",11); c.drawString(40,y,"Risk score: %s | %s" % (result['cross_verification'].get('score','—'),result['cross_verification'].get('level','—'))); y-=20
 c.setFont("Helvetica",10)
 for reason in result['cross_verification'].get('reasons',[]): c.drawString(40,y,"• "+reason); y-=16
 for kind,item in result['documents'].items():
  c.setFont("Helvetica-Bold",11); c.drawString(40,y,kind.upper()+": "+item['state']); y-=18; c.setFont("Helvetica",10)
  c.drawString(55,y,"OCR: %s confidence %s%%" % (item.get('ocr',{}).get('engine','—'), round(item.get('ocr',{}).get('confidence',0)*100))); y-=16
  c.drawString(55,y,"Forensic indicator score: %s" % item.get('forensics',{}).get('indicator_score','—')); y-=16
  for f in item.get('fields',[]):
   c.drawString(55,y,f"{f['field']}: {f.get('extracted_value') or '—'}  [{f['status']}]"); y-=18
  if y<70: c.showPage(); y=h-60
 c.showPage(); c.save(); b.seek(0); return b
