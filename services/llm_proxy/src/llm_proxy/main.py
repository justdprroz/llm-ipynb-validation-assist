from __future__ import annotations

import json
import logging
import os
import time
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from pymongo import MongoClient

from llm_proxy.config import Settings, get_settings
from llm_proxy.inference_profiles import (
    InferenceProfileCreate,
    InferenceProfileRead,
    _to_read,
    create_profile,
    delete_profile,
    ensure_dummy_profile,
    ensure_indexes,
    get_profile,
    list_profiles,
    resolve_profile,
)


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
    resource = Resource.create({"service.name": "gradelab-llm-proxy"})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=ep, insecure=True)))
    trace.set_tracer_provider(provider)
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore[import-not-found]
        FastAPIInstrumentor().instrument()
    except ImportError:
        pass
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor  # type: ignore[import-not-found]
        HTTPXClientInstrumentor().instrument()
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


app = FastAPI(title="GradeLab LLMProxy", version="0.1.0")


@app.on_event("startup")
def _startup() -> None:
    level = os.environ.get("LOG_LEVEL", "DEBUG").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        force=True,
    )
    for noisy in ("urllib3", "httpcore", "hpack"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _setup_otel()
    settings = get_settings()
    db = _mongo(settings)
    ensure_indexes(db)
    ensure_dummy_profile(db)


def verify_service_token(
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.LLMPROXY_SERVICE_TOKEN:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    if authorization.removeprefix("Bearer ").strip() != settings.LLMPROXY_SERVICE_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")


def _mongo(settings: Settings) -> Any:
    return MongoClient(settings.MONGO_URI)[settings.MONGO_DB]


_OR_GPT_OSS_CANON = "openai/gpt-oss-120b"


def _normalize_openrouter_model(model: str) -> str:
    """Map common typos to an OpenRouter-valid slug (avoids 400 invalid model ID)."""
    m = (model or "").strip()
    if not m:
        return m
    key = m.lower().replace(" ", "").replace("_", "-")
    tail = key.rsplit("/", 1)[-1]
    if tail in ("gpt-oss-120", "gpt-oss-120b") or key == "openai/gpt-oss-120":
        return _OR_GPT_OSS_CANON
    return m


class ChatCompletionRequest(BaseModel):
    profile_id: str
    model: str | None = None
    messages: list[dict[str, Any]]
    temperature: float | None = None
    seed: int | None = None
    top_p: float | None = None
    max_tokens: int | None = Field(default=None, ge=1, le=128000)
    # OpenRouter-only: forwarded as JSON ``provider`` (``only``, ``allow_fallbacks``, etc.).
    openrouter_provider: dict[str, Any] | None = None


def _apply_upstream_sampling(
    payload: dict[str, Any],
    *,
    temperature: float,
    seed: int | None,
    top_p: float,
    default_top_p: float = 1.0,
) -> None:
    """Align with ``llm_notebook_grader.inference._apply_openai_compatible_sampling``."""
    payload["temperature"] = temperature
    if seed is not None:
        payload["seed"] = seed
    if top_p != default_top_p:
        payload["top_p"] = top_p


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/v1/inference-profiles",
    response_model=list[InferenceProfileRead],
    dependencies=[Depends(verify_service_token)],
)
def api_list_inference_profiles(settings: Settings = Depends(get_settings)) -> list[dict]:
    return list_profiles(_mongo(settings))


@app.post(
    "/v1/inference-profiles",
    response_model=InferenceProfileRead,
    status_code=201,
    dependencies=[Depends(verify_service_token)],
)
def api_create_inference_profile(
    data: InferenceProfileCreate,
    settings: Settings = Depends(get_settings),
) -> dict:
    return create_profile(_mongo(settings), data)


@app.get(
    "/v1/inference-profiles/{profile_id}",
    response_model=InferenceProfileRead,
    dependencies=[Depends(verify_service_token)],
)
def api_get_inference_profile(
    profile_id: str,
    settings: Settings = Depends(get_settings),
) -> dict:
    return _to_read(get_profile(_mongo(settings), profile_id))


@app.delete(
    "/v1/inference-profiles/{profile_id}",
    status_code=204,
    dependencies=[Depends(verify_service_token)],
)
def api_delete_inference_profile(profile_id: str, settings: Settings = Depends(get_settings)) -> None:
    delete_profile(_mongo(settings), profile_id)


@app.get(
    "/v1/inference-profiles/{profile_id}/resolve",
    dependencies=[Depends(verify_service_token)],
)
def api_resolve_inference_profile(profile_id: str, settings: Settings = Depends(get_settings)) -> dict:
    return resolve_profile(_mongo(settings), profile_id)


@app.post("/v1/chat/completions", dependencies=[Depends(verify_service_token)])
async def chat_completions(
    body: ChatCompletionRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    db = _mongo(settings)
    prof = db.inference_profiles.find_one({"_id": body.profile_id})
    if prof is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    api_key = prof.get("api_key")
    if not api_key:
        raise HTTPException(status_code=500, detail="Profile has no api_key")

    model = body.model or prof.get("model") or "gpt-4o-mini"
    provider = (prof.get("provider") or "openai").lower()
    yc_folder = prof.get("yc_folder")

    eff_temperature = body.temperature if body.temperature is not None else (prof.get("temperature") if prof.get("temperature") is not None else 0.0)
    eff_top_p = body.top_p if body.top_p is not None else (prof.get("top_p") if prof.get("top_p") is not None else 1.0)
    eff_seed = body.seed if body.seed is not None else prof.get("seed")
    eff_max_tokens = body.max_tokens if body.max_tokens is not None else prof.get("max_tokens")
    eff_or_provider = body.openrouter_provider if body.openrouter_provider is not None else prof.get("openrouter_provider")

    # Must match ``llm_notebook_grader.inference`` URLs: ``or`` is OpenRouter, not OpenAI.
    if provider in ("or", "openrouter"):
        base = "https://openrouter.ai/api/v1"
    elif provider == "do":
        base = "https://inference.do-ai.run/v1"
    elif provider == "yc":
        base = "https://llm.api.cloud.yandex.net/v1"
    else:
        base = settings.OPENAI_COMPAT_BASE.rstrip("/")

    if provider in ("or", "openrouter"):
        model = _normalize_openrouter_model(str(model))

    headers: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider == "yc" and yc_folder:
        headers["OpenAI-Project"] = yc_folder
        if not str(model).startswith("gpt://"):
            model = f"gpt://{yc_folder}/{model}"
    if "openrouter.ai" in base:
        headers.setdefault("X-Title", "GradeLab")

    payload: dict[str, Any] = {
        "model": model,
        "messages": body.messages,
    }
    _apply_upstream_sampling(
        payload,
        temperature=eff_temperature,
        seed=eff_seed,
        top_p=eff_top_p,
    )
    if eff_max_tokens is not None:
        payload["max_tokens"] = eff_max_tokens
    if eff_or_provider is not None:
        if "openrouter.ai" not in base:
            raise HTTPException(
                status_code=422,
                detail="openrouter_provider is only valid when the inference profile targets OpenRouter",
            )
        payload["provider"] = eff_or_provider
    elif "openrouter.ai" in base and "gpt-oss-120" in str(model).lower():
        # Align with ``llm_notebook_grader.inference.OR_PROVIDER_ROUTING`` when unset.
        payload["provider"] = {"allow_fallbacks": True, "only": ["Groq"]}

    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            f"{base}/chat/completions",
            headers=headers,
            json=payload,
        )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    meta = {
        "profile_id": body.profile_id,
        "model": model,
        "latency_ms": latency_ms,
        "upstream_status": r.status_code,
    }
    if settings.LOG_FULL_PAYLOADS:
        meta["request"] = payload
        try:
            meta["response"] = r.json()
        except Exception:
            meta["response_text"] = r.text[:2000]
    else:
        meta["usage_hint"] = len(body.messages)
    print(json.dumps({"event": "llm_completion", **meta}))

    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=r.text[:2000])
    return r.json()


def run() -> None:
    import uvicorn

    uvicorn.run("llm_proxy.main:app", host="0.0.0.0", port=8082)
