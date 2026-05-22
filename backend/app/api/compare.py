from fastapi import APIRouter, Query

from app.services import run_service

router = APIRouter(prefix="/compare", tags=["compare"])


@router.get("")
def compare(run_ids: str = Query(..., description="Comma-separated run UUIDs")):
    ids = [x.strip() for x in run_ids.split(",") if x.strip()]
    return run_service.compare_runs(ids)
