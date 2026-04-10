import json
from pathlib import Path

import colorful as cf

from utils import format_id


def load_from_gt_jsonl(gt_jsonl_path: str, root: str, dataset_name: str):
    gt_path = Path(gt_jsonl_path).expanduser().resolve()
    if not gt_path.exists():
        raise FileNotFoundError(f"gt_jsonl_path 不存在: {gt_path}")
    if not root:
        raise ValueError("gt_jsonl 模式需要 root")

    print(cf.green(f"🚀 开始从 GT jsonl 加载图片列表: {gt_path}"))

    seen = set()
    image_list = []

    with gt_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            obj = json.loads(line)
            if not isinstance(obj, dict) or len(obj) != 1:
                raise ValueError(f"{gt_path}:{line_no} 需要是单 key dict")

            _, images = next(iter(obj.items()))
            if not isinstance(images, list):
                raise ValueError(f"{gt_path}:{line_no} value 需要是 list")

            for image in images:
                if not isinstance(image, str) or not image.strip():
                    continue
                image = image.strip()
                if image in seen:
                    continue
                seen.add(image)
                image_list.append(image)

    image_list.sort(key=lambda x: (format_id(Path(x).stem.split("_")[0]), x))

    data = []
    for idx, image in enumerate(image_list):
        data.append({
            "raw_id": idx,
            "id": format_id(Path(image).stem.split("_")[0]),
            "image": image,
            "root": str(Path(root).expanduser().resolve()),
            "dataset_name": dataset_name,
        })

    print(cf.green(f"📂 从 GT jsonl 去重得到 {len(data)} 张图片"))
    return data
