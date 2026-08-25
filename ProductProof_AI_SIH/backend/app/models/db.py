from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Float, Boolean, DateTime, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from app.core.config import settings

s=settings()
connect_args={"check_same_thread":False} if s.database_url.startswith("sqlite") else {}
engine=create_engine(s.database_url,connect_args=connect_args)
SessionLocal=sessionmaker(bind=engine,autoflush=False,autocommit=False)

class Base(DeclarativeBase): pass
class VerificationRecord(Base):
    __tablename__="verification_records"
    id: Mapped[int]=mapped_column(primary_key=True)
    created_at: Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
    title: Mapped[str]=mapped_column(String(500))
    decision: Mapped[str]=mapped_column(String(30))
    correctness_score: Mapped[float]=mapped_column(Float)
    confidence: Mapped[float]=mapped_column(Float)
    human_review_required: Mapped[bool]=mapped_column(Boolean,default=False)
    reviewer_note: Mapped[str]=mapped_column(Text,default="")
    result_json: Mapped[str]=mapped_column(Text)

def init_db(): Base.metadata.create_all(bind=engine)
