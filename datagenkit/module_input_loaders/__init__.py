from .input_loaders.load_from_root import load_images_from_root
from .input_loaders.load_from_meta_json import load_from_meta_json
from .input_loaders.load_from_jsonl import load_from_jsonl
from .input_loaders.load_from_jsonl_dir import load_from_jsonl_dir
from .input_loaders.load_from_path2info_json import load_from_path2info_json
from .input_loaders.load_from_list_of_path2info_json import load_from_list_of_path2info_json
from .input_loaders.load_from_gt_jsonl import load_from_gt_jsonl

def load_input_data(cfg: dict):
    if cfg["input_type"] == "root":
        assert cfg["root"] and cfg["dataset_name"], "root 模式需要 --root 和 --dataset_name"
        return load_images_from_root(cfg["root"], cfg["dataset_name"], cfg["sample_n_per_ds"])

    if cfg["input_type"] == "meta":
        assert cfg["meta_json_path"], "meta 模式需要 --meta_json_path"
        return load_from_meta_json(cfg["meta_json_path"], cfg["sample_n_per_ds"])

    if cfg["input_type"] == "jsonl":
        assert cfg["jsonl_path"], "jsonl 模式需要 --jsonl_path"
        return load_from_jsonl(
            cfg["jsonl_path"],
            cfg["sample_n_per_ds"]
        )

    if cfg["input_type"] == "gt_jsonl":
        assert cfg["gt_jsonl_path"] and cfg["root"] and cfg["dataset_name"], "gt_jsonl 模式需要 --gt_jsonl_path --root --dataset_name"
        return load_from_gt_jsonl(
            cfg["gt_jsonl_path"],
            cfg["root"],
            cfg["dataset_name"],
        )

    if cfg["input_type"] == "jsonl_dir":
        assert cfg["jsonl_dir"], "jsonl_dir 模式需要 --jsonl_dir"
        return load_from_jsonl_dir(
            cfg["jsonl_dir"],
            cfg["sample_n_per_ds"]
        )

    if cfg["input_type"] == "path2info_json":
        assert cfg["json_path"] and cfg["dataset_name"], "path2info_json 模式需要 --json_path 和 --dataset_name"
        return load_from_path2info_json(
            cfg["json_path"],
            cfg["dataset_name"],
            cfg["sample_n_per_ds"]
        )

    if cfg["input_type"] == "list_of_path2info_json":
        assert cfg["list_json_path"], "list_of_path2info_json 模式需要 --list_json_path"
        return load_from_list_of_path2info_json(
            cfg["list_json_path"],
            cfg["sample_n_per_ds"]
        )

    raise ValueError(cfg["input_type"])
