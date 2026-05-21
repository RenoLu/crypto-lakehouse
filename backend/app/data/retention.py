"""Data retention manager - cleans old data when storage approaches limits."""

import shutil
from pathlib import Path

from app.core.config import settings
from app.core.logging import logger


def get_dir_size(path: Path) -> int:
    total = 0
    if path.exists():
        for p in path.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
    return total


def get_dir_size_mb(path: Path) -> float:
    return get_dir_size(path) / (1024 * 1024)


def cleanup_old_data(max_size_mb: float = 400.0) -> dict:
    root = settings.lakehouse_path
    current_size = get_dir_size_mb(root)

    logger.info(f"Data size: {current_size:.1f} MB / {max_size_mb:.0f} MB limit")

    if current_size < max_size_mb:
        return {"cleaned": False, "size_before_mb": current_size, "size_after_mb": current_size, "reason": "under limit"}

    logger.warning(f"Storage at {current_size:.1f} MB, cleaning up old data...")

    cleaned = 0
    for layer_dir in [root / "bronze", root / "silver"]:
        if not layer_dir.exists():
            continue
        for date_dir in sorted(layer_dir.rglob("date=*")):
            try:
                dir_size = get_dir_size_mb(date_dir)
                shutil.rmtree(date_dir)
                cleaned += dir_size
                logger.info(f"  Removed {date_dir.relative_to(root)} ({dir_size:.1f} MB)")
            except Exception as e:
                logger.warning(f"  Failed to remove {date_dir}: {e}")

    for gold_file in sorted((root / "gold").rglob("*.parquet")):
        try:
            file_size = gold_file.stat().st_size / (1024 * 1024)
            gold_file.unlink()
            cleaned += file_size
        except Exception as e:
            logger.warning(f"  Failed to remove {gold_file}: {e}")

    duckdb_path = settings.duckdb_db_path
    if duckdb_path.exists():
        db_size = duckdb_path.stat().st_size / (1024 * 1024)
        duckdb_path.unlink()
        cleaned += db_size
        logger.info(f"  Removed DuckDB ({db_size:.1f} MB)")

    new_size = get_dir_size_mb(root)
    logger.info(f"Cleanup complete: freed {cleaned:.1f} MB, now {new_size:.1f} MB")

    return {
        "cleaned": True,
        "size_before_mb": current_size,
        "size_after_mb": new_size,
        "freed_mb": round(cleaned, 1),
    }
