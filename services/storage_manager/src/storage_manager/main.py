from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import Annotated

from botocore.exceptions import ClientError
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from storage_manager.config import Settings, get_settings
from storage_manager.mongo_store import ensure_mongo_indexes
from storage_manager.realm_service import (
    delete_realm,
    get_file_content,
    get_homework_detail,
    get_realm,
    list_realms,
    upload_gold_file,
    upload_realm,
)
from storage_manager.schemas import HomeworkRead, RealmRead
from storage_manager.s3client import ensure_buckets, make_client


def _setup_otel() -> None:
    ep = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not ep:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        return
    resource = Resource.create({"service.name": "gradelab-storage-manager"})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=ep, insecure=True)))
    trace.set_tracer_provider(provider)
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore[import-not-found]
        FastAPIInstrumentor().instrument()
    except ImportError:
        pass
    try:
        from opentelemetry.sdk.logs import LoggerProvider, LoggingHandler  # type: ignore[import-not-found]
        from opentelemetry.sdk.logs.export import BatchLogRecordProcessor  # type: ignore[import-not-found]
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter  # type: ignore[import-not-found]
        from opentelemetry._logs import set_logger_provider  # type: ignore[import-not-found]
        log_provider = LoggerProvider(resource=resource)
        log_provider.add_log_record_processor(
            BatchLogRecordProcessor(OTLPLogExporter(endpoint=ep, insecure=True))
        )
        set_logger_provider(log_provider)
        logging.getLogger().addHandler(LoggingHandler(level=logging.DEBUG, logger_provider=log_provider))
    except Exception:
        pass


app = FastAPI(title="GradeLab StorageManager", version="0.1.0")


def verify_token(
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.STORAGE_MANAGER_TOKEN:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != settings.STORAGE_MANAGER_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")


@app.on_event("startup")
def startup() -> None:
    level = os.environ.get("LOG_LEVEL", "DEBUG").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        force=True,
    )
    for noisy in ("boto3", "botocore", "urllib3", "s3transfer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _setup_otel()
    settings = get_settings()
    client = make_client(settings)
    ensure_buckets(client, settings.bucket_list)
    ensure_mongo_indexes()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    client = make_client(settings)
    client.list_buckets()
    return {"status": "ready"}


class PresignBody(BaseModel):
    bucket: str
    key: str
    content_type: str | None = None


class PresignResponse(BaseModel):
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    expires_at: str


@app.post("/v1/presign/put", dependencies=[Depends(verify_token)])
def presign_put(body: PresignBody, settings: Settings = Depends(get_settings)) -> PresignResponse:
    client = make_client(settings)
    params: dict[str, str] = {"Bucket": body.bucket, "Key": body.key}
    if body.content_type:
        params["ContentType"] = body.content_type
    url = client.generate_presigned_url("put_object", Params=params, ExpiresIn=3600)
    from datetime import datetime, timezone

    exp = (datetime.now(timezone.utc) + timedelta(seconds=3600)).isoformat()
    return PresignResponse(url=url, headers={}, expires_at=exp)


@app.post("/v1/presign/get", dependencies=[Depends(verify_token)])
def presign_get(body: PresignBody, settings: Settings = Depends(get_settings)) -> PresignResponse:
    client = make_client(settings)
    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": body.bucket, "Key": body.key},
        ExpiresIn=3600,
    )
    from datetime import datetime, timezone

    exp = (datetime.now(timezone.utc) + timedelta(seconds=3600)).isoformat()
    return PresignResponse(url=url, headers={}, expires_at=exp)


@app.put("/v1/objects/{bucket}/{key:path}", dependencies=[Depends(verify_token)])
async def put_object(
    bucket: str,
    key: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    body = await request.body()
    client = make_client(settings)
    client.put_object(Bucket=bucket, Key=key, Body=body)
    return {"bucket": bucket, "key": key, "status": "stored"}


@app.get("/v1/objects/{bucket}/{key:path}", dependencies=[Depends(verify_token)])
def get_object(bucket: str, key: str, settings: Settings = Depends(get_settings)):
    client = make_client(settings)
    try:
        obj = client.get_object(Bucket=bucket, Key=key)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey"):
            raise HTTPException(status_code=404, detail="Not found") from e
        raise HTTPException(status_code=500, detail=str(e)) from e

    stream = obj["Body"]

    def iterfile():
        for chunk in iter(lambda: stream.read(65536), b""):
            if not chunk:
                break
            yield chunk

    return StreamingResponse(
        iterfile(),
        media_type=obj.get("ContentType") or "application/octet-stream",
    )


@app.delete("/v1/objects/{bucket}/{key:path}", dependencies=[Depends(verify_token)])
def delete_object(bucket: str, key: str, settings: Settings = Depends(get_settings)) -> dict[str, str]:
    client = make_client(settings)
    client.delete_object(Bucket=bucket, Key=key)
    return {"bucket": bucket, "key": key, "status": "deleted"}


@app.get("/v1/list", dependencies=[Depends(verify_token)])
def list_objects(
    bucket: str = Query(...),
    prefix: str = Query(""),
    settings: Settings = Depends(get_settings),
) -> dict:
    client = make_client(settings)
    resp = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    keys = [o["Key"] for o in resp.get("Contents", [])]
    return {"bucket": bucket, "prefix": prefix, "keys": keys}


@app.post("/v1/realms/upload", response_model=RealmRead, status_code=201, dependencies=[Depends(verify_token)])
async def api_upload_realm(
    file: UploadFile = File(...),
    name: str = Form(...),
):
    return await upload_realm(file, name)


@app.get("/v1/realms", response_model=list[RealmRead], dependencies=[Depends(verify_token)])
def api_list_realms():
    return list_realms()


@app.get("/v1/realms/{realm_id}", response_model=RealmRead, dependencies=[Depends(verify_token)])
def api_get_realm(realm_id: str):
    return get_realm(realm_id)


@app.get(
    "/v1/realms/{realm_id}/homeworks/{homework_id}",
    response_model=HomeworkRead,
    dependencies=[Depends(verify_token)],
)
def api_get_homework(realm_id: str, homework_id: str):
    return get_homework_detail(realm_id, homework_id)


@app.get(
    "/v1/realms/{realm_id}/homeworks/{homework_id}/files/{file_path:path}",
    dependencies=[Depends(verify_token)],
)
def api_get_homework_file(realm_id: str, homework_id: str, file_path: str):
    return get_file_content(realm_id, homework_id, file_path)


@app.post(
    "/v1/realms/{realm_id}/homeworks/{homework_id}/gold",
    status_code=201,
    dependencies=[Depends(verify_token)],
)
async def api_upload_gold_file(
    realm_id: str,
    homework_id: str,
    file: UploadFile = File(...),
):
    return await upload_gold_file(realm_id, homework_id, file)


@app.delete("/v1/realms/{realm_id}", status_code=204, dependencies=[Depends(verify_token)])
def api_delete_realm(realm_id: str):
    delete_realm(realm_id)


def run() -> None:
    import uvicorn

    uvicorn.run("storage_manager.main:app", host="0.0.0.0", port=8081)
