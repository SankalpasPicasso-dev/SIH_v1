from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

class FieldResult(BaseModel):
    field: str; extracted_value: Optional[str] = None; expected_value: Optional[str] = None
    status: Literal["MATCH","MISMATCH","NOT_FOUND","NOT_AVAILABLE","LOW_CONFIDENCE","INVALID_FORMAT"]
    severity: Literal["info","low","medium","high"] = "info"; confidence: Optional[float] = None

class VerifyResponse(BaseModel):
    id: str; document_type: str; extracted_fields: dict[str, Any]
    fields: list[FieldResult]; forensics: dict[str, Any]
    risk: dict[str, Any]; image: dict[str, Any]; disclaimer: str
