from typing import List
import json

import colorful as cf

from typing import Any, Dict


# =========================
# qwen3vl_thinking 输出格式check
# =========================

def _err(errors: List[str], path: str, msg: str) -> None:
    errors.append(f"{path}: {msg}")


def _warn(path: str, msg: str) -> None:
    text = f"【WARN】{path}: {msg}"
    try:
        print(cf.yellow(text))
    except Exception:
        print(text)


def _expect_type(x: Any, t: type, path: str, errors: List[str]) -> bool:
    if not isinstance(x, t):
        _err(errors, path, f"类型错误，期望 {t.__name__}，实际 {type(x).__name__}")
        return False
    return True


def _require_keys(d: Dict[str, Any], keys: List[str], path: str, errors: List[str]) -> None:
    for k in keys:
        if k not in d:
            _err(errors, path, f"缺少'{k}'字段")


def _no_extra_keys(d: Dict[str, Any], allowed: List[str], path: str, errors: List[str]) -> None:
    allow = set(allowed)
    for k in d.keys():
        if k not in allow:
            _err(errors, path, f"出现未定义字段'{k}'")
            

def _exact_keys(d: Dict[str, Any], keys: List[str], path: str, errors: List[str]) -> None:
    _require_keys(d, keys, path, errors)
    _no_extra_keys(d, keys, path, errors)
            
            
def _check_list_str(x: Any, path: str, errors: List[str]) -> None:
    if not _expect_type(x, list, path, errors):
        return
    for i, v in enumerate(x):
        if not isinstance(v, str):
            _err(errors, f"{path}[{i}]", f"类型错误，期望 str，实际 {type(v).__name__}")

# =========================
# 1) gate：check_dict（解析失败就是错，不往下走）
# =========================
def check_dict(d_string, key2type, context=None):
    """
    校验 JSON 字符串
    context: str | None，例如 "think" / "answer"
    返回:
        ok: bool
        errors: list[str]
    """
    errors: List[str] = []
    prefix = f"{context}: " if context else ""

    try:
        d = json.loads(d_string)
    except json.JSONDecodeError as e:
        errors.append(f"{prefix}JSON解析错误: {str(e)}")
        return False, errors

    for key_desc, key_type in key2type.items():
        if key_desc not in d:
            errors.append(f"{prefix}缺少'{key_desc}'字段")
        elif not isinstance(d[key_desc], key_type):
            errors.append(f"{prefix}'{key_desc}'字段不是'{key_type.__name__}'类型")

    return (len(errors) == 0), errors

# =========================
# qwen3vl_thinking 输出格式check
# =========================

def qwen3vl_235b_thinking_check_and_strip_think(text: str):
    """
    只负责 think 校验和剥离
    只检测 </think>（不要求 <think>）

    返回:
        ok: bool
        errors: list[str]
        think_text: str | None
        answer_text: str | None
    """
    errors: List[str] = []

    close_cnt = text.count("</think>")
    if close_cnt != 1:
        errors.append(f"存在 {close_cnt} 个 </think>，</think> 应当有且只有1个。")
        return False, errors, None, None

    think_part, answer_part = text.split("</think>", 1)
    think_text = think_part.strip()
    answer_text = answer_part.strip()

    if not think_text:
        errors.append("think 内容为空（</think> 前为空），你应当做思考。")
        return False, errors, None, None

    if not answer_text:
        errors.append("answer 内容为空（</think> 后为空），做完思考后你应当总结，并输出最终结果。")
        return False, errors, None, None

    return True, [], think_text, answer_text
