import json

def load_from_jsonl(jsonl_path: str, sample_n_per_ds=None):
    print(f"🚀 开始从 jsonl 加载: {jsonl_path}")

    data = []
    dataset_counter = {}

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line_idx, line in enumerate(f):
            if not line.strip():
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  JSON解析失败 {jsonl_path}:{line_idx+1} | {e}")
                continue

            ds = item.get("dataset_name") or "UNKNOWN"

            if sample_n_per_ds is not None:
                cnt = dataset_counter.get(ds, 0)
                if cnt >= sample_n_per_ds:
                    continue
                dataset_counter[ds] = cnt + 1

            # data.append({
            #     "raw_id": int(item["raw_id"]),
            #     "id": item.get("id"),
            #     "image": item.get("image"),
            #     "root": item.get("root"),
            #     "dataset_name": ds,
            #     "output": item.get("output"),
            # })
            
            data.append(item)

    print(f"📂 从 jsonl 加载到 {len(data)} 条数据")
    return data
