from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Hazard(Base):
    __tablename__ = "hazards"

    id = Column(Integer, primary_key=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    hazard_type = Column(String(50), nullable=False)
    severity = Column(Integer, nullable=False)
    description = Column(Text)
    source = Column(String(50), nullable=False, default="user")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
