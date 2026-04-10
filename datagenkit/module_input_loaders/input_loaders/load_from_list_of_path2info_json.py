import json

from .load_from_path2info_json import load_from_path2info_json


def load_from_list_of_path2info_json(list_json_path: str, sample_n_per_ds=None):
    print(f"🚀 开始从 list_of_path2info_json 加载: {list_json_path}")

    with open(list_json_path, "r", encoding="utf-8") as f:
        data_list = json.load(f)

    if not isinstance(data_list, dict):
        raise ValueError(f"list_of_path2info_json 必须是 dict，实际是 {type(data_list).__name__}")

    data = []
    for dataset_name, dataset_meta in data_list.items():
        if not isinstance(dataset_meta, dict):
            raise ValueError(f"{dataset_name}: list meta 必须是 dict，实际是 {type(dataset_meta).__name__}")

        if "skip" not in dataset_meta:
            raise ValueError(f"{dataset_name}: list meta 缺少 skip")
        if dataset_meta["skip"] is True:
            print(f"⏭️ 跳过数据集 {dataset_name}: skip=True")
            continue

        if "json" not in dataset_meta:
            raise ValueError(f"{dataset_name}: list meta 缺少 json")

        data.extend(
            load_from_path2info_json(
                dataset_meta["json"],
                dataset_name,
                sample_n_per_ds,
            )
        )

    print(f"📂 从 list_of_path2info_json 加载到 {len(data)} 条数据")
    return data
