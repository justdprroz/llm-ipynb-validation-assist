import asyncio
import json
import logging
import os
from functools import partial
from typing import Any

import requests
from requests import Response

_log = logging.getLogger(__name__)

DO_ENDPOINT = "https://inference.do-ai.run/v1/chat/completions"
YC_ENDPOINT = "https://llm.api.cloud.yandex.net/v1/chat/completions"
OR_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"

_OR_GPT_OSS_CANON = "openai/gpt-oss-120b"


def normalize_inference_provider(provider: str) -> str:
    """Lower-case provider id and map UI / Mongo aliases (``openrouter`` → ``or``)."""
    p = (provider or "").strip().lower()
    if p == "openrouter":
        return "or"
    return p


def _normalize_openrouter_model_slug(model_name: str) -> str:
    """Map common typos to an OpenRouter-valid model id."""
    m = (model_name or "").strip()
    if not m:
        return m
    key = m.lower().replace(" ", "").replace("_", "-")
    tail = key.rsplit("/", 1)[-1]
    if tail in ("gpt-oss-120", "gpt-oss-120b") or key == "openai/gpt-oss-120":
        return _OR_GPT_OSS_CANON
    return m

# Reproducible sampling defaults for grading (GradeLab merges these into RunContext.config).
# Provider limits: Anthropic Messages API supports temperature only (no seed parameter).
# OpenAI-style chat completions (do, or, yc) accept temperature and often seed/top_p,
# but seed support varies by model; Yandex Cloud may reject unknown JSON keys—in that
# case gate or omit optional fields per provider.
DEFAULT_TEMPERATURE = 0.0
DEFAULT_SEED = 42
DEFAULT_TOP_P = 1.0

# OpenRouter provider routing pinned per-model (substring match on the model slug).
# Applied inside ``openai_prompt`` when the request targets OR_ENDPOINT unless
# ``openrouter_provider`` is set from RunContext ``pipeline_config``.
OR_PROVIDER_ROUTING: dict[str, dict] = {
    "gpt-oss-120b": {
        "allow_fallbacks": True,
        "only": ["Groq"],
    },
}


