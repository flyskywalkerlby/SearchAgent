"""
Run:
python datagenkit/pools_gather/gather_life.py
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
INPUT_JSONL = REPO_ROOT / "datagenkit" / "outputs" / "gt_fix" / "test_imgs_image_multi_query_step2_122b" / "test_imgs_gt_fix.jsonl"
OUTPUT_DIR = REPO_ROOT / "gt_optimization" / "gt_refine_20260415"
QUERY2IMAGES_PATH = OUTPUT_DIR / "life_query2images.jsonl"
IMAGE2QUERIES_PATH = OUTPUT_DIR / "life_image2queries.jsonl"


def load_query_results(record: dict) -> dict:
    output = record.get("output") or {}
    query_results = output.get("query_results")
    if isinstance(query_results, dict):
        return query_results

    legacy_results = output.get("results")
    if isinstance(legacy_results, dict):
        return legacy_results

    step2_results = ((record.get("outputs") or {}).get("split_query_batch") or {}).get("results")
    if isinstance(step2_results, dict):
        return step2_results

    return {}


def main():
    if not INPUT_JSONL.exists():
        raise SystemExit(f"input not found: {INPUT_JSONL}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    image2queries = []
    query2images = defaultdict(list)

    with INPUT_JSONL.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            record = json.loads(line)
            image = record.get("image") or (record.get("output") or {}).get("image")
            root = record.get("root") or (record.get("output") or {}).get("root") or ""
            if not isinstance(image, str) or not image.strip():
                continue
            image = image.strip()

            query_results = load_query_results(record)
            positive_queries = {}
            for query, result in query_results.items():
                if not isinstance(query, str) or not query.strip() or not isinstance(result, dict):
                    continue
                if result.get("is_present") is not True:
                    continue
                clean_query = query.strip()
                item = {
                    "is_main_subject": bool(result.get("is_main_subject")),
                    "importance_score": int(result.get("importance_score", 0)),
                    "location": str(result.get("location", "") or ""),
                    "analysis": str(result.get("analysis", "") or ""),
                }
                positive_queries[clean_query] = item
                query2images[clean_query].append({
                    "image": image,
                    "root": root,
                    **item,
                })

            image2queries.append({
                "image": image,
                "root": root,
                "queries": dict(sorted(positive_queries.items(), key=lambda x: x[0])),
            })

    image2queries.sort(key=lambda x: x["image"])
    for query, items in query2images.items():
        items.sort(key=lambda x: (-x["importance_score"], x["image"]))

    with QUERY2IMAGES_PATH.open("w", encoding="utf-8") as f:
        for query in sorted(query2images.keys()):
            f.write(json.dumps({"query": query, "items": query2images[query]}, ensure_ascii=False) + "\n")

    with IMAGE2QUERIES_PATH.open("w", encoding="utf-8") as f:
        for item in image2queries:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"input            : {INPUT_JSONL}")
    print(f"query2images     : {QUERY2IMAGES_PATH}")
    print(f"image2queries    : {IMAGE2QUERIES_PATH}")
    print(f"images           : {len(image2queries)}")
    print(f"queries          : {len(query2images)}")


if __name__ == "__main__":
    main()
