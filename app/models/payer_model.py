from sqlalchemy import Column, String
from app.models.base import Base


class Payer(Base):
    __tablename__ = "payers"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    payer_type = Column(String)  # Medicare / Commercial / Medicaid