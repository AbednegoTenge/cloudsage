from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str


class AppInfoResponse(BaseModel):
    """Non-sensitive runtime info the frontend uses to render its context bar."""

    name: str
    version: str
    environment: str
    aws_mode: str
    bedrock_configured: bool
