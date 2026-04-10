import json
import os

from tqdm import tqdm

from utils import format_id


def load_from_path2info_json(json_path: str, dataset_name: str, sample_n_per_ds=None):
    print(f"🚀 开始从 path2info json 加载: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        path2info = json.load(f)

    if not isinstance(path2info, dict):
        raise ValueError(f"path2info json 必须是 dict，实际是 {type(path2info).__name__}")

    items = list(path2info.items())
    if not items:
        print("📂 path2info json 为空")
        return []

    norm_image_paths = [
        os.path.abspath(os.path.normpath(image_path))
        for image_path, _ in tqdm(items, desc="解析图片路径", unit="img")
    ]

    if len(norm_image_paths) == 1:
        common_root = os.path.dirname(norm_image_paths[0])
    else:
        common_root = os.path.commonpath(norm_image_paths)

    data = []
    for raw_id, ((_, label), image_path) in enumerate(
        zip(tqdm(items, desc="构建样本", unit="img"), norm_image_paths)
    ):
        if sample_n_per_ds is not None and raw_id >= sample_n_per_ds:
            break

        data.append({
            "raw_id": raw_id,
            "id": format_id(raw_id),
            "root": common_root,
            "image": os.path.relpath(image_path, common_root),
            "dataset_name": dataset_name,
            "info": label,
        })

    print(f"📂 从 path2info json 加载到 {len(data)} 条数据")
    return data
