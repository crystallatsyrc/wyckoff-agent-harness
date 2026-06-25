"""CLI entrypoint for database maintenance."""

from __future__ import annotations

import argparse

import _bootstrap  # noqa: F401

from workflows.db_maintenance import DbMaintenanceRequest, run_db_maintenance


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="数据库维护 — 多表过期数据清理")
    parser.add_argument("--dry-run", action="store_true", help="只查询待清理行数，不实际删除")
    parser.add_argument(
        "--skip-if-unconfigured",
        action="store_true",
        help="exit successfully when Supabase admin credentials are not configured",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run_db_maintenance(
        DbMaintenanceRequest(dry_run=args.dry_run, skip_if_unconfigured=args.skip_if_unconfigured)
    )


if __name__ == "__main__":
    raise SystemExit(main())
