"""Internal callbacks (m2m token)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.mongo_repo import run_results_insert_many, run_update
from app.services import run_service

router = APIRouter(prefix="/internal/v1", tags=["internal"])


def verify_internal(
    authorization: str | None = Header(default=None),
) -> None:
    tok = get_settings().INTERNAL_API_TOKEN
    if not tok:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    if authorization.removeprefix("Bearer ").strip() != tok:
        raise HTTPException(status_code=403, detail="Invalid bearer token")


class RunEventBody(BaseModel):
    type: Literal["RUN_STARTED", "RUN_PROGRESS", "RUN_COMPLETED", "RUN_FAILED"]
    timestamp: datetime | None = None
    payload: dict[str, Any] = {}


@router.post("/runs/{run_id}/events", dependencies=[Depends(verify_internal)])
def post_run_event(run_id: str, body: RunEventBody) -> dict[str, str]:
    return {"status": "ok", "run_id": run_id, "type": body.type}


class RunResultItem(BaseModel):
    student_id: str
    total_score: float
    tasks: list[dict[str, Any]]
    report: str | None = None
    metadata: dict[str, Any] | None = None


@router.post("/runs/{run_id}/results", dependencies=[Depends(verify_internal)])
def post_run_results(run_id: str, items: list[RunResultItem]) -> dict[str, str]:
    run_service.get_run(run_id)
    docs = []
    for it in items:
        docs.append(
            {
                "_id": str(uuid.uuid4()),
                "run_id": run_id,
                "student_id": it.student_id,
                "total_score": it.total_score,
                "tasks_json": json.dumps(it.tasks),
                "report": it.report,
                "result_metadata": json.dumps(it.metadata) if it.metadata is not None else None,
            }
        )
    run_results_insert_many(docs)
    run_update(
        run_id,
        {"status": "completed", "finished_at": datetime.utcnow()},
    )
    return {"status": "stored"}
