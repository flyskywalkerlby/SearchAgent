# module_clients/client_factory.py
from __future__ import annotations

from typing import Any, Dict
import asyncio


async def build_client(cfg: Dict[str, Any]) -> Any:
    backend = cfg.get("backend", "http")

    if backend == "http":
        import aiohttp
        from aiohttp import TCPConnector

        connector = TCPConnector(limit=cfg.get("max_concurrent", 16))
        return aiohttp.ClientSession(connector=connector)

    if backend == "openai":
        from openai import AsyncOpenAI

        # 统一从 cfg 读：要求 api_url 为 .../v1
        return AsyncOpenAI(
            base_url=cfg["api_url"],
            api_key=cfg.get("api_key", "EMPTY"),
        )

    if backend == "local":
        # 本地如果不需要 client，就返回 None
        return None

    raise ValueError(f"Unknown backend: {backend}")


async def close_client(client: Any) -> None:
    if client is None:
        return

    aclose = getattr(client, "aclose", None)
    if callable(aclose):
        await aclose()
        return

    close = getattr(client, "close", None)
    if callable(close):
        ret = close()
        if asyncio.iscoroutine(ret):
            await ret
            