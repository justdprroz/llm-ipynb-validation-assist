"""Multi-provider LLM client (do / yc / or / anthropic / llm_proxy).

Vision-aware: anthropic-style content blocks are sent natively to Anthropic and
re-shaped for OpenAI-compatible vision providers; non-vision providers receive a
text-only flattening.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from functools import partial
from typing import Any

import requests

_log = logging.getLogger(__name__)

DO_ENDPOINT = "https://inference.do-ai.run/v1/chat/completions"
YC_ENDPOINT = "https://llm.api.cloud.yandex.net/v1/chat/completions"
OR_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"

DEFAULT_TEMPERATURE = 0.0
DEFAULT_SEED = 42
DEFAULT_TOP_P = 1.0

_VISION_PROVIDERS = {"or", "do"}

EFFORT_MODES = {
    "light": (
        "GRADING EFFORT: LIGHT — be lenient. Penalize only severe failures "
        "(does not run, wrong problem, no attempt, fundamentally wrong result). "
        "Ignore style, minor inefficiency, cosmetic differences."
    ),
    "normal": (
        "GRADING EFFORT: NORMAL — penalize mistakes that affect the result "
        "(wrong logic, missing required parts, wrong outputs/plots). Tolerate "
        "minor style differences and valid alternative approaches."
    ),
    "strict": (
        "GRADING EFFORT: STRICT — penalize any deviation from the rubric: "
        "suboptimal algorithm, missing edge cases, output/plot differences, "
        "code-quality issues. Full marks only for correct, complete work."
    ),
}


def sampling_triple(cfg: dict | None) -> tuple[float, int | None, float]:
    c = cfg or {}
    temperature = float(c.get("temperature", DEFAULT_TEMPERATURE))
    top_p = float(c.get("top_p", DEFAULT_TOP_P))
    if "seed" in c:
        s = c["seed"]
        seed = None if s is None else int(s)
    else:
        seed = DEFAULT_SEED
    return temperature, seed, top_p


def normalize_provider(provider: str) -> str:
    p = (provider or "").strip().lower()
    return "or" if p == "openrouter" else p


def _log_enabled() -> bool:
    return os.environ.get("LLM_NOTEBOOK_NG_LOG_REQUESTS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _log_request(summary: dict) -> None:
    if not _log_enabled():
        return
    _log.setLevel(logging.INFO)
    if not logging.root.handlers:
        logging.basicConfig(level=logging.INFO)
    _log.info("ng_inference %s", json.dumps(summary, default=str))


def _apply_sampling(
    data: dict, *, temperature: float, seed: int | None, top_p: float
) -> None:
    data["temperature"] = temperature
    if seed is not None:
        data["seed"] = seed
    if top_p != DEFAULT_TOP_P:
        data["top_p"] = top_p


def blocks_to_text(blocks: list[dict]) -> str:
    parts = []
    for b in blocks:
        if b.get("type") == "text":
            parts.append(b["text"])
        elif b.get("type") == "image":
            parts.append("[image omitted: provider has no vision support]")
    return "\n".join(parts)


def _anthropic_to_openai_blocks(blocks: list[dict]) -> list[dict]:
    result = []
    for b in blocks:
        if b.get("type") == "text":
            result.append({"type": "text", "text": b["text"]})
        elif b.get("type") == "image":
            src = b["source"]
            result.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{src['media_type']};base64,{src['data']}"
                    },
                }
            )
    return result


def _anthropic_request(
    *,
    model: str,
    api_key: str,
    system: str,
    content: Any,
    temperature: float,
    max_tokens: int = 16384,
) -> str:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": content}],
        "temperature": temperature,
    }
    _log_request({"api": "anthropic", "model": model, "temperature": temperature})
    r = requests.post(ANTHROPIC_ENDPOINT, headers=headers, json=body, timeout=300)
    if r.status_code != 200:
        raise RuntimeError(f"Anthropic error {r.status_code}: {r.text[:1000]}")
    data = r.json()
    return "\n".join(
        b["text"] for b in data.get("content", []) if b.get("type") == "text"
    )


def _openai_request(
    *,
    url: str,
    model: str,
    headers: dict,
    messages: list[dict],
    temperature: float,
    seed: int | None,
    top_p: float,
    openrouter_provider: dict | None,
) -> str:
    body: dict = {"model": model, "messages": messages}
    _apply_sampling(body, temperature=temperature, seed=seed, top_p=top_p)
    if url == OR_ENDPOINT and openrouter_provider:
        body["provider"] = openrouter_provider
    _log_request(
        {
            "api": "openai",
            "endpoint": url,
            "model": model,
            "temperature": temperature,
            "seed": seed,
        }
    )
    r = requests.post(url, headers=headers, json=body, timeout=300)
    if r.status_code != 200:
        raise RuntimeError(f"API error {r.status_code}: {r.text[:1000]}")
    data = r.json()
    if not data.get("choices"):
        raise RuntimeError(f"No choices in response: {str(data)[:500]}")
    return data["choices"][0]["message"]["content"]


def _llm_proxy_request(
    *,
    model: str,
    api_token: str,
    messages: list[dict],
    temperature: float,
    seed: int | None,
    top_p: float,
    openrouter_provider: dict | None,
) -> str:
    profile_id = os.environ.get("GRADELAB_INFERENCE_PROFILE_ID", "")
    base = (os.environ.get("LLMPROXY_URL") or "").rstrip("/")
    if not profile_id or not base:
        raise RuntimeError(
            "llm_proxy requires GRADELAB_INFERENCE_PROFILE_ID and LLMPROXY_URL"
        )
    body: dict = {"profile_id": profile_id, "model": model, "messages": messages}
    _apply_sampling(body, temperature=temperature, seed=seed, top_p=top_p)
    if openrouter_provider:
        body["openrouter_provider"] = openrouter_provider
    _log_request({"api": "llm_proxy", "model": model, "profile_id": profile_id})
    r = requests.post(
        f"{base}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=300,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"LLMProxy error {r.status_code}: {r.text[:1000]}")
    data = r.json()
    if not data.get("choices"):
        raise RuntimeError(f"Unexpected LLMProxy response: {str(data)[:500]}")
    return data["choices"][0]["message"]["content"]


def _dispatch(
    provider: str,
    model: str,
    api_key: str,
    system: str,
    user_content: Any,
    *,
    yc_folder: str | None,
    temperature: float,
    seed: int | None,
    top_p: float,
    openrouter_provider: dict | None,
) -> str:
    p = normalize_provider(provider)
    is_multimodal = isinstance(user_content, list)

    if p == "anthropic":
        content = (
            user_content if is_multimodal else [{"type": "text", "text": user_content}]
        )
        return _anthropic_request(
            model=model,
            api_key=api_key,
            system=system,
            content=content,
            temperature=temperature,
        )

    if is_multimodal and p in _VISION_PROVIDERS:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": _anthropic_to_openai_blocks(user_content)},
        ]
        url = OR_ENDPOINT if p == "or" else DO_ENDPOINT
        return _openai_request(
            url=url,
            model=model,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            messages=messages,
            temperature=temperature,
            seed=seed,
            top_p=top_p,
            openrouter_provider=openrouter_provider if p == "or" else None,
        )

    text = (
        user_content if isinstance(user_content, str) else blocks_to_text(user_content)
    )
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    if p == "do":
        url = DO_ENDPOINT
    elif p == "or":
        url = OR_ENDPOINT
    elif p == "yc" and yc_folder:
        headers["OpenAI-Project"] = yc_folder
        url = YC_ENDPOINT
        model = f"gpt://{yc_folder}/{model}"
    elif p == "llm_proxy":
        msgs = [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ]
        return _llm_proxy_request(
            model=model,
            api_token=api_key,
            messages=msgs,
            temperature=temperature,
            seed=seed,
            top_p=top_p,
            openrouter_provider=openrouter_provider,
        )
    else:
        url = DO_ENDPOINT
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": text},
    ]
    return _openai_request(
        url=url,
        model=model,
        headers=headers,
        messages=messages,
        temperature=temperature,
        seed=seed,
        top_p=top_p,
        openrouter_provider=openrouter_provider if p == "or" else None,
    )


_RATE_LIMIT_MARKERS = (
    "429",
    "rate-limit",
    "rate limit",
    "ratelimited",
    "too many requests",
    "502",
    "temporarily",
)


def _is_rate_limited(error: str) -> bool:
    return any(m in error.lower() for m in _RATE_LIMIT_MARKERS)


def _backoff(attempt: int, error: str) -> float:
    """Gentle jittered waits — enough to let a transient 429 clear without
    starving throughput (the real throttle lever is concurrency/RPS, below)."""
    if _is_rate_limited(error):
        base = min(4 * 2**attempt, 30)
    else:
        base = min(2**attempt, 15)
    return base + random.uniform(0, base * 0.25)


# Process-wide adaptive throttle: one worker hitting a 429 nudges the others to
# pause briefly so they desync, instead of all hammering the throttled provider.
# Capped small + jittered so the pipeline keeps making forward progress.
_cooldown_until = 0.0
_COOLDOWN_CAP = 12.0
_RATE_LIMIT_BONUS_ATTEMPTS = 2

# Operator-set throttle, configured at the deployment / worker (executor) layer
# via env — NOT hardcoded in pipeline guts. 0 disables.
#   LLM_NOTEBOOK_NG_MAX_RPS         — global ceiling on outbound LLM requests/sec
_MAX_RPS = float(os.environ.get("LLM_NOTEBOOK_NG_MAX_RPS", "0") or 0)
_rps_lock = asyncio.Lock()
_next_slot = 0.0


async def _rps_gate() -> None:
    """Global token-bucket: spaces outbound requests to <= _MAX_RPS."""
    if _MAX_RPS <= 0:
        return
    global _next_slot
    interval = 1.0 / _MAX_RPS
    async with _rps_lock:
        now = time.monotonic()
        start = max(now, _next_slot)
        _next_slot = start + interval
    wait = start - now
    if wait > 0:
        await asyncio.sleep(wait)


async def _respect_cooldown() -> None:
    delay = _cooldown_until - time.monotonic()
    if delay > 0:
        await asyncio.sleep(delay + random.uniform(0, 1.5))


def _trip_cooldown(seconds: float) -> None:
    global _cooldown_until
    _cooldown_until = max(
        _cooldown_until, time.monotonic() + min(seconds, _COOLDOWN_CAP)
    )


async def call_llm(
    provider: str,
    model: str,
    api_key: str,
    system: str,
    user_content: Any,
    *,
    yc_folder: str | None = None,
    retry: int = 3,
    temperature: float = DEFAULT_TEMPERATURE,
    seed: int | None = DEFAULT_SEED,
    top_p: float = DEFAULT_TOP_P,
    openrouter_provider: dict | None = None,
    label: str = "",
) -> str | None:
    """Returns model text, or None after exhausting retries."""
    last_error = ""
    attempt = 0
    while True:
        await _respect_cooldown()
        await _rps_gate()
        try:
            t0 = time.time()
            func = partial(
                _dispatch,
                provider,
                model,
                api_key,
                system,
                user_content,
                yc_folder=yc_folder,
                temperature=temperature,
                seed=seed,
                top_p=top_p,
                openrouter_provider=openrouter_provider,
            )
            result = await asyncio.to_thread(func)
            print(f"    {label} -> {time.time() - t0:.1f}s")
            return result
        except Exception as exc:  # noqa: BLE001 — provider faults must not abort the run
            last_error = str(exc)
            is_rl = _is_rate_limited(last_error)
            print(f"    error ({label}): {last_error[:200]}")
            budget = retry + (_RATE_LIMIT_BONUS_ATTEMPTS if is_rl else 0)
            if attempt >= budget:
                break
            wait = _backoff(attempt, last_error)
            if is_rl:
                # Make every concurrent worker wait out the same window.
                _trip_cooldown(wait)
            await asyncio.sleep(wait)
            attempt += 1
            print(f"    retry {attempt}/{budget} ({label})")
    print(f"    failed after {attempt} retries ({label}): {last_error[:300]}")
    return None
