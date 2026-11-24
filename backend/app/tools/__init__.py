"""Read-only AWS investigation tools.

Importing this package registers every tool. See ``base.py`` for the tool contract and
``runner.py`` for how calls are validated, limited and recorded as evidence.
"""

from app.tools import cloudwatch, ec2, ecs, lambda_fn, rds  # noqa: F401 - registration
from app.tools.base import REGISTRY, ToolSpec, get_tool

__all__ = ["REGISTRY", "ToolSpec", "get_tool"]
