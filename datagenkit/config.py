# -*- coding: utf-8 -*-
"""
config_loader.py

修复点：
1) CLI 传 --xxx None / null / ~ 时，不再把字符串 "None" 当成有效值覆盖配置
2) YAML 里（包括分组 dict 的 kk/vv 展开）出现 "None"/"null"/"~" 也会被归一化为 None
3) --config None 也会被归一化成 None，避免拿 "None" 去 open 文件
"""

import argparse
import yaml
import colorful as cf
from pathlib import Path


DEFAULT_CONFIG = {
    
    # runner
    "runner_type": "flow",
    
    # task_processor
    "task_processor_module": None,
    "task_processor_name": None,
    
    # prepare_prompt
    "prepare_prompt_module": None,
    "prepare_prompt_func_name": "prepare_prompt_func",
    
    # post_check
    "post_check_module": None,
    "post_check_func_name": "post_check_func",
    
    # input_loader
    "input_type": "root",
    "dataset_name": None,
    "select_datasets": [],
    "ignore_datasets": [],
    
    # 若为 True，必须通过检查才能保留（例如 gt）
    "strict_post_check": True,

    "root": None,
    "meta_json_path": None,
    "sample_n_per_ds": None,

    "api_url": "http://localhost:9002/v1/chat/completions",
    "model_name": "qwen3_vl_moe",
    "model_tag": "235ba22bfp8",

    "dir_prompts": "./prompts/end2end",
    "prompt_type": "vN",
    "prompt_key": "prompt_template",
    "add_info": True,

    "max_concurrent": 4,
    "start_step": None,
    "max_step": None,
    "max_retry": 5,
    "max_items": None,
    "do_sample": False,
    "rerun": False,
    "resume": False,
    "test": False,

    "output_dir": None,

    "gt_version": None,

    # ✅ extra
    "extra": {},
}


def normalize_value(v):
    """
    把外部输入（YAML/CLI）里常见的“伪 None/Bool”字符串做语义归一化。
    你提到的 bug：None 变成字符串 "None" 就在这里统一收口。
    """
    if isinstance(v, str):
        s = v.strip().lower()
        if s in {"none", "null", "~"}:
            return None
        if s in {"true", "false"}:
            return s == "true"
    return v


def parse_args():
    p = argparse.ArgumentParser("base")
    p.add_argument("--config")

    p.add_argument("--input_type")
    p.add_argument("--dataset_name")

    p.add_argument("--select_datasets", nargs="+", default=None)
    p.add_argument("--ignore_datasets", nargs="+", default=None)

    p.add_argument("--root")
    p.add_argument("--meta_json_path")
    p.add_argument("--sample_n_per_ds", type=int)

    p.add_argument("--api_url")
    p.add_argument("--model_name")
    p.add_argument("--model_tag")

    p.add_argument("--dir_prompts")
    p.add_argument("--prompt_type")
    p.add_argument("--add_info", action="store_true", default=None)

    p.add_argument("--max_concurrent", type=int)
    p.add_argument("--start_step", type=int)
    p.add_argument("--max_step", type=int)
    p.add_argument("--max_retry", type=int)
    p.add_argument("--max_items", type=int)
    p.add_argument("--do_sample", action="store_true", default=None)
    p.add_argument("--rerun", action="store_true", default=None)
    p.add_argument("--resume", action="store_true", default=None)
    p.add_argument("--test", action="store_true", default=None)

    p.add_argument("--retoken", action="store_true", default=None)

    p.add_argument("--output_dir")

    p.add_argument("--gt_version")
    p.add_argument("--post_check_module")

    args = p.parse_args()

    # ✅ 关键：--config None 归一化，避免 open("None")
    args.config = normalize_value(args.config)

    return args


def _replace_vn_in_obj(obj, new_vn: str, path: str = "cfg"):
    changed = []

    if isinstance(obj, str):
        if "vN" not in obj:
            return obj, changed
        new_obj = obj.replace("vN", new_vn)
        if new_obj != obj:
            changed.append((path, obj, new_obj))
        return new_obj, changed

    if isinstance(obj, list):
        new_list = []
        for i, item in enumerate(obj):
            new_item, sub_changed = _replace_vn_in_obj(item, new_vn, f"{path}[{i}]")
            new_list.append(new_item)
            changed.extend(sub_changed)
        return new_list, changed

    if isinstance(obj, dict):
        new_dict = {}
        for k, v in obj.items():
            sub_path = f"{path}.{k}"
            new_v, sub_changed = _replace_vn_in_obj(v, new_vn, sub_path)
            new_dict[k] = new_v
            changed.extend(sub_changed)
        return new_dict, changed

    return obj, changed


