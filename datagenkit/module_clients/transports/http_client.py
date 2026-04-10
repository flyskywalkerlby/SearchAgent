# module_clients/transports/http_client.py
import aiohttp


async def run_http(
    client: aiohttp.ClientSession,
    cfg: dict,
    prompt: str,
    img_b64: str,
    max_new_token: int = 1024,
) -> str:
    payload = {
        "model": cfg["model_name"],
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                },
            ],
        }],
        "max_tokens": max_new_token,
        "do_sample": cfg.get("do_sample", True),
    }

    async with client.post(cfg["api_url"], json=payload) as r:
        if r.status != 200:
            txt = await r.text()
            raise RuntimeError(f"API错误 status={r.status} resp={txt[:200]}.")
        res = await r.json()
        return res["choices"][0]["message"]["content"]