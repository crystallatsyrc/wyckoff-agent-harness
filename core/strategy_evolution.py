"""Deterministic strategy evolution loop used by strategy reflection jobs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from statistics import mean
from typing import Any


@dataclass(frozen=True)
class StrategyEvolutionConfig:
    worst_limit: int = 10
    best_limit: int = 10
    recent_limit: int = 20
    validation_ratio: float = 0.35
    min_validation_samples: int = 12
    min_candidate_samples: int = 3
    min_score_improvement: float = 0.05
    fusion_alpha: float = 0.8
    fusion_regression_tolerance: float = 0.35


DEFAULT_EVOLUTION_CONFIG = StrategyEvolutionConfig()
_VARIANTS = {"conservative": 0.35, "balanced": 0.65, "aggressive": 1.0}
_META_KEYS = {"sample_count", "win_rate", "avg_return_pct", "avg_drawdown_pct", "avg_critic_score", "rank_score"}


def run_strategy_evolution(
    outcomes: list[dict[str, Any]],
    shadow_runs: list[dict[str, Any]],
    *,
    observations: list[dict[str, Any]] | None = None,
    market: str = "cn",
    as_of_date: str = "",
    horizon_days: int = 5,
    shadow_summary: dict[str, Any] | None = None,
    config: StrategyEvolutionConfig | None = None,
) -> dict[str, Any]:
    """Run Critic sampling -> Reflector -> Evolver -> validation -> fusion."""

    cfg = config or DEFAULT_EVOLUTION_CONFIG
    trajectories = build_execution_trajectories(outcomes, observations or [], market=market, horizon_days=horizon_days)
    if len(trajectories) < cfg.min_validation_samples:
        return {
            "version": "strategy_evolution_v1",
            "status": "INSUFFICIENT_DATA",
            "market": market,
            "as_of_date": as_of_date,
            "horizon_days": int(horizon_days),
            "trajectory_count": len(trajectories),
            "required_trajectories": cfg.min_validation_samples,
            "config": asdict(cfg),
        }

    diagnostic_pool, validation_set, holdout = split_diagnostic_validation(trajectories, cfg)
    samples = sample_critic_trajectories(diagnostic_pool, cfg)
    diagnostic = build_diagnostic_report(samples, diagnostic_pool, shadow_runs, shadow_summary or {})
    baseline_policy = build_baseline_policy(horizon_days)
    candidates = generate_candidate_strategies(diagnostic, horizon_days)
    validation = validate_strategy_suite(baseline_policy, candidates, validation_set, cfg)
    decision = choose_evolution_direction(validation, cfg)
    fusion = run_fusion_validation(baseline_policy, candidates, decision, validation_set, diagnostic, cfg)
    status = fusion.get("decision_status") or decision.get("status") or "NO_BETTER_CANDIDATE"
    return {
        "version": "strategy_evolution_v1",
        "status": status,
        "market": market,
        "as_of_date": as_of_date,
        "horizon_days": int(horizon_days),
        "trajectory_count": len(trajectories),
        "diagnostic_count": len(diagnostic_pool),
        "validation_count": len(validation_set),
        "validation_holdout": holdout,
        "trajectory_samples": {k: [compact_trajectory(x) for x in rows] for k, rows in samples.items()},
        "diagnostic_report": diagnostic,
        "baseline_policy": baseline_policy,
        "candidate_policies": candidates,
        "validation": validation,
        "decision": decision,
        "fusion": fusion,
        "config": asdict(cfg),
    }


def build_execution_trajectories(
    outcomes: list[dict[str, Any]],
    observations: list[dict[str, Any]] | None = None,
    *,
    market: str = "cn",
    horizon_days: int = 5,
) -> list[dict[str, Any]]:
    obs_by_id, obs_by_key = _index_observations(observations or [])
    rows = []
    for outcome in outcomes or []:
        if int(outcome.get("horizon_days") or 0) != int(horizon_days):
            continue
        if str(outcome.get("status") or "").lower() != "done":
            continue
        obs = _match_observation(outcome, obs_by_id, obs_by_key)
        features = _dict(outcome.get("features_json")) or _dict(obs.get("features_json"))
        signal = str(outcome.get("signal_type") or obs.get("signal_type") or "").strip().lower()
        track = str(outcome.get("track") or obs.get("track") or "").strip() or _track_for_signal(signal)
        trade_date = str(outcome.get("trade_date") or obs.get("trade_date") or "")
        code = str(outcome.get("code") or obs.get("code") or "")
        score, score_source = _critic_score(outcome, obs, features)
        ret = _float(outcome.get("return_pct"))
        drawdown = _float(outcome.get("max_drawdown_pct"))
        row_id = outcome.get("observation_id") or obs.get("id") or outcome.get("id")
        rows.append(
            {
                "trajectory_id": str(row_id or f"{market}:{trade_date}:{code}:{signal}:{horizon_days}"),
                "market": str(outcome.get("market") or obs.get("market") or market),
                "trade_date": trade_date,
                "code": code,
                "signal_type": signal,
                "track": track,
                "regime": str(outcome.get("regime") or obs.get("regime") or "ALL").strip().upper() or "ALL",
                "horizon_days": int(horizon_days),
                "critic_score": score,
                "critic_score_source": score_source,
                "return_pct": ret,
                "max_drawdown_pct": drawdown,
                "snapshot": _snapshot(outcome, obs, features),
                "prediction": _prediction(outcome, obs, score),
                "critique": _dict(outcome.get("critique"))
                or {"return_pct": _round(ret), "max_drawdown_pct": _round(drawdown)},
            }
        )
    return _sort_rows(rows)


def split_diagnostic_validation(
    trajectories: list[dict[str, Any]], config: StrategyEvolutionConfig | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    cfg = config or DEFAULT_EVOLUTION_CONFIG
    rows = _sort_rows(trajectories)
    n = max(cfg.min_validation_samples, int(len(rows) * max(min(cfg.validation_ratio, 0.8), 0.1)))
    return (rows, rows, False) if len(rows) < n + cfg.min_validation_samples else (rows[:-n], rows[-n:], True)


def sample_critic_trajectories(
    trajectories: list[dict[str, Any]], config: StrategyEvolutionConfig | None = None
) -> dict[str, list[dict[str, Any]]]:
    cfg = config or DEFAULT_EVOLUTION_CONFIG
    by_score = sorted(trajectories, key=lambda x: (_float(x.get("critic_score")), str(x.get("trade_date"))))
    by_recent = sorted(trajectories, key=lambda x: str(x.get("trade_date") or ""), reverse=True)
    return {
        "worst": by_score[: cfg.worst_limit],
        "best": list(reversed(by_score[-cfg.best_limit :])),
        "recent": by_recent[: cfg.recent_limit],
    }


def compact_trajectory(row: dict[str, Any]) -> dict[str, Any]:
    keys = ("trajectory_id", "trade_date", "code", "signal_type", "track", "regime", "critic_score_source")
    out = {key: row.get(key) for key in keys}
    out.update(
        {
            "critic_score": _round(row.get("critic_score")),
            "return_pct": _round(row.get("return_pct")),
            "max_drawdown_pct": _round(row.get("max_drawdown_pct")),
            "snapshot": row.get("snapshot"),
            "prediction": row.get("prediction"),
            "critique": row.get("critique"),
        }
    )
    return out


def build_diagnostic_report(
    samples: dict[str, list[dict[str, Any]]],
    diagnostic_pool: list[dict[str, Any]],
    shadow_runs: list[dict[str, Any]],
    shadow_summary: dict[str, Any],
) -> dict[str, Any]:
    track_stats = _performance_by(diagnostic_pool, "track")
    signal_stats = _performance_by(diagnostic_pool, "signal_type")
    regime_stats = _performance_by(diagnostic_pool, "regime")
    weak_track, strong_track = _weak_strong(track_stats)
    weak_signal, strong_signal = _weak_strong(signal_stats)
    weak_regime, strong_regime = _weak_strong(regime_stats)
    failure_tags = _failure_tag_counts(samples.get("worst", []))
    return {
        "reflector": "deterministic_reflector_v1",
        "sample_counts": {k: len(v) for k, v in samples.items()},
        "root_causes": _root_causes(
            weak_track, strong_track, weak_signal, strong_signal, weak_regime, shadow_runs, shadow_summary, failure_tags
        ),
        "failure_tags": failure_tags,
        "weak_track": weak_track,
        "strong_track": strong_track,
        "weak_signal": weak_signal,
        "strong_signal": strong_signal,
        "weak_regime": weak_regime,
        "strong_regime": strong_regime,
        "track_stats": track_stats,
        "signal_stats": signal_stats,
        "regime_stats": regime_stats,
        "shadow_summary": shadow_summary,
    }


def build_baseline_policy(horizon_days: int) -> dict[str, Any]:
    return _policy(
        "baseline",
        horizon_days,
        track_weights={},
        signal_weights={},
        regime_weights={},
        selection={"critic_score_floor": 0.0, "minimum_policy_weight": 0.0},
        prompt_directives=["Preserve the existing Wyckoff prompt and current risk controls."],
    )


def generate_candidate_strategies(diagnostic: dict[str, Any], horizon_days: int) -> list[dict[str, Any]]:
    return [_candidate_strategy(name, intensity, diagnostic, horizon_days) for name, intensity in _VARIANTS.items()]


def validate_strategy_suite(
    baseline_policy: dict[str, Any],
    candidates: list[dict[str, Any]],
    validation_set: list[dict[str, Any]],
    config: StrategyEvolutionConfig | None = None,
) -> dict[str, Any]:
    cfg = config or DEFAULT_EVOLUTION_CONFIG
    return {
        "validator": "heldout_trajectory_validator_v1",
        "baseline": validate_policy(baseline_policy, validation_set, min_samples=1),
        "candidates": [validate_policy(p, validation_set, min_samples=cfg.min_candidate_samples) for p in candidates],
    }


def choose_evolution_direction(
    validation: dict[str, Any], config: StrategyEvolutionConfig | None = None
) -> dict[str, Any]:
    cfg = config or DEFAULT_EVOLUTION_CONFIG
    baseline = validation.get("baseline") if isinstance(validation.get("baseline"), dict) else {}
    candidates = [x for x in validation.get("candidates", []) if x.get("viable")]
    if not candidates:
        return {"status": "NO_VIABLE_CANDIDATE", "reason": "all candidates selected too few validation samples"}
    best = max(candidates, key=lambda x: _float(x.get("validation_score"), -999999.0))
    improvement = _float(best.get("validation_score")) - _float(baseline.get("validation_score"))
    if improvement <= cfg.min_score_improvement:
        return {
            "status": "NO_BETTER_CANDIDATE",
            "reason": "best candidate did not clear baseline improvement threshold",
            "best_variant": best.get("variant"),
            "score_improvement": _round(improvement),
            "required_improvement": cfg.min_score_improvement,
        }
    return {
        "status": "CANDIDATE_SELECTED",
        "best_variant": best.get("variant"),
        "score_improvement": _round(improvement),
        "required_improvement": cfg.min_score_improvement,
        "candidate_result": best,
    }


def run_fusion_validation(
    baseline_policy: dict[str, Any],
    candidates: list[dict[str, Any]],
    decision: dict[str, Any],
    validation_set: list[dict[str, Any]],
    diagnostic: dict[str, Any],
    config: StrategyEvolutionConfig | None = None,
) -> dict[str, Any]:
    cfg = config or DEFAULT_EVOLUTION_CONFIG
    if decision.get("status") != "CANDIDATE_SELECTED":
        return {"decision_status": decision.get("status", "NO_BETTER_CANDIDATE"), "rollback": False}
    selected = next((p for p in candidates if p.get("variant") == decision.get("best_variant")), None)
    if not selected:
        return {"decision_status": "ROLLBACK", "rollback": True, "reason": "selected candidate policy missing"}
    fused = fuse_strategy_policy(baseline_policy, selected, diagnostic, cfg)
    fused_result = validate_policy(fused, validation_set, min_samples=cfg.min_candidate_samples)
    candidate_score = _float((decision.get("candidate_result") or {}).get("validation_score"))
    fused_score = _float(fused_result.get("validation_score"))
    regression = candidate_score - fused_score
    status = "ROLLBACK" if regression > cfg.fusion_regression_tolerance else "CONFIRMED"
    return {
        "decision_status": status,
        "rollback": status == "ROLLBACK",
        "reason": "fused policy regressed beyond tolerance" if status == "ROLLBACK" else "",
        "selected_variant": selected.get("variant"),
        "candidate_validation_score": _round(candidate_score),
        "fused_validation_score": _round(fused_score),
        "regression": _round(regression),
        "regression_tolerance": cfg.fusion_regression_tolerance,
        "policy": fused,
        "validation_result": fused_result,
    }


def fuse_strategy_policy(
    baseline_policy: dict[str, Any],
    selected_policy: dict[str, Any],
    diagnostic: dict[str, Any],
    config: StrategyEvolutionConfig | None = None,
) -> dict[str, Any]:
    cfg = config or DEFAULT_EVOLUTION_CONFIG
    alpha = max(0.0, min(float(cfg.fusion_alpha), 1.0))
    selected_sel = selected_policy.get("selection") if isinstance(selected_policy.get("selection"), dict) else {}
    return _policy(
        f"fused_{selected_policy.get('variant')}",
        int(selected_policy.get("horizon_days") or baseline_policy.get("horizon_days") or 5),
        track_weights=_fuse_weights(selected_policy.get("track_weights"), alpha),
        signal_weights=_fuse_weights(selected_policy.get("signal_weight_adjustments"), alpha),
        regime_weights=_fuse_weights(selected_policy.get("regime_weight_adjustments"), alpha),
        selection={
            "critic_score_floor": _round(_float(selected_sel.get("critic_score_floor")) * alpha),
            "minimum_policy_weight": _round(_float(selected_sel.get("minimum_policy_weight")) * alpha),
        },
        prompt_directives=[
            *(baseline_policy.get("prompt_directives") or []),
            "Fuse, do not replace: keep stable historical Wyckoff rules unless validation evidence contradicts them.",
            *(selected_policy.get("prompt_directives") or []),
        ],
        parent_variant=selected_policy.get("variant"),
        fusion_alpha=alpha,
        preserve_baseline=True,
        diagnostic_focus={k: diagnostic.get(k) for k in ("weak_track", "strong_track", "weak_signal", "strong_signal")},
    )


def validate_policy(
    policy: dict[str, Any], validation_set: list[dict[str, Any]], *, min_samples: int = 1
) -> dict[str, Any]:
    selected, adjusted = [], []
    for row in validation_set:
        weight = _policy_weight(policy, row)
        score = _float(row.get("critic_score")) * weight
        sel = policy.get("selection") if isinstance(policy.get("selection"), dict) else {}
        if score >= _float(sel.get("critic_score_floor")) and weight >= _float(sel.get("minimum_policy_weight")):
            selected.append(row)
            adjusted.append(score)
    metrics = _validation_metrics(selected, len(validation_set), adjusted)
    metrics.update(
        {
            "variant": policy.get("variant"),
            "viable": metrics["selected_count"] >= min_samples,
            "min_samples": min_samples,
        }
    )
    return metrics


def _policy(
    variant: str,
    horizon_days: int,
    *,
    track_weights: dict[str, float],
    signal_weights: dict[str, float],
    regime_weights: dict[str, float],
    selection: dict[str, float],
    prompt_directives: list[str],
    **extra: Any,
) -> dict[str, Any]:
    return {
        "variant": variant,
        "mode": "shadow",
        "horizon_days": int(horizon_days),
        "auto_promote": False,
        "track_weights": track_weights,
        "signal_weight_adjustments": signal_weights,
        "regime_weight_adjustments": regime_weights,
        "selection": selection,
        "prompt_directives": prompt_directives,
        **extra,
    }


def _candidate_strategy(
    variant: str, intensity: float, diagnostic: dict[str, Any], horizon_days: int
) -> dict[str, Any]:
    weak_track, strong_track = str(diagnostic.get("weak_track") or ""), str(diagnostic.get("strong_track") or "")
    weak_signal, strong_signal = str(diagnostic.get("weak_signal") or ""), str(diagnostic.get("strong_signal") or "")
    weak_regime, strong_regime = str(diagnostic.get("weak_regime") or ""), str(diagnostic.get("strong_regime") or "")
    return _policy(
        variant,
        horizon_days,
        track_weights=_weights(weak_track, strong_track, down=0.25 * intensity, up=0.25 * intensity),
        signal_weights=_weights(weak_signal, strong_signal, down=0.35 * intensity, up=0.30 * intensity),
        regime_weights=_weights(weak_regime, strong_regime, down=0.20 * intensity, up=0.15 * intensity),
        selection={
            "critic_score_floor": _round(25.0 + 20.0 * intensity),
            "minimum_policy_weight": _round(0.75 + 0.10 * intensity),
        },
        prompt_directives=[
            f"Prefer {strong_track or 'validated'} structures when evidence quality is comparable.",
            f"De-emphasize {weak_signal or weak_track or 'weak'} setups unless Critic score is strong.",
            "Treat the change as shadow-only until held-out validation remains better than baseline.",
        ],
        pareto_objective={
            "conservative": "lower drawdown and keep more historical coverage",
            "balanced": "improve risk-adjusted return with moderate coverage loss",
            "aggressive": "maximize validated upside from strongest root-cause signal",
        }[variant],
        preferred_track=strong_track,
        deemphasized_track=weak_track,
        root_causes=diagnostic.get("root_causes") or [],
    )


def _index_observations(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str, str, str], dict[str, Any]]]:
    by_id, by_key = {}, {}
    for row in rows:
        if row.get("id") is not None:
            by_id[str(row.get("id"))] = row
        by_key[
            (
                str(row.get("market") or ""),
                str(row.get("trade_date") or ""),
                str(row.get("code") or ""),
                str(row.get("signal_type") or "").lower(),
            )
        ] = row
    return by_id, by_key


def _match_observation(
    outcome: dict[str, Any], by_id: dict[str, dict[str, Any]], by_key: dict[tuple[str, str, str, str], dict[str, Any]]
) -> dict[str, Any]:
    obs_id = str(outcome.get("observation_id") or "")
    return (
        by_id.get(obs_id)
        or by_key.get(
            (
                str(outcome.get("market") or ""),
                str(outcome.get("trade_date") or ""),
                str(outcome.get("code") or ""),
                str(outcome.get("signal_type") or "").lower(),
            )
        )
        or {}
    )


def _dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _float(raw: Any, default: float = 0.0) -> float:
    try:
        if raw is None or str(raw).strip() == "":
            return default
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value == value else default


def _round(raw: Any, digits: int = 4) -> float:
    return round(_float(raw), digits)


def _bounded(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _track_for_signal(signal: str) -> str:
    return "Trend" if signal in {"sos", "evr", "trend_pullback"} else "Accum"


def _critic_score(row: dict[str, Any], obs: dict[str, Any], features: dict[str, Any]) -> tuple[float, str]:
    for source, container in (("outcome", row), ("observation", obs)):
        for key in ("critic_score", "funnel_score", "priority_score", "score"):
            if key in container:
                return _bounded(_float(container.get(key), 50.0)), f"{source}.{key}"
    shadow = features.get("candidate_shadow_score")
    if isinstance(shadow, dict) and "score" in shadow:
        return _bounded(_float(shadow.get("score"), 50.0)), "features_json.candidate_shadow_score.score"
    return _bounded(
        50.0 + _float(row.get("return_pct")) * 8.0 - abs(_float(row.get("max_drawdown_pct"))) * 2.0
    ), "outcome_proxy"


def _snapshot(row: dict[str, Any], obs: dict[str, Any], features: dict[str, Any]) -> dict[str, Any]:
    explicit = _dict(row.get("snapshot")) or _dict(obs.get("snapshot"))
    if explicit:
        return explicit
    footprint = (
        features.get("price_action_footprint") if isinstance(features.get("price_action_footprint"), dict) else {}
    )
    return {
        "features": {
            "candidate_shadow_score": features.get("candidate_shadow_score"),
            "price_action_tags": footprint.get("tags") or [],
            "negative_tags": footprint.get("negative_tags") or [],
            "data_lineage": features.get("data_lineage"),
        },
        "selected_for_ai": bool(obs.get("selected_for_ai", False)),
        "ai_recommended": bool(obs.get("ai_recommended", False)),
    }


def _prediction(row: dict[str, Any], obs: dict[str, Any], score: float) -> dict[str, Any]:
    return (
        _dict(row.get("prediction"))
        or _dict(obs.get("prediction"))
        or {
            "critic_score": _round(score),
            "policy_version": row.get("policy_version") or obs.get("policy_version") or "",
            "selection_mode": row.get("selection_mode") or obs.get("selection_mode") or "",
        }
    )


def _performance_by(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        buckets.setdefault(str(row.get(field) or "unknown"), []).append(row)
    stats = []
    for key, values in buckets.items():
        returns = [_float(x.get("return_pct")) for x in values]
        drawdowns = [abs(_float(x.get("max_drawdown_pct"))) for x in values]
        scores = [_float(x.get("critic_score"), 50.0) for x in values]
        win_rate = sum(x > 0 for x in returns) / len(returns)
        avg_return, avg_drawdown, avg_score = mean(returns), mean(drawdowns), mean(scores)
        rank = avg_return + win_rate * 2.0 - avg_drawdown * 0.35 + avg_score * 0.01
        stats.append(
            {
                field: key,
                "sample_count": len(values),
                "win_rate": _round(win_rate),
                "avg_return_pct": _round(avg_return),
                "avg_drawdown_pct": _round(avg_drawdown),
                "avg_critic_score": _round(avg_score),
                "rank_score": _round(rank),
            }
        )
    return sorted(stats, key=lambda x: _float(x.get("rank_score")), reverse=True)


def _weak_strong(stats: list[dict[str, Any]]) -> tuple[str, str]:
    if not stats:
        return "", ""
    key = next((k for k in stats[0] if k not in _META_KEYS), "")
    return (str(stats[-1].get(key) or ""), str(stats[0].get(key) or "")) if key else ("", "")


def _failure_tag_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        snapshot = row.get("snapshot") if isinstance(row.get("snapshot"), dict) else {}
        features = snapshot.get("features") if isinstance(snapshot.get("features"), dict) else {}
        for tag in features.get("negative_tags") or []:
            tag_s = str(tag).strip()
            if tag_s:
                counts[tag_s] = counts.get(tag_s, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:10])


def _root_causes(
    weak_track: str,
    strong_track: str,
    weak_signal: str,
    strong_signal: str,
    weak_regime: str,
    shadow_runs: list[dict[str, Any]],
    shadow_summary: dict[str, Any],
    failure_tags: dict[str, int],
) -> list[str]:
    causes = []
    if weak_track and strong_track and weak_track != strong_track:
        causes.append(f"{weak_track} track underperforms while {strong_track} track leads validation evidence")
    if weak_signal and strong_signal and weak_signal != strong_signal:
        causes.append(f"{weak_signal} signal contributes more failures than {strong_signal} signal")
    if weak_regime:
        causes.append(f"{weak_regime} regime needs tighter selection or lower allocation")
    if shadow_runs and _float(shadow_summary.get("avg_added")) + _float(shadow_summary.get("avg_removed")) >= 2.0:
        causes.append("dynamic policy shadow runs show high candidate churn")
    if failure_tags:
        causes.append(f"worst trajectories repeatedly contain negative tag: {next(iter(failure_tags))}")
    return causes or ["no dominant root cause; keep conservative shadow review"]


def _weights(weak: str, strong: str, *, down: float, up: float) -> dict[str, float]:
    out = {}
    if weak and weak != "unknown":
        out[weak] = _round(max(0.1, 1.0 - down))
    if strong and strong != "unknown":
        out[strong] = _round(1.0 + up)
    return out


def _fuse_weights(raw: Any, alpha: float) -> dict[str, float]:
    weights = raw if isinstance(raw, dict) else {}
    return {str(k): _round(1.0 + (_float(v, 1.0) - 1.0) * alpha) for k, v in weights.items()}


def _policy_weight(policy: dict[str, Any], row: dict[str, Any]) -> float:
    weight = 1.0
    for field, key in (
        ("track", "track_weights"),
        ("signal_type", "signal_weight_adjustments"),
        ("regime", "regime_weight_adjustments"),
    ):
        weights = policy.get(key) if isinstance(policy.get(key), dict) else {}
        weight *= _float(weights.get(str(row.get(field) or "")), 1.0)
    return max(weight, 0.0)


def _validation_metrics(selected: list[dict[str, Any]], total: int, adjusted: list[float]) -> dict[str, Any]:
    returns = [_float(x.get("return_pct")) for x in selected]
    drawdowns = [abs(_float(x.get("max_drawdown_pct"))) for x in selected]
    n = len(selected)
    win_rate = sum(x > 0 for x in returns) / n if n else 0.0
    avg_return = mean(returns) if returns else 0.0
    avg_drawdown = mean(drawdowns) if drawdowns else 0.0
    selection_rate = n / total if total else 0.0
    score = (
        -999999.0
        if not selected
        else avg_return + win_rate * 2.0 - avg_drawdown * 0.35 - max(0.0, 0.2 - selection_rate) * 0.5
    )
    return {
        "selected_count": n,
        "total_count": total,
        "selection_rate": _round(selection_rate),
        "win_rate": _round(win_rate),
        "avg_return_pct": _round(avg_return),
        "avg_drawdown_pct": _round(avg_drawdown),
        "avg_adjusted_score": _round(mean(adjusted) if adjusted else 0.0),
        "validation_score": _round(score),
    }


def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda x: (str(x.get("trade_date") or ""), str(x.get("code") or "")))
