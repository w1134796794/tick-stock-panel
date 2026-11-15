"""使用 stock-panel 本地数据回算原生情绪因子和历史龙头池。"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.integrations.a_stock_sentiment import (
    compute_native_factor_partitions,
    rebuild_native_leader_pool,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(settings.data_dir))
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    args = parser.parse_args()
    result = compute_native_factor_partitions(args.data_dir, start=args.start, end=args.end)
    for value in result.dates:
        rebuild_native_leader_pool(args.data_dir, date.fromisoformat(value))
    print(
        f"完成: dates={len(result.dates)} factors={result.factor_rows} context={result.context_rows}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
