# Runbook

This runbook assumes the WyckoffAgent package is installed in a local Python 3.11 virtual environment.

## 1. Create Runtime

```bash
python3.11 -m venv work/wyckoff-venv
work/wyckoff-venv/bin/python -m pip install --upgrade pip
work/wyckoff-venv/bin/python -m pip install youngcan-wyckoff-analysis
```

## 2. Configure Model

Use Kimi Code Coding Plan as an OpenAI-compatible model provider.

```bash
work/wyckoff-venv/bin/wyckoff model set kimi-code openai "$KIMI_CODE_API_KEY" \
  --model kimi-for-coding \
  --base-url https://api.kimi.com/coding/v1

work/wyckoff-venv/bin/wyckoff model default kimi-code
work/wyckoff-venv/bin/wyckoff model cost kimi-code --context-window 262144
```

Never commit the API key. Prefer setting it temporarily in your shell:

```bash
export KIMI_CODE_API_KEY="..."
```

## 3. Configure Market Data

```bash
work/wyckoff-venv/bin/wyckoff config tickflow
```

The command stores the key in local Wyckoff config. Do not commit that config file.

## 4. Apply Kimi Compatibility Patch

If the package still sends `temperature=0.4`, apply the patch in `patches/kimi-code-temperature.patch` or update the local LLM client manually.

## 5. Validate Chain

```bash
python scripts/verify_chain.py \
  --venv work/wyckoff-venv \
  --symbol 000001
```

Expected high-level checks:

- model registry contains `kimi-code`
- TickFlow config exists
- data fetch returns rows with `source=tickflow`
- `wyckoff report 000001` finishes without the Kimi temperature error

## 6. Run Dashboard

```bash
work/wyckoff-venv/bin/wyckoff dashboard --port 8765
```

Open:

```text
http://127.0.0.1:8765
```

## 7. Run Report

```bash
work/wyckoff-venv/bin/wyckoff report 000001
```

Successful output should include a line similar to:

```text
[step3] 研报实际使用模型=Trend:openai:kimi-for-coding
```

