"""Optional LLM reflector adapter for GEPA-inspired strategy evolution."""

from __future__ import annotations

import json
import os
from typing import Any

from core.strategy_evolution import ReflectorFn
from integrations.llm_client import call_llm, provider_route_chain, resolve_provider_name

SYSTEM_PROMPT = """You are the Reflector in a GEPA-inspired prompt evolution loop.
Read compact execution traces and return only JSON with:
root_causes, prompt_failures, suggested_edits, risk_notes, trace_summary.
Keep suggestions conservative, shadow-only, and compatible with existing Wyckoff risk controls."""


def strategy_evolution_reflector_from_env() -> ReflectorFn | None:
    if not _env_enabled("STRATEGY_EVOLUTION_LLM_REFLECTOR", default=False):
        return None
    routes = provider_route_chain(
        resolve_provider_name("STRATEGY_EVOLUTION_REFLECTOR_PROVIDER", "gemini"),
        provider_fallbacks_from_env("STRATEGY_EVOLUTION_REFLECTOR_FALLBACKS"),
    )
    if not routes:
        return None

    def _reflect(request: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(request, ensure_ascii=False, sort_keys=True)
        last_error = ""
        for route in routes:
            try:
                text = call_llm(
                    route["provider"],
                    route["model"],
                    route["api_key"],
                    SYSTEM_PROMPT,
                    payload,
                    base_url=route.get("base_url") or None,
                    timeout=_env_int("STRATEGY_EVOLUTION_REFLECTOR_TIMEOUT", 120),
                    max_output_tokens=_env_int("STRATEGY_EVOLUTION_REFLECTOR_MAX_TOKENS", 4096),
                    allow_truncated_text=True,
                )
                return _parse_reflector_json(text)
            except Exception as exc:
                last_error = str(exc)
        return {
            "reflector": "llm_reflector_failed",
            "root_causes": [],
            "prompt_failures": [last_error],
            "suggested_edits": [],
            "risk_notes": ["Fallback to deterministic reflector output."],
            "trace_summary": "LLM reflector failed or returned invalid JSON.",
        }

    return _reflect


def provider_fallbacks_from_env(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "").strip()
    return tuple(item.strip().lower() for item in raw.split(",") if item.strip())


def _parse_reflector_json(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(raw[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Reflector response must be a JSON object")
    return parsed


def _env_enabled(name: str, *, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return max(int(float(os.getenv(name, str(default)))), 1)
    except (TypeError, ValueError):
        return default
