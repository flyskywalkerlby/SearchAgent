import os
import json
from utils import format_id

def load_from_meta_json(meta_path: str, sample_n_per_ds=None):
    print(f"🚀 开始加载 meta: {meta_path}")
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    print(f"成功加载meta文件，包含 {len(meta)} 个数据集")

    data = []
    for ds_name, info in meta.items():
        ann = info["annotation"]
        root = info["root"]

        print(f"正在处理数据集: {ds_name}")
        print(f"  Annotation文件: {ann}")
        print(f"  Root路径: {root}")

        if not os.path.exists(ann):
            print(f"  警告: annotation文件不存在: {ann}")
            continue

        dataset_count = 0
        try:
            with open(ann, "r", encoding="utf-8") as f_ann:
                for line_idx, line in enumerate(f_ann):
                    if sample_n_per_ds is not None and dataset_count >= sample_n_per_ds:
                        break

                    line = line.strip()
                    if not line:
                        continue

                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError as e:
                        print(f"  第{line_idx+1}行JSON解析错误: {e}")
                        continue

                    item["root"] = root
                    item.setdefault("dataset_name", ds_name)

                    item["raw_id"] = int(line_idx)

                    if item.get("id") is None:
                        item["id"] = format_id(line_idx)

                    data.append(item)
                    dataset_count += 1

            print(f"  成功加载 {dataset_count} 条数据")
        except Exception as e:
            print(f"  读取annotation文件失败: {e}")

    print(f"总共加载了 {len(data)} 条数据")
    return data