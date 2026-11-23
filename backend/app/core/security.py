"""Authentication: resolves the calling user.

* ``dev`` mode (local development and tests only, refused in production by config): the user
  is identified by the ``X-CloudSage-User`` header (an email), falling back to a default dev
  user. Users are provisioned on first sight.
* ``oidc`` mode: bearer-token validation against the configured identity provider. Implemented
  with security hardening in Phase 7; until then requests are rejected rather than trusted.
"""

import re
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.models import User
from app.repositories.users import UserRepository

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}$")


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    x_cloudsage_user: Annotated[str | None, Header()] = None,
) -> User:
    if settings.auth_mode != "dev":
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED, "OIDC authentication is not configured yet"
        )
    email = (x_cloudsage_user or settings.dev_default_user_email).strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid user identity")
    return await UserRepository(db).get_or_create(email)
