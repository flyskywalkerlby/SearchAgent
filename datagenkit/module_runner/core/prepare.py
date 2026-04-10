# module_runner/core/prepare.py

import os
from typing import Any, Dict, Tuple
from collections.abc import Callable
import colorful as cf

from utils import image_to_base64
from module_task_processor import BaseTaskProcessor


def may_forget_check(base_prompt):
    
    # 定义可能会忘记替换的占位符列表
    forget_list = [
        "{{EXTRA_INFO_BLOCK}}",
    ]
    
    for placeholder in forget_list:
        if placeholder in base_prompt:
            print(cf.yellow(f"[WARN] prompt 中存在 {placeholder}，已替换为空字符串"))
            base_prompt = base_prompt.replace(placeholder, "")
            
    if "{{" in base_prompt and "}}" in base_prompt:
        print(cf.yellow("[WARN] prompt 仍存在 {{...}}，可能需要检查"))

    return base_prompt


def _prepare_common(
    cfg: Dict[str, Any],
    data: Dict[str, Any],
) -> Tuple[bool, str | None, Dict[str, Any] | None]:
    img_path = os.path.join(data["root"], data["image"])
    if not os.path.exists(img_path):
        return False, (
            f"图片不存在: ds={data.get('dataset_name')} "
            f"raw_id={data.get('raw_id')} path={img_path}"
        ), None

    try:
        img_b64 = image_to_base64(img_path)
    except Exception as e:
        print(cf.yellow(f"图片导入失败：{e}"))
        return False, (
            f"图片导入失败: ds={data.get('dataset_name')} "
            f"raw_id={data.get('raw_id')} path={img_path}"
        ), None

    record: Dict[str, Any] = {
        "raw_id": int(data["raw_id"]),
        "id": data["id"],
        "root": data["root"],
        "image": data["image"],
        "dataset_name": data.get("dataset_name", cfg.get("dataset_name")),
    }

    runtime: Dict[str, Any] = {
        "img_path": img_path,
        "img_b64": img_b64,
    }

    return True, None, {
        "runtime": runtime,
        "record": record,
    }


def prepare_sample(
    task_processor: BaseTaskProcessor,
    cfg: Dict[str, Any],
    data: Dict[str, Any],
) -> Tuple[bool, str | None, Dict[str, Any] | None]:
    """
    通用样本准备：
      - 检查图片是否存在
      - 转 base64
      - 调 generate_prompt_module (如有) 得到 (prompt, extra)
      - 拆成 runtime / record 两块：

        ctx = {
          "runtime": {...只在运行期用，不落盘...},
          "record":  {...最终会写入 jsonl 的字段（含 extra）...}
        }
    """
    ok, err, ctx = _prepare_common(cfg, data)
    if not ok or ctx is None:
        return ok, err, ctx

    runtime = ctx["runtime"]
    record = ctx["record"]
    img_path = runtime["img_path"]

    # 调用 prompt 预处理，默认返回原始 prompt, extra_info=None
    base_prompt, pre_extra_info = task_processor.prepare_prompt(img_path, data)

    if isinstance(base_prompt, str):
        base_prompt = may_forget_check(base_prompt)
    else:
        assert isinstance(base_prompt, list), (
            f"prepare_prompt 返回的 base_prompt 必须是 str 或 list[str]，实际是 {type(base_prompt).__name__}"
        )
        assert base_prompt, "prepare_prompt 返回的 prompt list 不能为空"
        assert all(isinstance(x, str) for x in base_prompt), "prompt list 的元素必须全是 str"
        base_prompt = [may_forget_check(x) for x in base_prompt]

    if pre_extra_info:
        record["pre_extra"] = pre_extra_info  # extra 独立到记录里

    runtime["base_prompt"] = base_prompt
    runtime["pre_extra"] = pre_extra_info
    runtime["skip_vlm"] = pre_extra_info.get("skip_vlm", False) if pre_extra_info else False

    return True, None, ctx


def prepare_flow_sample(
    task_processor: BaseTaskProcessor,
    cfg: Dict[str, Any],
    data: Dict[str, Any],
) -> Tuple[bool, str | None, Dict[str, Any] | None]:
    """
    历史 split 任务兼容入口：
      - 只准备图片 / record
      - 不在这里提前 prepare_prompt
      - prompt 由 processor 过程动态生成
    """
    ok, err, ctx = _prepare_common(cfg, data)
    if not ok or ctx is None:
        return ok, err, ctx

    runtime = ctx["runtime"]
    runtime["skip_vlm"] = False
    return True, None, ctx
