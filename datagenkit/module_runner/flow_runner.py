from asyncio import Lock, Semaphore
from copy import deepcopy
from typing import Any, Dict, Optional, Tuple

import colorful as cf

from .core.prepare import prepare_flow_sample, may_forget_check
from .core.cache_writer import append_record_to_cache
from .utils import RETRY_PROMPT

from module_clients.transports.http_client import run_http
from module_clients.transports.openai_client import run_openai
from module_clients.transports.local_client import run_local
from module_task_processor.task_processor import FlowTaskProcessor


class FlowRunner:
    def __init__(
        self,
        cfg: Dict[str, Any],
        stats: Dict[str, Any],
        task_processor: FlowTaskProcessor,
    ) -> None:
        self.cfg_main = cfg
        self.cfg_retry = deepcopy(cfg)
        assert "do_sample" in self.cfg_retry, "cfg 缺少 do_sample 字段，无法在 retry 阶段自动开启采样"
        self.cfg_retry["do_sample"] = True

        self.stats = stats
        self.task_processor = task_processor

        self.sem = Semaphore(cfg["max_concurrent"])
        self.lock = Lock()

    def _maybe_finish_at_max_step(self, flow_ctx: Dict[str, Any]) -> None:
        max_step = self.cfg_main.get("max_step")
        if max_step is None:
            return
        if not isinstance(max_step, int) or max_step <= 0:
            return

        target_key = f"step{max_step}"
        outputs = flow_ctx.get("outputs", {})
        if target_key not in outputs:
            return

        flow_ctx["output"] = outputs[target_key]
        flow_ctx["finished"] = True

    async def _record_failed_case(
        self,
        data: Dict[str, Any],
        path: Optional[str],
        reason: Optional[str],
        final_file: Optional[str] = None,
        failed_output: Any = None,
    ) -> None:
        async with self.lock:
            self.stats["error"] += 1
            failed_case = {
                "raw_id": data.get("raw_id"),
                "dataset_name": data.get("dataset_name"),
                "image": data.get("image"),
                "path": path,
                "reason": reason,
                "final_file": final_file,
            }
            if failed_output is not None:
                failed_case["failed_output"] = failed_output
            self.stats["failed_cases"].append(failed_case)

    async def _append_success_record(
        self,
        cache_file: str,
        record: Dict[str, Any],
    ) -> None:
        await append_record_to_cache(
            cache_file=cache_file,
            rec=record,
            stats=self.stats,
            lock=self.lock,
        )

    async def _infer_once(
        self,
        client,
        cfg: Dict[str, Any],
        prompt: str,
        img_b64: str,
    ) -> str:
        backend = cfg.get("backend", "http")

        if backend == "http":
            return await run_http(client, cfg, prompt, img_b64)
        if backend == "openai":
            return await run_openai(client, cfg, prompt, img_b64)
        if backend == "local":
            return await run_local(client, cfg, prompt, img_b64)

        raise ValueError(f"Unknown backend: {backend}")

    async def _execute_step_with_retry(
        self,
        client,
        data: Dict[str, Any],
        runtime: Dict[str, Any],
        flow_ctx: Dict[str, Any],
        step_info: Dict[str, Any],
        max_retry: int,
    ) -> Tuple[bool, Optional[str], Any, Any]:
        prompt = step_info.get("prompt", "") or ""
        prompt = may_forget_check(prompt)
        start_prompt = prompt

        step_max_retry = 1 if step_info.get("skip_vlm") else step_info.get("max_retry", max_retry)

        raw_text = None
        checked_output = None
        last_error_msg = None

        for attempt in range(1, step_max_retry + 1):
            cfg_for_this_try = self.cfg_main if attempt == 1 else self.cfg_retry

            if step_info.get("skip_vlm"):
                raw_text = await self.task_processor.local_run_current_step(
                    flow_ctx=flow_ctx,
                    step_info=step_info,
                    img_path=runtime["img_path"],
                    data=data,
                    runtime=runtime,
                )
            else:
                raw_text = await self._infer_once(
                    client=client,
                    cfg=cfg_for_this_try,
                    prompt=prompt,
                    img_b64=runtime["img_b64"],
                )

            ok, error_msg, checked_output = self.task_processor.post_check_current_step(
                raw_text,
                flow_ctx=flow_ctx,
                step_info=step_info,
            )
            if ok:
                return True, raw_text, checked_output, None

            last_error_msg = error_msg or "post_check 失败"

            if attempt < step_max_retry:
                async with self.lock:
                    self.stats["retry_total"] += 1

                print(cf.orange(prompt))
                print(cf.yellow(last_error_msg))
                if raw_text is not None:
                    print(cf.bold_white(str(raw_text)))
                print(
                    f"⚠️ step 失败，重试 {attempt}/{step_max_retry} "
                    f"step={step_info.get('step_name')} "
                    f"ds={data.get('dataset_name')} raw_id={data.get('raw_id')}"
                )

                prompt = RETRY_PROMPT.format(
                    start_prompt=start_prompt,
                    bad_output=raw_text,
                    error_message=last_error_msg,
                )

        return False, raw_text, checked_output, last_error_msg

    async def send_one(
        self,
        client,
        data: Dict[str, Any],
        cache_file: str,
        final_file: str,
        max_retry: int = 1,
    ) -> None:
        async with self.sem:
            ok_prep, err_msg, ctx = prepare_flow_sample(
                self.task_processor,
                self.cfg_main,
                data,
            )
            if not ok_prep or ctx is None:
                await self._record_failed_case(
                    data=data,
                    path=data.get("image"),
                    reason=err_msg,
                    final_file=final_file,
                )
                print(cf.red(err_msg))
                return

            runtime = ctx["runtime"]
            base_record = ctx["record"]
            img_path = runtime["img_path"]

            try:
                flow_ctx = self.task_processor.init_flow_ctx(
                    img_path=img_path,
                    data=data,
                    runtime=runtime,
                )
                prev_outputs = data.get("__prev_outputs")
                if isinstance(prev_outputs, dict) and prev_outputs:
                    flow_ctx["outputs"] = deepcopy(prev_outputs)
                prev_output = data.get("__prev_output")
                if prev_output is not None and flow_ctx.get("output") is None:
                    flow_ctx["output"] = deepcopy(prev_output)

                while True:
                    if flow_ctx.get("finished"):
                        break

                    step_info = self.task_processor.prepare_current_step(
                        flow_ctx=flow_ctx,
                        img_path=img_path,
                        data=data,
                        runtime=runtime,
                    )
                    if step_info is None:
                        break

                    ok, raw_text, checked_output, fail_reason = await self._execute_step_with_retry(
                        client=client,
                        data=data,
                        runtime=runtime,
                        flow_ctx=flow_ctx,
                        step_info=step_info,
                        max_retry=max_retry,
                    )
                    if not ok:
                        await self._record_failed_case(
                            data=data,
                            path=img_path,
                            reason=fail_reason,
                            final_file=final_file,
                            failed_output=raw_text,
                        )
                        print(
                            f"❌ step 失败 "
                            f"step={step_info.get('step_name')} "
                            f"ds={data.get('dataset_name')} raw_id={data.get('raw_id')}"
                        )
                        print(cf.red(f"Failed Reason: {fail_reason}"))
                        return

                    step_extra = self.task_processor.get_step_extra(
                        flow_ctx=flow_ctx,
                        step_info=step_info,
                        checked_output=checked_output,
                        raw_text=raw_text,
                        data=data,
                        runtime=runtime,
                    )
                    self.task_processor.record_step_extra(
                        flow_ctx=flow_ctx,
                        step_name=step_info.get("step_name", "unknown_step"),
                        step_extra=step_extra,
                    )

                    self.task_processor.consume_step_result(
                        flow_ctx=flow_ctx,
                        step_info=step_info,
                        checked_output=checked_output,
                        raw_text=raw_text,
                        data=data,
                        runtime=runtime,
                    )
                    step_name = step_info.get("step_name")
                    if isinstance(step_name, str) and step_name.startswith("step"):
                        flow_ctx.setdefault("written_steps", set()).add(step_name)
                    self._maybe_finish_at_max_step(flow_ctx)

                final_record = self.task_processor.build_final_record(
                    base_record=base_record,
                    flow_ctx=flow_ctx,
                    data=data,
                    runtime=runtime,
                )
                await self._append_success_record(cache_file=cache_file, record=final_record)

            except Exception as e:
                await self._record_failed_case(
                    data=data,
                    path=img_path,
                    reason=str(e),
                    final_file=final_file,
                )
                print(
                    f"❌ 处理 ds={data.get('dataset_name')} "
                    f"raw_id={data.get('raw_id', '未知')} 失败: {e}"
                )

    async def send_one_with_retry(
        self,
        client,
        data: Dict[str, Any],
        cache_file: str,
        final_file: str,
        max_retry: int = 5,
    ) -> None:
        return await self.send_one(
            client=client,
            data=data,
            cache_file=cache_file,
            final_file=final_file,
            max_retry=max_retry,
        )
