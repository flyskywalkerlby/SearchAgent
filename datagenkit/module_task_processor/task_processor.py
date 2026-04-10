from typing import Any, Dict, List, Optional, Tuple
import colorful as cf
from pathlib import Path
import yaml


class BaseTaskProcessor:
    def __init__(self, cfg):
        self.cfg = cfg
        self.prompt_template = None
        self.prompt_bank: Dict[str, str] = {}

    def load_prompt(self, cfg):
        prompt_path = Path(cfg["dir_prompts"]) / f"{cfg['prompt_type']}.yaml"
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_yaml_content = yaml.safe_load(f)

        self.prompt_bank = prompt_yaml_content
        prompt_template = prompt_yaml_content[cfg["prompt_key"]]
        print(cf.bold_yellow_on_purple(prompt_template))
        self.prompt_template = prompt_template
        return prompt_template

    def get_prompt(self, key: str) -> str:
        assert self.prompt_bank, "prompt_bank 为空，请先调用 load_prompt"
        assert key in self.prompt_bank, f"prompt key 不存在: {key}"
        return self.prompt_bank[key]

    def prepare_prompt(self, img_path, data, *args, **kwargs):
        prompt = self.prompt_template
        return prompt, None

    def post_check(
        self,
        text: str,
        enable_warn_print: bool = True,
        pre_extra: Dict[str, Any] = None,
    ):
        return True, None, None

    async def local_run_once_core(self, img_path, data) -> str:
        return None

    # =========================
    # 历史 split hooks（当前推荐统一使用 FlowTaskProcessor）
    # =========================

    def build_split_plan(self, data: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        return None

    def init_split_state(
        self,
        img_path: str,
        data: Dict[str, Any],
        split_item: Dict[str, Any],
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def build_next_prompt(
        self,
        img_path: str,
        data: Dict[str, Any],
        split_item: Dict[str, Any],
        split_state: Dict[str, Any],
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        raise NotImplementedError

    def consume_split_step(
        self,
        split_state: Dict[str, Any],
        out: Any,
        post_extra_info: Dict[str, Any],
        data: Dict[str, Any],
        split_item: Dict[str, Any],
        pre_extra: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def build_split_result(
        self,
        split_state: Dict[str, Any],
        step_results: List[Dict[str, Any]],
        data: Dict[str, Any],
        split_item: Dict[str, Any],
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def build_final_output(
        self,
        split_results: List[Dict[str, Any]],
        data: Dict[str, Any] = None,
        runtime: Dict[str, Any] = None,
    ):
        raise NotImplementedError

    @staticmethod
    def _err(errors: List[str], msg: str):
        errors.append(msg)

    @staticmethod
    def _warn(warns: List[str], msg: str, *, enable_print: bool = True):
        warns.append(msg)
        if enable_print:
            try:
                print(cf.yellow(msg))
            except Exception:
                print(msg)


class FlowTaskProcessor(BaseTaskProcessor):
    """
    新的端到端 flow processor 协议。
    runner 只串行执行“当前 step”，具体 step 如何切换完全由 processor 内部控制。
    """

    def load_prompt(self, cfg):
        prompt_path = Path(cfg["dir_prompts"]) / f"{cfg['prompt_type']}.yaml"
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_yaml_content = yaml.safe_load(f) or {}

        self.prompt_bank = prompt_yaml_content
        self.prompt_template = None
        return None

    def get_max_step_count(self) -> int | None:
        return None

    def rebuild_final_output_from_outputs(
        self,
        outputs: Dict[str, Any],
        current_output: Any = None,
    ) -> Any:
        if current_output is not None:
            return current_output
        step_names = [
            k for k in (outputs or {}).keys()
            if isinstance(k, str) and k.startswith("step") and k[4:].isdigit()
        ]
        if not step_names:
            return current_output
        step_names.sort(key=lambda x: int(x[4:]))
        return outputs[step_names[-1]]

    def init_flow_ctx(
        self,
        img_path: str,
        data: Dict[str, Any],
        runtime: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "finished": False,
            "output": None,
            "extra": {},
            "step_extras": {},
            "outputs": {},
            "written_steps": set(),
            "runtime": {},
        }

    @staticmethod
    def _is_empty_extra(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, (dict, list, tuple, set, str)):
            return len(value) == 0
        return False

    def get_step_extra(
        self,
        flow_ctx: Dict[str, Any],
        step_info: Dict[str, Any],
        checked_output: Any,
        raw_text: str,
        data: Dict[str, Any],
        runtime: Dict[str, Any],
    ) -> Any:
        return step_info.get("record_extra")

    def record_step_extra(
        self,
        flow_ctx: Dict[str, Any],
        step_name: str,
        step_extra: Any,
    ) -> None:
        if self._is_empty_extra(step_extra):
            return

        step_extras = flow_ctx.setdefault("step_extras", {})
        if step_name not in step_extras:
            step_extras[step_name] = step_extra
            return

        prev = step_extras[step_name]
        if prev == step_extra:
            return

        if isinstance(prev, list):
            if step_extra not in prev:
                prev.append(step_extra)
            return

        step_extras[step_name] = [prev, step_extra]

    def prepare_current_step(
        self,
        flow_ctx: Dict[str, Any],
        img_path: str,
        data: Dict[str, Any],
        runtime: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def post_check_current_step(
        self,
        text: str,
        flow_ctx: Dict[str, Any],
        step_info: Dict[str, Any],
    ):
        return self.post_check(text)

    async def local_run_current_step(
        self,
        flow_ctx: Dict[str, Any],
        step_info: Dict[str, Any],
        img_path: str,
        data: Dict[str, Any],
        runtime: Dict[str, Any],
    ):
        return await self.local_run_once_core(img_path, data)

    def consume_step_result(
        self,
        flow_ctx: Dict[str, Any],
        step_info: Dict[str, Any],
        checked_output: Any,
        raw_text: str,
        data: Dict[str, Any],
        runtime: Dict[str, Any],
    ) -> None:
        raise NotImplementedError

    def build_final_record(
        self,
        base_record: Dict[str, Any],
        flow_ctx: Dict[str, Any],
        data: Dict[str, Any],
        runtime: Dict[str, Any],
    ) -> Dict[str, Any]:
        rec = dict(base_record)
        rec["output"] = flow_ctx.get("output")

        step_extras = {
            k: v for k, v in flow_ctx.get("step_extras", {}).items()
            if not self._is_empty_extra(v)
        }
        rec["extra"] = step_extras

        rec["outputs"] = flow_ctx.get("outputs", {})
        rec["written_steps"] = sorted(flow_ctx.get("written_steps", set()))
        return rec
