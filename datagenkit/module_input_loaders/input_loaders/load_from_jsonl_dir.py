import os
import json
from pathlib import Path

# 上一轮输出格式

def load_from_jsonl_dir(jsonl_dir: str, sample_n_per_ds=None):
    print(f"🚀 开始从 jsonl_dir 加载: {jsonl_dir}")

    jsonl_dir = os.path.abspath(jsonl_dir)
    data = []
    dataset_counter = {}

    # jsonl_files = sorted(Path(jsonl_dir).glob("*.jsonl"))

    jsonl_dir = Path(jsonl_dir)

    import time
    from datetime import datetime
    while True:
        jsonl_files = sorted(jsonl_dir.glob("*.jsonl"))
        if jsonl_files:
            print(f"✅ [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检测到 jsonl 文件，继续执行")
            break

        print(f"⏳ [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 未检测到 jsonl 文件，5 分钟后重试")
        time.sleep(5 * 60)

    for p in jsonl_files:
        print(f"  读取文件: {p.name}")
        # print(cf.yellow(p))
        with open(p, "r", encoding="utf-8") as f:
            for line_idx, line in enumerate(f):
                if not line.strip():
                    continue

                try:
                    item = json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"  JSON解析失败 {p}:{line_idx+1} | {e}")
                    continue

                ds = item.get("dataset_name") or p.stem

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

    print(f"📂 从 jsonl_dir 加载到 {len(data)} 条数据")

    return data