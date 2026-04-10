# module_clients/transports/local_client.py
from __future__ import annotations

from typing import Any, Dict, Optional
import importlib
import inspect


def _load_entry(entry: str):
    """
    entry: "package.module:func_name"
    """
    if ":" not in entry:
        raise ValueError(f"local_entry format must be 'pkg.mod:func', got: {entry!r}")
    mod_name, fn_name = entry.split(":", 1)
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, fn_name, None)
    if fn is None:
        raise AttributeError(f"Cannot find function {fn_name!r} in module {mod_name!r}")
    return fn


def _extract_text(res: Any) -> str:
    """
    兼容一些常见返回结构：
    - str
    - {"content": "..."} / {"text": "..."} / {"message": {"content": "..."}}
    - OpenAI-like: {"choices":[{"message":{"content":"..."}}]}
    """
    if res is None:
        return ""

    if isinstance(res, str):
        return res

    if isinstance(res, dict):
        if "content" in res and isinstance(res["content"], str):
            return res["content"]
        if "text" in res and isinstance(res["text"], str):
            return res["text"]
        msg = res.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            return msg["content"]

        choices = res.get("choices")
        if isinstance(choices, list) and choices:
            c0 = choices[0]
            if isinstance(c0, dict):
                m = c0.get("message")
                if isinstance(m, dict) and isinstance(m.get("content"), str):
                    return m["content"]
                # 有些会是 {"choices":[{"text":"..."}]}
                if isinstance(c0.get("text"), str):
                    return c0["text"]

    # 兜底
    return str(res)


async def _maybe_await(fn_res: Any) -> Any:
    if inspect.isawaitable(fn_res):
        return await fn_res
    return fn_res


async def run_local(
    client: Any,
    cfg: Dict[str, Any],
    prompt: str,
    img_b64: str,
    max_new_token: int = 1024,
) -> str:
    """
    Local 后端：只负责 I/O，不做 retry / cache / post_check。

    支持：
    1) cfg["local_entry"] = "pkg.mod:func"
       - func signature 推荐：func(prompt: str, img_b64: str, cfg: dict) -> str|dict (sync/async)
    2) client 是 callable：client(prompt, img_b64, cfg) -> str|dict (sync/async)
    3) client 有方法：run/generate/infer/chat (sync/async)
       - method signature 推荐：method(prompt, img_b64, cfg)

    返回：str
    """
    # 把 max_new_token 放回 cfg 里，给本地实现用（不强依赖）
    # 不改你 cfg 原结构：只是在调用层做一个浅拷贝，避免污染全局 cfg
    call_cfg = dict(cfg)
    call_cfg.setdefault("max_tokens", max_new_token)
    call_cfg.setdefault("max_new_token", max_new_token)

    # (1) cfg 配 entry 函数：最推荐的扩展方式
    entry = call_cfg.get("local_entry")
    if entry:
        fn = _load_entry(entry)
        res = await _maybe_await(fn(prompt=prompt, img_b64=img_b64, cfg=call_cfg))
        return _extract_text(res)

    # (2) client 自己就是可调用
    if callable(client):
        # 兼容用户实现用位置参数的习惯
        try:
            res = await _maybe_await(client(prompt=prompt, img_b64=img_b64, cfg=call_cfg))
        except TypeError:
            res = await _maybe_await(client(prompt, img_b64, call_cfg))
        return _extract_text(res)

    # (3) client 上的常见方法名
    for meth_name in ("run", "generate", "infer", "chat"):
        meth = getattr(client, meth_name, None)
        if meth and callable(meth):
            try:
                res = await _maybe_await(meth(prompt=prompt, img_b64=img_b64, cfg=call_cfg))
            except TypeError:
                res = await _maybe_await(meth(prompt, img_b64, call_cfg))
            return _extract_text(res)

    raise TypeError(
        "local backend requires one of:\n"
        "  - cfg['local_entry']='pkg.mod:func'\n"
        "  - client is callable: client(prompt, img_b64, cfg)\n"
        "  - client has method: run/generate/infer/chat"
    )
    