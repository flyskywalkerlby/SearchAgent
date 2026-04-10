# module_data_plans/check_rerun.py

import os
from typing import Dict, Any

import colorful as cf

from module_cache.cache_utils import (
    get_cache_file_of_final,
    get_target_file_of_final,
    get_step_output_file_of_final,
)
from module_cache.cache_io import remove_failed_artifacts


def _normalize_start_step(cfg: Dict[str, Any]) -> int | None:
    start_step = cfg.get("start_step")
    if isinstance(start_step, int) and start_step > 0:
        return start_step
    return None


def _processor_max_step_count(cfg: Dict[str, Any]) -> int:
    n = cfg.get("_processor_max_step_count")
    if isinstance(n, int) and n > 0:
        return n
    return 1


def _remove_if_exists(path: str) -> None:
    if not os.path.exists(path):
        return
    print(cf.yellow(f"🧹 删除文件: {path}"))
    try:
        os.remove(path)
    except Exception as e:
        print(cf.red(f"⚠️ 删除失败 {path} | {e}"))
        raise SystemExit(1)


def _step_files_from(base_final_file: str, start_step: int, processor_max_step_count: int) -> list[str]:
    return [
        get_step_output_file_of_final(base_final_file, step)
        for step in range(start_step, processor_max_step_count + 1)
    ]


def _step_cache_files_from(base_final_file: str, start_step: int, processor_max_step_count: int) -> list[str]:
    return [
        get_cache_file_of_final(get_step_output_file_of_final(base_final_file, step))
        for step in range(start_step, processor_max_step_count + 1)
    ]


def prepare_output_env(cfg: Dict[str, Any], groups: Dict[str, Any]) -> None:
    """
    基于 dataset_name -> groups，结合 cfg["rerun"] / cfg["resume"] + 当前文件情况，决定：
      - 删哪些 final/cache/out_dir
      - 要不要直接退出

    语义说明：
      - rerun=True  : 删除旧结果后重跑
      - resume=True : 保留旧结果，允许继续跑
      - rerun=False 且 resume=False:
            若检测到已有结果，则直接退出，避免覆盖/混用
      - rerun 和 resume 不能同时为 True

    注意：
      - 这里只负责“环境准备 / 保护性检查”
      - 真正的 resume 判定（cache 存在 / final 已完成）由 build_plans 负责
    """
    out_dir = cfg["output_dir"]
    num_datasets = len(groups)

    if num_datasets == 0:
        print(cf.red("❌ 没有任何数据集可处理（group_by_dataset 结果为空）"))
        raise SystemExit(1)

    rerun = bool(cfg.get("rerun", False))
    resume = bool(cfg.get("resume", False))
    start_step = _normalize_start_step(cfg)
    processor_max = _processor_max_step_count(cfg)

    if rerun and resume:
        print(cf.red("❌ rerun 和 resume 不能同时为 True"))
        raise SystemExit(1)

    # ========== single-file 模式：只有 1 个 dataset，会生成 1 个 final_file ==========
    if num_datasets == 1:
        ds_name = next(iter(groups.keys()))
        base_final_file = os.path.join(out_dir, f"{ds_name}.jsonl")
        final_file = get_target_file_of_final(base_final_file, cfg.get("max_step"), processor_max)
        cache_file = get_cache_file_of_final(final_file)
        step_files = _step_files_from(base_final_file, start_step or 1, processor_max)
        step_cache_files = _step_cache_files_from(base_final_file, start_step or 1, processor_max)

        os.makedirs(out_dir, exist_ok=True)

        if rerun:
            _remove_if_exists(cache_file)
            _remove_if_exists(final_file)
            for step_file in step_files:
                _remove_if_exists(step_file)
            try:
                remove_failed_artifacts(base_final_file)
            except Exception as e:
                print(cf.red(f"⚠️ 删除失败产物失败: {base_final_file} | {e}"))
                raise SystemExit(1)

        elif resume:
            print(cf.cyan("resume=True，保留已有输出，继续执行。"))
            if os.path.exists(final_file):
                print(cf.cyan(f"检测到已有 final_file：{final_file}"))
            if os.path.exists(cache_file):
                print(cf.cyan(f"检测到已有 cache_file：{cache_file}"))

        else:
            dirty_outputs = [f for f in [final_file, *step_files] if os.path.exists(f)]
            dirty_caches = [f for f in [cache_file, *step_cache_files] if os.path.exists(f)]
            if dirty_outputs or dirty_caches:
                print(cf.red("❌ rerun=False 且 resume=False 时，相关 output 和 cache 必须干净。"))
                if dirty_outputs:
                    print(cf.red(f"dirty_outputs: {dirty_outputs[:5]}"))
                if dirty_caches:
                    print(cf.red(f"dirty_caches: {dirty_caches[:5]}"))
                raise SystemExit(1)

    # ========== multi-file 模式：多个 dataset，共用一个 out_dir ==========
    else:
        if rerun:
            for ds_name in groups.keys():
                base_final_file = os.path.join(out_dir, f"{ds_name}.jsonl")
                final_file = get_target_file_of_final(base_final_file, cfg.get("max_step"), processor_max)
                cache_file = get_cache_file_of_final(final_file)
                _remove_if_exists(cache_file)
                _remove_if_exists(final_file)
                for step_file in _step_files_from(base_final_file, start_step or 1, processor_max):
                    _remove_if_exists(step_file)
                for step_cache_file in _step_cache_files_from(base_final_file, start_step or 1, processor_max):
                    _remove_if_exists(step_cache_file)
                try:
                    remove_failed_artifacts(base_final_file)
                except Exception as e:
                    print(cf.red(f"⚠️ 删除失败产物失败: {base_final_file} | {e}"))
                    raise SystemExit(1)

            os.makedirs(out_dir, exist_ok=True)

        elif resume:
            if os.path.exists(out_dir):
                print(cf.cyan(f"resume=True，检测到已有 out_dir：{out_dir}"))
                print(cf.cyan("保留目录内容，继续执行。"))
            else:
                os.makedirs(out_dir, exist_ok=True)
                print(cf.cyan(f"resume=True，但 out_dir 不存在，已创建：{out_dir}"))

        else:
            os.makedirs(out_dir, exist_ok=True)
            for ds_name in groups.keys():
                base_final_file = os.path.join(out_dir, f"{ds_name}.jsonl")
                final_file = get_target_file_of_final(base_final_file, cfg.get("max_step"), processor_max)
                cache_file = get_cache_file_of_final(final_file)
                step_files = _step_files_from(base_final_file, start_step or 1, processor_max)
                step_cache_files = _step_cache_files_from(base_final_file, start_step or 1, processor_max)
                dirty_outputs = [f for f in [final_file, *step_files] if os.path.exists(f)]
                dirty_caches = [f for f in [cache_file, *step_cache_files] if os.path.exists(f)]
                if dirty_outputs or dirty_caches:
                    print(cf.red("❌ rerun=False 且 resume=False 时，相关 output 和 cache 必须干净。"))
                    if dirty_outputs:
                        print(cf.red(f"dirty_outputs: {dirty_outputs[:5]}"))
                    if dirty_caches:
                        print(cf.red(f"dirty_caches: {dirty_caches[:5]}"))
                    raise SystemExit(1)
