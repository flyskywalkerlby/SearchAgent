import json
from typing import Any, Dict

from module_task_processor.task_processor import FlowTaskProcessor


def build_extra_info_block(extra_info: str) -> str:
    extra_info = (extra_info or "").strip()
    if not extra_info:
        return ""
    return "\n\n# 额外信息\n" + extra_info


class _BaseExampleFlowProcessor(FlowTaskProcessor):
    def _parse_json_dict(self, text: str):
        text = (text or "").strip()
        if not text:
            return False, "输出为空", None
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            return False, f"JSON解析错误: {e}", None
        if not isinstance(obj, dict):
            return False, f"输出必须是 dict，实际是 {type(obj).__name__}", None
        return True, None, obj


class SimpleCaptionFlowProcessor(_BaseExampleFlowProcessor):
    def get_max_step_count(self) -> int | None:
        return 1

    def prepare_current_step(self, flow_ctx, img_path, data, runtime):
        if "step1" in flow_ctx["outputs"]:
            return None
        return {
            "step_name": "step1",
            "prompt": self.get_prompt("prompt_simple_caption"),
        }

    def post_check_current_step(self, text: str, flow_ctx: Dict[str, Any], step_info: Dict[str, Any]):
        ok, err, obj = self._parse_json_dict(text)
        if not ok:
            return False, err, None
        if "caption" not in obj:
            return False, "缺少 caption", None
        if not isinstance(obj["caption"], str) or not obj["caption"].strip():
            return False, "caption 必须是非空字符串", None
        return True, None, obj

    def consume_step_result(self, flow_ctx, step_info, checked_output, raw_text, data, runtime):
        flow_ctx["outputs"]["step1"] = checked_output
        flow_ctx["output"] = checked_output
        flow_ctx["finished"] = True


class AddInfoCaptionFlowProcessor(SimpleCaptionFlowProcessor):
    def prepare_current_step(self, flow_ctx, img_path, data, runtime):
        if "step1" in flow_ctx["outputs"]:
            return None
        extra_info = ""
        if self.cfg.get("add_info", False):
            extra_info = str(data.get("info") or self.cfg.get("extra", {}).get("static_extra_info") or "").strip()
        prompt = self.get_prompt("prompt_add_info_caption")
        prompt = prompt.replace("{{EXTRA_INFO_BLOCK}}", build_extra_info_block(extra_info))
        return {
            "step_name": "step1",
            "prompt": prompt,
            "record_extra": {"meta_info": extra_info} if extra_info else None,
        }


class OneStepFlowExampleProcessor(_BaseExampleFlowProcessor):
    def get_max_step_count(self) -> int | None:
        return 1

    def prepare_current_step(self, flow_ctx, img_path, data, runtime):
        if "step1" in flow_ctx["outputs"]:
            return None
        return {
            "step_name": "step1",
            "prompt": self.get_prompt("prompt_one_step"),
        }

    def post_check_current_step(self, text: str, flow_ctx: Dict[str, Any], step_info: Dict[str, Any]):
        ok, err, obj = self._parse_json_dict(text)
        if not ok:
            return False, err, None
        if "label" not in obj:
            return False, "缺少 label", None
        return True, None, obj

    def consume_step_result(self, flow_ctx, step_info, checked_output, raw_text, data, runtime):
        flow_ctx["outputs"]["step1"] = checked_output
        flow_ctx["output"] = checked_output
        flow_ctx["finished"] = True


class MultiStepFlowExampleProcessor(_BaseExampleFlowProcessor):
    def get_max_step_count(self) -> int | None:
        return 3

    def prepare_current_step(self, flow_ctx, img_path, data, runtime):
        outputs = flow_ctx["outputs"]
        if "step1" not in outputs:
            return {"step_name": "step1", "prompt": self.get_prompt("prompt_multi_step1")}
        if "step2" not in outputs:
            prompt = self.get_prompt("prompt_multi_step2").replace("{{SEED}}", outputs["step1"]["seed"])
            return {"step_name": "step2", "prompt": prompt}
        if "step3" not in outputs:
            prompt = self.get_prompt("prompt_multi_step3").replace("{{MESSAGE}}", outputs["step2"]["message"])
            return {"step_name": "step3", "prompt": prompt}
        return None

    def post_check_current_step(self, text: str, flow_ctx: Dict[str, Any], step_info: Dict[str, Any]):
        ok, err, obj = self._parse_json_dict(text)
        if not ok:
            return False, err, None
        step_name = step_info["step_name"]
        if step_name == "step1" and "seed" not in obj:
            return False, "step1 缺少 seed", None
        if step_name == "step2" and "message" not in obj:
            return False, "step2 缺少 message", None
        if step_name == "step3" and "summary" not in obj:
            return False, "step3 缺少 summary", None
        return True, None, obj

    def consume_step_result(self, flow_ctx, step_info, checked_output, raw_text, data, runtime):
        step_name = step_info["step_name"]
        flow_ctx["outputs"][step_name] = checked_output
        if step_name == "step3":
            flow_ctx["output"] = checked_output
            flow_ctx["finished"] = True


class SplitStepFlowExampleProcessor(_BaseExampleFlowProcessor):
    def get_max_step_count(self) -> int | None:
        return 2

    def init_flow_ctx(self, img_path, data, runtime):
        flow_ctx = super().init_flow_ctx(img_path, data, runtime)
        flow_ctx["runtime"]["split_items"] = []
        flow_ctx["runtime"]["split_idx"] = 0
        return flow_ctx

    def prepare_current_step(self, flow_ctx, img_path, data, runtime):
        outputs = flow_ctx["outputs"]
        rt = flow_ctx["runtime"]

        if "step1" not in outputs:
            return {"step_name": "step1", "prompt": self.get_prompt("prompt_split_step1")}

        if not rt["split_items"]:
            rt["split_items"] = list(outputs["step1"]["items"])

        if rt["split_idx"] < len(rt["split_items"]):
            item = rt["split_items"][rt["split_idx"]]
            prompt = self.get_prompt("prompt_split_item").replace("{{ITEM}}", item)
            return {"step_name": "split_item", "prompt": prompt, "item": item}

        if "step2" not in outputs:
            merged = ",".join(x["tag"] for x in outputs.get("split_item", []))
            prompt = self.get_prompt("prompt_split_final").replace("{{MERGED}}", merged)
            return {"step_name": "step2", "prompt": prompt}

        return None

    def post_check_current_step(self, text: str, flow_ctx: Dict[str, Any], step_info: Dict[str, Any]):
        ok, err, obj = self._parse_json_dict(text)
        if not ok:
            return False, err, None
        step_name = step_info["step_name"]
        if step_name == "step1" and "items" not in obj:
            return False, "step1 缺少 items", None
        if step_name == "split_item" and ("item" not in obj or "tag" not in obj):
            return False, "split_item 缺少 item/tag", None
        if step_name == "step2" and "final" not in obj:
            return False, "step2 缺少 final", None
        return True, None, obj

    def consume_step_result(self, flow_ctx, step_info, checked_output, raw_text, data, runtime):
        step_name = step_info["step_name"]
        rt = flow_ctx["runtime"]

        if step_name == "step1":
            flow_ctx["outputs"]["step1"] = checked_output
            return
        if step_name == "split_item":
            flow_ctx["outputs"].setdefault("split_item", []).append(checked_output)
            rt["split_idx"] += 1
            return
        if step_name == "step2":
            flow_ctx["outputs"]["step2"] = checked_output
            flow_ctx["output"] = checked_output
            flow_ctx["finished"] = True
