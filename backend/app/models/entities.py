from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base

class Citizen(Base):
    __tablename__ = "citizens"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    date_of_birth: Mapped[str] = mapped_column(String(20))
    gender: Mapped[str] = mapped_column(String(20))
    address: Mapped[str] = mapped_column(String(300))

class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    citizen_id: Mapped[int] = mapped_column(ForeignKey("citizens.id"))
    document_type: Mapped[str] = mapped_column(String(30))
    identifier: Mapped[str] = mapped_column(String(40), unique=True)
    fields_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="valid")

class VerificationResult(Base):
    __tablename__ = "verification_results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_type: Mapped[str] = mapped_column(String(30))
    score: Mapped[int] = mapped_column(Integer)
    level: Mapped[str] = mapped_column(String(30))
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class VerificationCase(Base):
    """A persistent, user-accessible verification case (synthetic demo only)."""
    __tablename__ = "verification_cases"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    pin_hash: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(40), default="SUBMITTED")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CaseDocument(Base):
    __tablename__ = "case_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("verification_cases.id"), index=True)
    document_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(40), default="PROCESSING")
    automated_status: Mapped[str] = mapped_column(String(40), default="PROCESSING")
    payload_json: Mapped[str] = mapped_column(Text)
    officer_decision: Mapped[str | None] = mapped_column(String(40), nullable=True)
    officer_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    officer_decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CaseEvent(Base):
    __tablename__ = "case_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("verification_cases.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(60))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CaseCrossVerification(Base):
    __tablename__ = "case_cross_verifications"
    case_id: Mapped[str] = mapped_column(ForeignKey("verification_cases.id"), primary_key=True)
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
