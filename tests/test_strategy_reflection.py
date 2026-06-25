from __future__ import annotations

from datetime import date, timedelta


def _synthetic_rows(*, days: int = 80, edge: bool = True) -> tuple[list[dict], list[dict]]:
    outcomes: list[dict] = []
    observations: list[dict] = []
    start = date(2026, 1, 1)
    for i in range(days):
        is_strong = i % 2 == 1
        signal_type = "spring" if is_strong else "sos"
        track = "Accum" if is_strong else "Trend"
        score = 78.0 if is_strong else 28.0
        return_pct = 2.2 if is_strong and edge else 0.8
        if not is_strong and edge:
            return_pct = -1.4
        drawdown = (0.6 if is_strong else 3.2) if edge else 1.0
        trade_date = (start + timedelta(days=i)).isoformat()
        observation_id = i + 1
        observations.append(
            {
                "id": observation_id,
                "market": "cn",
                "trade_date": trade_date,
                "code": f"{i + 1:06d}",
                "signal_type": signal_type,
                "track": track,
                "regime": "RISK_ON",
                "features_json": {
                    "candidate_shadow_score": {"score": score, "grade": "A" if is_strong else "D"},
                    "price_action_footprint": {
                        "tags": ["reclaim"] if is_strong else [],
                        "negative_tags": [] if is_strong else ["failed_breakout"],
                    },
                },
            }
        )
        outcomes.append(
            {
                "observation_id": observation_id,
                "market": "cn",
                "trade_date": trade_date,
                "code": f"{i + 1:06d}",
                "signal_type": signal_type,
                "track": track,
                "regime": "RISK_ON",
                "horizon_days": 5,
                "status": "done",
                "return_pct": return_pct,
                "max_drawdown_pct": drawdown,
            }
        )
    return outcomes, observations


def test_build_strategy_reflection_and_candidate():
    from core.strategy_reflection import build_policy_candidate, build_strategy_reflection

    outcomes = [
        {"track": "Trend", "regime": "RISK_ON", "horizon_days": 5, "status": "done", "return_pct": 0.5},
        {"track": "Accum", "regime": "RISK_ON", "horizon_days": 5, "status": "done", "return_pct": 3.0},
        {"track": "Accum", "regime": "RISK_ON", "horizon_days": 5, "status": "done", "return_pct": -1.0},
    ]
    shadow_runs = [{"diff_added": ["000001"], "diff_removed": ["000002", "000003"]}]

    reflection = build_strategy_reflection(outcomes, shadow_runs, market="cn", as_of_date="2026-06-12")
    candidate = build_policy_candidate(reflection)

    assert reflection["status"] == "SHADOW"
    assert reflection["summary"]["preferred_track"] == "Accum"
    assert reflection["summary"]["shadow"]["avg_removed"] == 2.0
    assert candidate is not None
    assert candidate["status"] == "READY_FOR_REVIEW"
    assert candidate["candidate_policy"]["auto_promote"] is False


def test_strategy_evolution_confirms_fused_policy_on_synthetic_edge():
    from core.strategy_reflection import build_policy_candidate, build_strategy_reflection

    outcomes, observations = _synthetic_rows()
    reflection = build_strategy_reflection(
        outcomes,
        [{"diff_added": ["000001", "000002"], "diff_removed": ["000003"]}],
        observations=observations,
        market="cn",
        as_of_date="2026-06-12",
    )
    evolution = reflection["summary"]["evolution"]
    candidate = build_policy_candidate(reflection)

    assert evolution["status"] == "CONFIRMED"
    assert len(evolution["trajectory_samples"]["worst"]) == 10
    assert len(evolution["trajectory_samples"]["best"]) == 10
    assert len(evolution["trajectory_samples"]["recent"]) == 20
    assert [row["variant"] for row in evolution["candidate_policies"]] == [
        "conservative",
        "balanced",
        "aggressive",
    ]
    assert evolution["validation"]["baseline"]["validation_score"] < evolution["fusion"]["validation_result"][
        "validation_score"
    ]
    assert candidate is not None
    assert candidate["status"] == "READY_FOR_REVIEW"
    assert candidate["candidate_policy"]["variant"].startswith("fused_")
    assert candidate["candidate_policy"]["auto_promote"] is False


def test_strategy_evolution_rejects_when_candidates_do_not_beat_baseline():
    from core.strategy_reflection import build_policy_candidate, build_strategy_reflection

    outcomes, observations = _synthetic_rows(edge=False)
    reflection = build_strategy_reflection(outcomes, [], observations=observations, market="cn", as_of_date="2026-06-12")
    evolution = reflection["summary"]["evolution"]
    candidate = build_policy_candidate(reflection)

    assert evolution["status"] == "NO_BETTER_CANDIDATE"
    assert candidate is not None
    assert candidate["status"] == "REJECTED"
    assert candidate["candidate_policy"]["evolution_decision"] == "NO_BETTER_CANDIDATE"


def test_strategy_reflection_job_dry_run_payload(monkeypatch):
    import workflows.strategy_reflection_job as job

    request = job.StrategyReflectionRequest(
        market="cn",
        as_of_date="2026-06-12",
        horizon_days=5,
        outcome_days=180,
        shadow_days=30,
        limit=100,
    )
    monkeypatch.setattr(
        job,
        "load_recent_signal_outcomes",
        lambda *_args: [{"track": "Trend", "regime": "ALL", "horizon_days": 5, "status": "done", "return_pct": 2}],
    )
    monkeypatch.setattr(job, "load_recent_signal_observations", lambda *_args: [])
    monkeypatch.setattr(job, "load_policy_shadow_runs", lambda *_args: [{"diff_added": [], "diff_removed": []}])

    reflection, candidate = job.build_strategy_reflection_payloads(request)

    assert reflection["as_of_date"] == "2026-06-12"
    assert reflection["summary"]["preferred_track"] == "Trend"
    assert candidate is not None
    assert candidate["status"] == "READY_FOR_REVIEW"
