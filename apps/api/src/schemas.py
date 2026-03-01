from datetime import datetime

from pydantic import BaseModel, Field


class HazardCreate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    hazard_type: str = Field(max_length=50)
    severity: int = Field(ge=1, le=5)
    description: str | None = None
    source: str = "user"


class HazardResponse(BaseModel):
    id: int
    latitude: float
    longitude: float
    hazard_type: str
    severity: int
    description: str | None
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}