def update_gt_tag_and_path(cfg):
    gt_version = cfg.get("gt_version")
    if not gt_version:
        return cfg

    new_vn = f"v{gt_version}"
    cfg_replaced, changed = _replace_vn_in_obj(cfg, new_vn)
    if changed:
        print(cf.green(f"GT_VERSION: {gt_version} | 替换 {len(changed)} 处 vN"))
        for path, old, new in changed[:20]:
            print(cf.cyan(f"{path}: {old} -> {new}"))
        if len(changed) > 20:
            print(cf.cyan(f"... 其余 {len(changed) - 20} 处省略"))
    return cfg_replaced



def load_config_yaml(path):
    # ✅ path 为 None 就不读
    if path is None:
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def rewrite_output_dir_for_test(output_dir: str | None) -> str | None:
    if not output_dir:
        return output_dir

    p = Path(output_dir)
    parts = list(p.parts)
    mapping = {
        "outputs": "test_outputs",
        "outputs_steps": "test_outputs_steps",
        "outputs_failed": "test_outputs_failed",
    }
    if any(part in {"test_outputs", "test_outputs_steps", "test_outputs_failed"} for part in parts):
        return str(p)
    for i, part in enumerate(parts):
        if part in mapping:
            parts[i] = mapping[part]
            return str(Path(*parts))

    if p.is_absolute():
        return str(p.parent / "test_outputs" / p.name)
    return str(Path("test_outputs") / p)


def resolve_config(args, cfg_yaml):
    """
    优先级：DEFAULT < YAML < CLI

    yaml 支持：
    - 扁平写法：output_dir: xxx / extra: {...}
    - 分组写法：input/model/runtime/output 等 dict 会被展开到顶层
    - ✅ extra 不会被展开到顶层，只会进入 cfg["extra"]

    修复：
    - YAML flatten 的 kk/vv 也会 normalize（"None" -> None）
    - CLI merge 的值也会 normalize（"None" -> None）
    """
    cfg = dict(DEFAULT_CONFIG)

    # ===== YAML merge =====
    yaml_extra = {}

    if cfg_yaml and isinstance(cfg_yaml, dict):
        for k, v in cfg_yaml.items():
            # ✅ extra 不展开，只收集
            if k == "extra" and isinstance(v, dict):
                # 也可以 normalize extra 里的值（可选；这里顺手做了）
                yaml_extra = {ek: normalize_value(ev) for ek, ev in v.items()}
                continue

            # 其它 dict 仍展开到顶层（保持你原来的行为）
            if isinstance(v, dict):
                for kk, vv in v.items():
                    vv = normalize_value(vv)
                    if vv is not None:
                        cfg[kk] = vv
            else:
                v = normalize_value(v)
                if v is not None:
                    cfg[k] = v

    # ===== CLI merge =====
    # CLI 覆盖（保持不变的策略：v is not None 才覆盖）
    for k, v in vars(args).items():
        if k == "config":
            continue
        v = normalize_value(v)
        if v is not None:
            cfg[k] = v

    # ===== extra merge (DEFAULT < YAML < CLI) =====
    # 目前没有 --extra_* 的 CLI 参数，所以只做 DEFAULT < YAML
    base_extra = dict(DEFAULT_CONFIG.get("extra", {}))
    base_extra.update(yaml_extra)
    cfg["extra"] = base_extra

    # ======== 
    cfg = update_gt_tag_and_path(cfg)

    if cfg.get("test"):
        old_output_dir = cfg.get("output_dir")
        cfg["output_dir"] = rewrite_output_dir_for_test(old_output_dir)
        print(cf.cyan(f"test=True，output_dir: {old_output_dir} -> {cfg['output_dir']}"))

    print(cf.green(cfg))

    return cfg


# （可选）如果你希望这个文件可直接运行：
if __name__ == "__main__":
    args = parse_args()
    cfg_yaml = load_config_yaml(args.config)
    cfg = resolve_config(args, cfg_yaml)
