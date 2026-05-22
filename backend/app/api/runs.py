from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Query, Response

from app.config import get_settings
from app.schemas import RunCreate, RunRead, RunResultRead, ViewerAdjustmentPayload, ViewerAdjustmentResponse
from app.services import run_service

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunRead, status_code=201)
def create_run(
    run_create: RunCreate,
    background_tasks: BackgroundTasks,
    response: Response,
):
    out = run_service.create_run(run_create, background_tasks)
    if get_settings().RUN_EXECUTOR == "arq":
        response.status_code = 202
    return out


@router.get("", response_model=list[RunRead])
def list_runs(
    pipeline_id: Optional[str] = Query(default=None),
    homework_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
):
    return run_service.list_runs(pipeline_id=pipeline_id, homework_id=homework_id, status=status)


@router.get("/{run_id}", response_model=RunRead)
def get_run(run_id: str):
    return run_service.get_run(run_id)


@router.get("/{run_id}/results", response_model=list[RunResultRead])
def get_run_results(run_id: str):
    return run_service.get_run_results(run_id)


@router.get("/{run_id}/viewer-adjustments", response_model=ViewerAdjustmentResponse)
def get_viewer_adjustments(run_id: str):
    return run_service.get_viewer_adjustments(run_id)


@router.put("/{run_id}/viewer-adjustments", response_model=ViewerAdjustmentResponse)
def put_viewer_adjustments(run_id: str, body: ViewerAdjustmentPayload):
    return run_service.put_viewer_adjustments(run_id, body)
