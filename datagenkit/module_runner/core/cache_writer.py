# module_runner/core/cache_writer.py

import json
import time
from asyncio import Lock
from typing import Any, Dict

import colorful as cf

from utils import format_time
async def append_record_to_cache(
    cache_file: str,
    rec: Dict[str, Any],
    stats: Dict[str, Any],
    lock: Lock,
) -> None:
    """
    只负责：
      - 把 rec 追加写入 cache_file
      - 更新 stats（new_done / 进度 / ETA 打印）
    """
    async with lock:
        with open(cache_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        stats["new_done"] += 1

        done_total = stats["cached_done"] + stats["new_done"]
        total = stats["total_target"]

        now = time.time()
        elapsed = now - stats["start_time"]

        avg_time = elapsed / stats["new_done"] if stats["new_done"] > 0 else 0
        remaining = total - done_total
        eta_seconds = avg_time * remaining

        if done_total % stats["log_every"] == 0 or done_total == total:
            percent = done_total / total * 100 if total > 0 else 0
            print(
                f"✅ 已处理 {done_total}/{total} "
                f"({percent:.2f}%) | "
                f"⏱ 已用时: {format_time(elapsed)} | "
                f"⏳ ETA: {format_time(eta_seconds)} | "
                f"cache: {stats['cached_done']} | "
                f"err: {stats['error']}"
            )
            
