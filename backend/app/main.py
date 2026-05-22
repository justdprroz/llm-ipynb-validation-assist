import logging
import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.compare import router as compare_router
from app.api.credentials import router as credentials_router
from app.api.deps_auth import public_route_auth
from app.api.health import router as health_router
from app.api.integrations_anytask import router as anytask_integration_router
from app.api.inference_profiles import router as inference_profiles_router
from app.api.internal_runs import router as internal_router
from app.api.meta import router as meta_router
from app.api.pipelines import router as pipelines_router
from app.api.realms import router as realms_router
from app.api.runs import router as runs_router
from app.config import get_settings
from app.mongo_store import ensure_mongo_indexes, get_mongo_client
from app.telemetry import setup_telemetry


def _configure_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "DEBUG").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        force=True,
    )
    # Quieten noisy third-party loggers that aren't useful at DEBUG
    for noisy in ("boto3", "botocore", "urllib3", "s3transfer", "httpcore", "hpack"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    setup_telemetry("gradelab-backend")
    settings = get_settings()
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings.REALMS_DIR.mkdir(parents=True, exist_ok=True)
    settings.PIPELINE_VENVS_DIR.mkdir(parents=True, exist_ok=True)
    settings.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    get_mongo_client()
    ensure_mongo_indexes()
    from app.seed import seed

    seed()
    yield


app = FastAPI(title="GradeLab API", version="0.1.0", lifespan=lifespan)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(internal_router)

v1 = APIRouter(prefix="/api/v1", dependencies=[Depends(public_route_auth)])
v1.include_router(realms_router)
v1.include_router(pipelines_router)
v1.include_router(meta_router)
v1.include_router(runs_router)
v1.include_router(compare_router)
v1.include_router(credentials_router)
v1.include_router(inference_profiles_router)
v1.include_router(anytask_integration_router)
app.include_router(v1)
