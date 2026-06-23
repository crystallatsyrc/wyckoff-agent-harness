# Wyckoff Agent Harness

Local Harness Engineering practice for a financial research agent built around Wyckoff-style price-volume analysis.

## What This Project Is

This repository documents and reproduces a local financial Agent Harness that turns an open-source Wyckoff analysis agent into a runnable research workflow. The focus is not the model alone, but the harness around it:

- model routing and provider configuration
- market data source adaptation and fallback behavior
- structured context construction for financial analysis
- tool execution through CLI and dashboard entry points
- runtime error recovery and source-level compatibility fixes
- validation through repeatable local smoke tests

## Harness Architecture

```text
User task
  -> CLI / Dashboard
  -> Runtime config
  -> Model router
  -> Context builder
  -> Market data adapter
  -> Tool execution
  -> LLM report generation
  -> Logs / validation output
```

## Implemented Integration

| Layer | Implementation |
| --- | --- |
| Model backend | Kimi Code Coding Plan via OpenAI-compatible API |
| Model id | `kimi-for-coding` |
| Context window | 262K configured in local model registry |
| Market data | TickFlow as primary A-share data source |
| Fallback understanding | AkShare / Baostock fallback path inspected and verified |
| User surfaces | Wyckoff CLI and local Dashboard |
| Validation target | `wyckoff report 000001` |

## Key Engineering Fix

The original OpenAI-compatible LLM call path sent `temperature=0.4`. Kimi Code's coding endpoint rejects this value and only accepts `temperature=1` for `kimi-for-coding`.

This project includes a patch that adapts the LLM client:

```python
temperature = 1 if "api.kimi.com/coding" in base_url or model == "kimi-for-coding" else 0.4
```

After applying the fix, the report generation chain successfully used:

```text
Trend:openai:kimi-for-coding
```

## Repository Contents

```text
docs/runbook.md                       Local setup and operating guide
patches/kimi-code-temperature.patch   Compatibility patch for Kimi Code
scripts/bootstrap_wyckoff.sh          Reproducible local bootstrap helper
scripts/verify_chain.py               Local validation script
```

## Security Notes

Do not commit API keys. Local credentials should stay in:

```text
~/.wyckoff/wyckoff.json
```

This repository intentionally excludes virtual environments, logs, credentials, and generated data.

## Resume Framing

This project should be framed as a Harness Engineering project:

> Built a local financial Agent Harness around WyckoffAgent, integrating model routing, TickFlow data access, structured financial context generation, CLI/Dashboard execution, runtime validation, and provider-specific error recovery.

