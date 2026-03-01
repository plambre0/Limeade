from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models import Hazard
from src.schemas import HazardCreate, HazardResponse

router = APIRouter(prefix="/hazards", tags=["hazards"])


@router.get("", response_model=list[HazardResponse])
async def list_hazards(
    lat: float = Query(description="Center latitude"),
    lng: float = Query(description="Center longitude"),
    radius_km: float = Query(default=1.0, description="Search radius in km"),
    db: AsyncSession = Depends(get_db),
):
    # Simple bounding box filter (~0.009 degrees per km at equator)
    deg = radius_km * 0.009
    stmt = select(Hazard).where(
        Hazard.latitude.between(lat - deg, lat + deg),
        Hazard.longitude.between(lng - deg, lng + deg),
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=HazardResponse, status_code=201)
async def create_hazard(
    body: HazardCreate,
    db: AsyncSession = Depends(get_db),
):
    hazard = Hazard(**body.model_dump())
    db.add(hazard)
    await db.commit()
    await db.refresh(hazard)
    return hazard


@router.get("/{hazard_id}", response_model=HazardResponse)
async def get_hazard(
    hazard_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Hazard).where(Hazard.id == hazard_id))
    hazard = result.scalar_one_or_none()
    if not hazard:
        raise HTTPException(status_code=404, detail="Hazard not found")
    return hazard
