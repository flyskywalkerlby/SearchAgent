# module_clients/transports/openai_client.py
from typing import Any, Dict
from openai import AsyncOpenAI


async def run_openai(
    client: AsyncOpenAI,
    cfg: Dict[str, Any],
    prompt: str,
    img_b64: str,
    max_new_token: int = 1024,
) -> str:
    resp = await client.chat.completions.create(
        model=cfg["model_name"],
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                },
            ],
        }],
        max_tokens=cfg.get("max_tokens", max_new_token),
        temperature=cfg.get("temperature", 1.0),
        top_p=cfg.get("top_p", 0.95),
        presence_penalty=cfg.get("presence_penalty", 0.0),
        stream=False,
        extra_body=cfg.get("extra_body", {}),
    )
    msg = resp.choices[0].message
    return msg.content or ""
