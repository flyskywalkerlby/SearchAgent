# module_runner/core/core_call.py
from typing import Any, Dict, Tuple, Optional

from module_clients.transports.http_client import run_http
from module_clients.transports.openai_client import run_openai
from module_clients.transports.local_client import run_local

from module_task_processor import BaseTaskProcessor


async def run_once_core(
    client,
    cfg: Dict[str, Any],
    prompt: str,
    img_b64: str,
    task_processor: BaseTaskProcessor,
    pre_extra: Dict[str, Any] = None,
) -> Tuple[bool, Any, Optional[str], Any]:
    """
    后端无关的一次调用：
      - 根据 cfg["backend"] 调用 api/local 后端
      - 跑一次 post_check（如果有）
      - 返回 (ok, out, error_msg, extra_info)
    """

    backend = cfg.get("backend", "http")

    if backend == "http":
        out = await run_http(client, cfg, prompt, img_b64)
    elif backend == "openai":
        out = await run_openai(client, cfg, prompt, img_b64)
    elif backend == "local":
        out = await run_local(client, cfg, prompt, img_b64)
    else:
        raise ValueError(f"Unknown backend: {backend}")

    ok, error_msg, extra_info = task_processor.post_check(out, pre_extra=pre_extra)
    return ok, out, error_msg, extra_info