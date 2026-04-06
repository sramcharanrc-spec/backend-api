from sqlalchemy import (
    Column,
    String,
    Float,
    JSON,
    Integer,
    DateTime,
    Enum,
    Boolean,
    Index,
)
from datetime import datetime
from app.models.base import Base
from app.models.enums import ClaimStatusEnum


class Claim(Base):
    __tablename__ = "claims"

    id = Column(String, primary_key=True)
    patient_id = Column(String, nullable=False, index=True)
    payer_id = Column(String, nullable=False, index=True)

    provider_npi = Column(String, nullable=True)

    cpt_codes = Column(JSON, nullable=False)
    icd_codes = Column(JSON, nullable=False)

    status = Column(
        Enum(ClaimStatusEnum),
        nullable=False,
        index=True,
    )

    transaction_id = Column(String, index=True)
    denial_code = Column(String)
    paid_amount = Column(Float)

    retry_count = Column(Integer, default=0, nullable=False)
    last_error = Column(String)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    is_deleted = Column(Boolean, default=False, index=True)
    deleted_at = Column(DateTime)

    encrypted_patient_name = Column(String)
    encrypted_dob = Column(String)
    encrypted_ssn = Column(String)

    __table_args__ = (
        Index("idx_status_payer", "status", "payer_id"),
        Index("idx_patient_status", "patient_id", "status"),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if self.retry_count is None:
            self.retry_count = 0

        if self.is_deleted is None:
            self.is_deleted = False

        if self.provider_npi is None:
            self.provider_npi = "TEST_NPI"

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()

    def __repr__(self):
        return f"<Claim id={self.id} status={self.status}>"