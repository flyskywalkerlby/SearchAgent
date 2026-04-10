import os
import json
import re
import colorful as cf
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .cache_utils import get_base_final_file, get_step_output_file_of_final


def load_cached_ids(cache_file: str) -> set[int]:
    if not os.path.exists(cache_file):
        return set()

    ids = set()
    with open(cache_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ids.add(int(json.loads(line)["raw_id"]))
            except Exception:
                continue
    return ids


def load_record_map(jsonl_file: str) -> Dict[int, Dict[str, Any]]:
    if not os.path.exists(jsonl_file):
        return {}

    out: Dict[int, Dict[str, Any]] = {}
    with open(jsonl_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                raw_id = int(obj["raw_id"])
            except Exception:
                continue
            out[raw_id] = obj
    return out


STEP_NAME_RE = re.compile(r"^step(\d+)$")


def _step_order(step_name: str) -> int:
    m = STEP_NAME_RE.match(step_name or "")
    if not m:
        return 10**9
    return int(m.group(1))


def _trim_outputs(outputs: Dict[str, Any], step_name: str) -> Dict[str, Any]:
    max_step = _step_order(step_name)
    trimmed = {}
    for k, v in (outputs or {}).items():
        if _step_order(k) <= max_step:
            trimmed[k] = v
    return trimmed


def _write_jsonl(path: str, items: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


def _merge_records_by_raw_id(
    old_items: List[Dict[str, Any]],
    new_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    merged: Dict[int, Dict[str, Any]] = {}
    for item in old_items:
        try:
            merged[int(item["raw_id"])] = item
        except Exception:
            continue
    for item in new_items:
        try:
            merged[int(item["raw_id"])] = item
        except Exception:
            continue
    return sorted(merged.values(), key=lambda x: int(x["raw_id"]))


def write_step_outputs(items: List[Dict[str, Any]], final_file: str) -> None:
    base_final = get_base_final_file(final_file)
    step_names = sorted(
        {
            step_name
            for item in items
            for step_name in (item.get("written_steps") or [])
            if STEP_NAME_RE.match(step_name or "")
        },
        key=_step_order,
    )

    for step_name in step_names:
        step_items: List[Dict[str, Any]] = []
        for item in items:
            written_steps = set(item.get("written_steps") or [])
            if step_name not in written_steps:
                continue
            outputs = item.get("outputs") or {}
            if step_name not in outputs:
                continue
            rec = dict(item)
            rec["output"] = outputs[step_name]
            rec["outputs"] = _trim_outputs(outputs, step_name)
            step_items.append(rec)

        step_file = get_step_output_file_of_final(base_final, step_name)
        old_items = []
        if os.path.exists(step_file):
            old_items = list(load_record_map(step_file).values())
        merged_items = _merge_records_by_raw_id(old_items, step_items)
        _write_jsonl(step_file, merged_items)
        print(cf.green(f"✅ Step written: {os.path.abspath(step_file)} ({len(merged_items)})"))


def flush_cache_to_final(
    cache_file: str,
    final_file: str,
    *,
    write_final: bool = True,
    task_processor=None,
    processor_max_step_count: int | None = None,
) -> int:
    """
    将 cache 中间结果排序后写入 final。
    语义：
      - cache 存在：执行 flush，并在成功后删除 cache
      - cache 不存在：直接跳过（这可能表示该 dataset 已经是 final 完成态）
    """
    if not os.path.exists(cache_file):
        print(cf.cyan(f"ℹ️ cache 不存在，跳过 flush: {cache_file}"))
        return 0

    items = []
    with open(cache_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                continue

    items.sort(key=lambda x: int(x["raw_id"]))
    write_step_outputs(items, final_file)

    if write_final:
        if (
            task_processor is not None
            and isinstance(processor_max_step_count, int)
            and processor_max_step_count > 0
        ):
            last_step_file = get_step_output_file_of_final(final_file, processor_max_step_count)
            if os.path.exists(last_step_file):
                write_final_from_step_file(last_step_file, final_file, task_processor=task_processor)
            else:
                old_items = []
                if os.path.exists(final_file):
                    old_items = list(load_record_map(final_file).values())
                merged_items = _merge_records_by_raw_id(old_items, items)
                _write_jsonl(final_file, merged_items)
                print(cf.green(f"✅ Final written: {os.path.abspath(final_file)} ({len(merged_items)})"))
        else:
            old_items = []
            if os.path.exists(final_file):
                old_items = list(load_record_map(final_file).values())
            merged_items = _merge_records_by_raw_id(old_items, items)
            _write_jsonl(final_file, merged_items)
            print(cf.green(f"✅ Final written: {os.path.abspath(final_file)} ({len(merged_items)})"))
    else:
        print(cf.green(f"✅ Step outputs flushed without final: {os.path.abspath(final_file)}"))

    try:
        os.remove(cache_file)
        print(f"🧹 Cache removed: {cache_file}")
    except Exception as e:
        print(f"⚠️ 删除 cache 失败: {cache_file} | {e}")

    return len(items)


def write_final_from_step_file(step_file: str, final_file: str, task_processor=None) -> int:
    if not os.path.exists(step_file):
        print(cf.red(f"❌ step 文件不存在，无法补写 final: {step_file}"))
        return 0

    items = []
    with open(step_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            outputs = rec.get("outputs") or {}
            current_output = rec.get("output")
            if task_processor is not None and hasattr(task_processor, "rebuild_final_output_from_outputs"):
                rec["output"] = task_processor.rebuild_final_output_from_outputs(outputs, current_output)
            items.append(rec)

    items.sort(key=lambda x: int(x["raw_id"]))
    _write_jsonl(final_file, items)
    print(cf.green(f"✅ Final written from step file: {os.path.abspath(final_file)} ({len(items)})"))
    return len(items)


def get_failed_artifact_paths(final_file: str) -> Tuple[str, str]:
    p = Path(final_file)
    parts = list(p.parts)
    if "outputs" in parts:
        idx = parts.index("outputs")
        parts[idx] = "outputs_failed"
        failed_root = Path(*parts)
    elif "test_outputs" in parts:
        idx = parts.index("test_outputs")
        parts[idx] = "test_outputs_failed"
        failed_root = Path(*parts)
    else:
        failed_root = Path("outputs_failed") / p

    failed_jsonl = failed_root.with_suffix(".failed.jsonl")
    failed_summary = failed_root.with_suffix(".failed.summary.json")
    return str(failed_jsonl), str(failed_summary)


def remove_failed_artifacts(final_file: str) -> None:
    failed_jsonl, failed_summary = get_failed_artifact_paths(final_file)
    for path in (failed_jsonl, failed_summary):
        if os.path.exists(path):
            print(cf.yellow(f"🧹 rerun=True，删除失败文件: {path}"))
            os.remove(path)


def write_failed_artifacts(final_file: str, failed_cases: List[Dict[str, Any]]) -> None:
    failed_jsonl, failed_summary = get_failed_artifact_paths(final_file)

    if not failed_cases:
        for path in (failed_jsonl, failed_summary):
            if os.path.exists(path):
                os.remove(path)
        return

    os.makedirs(os.path.dirname(failed_jsonl), exist_ok=True)

    with open(failed_jsonl, "w", encoding="utf-8") as f:
        for item in failed_cases:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    reason_counter = Counter((item.get("reason") or "UNKNOWN") for item in failed_cases)
    dataset_counter = Counter((item.get("dataset_name") or "UNKNOWN") for item in failed_cases)

    summary = {
        "total_failed": len(failed_cases),
        "by_dataset": dict(sorted(dataset_counter.items())),
        "by_reason": dict(sorted(reason_counter.items(), key=lambda kv: (-kv[1], kv[0]))),
    }

    with open(failed_summary, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(cf.yellow(f"⚠️ Failed cases written: {os.path.abspath(failed_jsonl)} ({len(failed_cases)})"))
    print(cf.yellow(f"📊 Failed summary written: {os.path.abspath(failed_summary)}"))
