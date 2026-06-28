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
    assert evolution["optimizer"] == "gepa_inspired_prompt_evolution_v1"
    assert evolution["trace_bundle"]["format"] == "gepa_trace_bundle_v1"
    assert "Snapshot:" in evolution["trace_bundle"]["text"]
    assert len(evolution["generation_history"]) >= 1
    assert evolution["prompt_genomes"]
    assert evolution["pareto_frontier"]
    assert (
        evolution["validation"]["baseline"]["validation_score"]
        < evolution["fusion"]["validation_result"]["validation_score"]
    )
    assert candidate is not None
    assert candidate["status"] == "READY_FOR_REVIEW"
    assert candidate["candidate_policy"]["variant"].startswith("fused_")
    assert candidate["candidate_policy"]["auto_promote"] is False


def test_strategy_evolution_rejects_when_candidates_do_not_beat_baseline():
    from core.strategy_reflection import build_policy_candidate, build_strategy_reflection

    outcomes, observations = _synthetic_rows(edge=False)
    reflection = build_strategy_reflection(
        outcomes, [], observations=observations, market="cn", as_of_date="2026-06-12"
    )
    evolution = reflection["summary"]["evolution"]
    candidate = build_policy_candidate(reflection)

    assert evolution["status"] == "NO_BETTER_CANDIDATE"
    assert candidate is not None
    assert candidate["status"] == "REJECTED"
    assert candidate["candidate_policy"]["evolution_decision"] == "NO_BETTER_CANDIDATE"


def test_strategy_evolution_accepts_reflector_feedback_into_prompt_genomes():
    from core.strategy_evolution import StrategyEvolutionConfig, run_strategy_evolution

    outcomes, observations = _synthetic_rows()
    calls = []

    def reflector(request):
        calls.append(request)
        return {
            "reflector": "stub_llm_reflector",
            "root_causes": ["EVR failures came from weak confirmation traces"],
            "prompt_failures": ["Prompt over-trusted weak breakouts"],
            "suggested_edits": ["Require volume confirmation before trusting EVR breakouts."],
            "risk_notes": ["Keep baseline stop and drawdown controls."],
            "trace_summary": "Stub read the compact GEPA bundle.",
        }

    evolution = run_strategy_evolution(
        outcomes,
        [{"diff_added": ["000001"], "diff_removed": ["000002"]}],
        observations=observations,
        market="cn",
        as_of_date="2026-06-12",
        config=StrategyEvolutionConfig(max_generations=1),
        reflector_fn=reflector,
    )

    assert calls
    assert calls[0]["trace_bundle"]["format"] == "gepa_trace_bundle_v1"
    assert evolution["reflection_report"]["reflector"] == "stub_llm_reflector"
    assert any(
        "Require volume confirmation" in directive
        for directive in evolution["candidate_policies"][0]["prompt_directives"]
    )
    assert evolution["prompt_genomes"][0]["parent_ids"] == ["g0:baseline"]


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


def test_strategy_reflection_job_passes_optional_reflector(monkeypatch):
    import workflows.strategy_reflection_job as job

    outcomes, observations = _synthetic_rows(days=30)
    request = job.StrategyReflectionRequest(
        market="cn",
        as_of_date="2026-06-12",
        horizon_days=5,
        outcome_days=180,
        shadow_days=30,
        limit=100,
    )

    def reflector(_request):
        return {
            "reflector": "job_stub_reflector",
            "root_causes": ["Trace text shows weak confirmation"],
            "prompt_failures": [],
            "suggested_edits": ["Require stronger confirmation in weak regimes."],
            "risk_notes": [],
            "trace_summary": "Workflow adapter passed reflector.",
        }

    monkeypatch.setattr(job, "load_recent_signal_outcomes", lambda *_args: outcomes)
    monkeypatch.setattr(job, "load_recent_signal_observations", lambda *_args: observations)
    monkeypatch.setattr(job, "load_policy_shadow_runs", lambda *_args: [])
    monkeypatch.setattr(job, "strategy_evolution_reflector_from_env", lambda: reflector)

    reflection, _candidate = job.build_strategy_reflection_payloads(request)

    evolution = reflection["summary"]["evolution"]
    assert evolution["reflection_report"]["reflector"] == "job_stub_reflector"
