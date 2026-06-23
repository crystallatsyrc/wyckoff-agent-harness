#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify local Wyckoff Agent Harness chain.")
    parser.add_argument("--venv", default="work/wyckoff-venv", help="Path to the local venv.")
    parser.add_argument("--symbol", default="000001", help="A-share symbol to validate.")
    args = parser.parse_args()

    cwd = Path.cwd()
    venv = Path(args.venv)
    wyckoff = venv / "bin" / "wyckoff"
    python = venv / "bin" / "python"

    if not wyckoff.exists() or not python.exists():
        print(f"Missing Wyckoff runtime under {venv}", file=sys.stderr)
        return 1

    config_path = Path.home() / ".wyckoff" / "wyckoff.json"
    if not config_path.exists():
        print("Missing ~/.wyckoff/wyckoff.json", file=sys.stderr)
        return 1

    config = json.loads(config_path.read_text(encoding="utf-8"))
    model_ids = {m.get("id") for m in config.get("models", [])}
    if "kimi-code" not in model_ids:
        print("Missing kimi-code model config", file=sys.stderr)
        return 1
    if not config.get("tickflow_api_key"):
        print("Missing TickFlow API key in local config", file=sys.stderr)
        return 1

    env = os.environ.copy()
    env["TICKFLOW_API_KEY"] = str(config.get("tickflow_api_key", ""))
    env["TUSHARE_TOKEN"] = str(config.get("tushare_token", ""))

    probe = subprocess.run(
        [
            str(python),
            "-c",
            (
                "from integrations.data_source import fetch_stock_hist;"
                f"df=fetch_stock_hist('{args.symbol}','20260501','20260623');"
                "print('source=' + str(df.attrs.get('source','')));"
                "print('rows=' + str(len(df)))"
            ),
        ],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    print(probe.stdout.strip())
    if probe.returncode != 0:
        print(probe.stderr.strip(), file=sys.stderr)
        return probe.returncode

    report = run([str(wyckoff), "report", args.symbol], cwd=cwd)
    print(report.stdout.strip())
    if report.returncode != 0:
        print(report.stderr.strip(), file=sys.stderr)
        return report.returncode
    if "invalid temperature" in report.stdout:
        print("Kimi temperature compatibility error still present", file=sys.stderr)
        return 1

    print("verify_chain=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

