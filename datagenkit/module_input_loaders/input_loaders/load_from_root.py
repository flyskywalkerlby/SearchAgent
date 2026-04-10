import os
from utils import format_id
from pathlib import Path
import colorful as cf


def load_images_from_root(root: str, dataset_name: str, sample_n_per_ds=None):
    root = os.path.abspath(root)
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

    print(f"🚀 开始从 root 加载图片: {root}")

    relpaths = []
    for dp, dirnames, fns in os.walk(root):
        dirnames.sort()
        for fn in fns:
            if Path(fn).suffix.lower() not in exts:
                continue
            relpaths.append(os.path.relpath(os.path.join(dp, fn), root))

    # ✅ 用 filename(不含后缀) 调 format_id，然后排序；再用完整相对路径兜底保证稳定
    def sort_key(rel: str):
        stem = Path(rel).stem               # filename without extension
        stem = stem.split("_")[0]           # id_{xxx}
        fid = format_id(stem)               # 你要求：不处理数字，直接调用
        return (fid, rel)                   # “format id 之后的完整路径排序”

    relpaths.sort(key=sort_key)

    if sample_n_per_ds is not None:
        relpaths = relpaths[:sample_n_per_ds]

    data = []
    for idx, rel in enumerate(relpaths):
        stem = Path(rel).stem
        fid = format_id(stem)

        data.append({
            "raw_id": idx,          # 运行序号（排序后重新编号）
            "id": fid,              # ✅ id 就用 filename->format_id 的结果
            "image": rel,
            "root": root,
            "dataset_name": dataset_name,
        })

    print(f"📂 从 {root} 加载到 {len(data)} 张图片")
    return data
