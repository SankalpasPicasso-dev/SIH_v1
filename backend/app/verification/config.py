DOCUMENTS = {
 "aadhaar": {"label":"Aadhaar-like (Demo)","identifier":"aadhaar_number", "pattern":r"^(?:DEM-[A-Z]{3}-\d{4}|\d{12})$", "fields":["name","date_of_birth","gender","aadhaar_number","address"]},
 "pan": {"label":"PAN-like (Demo)","identifier":"pan_number", "pattern":r"^(?:DEM[A-Z]{3}\d{3}X|[A-Z]{5}\d{4}[A-Z])$", "fields":["name","father_name","date_of_birth","pan_number"]},
 "passport": {"label":"Passport-like (Demo)","identifier":"passport_number", "pattern":r"^(?:DMP\d{6}|[A-Z]\d{7})$", "fields":["surname","given_name","passport_number","nationality","date_of_birth","sex","date_of_issue","date_of_expiry","place_of_birth"]},
}
