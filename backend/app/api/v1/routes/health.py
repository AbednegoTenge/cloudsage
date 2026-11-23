from fastapi import APIRouter

from app import __version__
from app.api.deps import SettingsDep
from app.schemas.meta import AppInfoResponse, HealthResponse

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe. Does not touch the database or AWS."""
    return HealthResponse(status="ok", version=__version__)


@router.get("/info", response_model=AppInfoResponse)
def info(settings: SettingsDep) -> AppInfoResponse:
    return AppInfoResponse(
        name=settings.app_name,
        version=__version__,
        environment=settings.environment.value,
        aws_mode=settings.aws_mode.value,
        bedrock_configured=bool(settings.bedrock_model_id and settings.bedrock_region),
    )
