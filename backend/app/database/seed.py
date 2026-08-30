"""Synthetic-only fixture generator. Every identifier uses an invented DEM/DMP format."""
import json
from datetime import date, timedelta
from app.database.session import Base, engine, SessionLocal
from app.models.entities import Citizen, Document

def records():
    people = [
      ("Demo Aarav Mehta","Male","1994-02-14","42 Demo Lane, Sample Nagar","AAR","AME"),
      ("Demo Naina Kapoor","Female","1991-07-09","7 Fiction Road, Sample Nagar","NAI","NKA"),
      ("Demo Dev Iyer","Male","1987-11-23","18 Model Avenue, Sample Nagar","DEV","DIY"),
      ("Demo Ira Shah","Female","1996-04-05","55 Test Path, Sample Nagar","IRA","ISH"),
      ("Demo Kabir Rao","Male","1989-09-18","9 Example Street, Sample Nagar","KAB","KRA"),
    ]
    for i, (name,gender,dob,address,aad,pancode) in enumerate(people, 1):
        first, last = name.split()[1:]
        sex = "F" if gender == "Female" else "M"
        aadhaar_id = "DEM-%s-%04d" % (aad, 1000+i)
        pan_id = "DEM%s%03dX" % (pancode, i)
        passport_id = "DMP%06d" % (100000+i)
        base = {"name":name,"date_of_birth":dob,"gender":gender,"address":address}
        yield name,dob,gender,address,"aadhaar",aadhaar_id,dict(base,aadhaar_number=aadhaar_id),"valid"
        yield name,dob,gender,address,"pan",pan_id,{"name":name,"father_name":"Demo Parent %03d" % i,"date_of_birth":dob,"pan_number":pan_id},"valid"
        expiry = date.today()-timedelta(days=60) if i == 3 else date.today()+timedelta(days=365*(2+i))
        yield name,dob,gender,address,"passport",passport_id,{"surname":last,"given_name":"Demo %s" % first,"passport_number":passport_id,"nationality":"DEMO REPUBLIC","date_of_birth":dob,"sex":sex,"date_of_issue":(expiry-timedelta(days=3650)).isoformat(),"date_of_expiry":expiry.isoformat(),"place_of_birth":"Sample Nagar"},"expired" if i == 3 else "valid"

def seed():
    Base.metadata.create_all(engine); db=SessionLocal()
    if db.query(Document).count() == 15 and db.query(Citizen).count() == 5: db.close(); return
    db.query(Document).delete(); db.query(Citizen).delete(); db.commit()
    current_citizen = None
    for name,dob,gender,address,kind,identifier,fields,status in records():
        if kind == "aadhaar":
            current_citizen=Citizen(name=name,date_of_birth=dob,gender=gender,address=address); db.add(current_citizen); db.flush()
        db.add(Document(citizen_id=current_citizen.id,document_type=kind,identifier=identifier,fields_json=json.dumps(fields),status=status))
    db.commit(); db.close()
