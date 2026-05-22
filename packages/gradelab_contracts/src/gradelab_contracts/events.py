from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

RunEventType = Literal[
    "RUN_QUEUED",
    "RUN_STARTED",
    "RUN_PROGRESS",
    "RUN_RETRY_SCHEDULED",
    "RUN_COMPLETED",
    "RUN_FAILED",
    "RUN_CANCELLED",
]


class RunEvent(BaseModel):
    run_id: str
    type: RunEventType
    timestamp: datetime
    actor: str = Field(description="backend-api|executor|user:{id}")
    data: dict[str, Any] = Field(default_factory=dict)
