
import io
import base64
from PIL import Image

import importlib.util
from pathlib import Path


def format_id(i, w=5) -> str:
    try:
        return str(int(i)).zfill(w)
    except (ValueError, TypeError):
        return str(i)


def format_time(seconds: int) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"


def image_to_base64(path, max_edge=2048, quality=85) -> str:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    max_wh = max(w, h)
    if max_wh > max_edge:
        scale = max_edge / max_wh
        img = img.resize((int(w * scale), int(h * scale)), Image.BICUBIC)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


def safe_div(a, b, ndigits=2):
    return round(a / b, ndigits=ndigits) if b > 0 else 0.0


def load_module_func(module_path: str, func_name: str):
    if not module_path:
        raise ValueError(f"module_path 为空：{module_path}")

    module_path = Path(module_path).expanduser().resolve()

    spec = importlib.util.spec_from_file_location(
        module_path.stem, module_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, func_name):
        raise AttributeError(f"模块中找不到函数：{func_name}")

    # return module_path.func_name
    return getattr(module, func_name)
