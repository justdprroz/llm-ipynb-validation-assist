from fastapi import APIRouter

from gradelab_contracts.pipeline_run_defaults import (
    PIPELINE_RUN_CONFIG_DEFAULTS,
    PIPELINE_RUN_CONFIG_DESCRIPTION,
)

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/pipeline-run-defaults")
def pipeline_run_defaults() -> dict[str, object]:
    """Defaults shallow-merged with POST /runs ``pipeline_config`` before pipeline execution."""
    return {
        "defaults": dict(PIPELINE_RUN_CONFIG_DEFAULTS),
        "description": PIPELINE_RUN_CONFIG_DESCRIPTION,
    }
