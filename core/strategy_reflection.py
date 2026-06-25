"""Build data-backed strategy reflection payloads."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from core.strategy_evolution import run_strategy_evolution


def _safe_float(raw: Any, default: float = 0.0) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value == value else default


def _done_rows(outcomes: list[dict[str, Any]], horizon_days: int) -> list[dict[str, Any]]:
    horizon = int(horizon_days)
    return [
        row
        for row in outcomes
        if int(row.get("horizon_days") or 0) == horizon and str(row.get("status") or "").lower() == "done"
    ]


def _track_of(row: dict[str, Any]) -> str:
    track = str(row.get("track") or "").strip()
    if track:
        return track
    signal = str(row.get("signal_type") or "").strip().lower()
    return "Trend" if signal in {"sos", "evr", "trend_pullback"} else "Accum"


def summarize_track_performance(outcomes: list[dict[str, Any]], horizon_days: int) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in _done_rows(outcomes, horizon_days):
        key = (_track_of(row), str(row.get("regime") or "ALL").strip().upper() or "ALL")
        buckets.setdefault(key, []).append(row)
    summary = []
    for (track, regime), rows in sorted(buckets.items()):
        returns = [_safe_float(row.get("return_pct")) for row in rows]
        drawdowns = [_safe_float(row.get("max_drawdown_pct")) for row in rows]
        wins = sum(ret > 0 for ret in returns)
        summary.append(
            {
                "track": track,
                "regime": regime,
                "sample_count": len(rows),
                "win_rate": round(wins / len(rows), 4) if rows else 0.0,
                "avg_return_pct": round(sum(returns) / len(returns), 4) if returns else 0.0,
                "avg_drawdown_pct": round(sum(drawdowns) / len(drawdowns), 4) if drawdowns else 0.0,
            }
        )
    return summary


def summarize_shadow_runs(shadow_runs: list[dict[str, Any]]) -> dict[str, Any]:
    added = sum(len(row.get("diff_added") or []) for row in shadow_runs)
    removed = sum(len(row.get("diff_removed") or []) for row in shadow_runs)
    return {
        "run_count": len(shadow_runs),
        "added_count": added,
        "removed_count": removed,
        "avg_added": round(added / len(shadow_runs), 4) if shadow_runs else 0.0,
        "avg_removed": round(removed / len(shadow_runs), 4) if shadow_runs else 0.0,
    }


def _best_track(track_summary: list[dict[str, Any]]) -> str:
    eligible = [row for row in track_summary if int(row.get("sample_count") or 0) > 0]
    if not eligible:
        return ""
    best = max(eligible, key=lambda row: (_safe_float(row.get("avg_return_pct")), _safe_float(row.get("win_rate"))))
    return str(best.get("track") or "")


def _reflection_text(
    track_summary: list[dict[str, Any]],
    shadow_summary: dict[str, Any],
    evolution: dict[str, Any] | None = None,
) -> str:
    if not track_summary:
        return "样本不足，保持 shadow 观察，不调整生产策略。"
    best = _best_track(track_summary) or "unknown"
    base = (
        f"{best} track has the strongest recent outcome profile. "
        f"Shadow runs={shadow_summary.get('run_count', 0)}, "
        f"avg_added={shadow_summary.get('avg_added', 0)}, avg_removed={shadow_summary.get('avg_removed', 0)}. "
    )
    if not evolution or evolution.get("status") == "INSUFFICIENT_DATA":
        return base + " Keep candidate in review; do not auto-promote."
    status = str(evolution.get("status") or "")
    if status == "CONFIRMED":
        selected = ((evolution.get("fusion") or {}).get("selected_variant")) or "candidate"
        return base + f" Evolution confirmed fused {selected} policy in shadow; do not auto-promote."
    if status == "ROLLBACK":
        return base + " Evolution candidate rolled back after fusion validation; keep baseline policy."
    return base + " No candidate beat baseline on validation; keep baseline policy."


def build_strategy_reflection(
    outcomes: list[dict[str, Any]],
    shadow_runs: list[dict[str, Any]],
    *,
    observations: list[dict[str, Any]] | None = None,
    market: str = "cn",
    as_of_date: str | None = None,
    horizon_days: int = 5,
) -> dict[str, Any]:
    track_summary = summarize_track_performance(outcomes, horizon_days)
    shadow_summary = summarize_shadow_runs(shadow_runs)
    evolution = run_strategy_evolution(
        outcomes,
        shadow_runs,
        observations=observations or [],
        market=market,
        as_of_date=as_of_date or date.today().isoformat(),
        horizon_days=horizon_days,
        shadow_summary=shadow_summary,
    )
    now_iso = datetime.now(UTC).isoformat()
    return {
        "market": market,
        "as_of_date": as_of_date or date.today().isoformat(),
        "horizon_days": int(horizon_days),
        "status": "SHADOW",
        "summary": {
            "track_performance": track_summary,
            "shadow": shadow_summary,
            "preferred_track": _best_track(track_summary),
            "evolution": evolution,
        },
        "reflection_text": _reflection_text(track_summary, shadow_summary, evolution),
        "created_at": now_iso,
        "updated_at": now_iso,
    }


def build_policy_candidate(reflection: dict[str, Any]) -> dict[str, Any] | None:
    summary = reflection.get("summary") if isinstance(reflection.get("summary"), dict) else {}
    evolution = summary.get("evolution") if isinstance(summary.get("evolution"), dict) else {}
    if evolution and evolution.get("status") != "INSUFFICIENT_DATA":
        return _build_evolved_policy_candidate(reflection, summary, evolution)
    preferred_track = str(summary.get("preferred_track") or "").strip()
    if not preferred_track:
        return None
    now_iso = datetime.now(UTC).isoformat()
    return {
        "market": reflection["market"],
        "as_of_date": reflection["as_of_date"],
        "status": "READY_FOR_REVIEW",
        "source_reflection_date": reflection["as_of_date"],
        "candidate_policy": {
            "mode": "shadow",
            "preferred_track": preferred_track,
            "horizon_days": reflection["horizon_days"],
            "auto_promote": False,
        },
        "validation_summary": summary,
        "created_at": now_iso,
        "updated_at": now_iso,
    }


def _build_evolved_policy_candidate(
    reflection: dict[str, Any],
    summary: dict[str, Any],
    evolution: dict[str, Any],
) -> dict[str, Any]:
    now_iso = datetime.now(UTC).isoformat()
    decision = str(evolution.get("status") or "")
    fused_policy = (
        ((evolution.get("fusion") or {}).get("policy")) if isinstance(evolution.get("fusion"), dict) else None
    )
    if decision == "CONFIRMED" and isinstance(fused_policy, dict):
        status = "READY_FOR_REVIEW"
        candidate_policy = dict(fused_policy)
        candidate_policy.update(
            {
                "evolution_decision": "CONFIRMED",
                "auto_promote": False,
            }
        )
    else:
        status = "REJECTED"
        candidate_policy = {
            "mode": "shadow",
            "horizon_days": reflection["horizon_days"],
            "auto_promote": False,
            "evolution_decision": decision,
            "preferred_track": summary.get("preferred_track") or "",
            "reason": (evolution.get("fusion") or evolution.get("decision") or {}).get("reason", ""),
        }
    return {
        "market": reflection["market"],
        "as_of_date": reflection["as_of_date"],
        "status": status,
        "source_reflection_date": reflection["as_of_date"],
        "candidate_policy": candidate_policy,
        "validation_summary": {
            "track_performance": summary.get("track_performance") or [],
            "shadow": summary.get("shadow") or {},
            "evolution": evolution,
        },
        "created_at": now_iso,
        "updated_at": now_iso,
    }
