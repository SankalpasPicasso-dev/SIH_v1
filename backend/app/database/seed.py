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
    # This source record is retained even though the supplied PAN image redacts
    # the number. The OCR pipeline must still report extraction failure rather
    # than use this reference value to fabricate an OCR result.
    yield "Pavani Praveen","2007-05-25","Female","Repo B test address","aadhaar","348426827270",{"name":"Pavani Praveen","date_of_birth":"2007-05-25","gender":"Female","aadhaar_number":"348426827270"},"valid","repo_b"
    yield "Pavani Praveen","2007-05-25","Female","Repo B test address","pan","IUWPP1391B",{"name":"PAVANI PRAVEEN","father_name":"PRAVEEN SUBBANANJAPPA","date_of_birth":"2007-05-25","pan_number":"IUWPP1391B"},"valid","repo_b"
    yield "Sukumar Karuppiah","1978-05-01","Male","Repo B test address","aadhaar","687006240742",{"name":"Sukumar Karuppiah","date_of_birth":"1978-05-01","gender":"Male","aadhaar_number":"687006240742"},"valid","repo_b"
    yield "Cheruku Sree Chaitra","2008-07-25","Female","Repo B test address","aadhaar","590554540961",{"name":"Cheruku Sree Chaitra","date_of_birth":"2008-07-25","gender":"Female","aadhaar_number":"590554540961"},"valid","repo_b"
    yield "Poornima V","2007-07-20","Female","Repo B test address","aadhaar","498714770290",{"name":"Poornima V","date_of_birth":"2007-07-20","gender":"Female","aadhaar_number":"498714770290"},"valid","repo_b"
    yield "Tanuja Thakur","2007-02-08","Female","Repo B test address","aadhaar","935349568480",{"name":"Tanuja Thakur","date_of_birth":"2007-02-08","gender":"Female","aadhaar_number":"935349568480"},"valid","repo_b"
    yield "Darakhshan Parween Zeeshan Shaikh","1997-02-25","Female","Repo B test address","aadhaar","893831116226",{"name":"Darakhshan Parween Zeeshan Shaikh","date_of_birth":"1997-02-25","gender":"Female","aadhaar_number":"893831116226"},"valid","repo_b"
    yield "Maqdooma Fathima","1981-06-23","Female","Repo B test address","passport","R7123405",{"given_name":"MAQDOOMA FATHIMA","passport_number":"R7123405","nationality":"IND"},"valid","repo_b"
    yield "Gagandeep Singh Sandhu","1997-02-01","Male","Repo B test address","passport","M9104700",{"surname":"SANDHU","given_name":"GAGANDEEP SINGH","passport_number":"M9104700","nationality":"IND","date_of_birth":"1997-02-01","sex":"M","date_of_issue":"2015-05-22","date_of_expiry":"2025-05-21","place_of_birth":"GANGOHAR, PUNJAB"},"expired","repo_b"
    yield "Santhoshi Kaluva","1993-07-09","Female","Repo B test address","passport","N7820370",{"surname":"KALUVA","given_name":"SANTHOSHI","passport_number":"N7820370","nationality":"IND","date_of_birth":"1993-07-09","sex":"F","date_of_issue":"2016-02-15","date_of_expiry":"2026-02-14","place_of_birth":"HYDERABAD, TELANGANA"},"expired","repo_b"
    yield "Jaspreet Kaur","1994-09-24","Female","Repo B test address","passport","J7335300",{"given_name":"JASPREET KAUR","passport_number":"J7335300","nationality":"IND","date_of_birth":"1994-09-24","sex":"F","date_of_issue":"2011-05-24","date_of_expiry":"2021-05-23","place_of_birth":"RAIKOT, PUNJAB"},"expired","repo_b"
    yield "Maqsood Alam","1973-08-14","Male","Repo B test address","passport","H9137927",{"surname":"ALAM","given_name":"MAQSOOD","passport_number":"H9137927","nationality":"IND","date_of_birth":"1973-08-14","sex":"M","date_of_issue":"2010-02-18","date_of_expiry":"2020-02-17","place_of_birth":"MUZAFFARPUR BIHAR"},"expired","repo_b"

def _ensure_document_source_column():
    with engine.begin() as connection:
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(documents)")}
        if "source" not in columns:
            connection.exec_driver_sql("ALTER TABLE documents ADD COLUMN source VARCHAR(30) NOT NULL DEFAULT 'synthetic'")

def seed():
    Base.metadata.create_all(engine); _ensure_document_source_column(); db=SessionLocal()
    if db.query(Document).count() == 31 and db.query(Citizen).count() == 18: db.close(); return
    db.query(Document).delete(); db.query(Citizen).delete(); db.commit()
    current_citizen = None; current_identity = None
    for name,dob,gender,address,kind,identifier,fields,status,source in records():
        identity = (name,dob,gender,address)
        if identity != current_identity:
            current_citizen=Citizen(name=name,date_of_birth=dob,gender=gender,address=address); db.add(current_citizen); db.flush()
            current_identity = identity
        db.add(Document(citizen_id=current_citizen.id,document_type=kind,identifier=identifier,fields_json=json.dumps(fields),status=status,source=source))
    db.commit(); db.close()
