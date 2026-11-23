"""A scoped view of one AWS account and region, handed to every tool.

Tools never build credentials. They receive an ``AwsContext`` that:

* holds a client factory bound to temporary STS credentials (live) or canned data (mock);
* knows the account, the region and the connection's allowed regions;
* knows the investigation's time window, so tools cannot read outside it.

Boundary checks live here so every tool applies them the same way.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.aws.session import BOTO_CONFIG, assume_role_session
from app.core.config import AwsMode, Settings

_ARN = re.compile(r"^arn:aws[a-z-]*:([a-z0-9-]+):([a-z0-9-]*):(\d{12})?:")


class BoundaryViolation(ValueError):
    """A request reached outside the connection's account, regions or time window."""


@dataclass(frozen=True)
class AwsContext:
    account_id: str
    region: str
    allowed_regions: tuple[str, ...]
    start: datetime
    end: datetime
    client_factory: Callable[[str], Any]
    mode: AwsMode = AwsMode.MOCK

    def client(self, service: str) -> Any:
        return self.client_factory(service)

    def check_arn(self, arn: str) -> None:
        m = _ARN.match(arn)
        if not m:
            raise BoundaryViolation("Not a valid ARN")
        _service, region, account = m.groups()
        if account and account != self.account_id:
            raise BoundaryViolation("The ARN belongs to a different AWS account")
        if region and region != self.region:
            raise BoundaryViolation(
                f"The ARN is in {region}, but this investigation is scoped to {self.region}"
            )

    def clamp(self, start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
        """Limit a requested time range to the investigation's window."""
        s = max(start or self.start, self.start)
        e = min(end or self.end, self.end)
        if s >= e:
            raise BoundaryViolation("The requested time range is outside the investigation window")
        return s, e


async def open_context(
    settings: Settings,
    *,
    role_arn: str,
    external_id: str | None,
    account_id: str,
    region: str,
    allowed_regions: list[str],
    start: datetime,
    end: datetime,
    session_name: str = "cloudsage-investigation",
) -> AwsContext:
    if region not in allowed_regions:
        raise BoundaryViolation(f"Region {region} is not allowed for this connection")
    if settings.aws_mode is AwsMode.MOCK:
        from app.aws.mock.clients import mock_client_factory

        factory = mock_client_factory(account_id, region, end)
    else:
        session = await asyncio.to_thread(
            assume_role_session,
            role_arn=role_arn,
            external_id=external_id,
            region=region,
            duration=settings.aws_sts_session_duration_seconds,
            session_name=session_name,
        )

        def factory(service: str) -> Any:
            return session.client(service, region_name=region, config=BOTO_CONFIG)

    return AwsContext(
        account_id=account_id,
        region=region,
        allowed_regions=tuple(allowed_regions),
        start=start,
        end=end,
        client_factory=factory,
        mode=settings.aws_mode,
    )
