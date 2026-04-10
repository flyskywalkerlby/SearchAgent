# module_data_plans/prepare_data_plans.py

import os
from collections import OrderedDict
from typing import Tuple, Dict, List, Any

import colorful as cf

from .check_rerun import prepare_output_env

from module_input_loaders import load_input_data

from module_cache.cache_utils import get_cache_file_of_final
from module_cache.cache_io import load_record_map
from module_cache.cache_utils import get_step_output_file_of_final, get_target_file_of_final


def group_by_dataset(data_list: List[Dict[str, Any]]) -> "OrderedDict[str, List[Dict[str, Any]]]":
    """
    按 dataset_name 分组：
    {
      "coco": [sample1, sample2, ...],
      "flickr30k": [...],
      ...
    }
    """
    groups: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
    for d in data_list:
        ds = d.get("dataset_name") or "UNKNOWN"
        if ds not in groups:
            groups[ds] = []
        groups[ds].append(d)
    return groups


def _normalize_start_step(cfg: Dict[str, Any]) -> int | None:
    start_step = cfg.get("start_step")
    if isinstance(start_step, int) and start_step > 0:
        return start_step
    return None


def _get_target_upper_step(cfg: Dict[str, Any]) -> int | None:
    max_step = cfg.get("max_step")
    if isinstance(max_step, int) and max_step > 0:
        return max_step
    processor_max = cfg.get("_processor_max_step_count")
    if isinstance(processor_max, int) and processor_max > 0:
        return processor_max
    return None


def _get_record_step_progress(rec: Dict[str, Any]) -> int:
    outputs = (rec or {}).get("outputs") or {}
    max_step = 0
    for key in outputs.keys():
        if isinstance(key, str) and key.startswith("step") and key[4:].isdigit():
            max_step = max(max_step, int(key[4:]))
    return max_step


def _step_file_complete(step_file: str, items: List[Dict[str, Any]]) -> bool:
    if not os.path.exists(step_file):
        return False
    rec_map = load_record_map(step_file)
    target_raw_ids = {int(d["raw_id"]) for d in items}
    return target_raw_ids.issubset(set(rec_map.keys()))


def _find_latest_complete_step(base_final_file: str, upper_step: int, items: List[Dict[str, Any]]) -> int:
    for step in range(upper_step, 0, -1):
        step_file = get_step_output_file_of_final(base_final_file, step)
        if _step_file_complete(step_file, items):
            return step
    return 0


def _collect_latest_formal_records(
    base_final_file: str,
    upper_step: int,
    target_raw_ids: set[int],
    min_step: int = 1,
) -> Dict[int, Dict[str, Any]]:
    latest: Dict[int, Dict[str, Any]] = {}
    for step in range(upper_step, min_step - 1, -1):
        step_file = get_step_output_file_of_final(base_final_file, step)
        if not os.path.exists(step_file):
            continue
        rec_map = load_record_map(step_file)
        for raw_id, rec in rec_map.items():
            if raw_id not in target_raw_ids or raw_id in latest:
                continue
            latest[raw_id] = {
                "step": step,
                "record": rec,
                "source_file": step_file,
            }
    return latest


