"""Create a consistent SQLite backup without overwriting an existing file."""

import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import ROOT, Settings


def backup(source: Path, destination: Path):
    source, destination = source.resolve(), destination.resolve()
    if not source.is_file():
        raise ValueError("数据库尚不存在")
    if source == destination or destination.exists():
        raise ValueError("备份目标必须是新文件")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation avoids clobbering an existing backup in a race.
    with destination.open("xb"):
        pass
    try:
        with (
            closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src,
            closing(sqlite3.connect(destination)) as dst,
        ):
            src.backup(dst)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="备份研迹数据库")
    parser.add_argument("destination", help="备份文件（相对仓库根目录或绝对路径）")
    args = parser.parse_args()
    target = Path(args.destination).expanduser()
    target = target if target.is_absolute() else ROOT / target
    backup(Settings().database_path, target)
    print(f"备份完成：{target.resolve()}")
