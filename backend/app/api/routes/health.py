from fastapi import APIRouter

from app.services.health_service import HealthReport, run_health_checks

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthReport)
async def health() -> HealthReport:
    return await run_health_checks()