def build_plans(cfg: Dict[str, Any], data_all: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    统一生成 dataset plans:
    [
      {
        "dataset_name": ds_name,
        "final_file": ...,
        "cache_file": ...,
        "target_list": [...],    # 该 ds 的所有样本
        "cached_done": int,      # 已完成数量（可能来自 cache，也可能来自 final 已完成态）
        "to_run": [...],         # 这次真正要跑的样本
        "status": "fresh" | "resume_from_cache" | "done_final",
      },
      ...
    ]

    状态语义：
      - cache_file 存在：
          说明该 ds 处于运行态 / 中断恢复态，按 cache resume
      - final_file 存在 且 cache_file 不存在：
          说明该 ds 已完整完成（之前 flush 过），本次直接跳过
      - final/cache 都不存在：
          说明该 ds 是全新任务
    """
    out_dir = cfg["output_dir"]
    groups = group_by_dataset(data_all)

    select = cfg.get("select_datasets") or []
    if select:
        before = list(groups.keys())
        groups = OrderedDict(
            (ds, group)
            for ds, group in groups.items()
            if any(key in ds for key in select)
        )
        after = list(groups.keys())
        print(cf.green(
            f"keys before : {before}\n"
            f"keys after  : {after}\n"
        ))

    ignore = cfg.get("ignore_datasets") or []
    if ignore:
        before = list(groups.keys())
        groups = OrderedDict(
            (ds, group)
            for ds, group in groups.items()
            if not any(key in ds for key in ignore)
        )
        after = list(groups.keys())
        print(cf.green(
            f"ignore keys : {ignore}\n"
            f"keys before : {before}\n"
            f"keys after  : {after}\n"
        ))

    plans: List[Dict[str, Any]] = []

    for ds_name, items in groups.items():
        base_final_file = os.path.join(out_dir, f"{ds_name}.jsonl")
        final_file = get_target_file_of_final(
            base_final_file,
            cfg.get("max_step"),
            cfg.get("_processor_max_step_count"),
        )
        cache_file = get_cache_file_of_final(final_file)

        explicit_start_step = _normalize_start_step(cfg)
        target_upper_step = _get_target_upper_step(cfg) or 1
        processor_max_step = cfg.get("_processor_max_step_count") or 1
        should_write_final = target_upper_step >= processor_max_step

        effective_start_step = explicit_start_step or 1
        latest_complete_step = 0
        finalize_from_step_file = None
        prev_step_file = None

        final_exists = os.path.exists(final_file)
        cache_exists = os.path.exists(cache_file)
        cache_map = load_record_map(cache_file) if cache_exists else {}

        target_raw_ids = {int(d["raw_id"]) for d in items}
        cache_done_ids = {
            raw_id
            for raw_id, rec in cache_map.items()
            if raw_id in target_raw_ids and _get_record_step_progress(rec) >= target_upper_step
        }

        if explicit_start_step is None and cfg.get("resume"):
            if should_write_final and final_exists:
                cached_done = len(items)
                to_run = []
                status = "done_final"
            else:
                latest_complete_step = _find_latest_complete_step(base_final_file, target_upper_step, items)
                if latest_complete_step >= target_upper_step:
                    cached_done = len(items)
                    to_run = []
                    if should_write_final:
                        finalize_from_step_file = get_step_output_file_of_final(base_final_file, target_upper_step)
                        status = "flush_from_last_step"
                    else:
                        status = "done_step"
                else:
                    effective_start_step = latest_complete_step + 1 if latest_complete_step > 0 else 1
                    if cache_done_ids:
                        cached_done = len(cache_done_ids)
                        to_run = [d for d in items if int(d["raw_id"]) not in cache_done_ids]
                        status = "resume_from_cache"
                    else:
                        cached_done = 0
                        to_run = items
                        status = "fresh"
        else:
            if explicit_start_step is None and final_exists:
                cached_done = len(items)
                to_run = []
                status = "done_final"
            elif explicit_start_step is None and cache_done_ids:
                cached_done = len(cache_done_ids)
                to_run = [d for d in items if int(d["raw_id"]) not in cache_done_ids]
                status = "resume_from_cache"
            elif explicit_start_step is None:
                cached_done = 0
                to_run = items
                status = "fresh"
            else:
                if cache_done_ids:
                    cached_done = len(cache_done_ids)
                    to_run = [d for d in items if int(d["raw_id"]) not in cache_done_ids]
                    status = "resume_from_cache"
                else:
                    cached_done = 0
                    to_run = items
                    status = "fresh"

        if effective_start_step > 1:
            prev_step_file = get_step_output_file_of_final(base_final_file, effective_start_step - 1)

        plans.append({
            "dataset_name": ds_name,
            "base_final_file": base_final_file,
            "final_file": final_file,
            "cache_file": cache_file,
            "target_upper_step": target_upper_step,
            "processor_max_step": processor_max_step,
            "should_write_final": should_write_final,
            "explicit_start_step": explicit_start_step,
            "effective_start_step": effective_start_step,
            "finalize_from_step_file": finalize_from_step_file,
            "prev_step_file": prev_step_file,
            "target_list": items,
            "cached_done": cached_done,
            "to_run": to_run,
            "status": status,
        })

    return plans


def get_data_and_plans(cfg: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    高层封装：
      1. 调用 load_input_data 读入所有样本
      2. 基于当前数据做 env 清理
      3. 基于当前 cache / final 状态构造 plans

    返回 (data, plans)
    """
    data = load_input_data(cfg)

    if not data:
        print(cf.red("❌ 未加载到有效数据"))
        raise SystemExit("❌ 未加载到有效数据")

    groups = group_by_dataset(data)

    # 先清理/检查环境，再构 plans，避免基于应当被删除的 cache 设计 plans
    prepare_output_env(cfg, groups)

    plans = build_plans(cfg, data)

    plan_by_ds = {p["dataset_name"]: p for p in plans}
    groups = OrderedDict(
        (ds_name, groups[ds_name])
        for ds_name in groups.keys()
        if ds_name in plan_by_ds
    )

    for ds_name, items in groups.items():
        plan = plan_by_ds[ds_name]
        start_step = plan.get("effective_start_step", 1) or 1
        target_upper_step = plan.get("target_upper_step", 1) or 1
        to_run_ids = {int(d["raw_id"]) for d in plan.get("to_run", [])}
        if not to_run_ids:
            continue

        min_step = max(1, start_step - 1)
        formal_records = _collect_latest_formal_records(
            plan["base_final_file"],
            max(target_upper_step - 1, min_step),
            to_run_ids,
            min_step=min_step,
        )
        cache_records = {}
        if cfg.get("resume") and os.path.exists(plan["cache_file"]):
            cache_records = load_record_map(plan["cache_file"])

        missing = []
        for d in items:
            raw_id = int(d["raw_id"])
            if raw_id not in to_run_ids:
                continue

            best_record = None
            best_step = 0
            best_source = None

            formal_info = formal_records.get(raw_id)
            if formal_info is not None:
                best_record = formal_info["record"]
                best_step = formal_info["step"]
                best_source = formal_info["source_file"]

            cache_rec = cache_records.get(raw_id)
            if cache_rec is not None:
                cache_step = _get_record_step_progress(cache_rec)
                if min_step <= cache_step < target_upper_step and cache_step >= best_step:
                    best_record = cache_rec
                    best_step = cache_step
                    best_source = plan["cache_file"]

            if start_step > 1 and best_step < start_step - 1:
                missing.append(raw_id)
                continue

            if best_record is not None:
                d["__prev_outputs"] = best_record.get("outputs", {})
                d["__prev_output"] = best_record.get("output")
                d["__prev_source_file"] = best_source

        if missing:
            prev_step_file = plan.get("prev_step_file")
            raise SystemExit(
                f"❌ 依赖 step 文件缺少样本结果: {prev_step_file} | missing_raw_ids={missing[:10]}"
            )

    return data, plans
