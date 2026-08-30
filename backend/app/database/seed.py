"""Fictional local reference-data generator for the demo datasets."""
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
        yield name,dob,gender,address,"aadhaar",aadhaar_id,dict(base,aadhaar_number=aadhaar_id),"valid","synthetic"
        yield name,dob,gender,address,"pan",pan_id,{"name":name,"father_name":"Demo Parent %03d" % i,"date_of_birth":dob,"pan_number":pan_id},"valid","synthetic"
        expiry = date.today()-timedelta(days=60) if i == 3 else date.today()+timedelta(days=365*(2+i))
        yield name,dob,gender,address,"passport",passport_id,{"surname":last,"given_name":"Demo %s" % first,"passport_number":passport_id,"nationality":"DEMO REPUBLIC","date_of_birth":dob,"sex":sex,"date_of_issue":(expiry-timedelta(days=3650)).isoformat(),"date_of_expiry":expiry.isoformat(),"place_of_birth":"Sample Nagar"},"expired" if i == 3 else "valid","synthetic"
    # Sanitized, fictional records exercise realistic identifier layouts observed in Repo B.
    name, gender, dob, address = "Sample Riya Verma", "Female", "1998-06-12", "12 Example Road, Test City"
    yield name,dob,gender,address,"aadhaar","111122223333",{"name":name,"date_of_birth":dob,"gender":gender,"address":address,"aadhaar_number":"111122223333"},"valid","repo_b"
    yield name,dob,gender,address,"pan","TESTV1234K",{"name":name,"father_name":"Sample Parent","date_of_birth":dob,"pan_number":"TESTV1234K"},"valid","repo_b"
    yield name,dob,gender,address,"passport","T1234567",{"surname":"Verma","given_name":"Sample Riya","passport_number":"T1234567","nationality":"TESTLAND","date_of_birth":dob,"sex":"F","date_of_issue":"2021-06-12","date_of_expiry":"2031-06-11","place_of_birth":"Test City"},"valid","repo_b"
    # Authorized fictional Repo B reference records, kept in the same local DB.
    yield "Basant Raj","2000-01-01","Male","Repo B test address","aadhaar","123456789101",{"name":"Basant Raj","date_of_birth":"2000-01-01","gender":"Male","aadhaar_number":"123456789101"},"valid","repo_b"
    # The supplied PAN number is redacted in its image.  Keep no invented
    # reference identifier: it must fail extraction rather than be fabricated.
    # Its other visible fields are covered by OCR regression tests below.
    yield "Maqdooma Fathima","1981-06-23","Female","Repo B test address","passport","R7123405",{"given_name":"MAQDOOMA FATHIMA","passport_number":"R7123405","nationality":"IND"},"valid","repo_b"

def _ensure_document_source_column():
    with engine.begin() as connection:
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(documents)")}
        if "source" not in columns:
            connection.exec_driver_sql("ALTER TABLE documents ADD COLUMN source VARCHAR(30) NOT NULL DEFAULT 'synthetic'")

def seed():
    Base.metadata.create_all(engine); _ensure_document_source_column(); db=SessionLocal()
    if db.query(Document).count() == 20 and db.query(Citizen).count() == 8: db.close(); return
    db.query(Document).delete(); db.query(Citizen).delete(); db.commit()
    current_citizen = None; current_identity = None
    for name,dob,gender,address,kind,identifier,fields,status,source in records():
        identity = (name,dob,gender,address)
        if identity != current_identity:
            current_citizen=Citizen(name=name,date_of_birth=dob,gender=gender,address=address); db.add(current_citizen); db.flush()
            current_identity = identity
        db.add(Document(citizen_id=current_citizen.id,document_type=kind,identifier=identifier,fields_json=json.dumps(fields),status=status,source=source))
    db.commit(); db.close()
