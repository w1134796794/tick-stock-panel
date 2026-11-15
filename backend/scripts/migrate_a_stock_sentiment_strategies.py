"""根据 stock-panel 内置配置生成并验证 13 个情绪策略。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.integrations.a_stock_sentiment_strategies import (
    migrate_strategies,
    render_strategy_report,
    verify_latest_candidates,
    write_json_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    local_config = Path(__file__).resolve().parents[1] / "app" / "integrations" / "a_stock_sentiment" / "config"
    parser.add_argument(
        "--combinations",
        type=Path,
        default=local_config / "strategy_combinations.yaml",
    )
    parser.add_argument(
        "--profiles",
        type=Path,
        default=local_config / "strategy_profiles.yaml",
    )
    parser.add_argument("--data-dir", type=Path, default=Path(settings.data_dir))
    parser.add_argument("--trade-date", help="验证所用交易日 YYYYMMDD；省略则不执行候选验证")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    migrations = migrate_strategies(
        args.combinations,
        args.profiles,
        args.data_dir,
    )
    counts = (
        verify_latest_candidates(args.data_dir, migrations, args.trade_date)
        if args.trade_date else {}
    )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(render_strategy_report(migrations, counts), encoding="utf-8")
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        write_json_manifest(args.manifest, migrations)
    print(f"完成: strategies={len(migrations)} verified={len(counts)}")
    for source_id, count in counts.items():
        print(f"{source_id}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
