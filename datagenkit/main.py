# main.py

import time
import asyncio
import colorful as cf

from module_clients import build_client, close_client

from config import parse_args, load_config_yaml, resolve_config

# input + plan
from module_data_plans.prepare_data_plans import get_data_and_plans

# cache
from module_cache.cache_io import flush_cache_to_final, write_failed_artifacts, write_final_from_step_file

# runner
from module_runner import FlowRunner

# BaseTaskProcessor
from module_task_processor import BaseTaskProcessor
from module_task_processor.task_processor import FlowTaskProcessor

# dynamic load
from utils import load_module_func, format_time


async def run_all(cfg: dict):
    """
    运行 pipeline：load → plan → runner → flush → summary
    """

    # ============================================================
    # 0) 动态加载 task_processor_module，并校验 max_step
    # ============================================================
    module_path = cfg["task_processor_module"]
    cls_name = cfg["task_processor_name"]

    if module_path is not None:
        task_processor_cls = load_module_func(module_path, cls_name)
    else:
        print(cf.green("使用默认 BaseTaskProcessor"))
        task_processor_cls = BaseTaskProcessor

    task_processor = task_processor_cls(cfg)
    if isinstance(task_processor, FlowTaskProcessor):
        processor_max_step_count = task_processor.get_max_step_count()
        cfg["_processor_max_step_count"] = processor_max_step_count
        max_step = cfg.get("max_step")
        if (
            isinstance(max_step, int)
            and max_step > 0
            and isinstance(processor_max_step_count, int)
            and processor_max_step_count > 0
            and max_step > processor_max_step_count
        ):
            raise SystemExit(
                f"❌ max_step={max_step} 超过 processor 最大 step={processor_max_step_count}"
            )
    else:
        cfg["_processor_max_step_count"] = 1

    # ============================================================
    # 1) 加载数据 + build plans
    # ============================================================
    data, plans = get_data_and_plans(cfg)

    total_target = sum(len(p["target_list"]) for p in plans)
    cached_done_global = sum(p["cached_done"] for p in plans)
    to_run_global = sum(len(p["to_run"]) for p in plans)

    print("=" * 100)
    print("🚀 任务启动")
    print(f"output_dir       : {cfg['output_dir']}")
    print(f"datasets         : {len(plans)}")
    print(f"total_target     : {total_target}")
    print(f"cached_done      : {cached_done_global}")
    print(f"to_run           : {to_run_global}")
    print("-" * 100)
    for p in plans:
        print(
            f"[{p['dataset_name']}]  "
            f"status={p['status']}  "
            f"target={len(p['target_list'])}  "
            f"cached={p['cached_done']}  "
            f"to_run={len(p['to_run'])}"
        )
        print(f"    final: {p['final_file']}")
        print(f"    cache: {p['cache_file']}")
    print("=" * 100)

    # ============================================================
    # 2) 如果没有要跑的，直接检查并 flush cache → final
    # ============================================================
    if to_run_global == 0:
        print("⚡ 没有需要新跑的条目，开始检查并 flush cache → final ...")
        for p in plans:
            if p.get("status") == "flush_from_last_step" and p.get("finalize_from_step_file"):
                write_final_from_step_file(
                    p["finalize_from_step_file"],
                    p["final_file"],
                    task_processor=task_processor if isinstance(task_processor, FlowTaskProcessor) else None,
                )
            elif p.get("status") in {"done_final", "done_step"}:
                continue
            else:
                flush_cache_to_final(
                    p["cache_file"],
                    p["final_file"],
                    write_final=bool(p.get("should_write_final")),
                    task_processor=task_processor if isinstance(task_processor, FlowTaskProcessor) else None,
                    processor_max_step_count=cfg.get("_processor_max_step_count"),
                )
        print("🎉 完成")
        return

    _prompt_template = task_processor.load_prompt(cfg)

    # ============================================================
    # 4) stats（Runner 内部会更新）
    # ============================================================
    stats = {
        "total_target": total_target,
        "cached_done": cached_done_global,
        "new_done": 0,
        "error": 0,
        "failed_cases": [],
        "start_time": time.time(),
        "log_every": cfg.get("log_every", 10),
        "retry_total": 0,
    }

    # ============================================================
    # 5) 初始化 Runner
    # ============================================================
    runner_type = cfg.get("runner_type", "flow")
    if runner_type not in {None, "flow"}:
        raise ValueError(f"当前仅支持 runner_type=flow，实际收到: {runner_type}")

    runner = FlowRunner(
        cfg=cfg,
        stats=stats,
        task_processor=task_processor,
    )

    # ============================================================
    # 6) 并发执行任务
    # ============================================================
    client = await build_client(cfg)
    try:
        tasks = []
        for p in plans:
            for d in p["to_run"]:
                tasks.append(
                    runner.send_one_with_retry(
                        client=client,
                        data=d,
                        cache_file=p["cache_file"],
                        final_file=p["final_file"],
                        max_retry=cfg.get("max_retry", 5),
                    )
                )
        await asyncio.gather(*tasks)
    finally:
        await close_client(client)

    # ============================================================
    # 7) flush cache → final
    # ============================================================
    print("\n📌 Flush cache → final ...")
    for p in plans:
        if p.get("status") == "flush_from_last_step" and p.get("finalize_from_step_file"):
            write_final_from_step_file(
                p["finalize_from_step_file"],
                p["final_file"],
                task_processor=task_processor if isinstance(task_processor, FlowTaskProcessor) else None,
            )
        elif p.get("status") in {"done_final", "done_step"}:
            pass
        else:
            flush_cache_to_final(
                p["cache_file"],
                p["final_file"],
                write_final=bool(p.get("should_write_final")),
                task_processor=task_processor if isinstance(task_processor, FlowTaskProcessor) else None,
                processor_max_step_count=cfg.get("_processor_max_step_count"),
            )
        plan_failed_cases = [
            c for c in stats["failed_cases"]
            if c.get("final_file") == p["final_file"]
        ]
        write_failed_artifacts(p["final_file"], plan_failed_cases)

    # ============================================================
    # 8) summary
    # ============================================================
    elapsed = time.time() - stats["start_time"]
    done_total = stats["cached_done"] + stats["new_done"]
    percent = done_total / stats["total_target"] * 100 if stats["total_target"] > 0 else 0

    print(
        f"\n🏁 完成 | done={done_total}/{stats['total_target']} ({percent:.2f}%) | "
        f"new={stats['new_done']} | cache={stats['cached_done']} | "
        f"err={stats['error']} | elapsed={format_time(elapsed)}"
    )

    avg_retry = stats["retry_total"] / stats["total_target"] if stats["total_target"] > 0 else 0.0
    print(f"🔁 重试统计 | retries={stats['retry_total']} | 重试率={avg_retry * 100:.2f}%")

    if stats["failed_cases"]:
        print(f"\n⚠️ failed_cases = {len(stats['failed_cases'])}")
        for c in stats["failed_cases"][:5]:
            print("  -", c)


def main():
    args = parse_args()
    cfg_yaml = load_config_yaml(args.config) if args.config else None
    cfg = resolve_config(args, cfg_yaml)

    asyncio.run(run_all(cfg))


if __name__ == "__main__":
    main()
