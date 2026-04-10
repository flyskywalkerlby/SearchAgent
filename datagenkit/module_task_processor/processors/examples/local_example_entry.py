import json
import re


def _extract_value(prompt: str, key: str, default: str = "") -> str:
    pattern = rf"^{re.escape(key)}=(.*)$"
    for line in prompt.splitlines():
        m = re.match(pattern, line.strip())
        if m:
            return m.group(1).strip()
    return default


async def example_local_entry(prompt: str, img_b64: str, cfg: dict) -> str:
    prompt = prompt.strip()

    if "EXAMPLE_SIMPLE_CAPTION" in prompt:
        return json.dumps({"caption": "一张用于演示的图片。"}, ensure_ascii=False)

    if "EXAMPLE_ADD_INFO_CAPTION" in prompt:
        extra = "带额外信息" if "# 额外信息" in prompt else "无额外信息"
        return json.dumps({"caption": f"一张{extra}的演示图片。"}, ensure_ascii=False)

    if "EXAMPLE_ONE_STEP" in prompt:
        return json.dumps({"label": "one-step-ok", "source": "local-entry"}, ensure_ascii=False)

    if "EXAMPLE_MULTI_STEP1" in prompt:
        return json.dumps({"seed": "alpha", "count": 2}, ensure_ascii=False)

    if "EXAMPLE_MULTI_STEP2" in prompt:
        seed = _extract_value(prompt, "SEED", "unknown")
        return json.dumps({"message": f"{seed}-expanded", "items": [f"{seed}-0", f"{seed}-1"]}, ensure_ascii=False)

    if "EXAMPLE_MULTI_STEP3" in prompt:
        message = _extract_value(prompt, "MESSAGE", "none")
        return json.dumps({"summary": f"final:{message}"}, ensure_ascii=False)

    if "EXAMPLE_SPLIT_STEP1" in prompt:
        return json.dumps({"items": ["apple", "banana", "citrus"]}, ensure_ascii=False)

    if "EXAMPLE_SPLIT_ITEM" in prompt:
        item = _extract_value(prompt, "ITEM", "unknown")
        return json.dumps({"item": item, "tag": item.upper()}, ensure_ascii=False)

    if "EXAMPLE_SPLIT_FINAL" in prompt:
        merged = _extract_value(prompt, "MERGED", "")
        return json.dumps({"final": f"merged:{merged}"}, ensure_ascii=False)

    raise ValueError(f"Unknown example prompt: {prompt[:120]}")