def inference_request_logging_enabled() -> bool:
    """When True, logs a one-line JSON summary before each outbound HTTP inference (no prompts, no keys).

    Enable with ``LLM_NOTEBOOK_GRADER_LOG_REQUESTS`` in Docker Compose / environment.
    """
    return os.environ.get("LLM_NOTEBOOK_GRADER_LOG_REQUESTS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _ensure_infer_request_log_visible() -> None:
    """Subprocess graders often have no handlers; attach a basic stderr handler once."""
    _log.setLevel(logging.INFO)
    if logging.root.handlers:
        return
    logging.basicConfig(level=logging.INFO)


def _log_inference_request(summary: dict) -> None:
    if not inference_request_logging_enabled():
        return
    _ensure_infer_request_log_visible()
    _log.info("inference_request %s", json.dumps(summary, default=str))


def _apply_openai_compatible_sampling(data: dict, *, temperature: float, seed: int | None, top_p: float) -> None:
    """Mutates ``data`` for chat/completions APIs. Omit ``seed`` if None (provider may not support)."""
    data["temperature"] = temperature
    if seed is not None:
        data["seed"] = seed
    if top_p != DEFAULT_TOP_P:
        data["top_p"] = top_p


def anthropic_prompt(
    *,
    model_name: str,
    api_key: str,
    system: str,
    messages: list[dict],
    max_tokens: int = 16384,
    temperature: float = DEFAULT_TEMPERATURE,
) -> tuple[str, dict, dict]:
    # Anthropic supports temperature only (no seed in Messages API).
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    data = {
        "model": model_name,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
        "temperature": temperature,
    }

    _log_inference_request({
        "api": "anthropic_messages",
        "endpoint": ANTHROPIC_ENDPOINT,
        "model": model_name,
        "temperature": temperature,
        "max_tokens": max_tokens,
    })

    response: Response = requests.post(ANTHROPIC_ENDPOINT, headers=headers, json=data)

    if response.status_code != 200:
        raise RuntimeError(f"Anthropic API error {response.status_code}: {response.text}")

    try:
        response_json = response.json()
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse Anthropic response: {e}\nRaw: {response.text}")

    content_blocks = response_json.get("content", [])
    text_parts = [b["text"] for b in content_blocks if b.get("type") == "text"]
    content = "\n".join(text_parts)

    return content, response_json.get("usage", {}), response_json


async def async_anthropic_prompt(
    *,
    model_name: str,
    api_key: str,
    system: str,
    messages: list[dict],
    max_tokens: int = 16384,
    temperature: float = DEFAULT_TEMPERATURE,
) -> tuple[str, dict, dict]:
    func = partial(
        anthropic_prompt,
        model_name=model_name,
        api_key=api_key,
        system=system,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return await asyncio.to_thread(func)


def openai_prompt(
    *,
    url: str,
    model_name: str,
    headers: dict,
    messages: list[dict],
    temperature: float = DEFAULT_TEMPERATURE,
    seed: int | None = DEFAULT_SEED,
    top_p: float = DEFAULT_TOP_P,
    openrouter_provider: dict[str, Any] | None = None,
) -> tuple[str, dict, dict]:
    data: dict = {
        "model": model_name,
        "messages": messages,
    }
    _apply_openai_compatible_sampling(data, temperature=temperature, seed=seed, top_p=top_p)

    or_routing_slug: str | None = None
    if url == OR_ENDPOINT:
        if openrouter_provider is not None:
            data["provider"] = openrouter_provider
            or_routing_slug = "pipeline_config"
        else:
            for slug, routing in OR_PROVIDER_ROUTING.items():
                if slug in model_name:
                    data["provider"] = routing
                    or_routing_slug = slug
                    break

    openai_summary: dict[str, object] = {
        "api": "openai_compatible",
        "endpoint": url,
        "model": model_name,
        "temperature": data.get("temperature"),
    }
    if "seed" in data:
        openai_summary["seed"] = data["seed"]
    else:
        openai_summary["seed_omitted"] = True
    if "top_p" in data:
        openai_summary["top_p"] = data["top_p"]
    if or_routing_slug is not None:
        openai_summary["or_provider_routing_slug"] = or_routing_slug

    _log_inference_request(openai_summary)

    response: Response = requests.post(url, headers=headers, json=data)

    if response.status_code != 200:
        raise RuntimeError(f"API error {response.status_code}: {response.text}")

    try:
        response_json = response.json()
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse response JSON: {e}\nRaw response: {response.text}")

    if "choices" not in response_json or not response_json["choices"]:
        raise RuntimeError(f"Unexpected response format: no choices in {response_json}")

    return (response_json["choices"][0]["message"]["content"], response_json["usage"], response_json)


async def async_openai_prompt(
    *,
    url: str,
    model_name: str,
    headers: dict,
    messages: list[dict],
    temperature: float = DEFAULT_TEMPERATURE,
    seed: int | None = DEFAULT_SEED,
    top_p: float = DEFAULT_TOP_P,
    openrouter_provider: dict[str, Any] | None = None,
) -> tuple[str, dict, dict]:
    func = partial(
        openai_prompt,
        url=url,
        model_name=model_name,
        headers=headers,
        messages=messages,
        temperature=temperature,
        seed=seed,
        top_p=top_p,
        openrouter_provider=openrouter_provider,
    )
    return await asyncio.to_thread(func)


def gradelab_llm_proxy_chat(
    *,
    model_name: str,
    api_token: str,
    messages: list[dict],
    temperature: float = DEFAULT_TEMPERATURE,
    seed: int | None = DEFAULT_SEED,
    top_p: float = DEFAULT_TOP_P,
    openrouter_provider: dict[str, Any] | None = None,
) -> tuple[str, dict, dict]:
    """POST to GradeLab LLMProxy (OpenAI-shaped response)."""
    profile_id = os.environ.get("GRADELAB_INFERENCE_PROFILE_ID", "")
    if not profile_id:
        raise RuntimeError("GRADELAB_INFERENCE_PROFILE_ID is required for llm_proxy provider")
    base = (os.environ.get("LLMPROXY_URL") or "").rstrip("/")
    if not base:
        raise RuntimeError("LLMPROXY_URL is required for llm_proxy provider")
    url = f"{base}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
    body: dict = {"profile_id": profile_id, "model": model_name, "messages": messages}
    _apply_openai_compatible_sampling(body, temperature=temperature, seed=seed, top_p=top_p)
    if openrouter_provider is not None:
        body["openrouter_provider"] = openrouter_provider
    proxy_summary: dict[str, object] = {
        "api": "gradelab_llm_proxy",
        "endpoint": url,
        "model": model_name,
        "profile_id": profile_id,
        "temperature": temperature,
        "seed": seed,
        "top_p": top_p,
    }
    if openrouter_provider is not None:
        proxy_summary["openrouter_provider"] = openrouter_provider
    _log_inference_request(proxy_summary)
    r = requests.post(url, headers=headers, json=body, timeout=180)
    if r.status_code >= 400:
        raise RuntimeError(f"LLMProxy error {r.status_code}: {r.text[:2000]}")
    response_json = r.json()
    if "choices" not in response_json or not response_json["choices"]:
        raise RuntimeError(f"Unexpected LLMProxy response: {response_json}")
    content = response_json["choices"][0]["message"]["content"]
    usage = response_json.get("usage") or {}
    return content, usage, response_json


def universal_prompt(
    provider: str,
    *,
    prompts: list[str],
    model_name: str,
    api_token: str,
    folder: str | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    seed: int | None = DEFAULT_SEED,
    top_p: float = DEFAULT_TOP_P,
    openrouter_provider: dict[str, Any] | None = None,
) -> tuple[str, dict, dict]:
    p = normalize_inference_provider(provider)

    headers: dict = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_token}",
    }

    if p == "do":
        url = DO_ENDPOINT
    elif p == "yc" and folder:
        headers["OpenAI-Project"] = folder
        url = YC_ENDPOINT
        model_name = f"gpt://{folder}/{model_name}"
    elif p == "or":
        url = OR_ENDPOINT
        model_name = _normalize_openrouter_model_slug(model_name)
    elif p == "anthropic":
        system = prompts[0] if len(prompts) > 1 else ""
        user_text = prompts[-1]
        return anthropic_prompt(
            model_name=model_name,
            api_key=api_token,
            system=system,
            messages=[{"role": "user", "content": user_text}],
            temperature=temperature,
        )

    if p == "llm_proxy":
        messages_ll: list[dict] = []
        if len(prompts) > 1:
            messages_ll.append({"role": "system", "content": prompts[0]})
        messages_ll.append({"role": "user", "content": prompts[-1]})
        return gradelab_llm_proxy_chat(
            model_name=model_name,
            api_token=api_token,
            messages=messages_ll,
            temperature=temperature,
            seed=seed,
            top_p=top_p,
            openrouter_provider=openrouter_provider,
        )

    messages: list[dict] = []

    if len(prompts) > 1:
        messages.append(
            {
                "role": "system",
                "content": prompts[0],
            }
        )

    messages.append(
        {
            "role": "user",
            "content": prompts[-1],
        }
    )

    return openai_prompt(
        url=url,
        model_name=model_name,
        headers=headers,
        messages=messages,
        temperature=temperature,
        seed=seed,
        top_p=top_p,
        openrouter_provider=openrouter_provider if p == "or" else None,
    )


async def async_universal_prompt(
    provider: str,
    *,
    prompts: list[str],
    model_name: str,
    api_token: str,
    folder: str | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    seed: int | None = DEFAULT_SEED,
    top_p: float = DEFAULT_TOP_P,
    openrouter_provider: dict[str, Any] | None = None,
) -> tuple[str, dict, dict]:
    func = partial(
        universal_prompt,
        provider,
        prompts=prompts,
        model_name=model_name,
        api_token=api_token,
        folder=folder,
        temperature=temperature,
        seed=seed,
        top_p=top_p,
        openrouter_provider=openrouter_provider,
    )
    return await asyncio.to_thread(func)
