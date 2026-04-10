import os
import hashlib
import re
from pathlib import Path


# CACHE_ROOT_DIR = os.environ.get("CACHE_ROOT", "./cache")
CACHE_ROOT_DIR = "./cache"
os.makedirs(CACHE_ROOT_DIR, exist_ok=True)


def _encode_cache_key(s: str, max_len: int = 180) -> str:
    s_abs = os.path.abspath(s).replace("\\", "/")
    key = s_abs.replace("/", "__").replace(":", "_")
    if len(key) <= max_len:
        return key
    h = hashlib.sha1(s_abs.encode("utf-8")).hexdigest()[:12]
    return key[: (max_len - 2 - len(h))] + "__" + h


def get_cache_file_of_final(final_file: str) -> str:
    key = _encode_cache_key(final_file)
    return os.path.join(CACHE_ROOT_DIR, key + ".cache.jsonl")


STEP_SUFFIX_RE = re.compile(r"\.step(\d+)$")

BASE_OUTPUT_ROOTS = {
    "outputs": "outputs",
    "outputs_steps": "outputs",
    "outputs_failed": "outputs",
    "test_outputs": "test_outputs",
    "test_outputs_steps": "test_outputs",
    "test_outputs_failed": "test_outputs",
}

STEP_OUTPUT_ROOTS = {
    "outputs": "outputs_steps",
    "outputs_steps": "outputs_steps",
    "outputs_failed": "outputs_steps",
    "test_outputs": "test_outputs_steps",
    "test_outputs_steps": "test_outputs_steps",
    "test_outputs_failed": "test_outputs_steps",
}


def _normalize_step_name(step: int | str) -> str:
    if isinstance(step, int):
        if step <= 0:
            raise ValueError(f"非法 step: {step}")
        return f"step{step}"
    if isinstance(step, str) and step.startswith("step") and step[4:].isdigit():
        return step
    raise ValueError(f"非法 step: {step}")


def _split_step_suffix(stem: str) -> tuple[str, str | None]:
    m = STEP_SUFFIX_RE.search(stem)
    if not m:
        return stem, None
    return stem[: m.start()], f"step{m.group(1)}"


def get_base_final_file(path: str) -> str:
    abs_path = os.path.abspath(path)
    dir_name = os.path.dirname(abs_path)
    base_name = os.path.basename(abs_path)
    stem, ext = os.path.splitext(base_name)
    clean_stem, _ = _split_step_suffix(stem)

    parts = list(Path(dir_name).parts)
    for i, part in enumerate(parts):
        if part in BASE_OUTPUT_ROOTS:
            parts[i] = BASE_OUTPUT_ROOTS[part]
            break
    dir_name = str(Path(*parts))
    return os.path.join(dir_name, clean_stem + ext)


def get_step_output_file_of_final(final_file: str, step: int | str) -> str:
    step_name = _normalize_step_name(step)
    base_final = get_base_final_file(final_file)
    dir_name = os.path.dirname(base_final)
    base_name = os.path.basename(base_final)
    stem, ext = os.path.splitext(base_name)

    parts = list(Path(dir_name).parts)
    replaced = False
    for i, part in enumerate(parts):
        if part in STEP_OUTPUT_ROOTS:
            parts[i] = STEP_OUTPUT_ROOTS[part]
            replaced = True
            break
    if not replaced:
        parts.append("outputs_steps")
    step_dir = str(Path(*parts))
    return os.path.join(step_dir, f"{stem}.{step_name}{ext}")


def get_target_file_of_final(final_file: str, max_step: int | None, processor_max_step_count: int | None = None) -> str:
    base_final = get_base_final_file(final_file)
    if (
        isinstance(max_step, int)
        and max_step > 0
        and isinstance(processor_max_step_count, int)
        and processor_max_step_count > 0
        and max_step == processor_max_step_count
    ):
        return base_final
    if isinstance(max_step, int) and max_step > 0:
        return get_step_output_file_of_final(base_final, max_step)
    return base_final
