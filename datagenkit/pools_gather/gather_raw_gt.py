"""
Run:
python datagenkit/pools_gather/gather_raw_gt.py
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "gt_optimization" / "gt_raw"

SPECS = [
    {
        "name": "card",
        "input": REPO_ROOT / "gt_optimization" / "gt" / "card_20251218_q2i_manucheck.jsonl",
        "root": "/srv/workspace/Kirin_AI_Workspace/AIC_I/g30064845/VLM/Chinese-CLIP/datasets/from_tuku_test_3k_together/card",
        "query2": OUTPUT_DIR / "card_query2images.jsonl",
        "image2": OUTPUT_DIR / "card_image2queries.jsonl",
    },
    {
        "name": "life",
        "input": REPO_ROOT / "gt_optimization" / "gt" / "test_imgs_rename_20251209_q2i_supplement_removelowSim_0.2.jsonl",
        "root": "/srv/workspace/Kirin_AI_Workspace/TMG_II/s00913809/projects/multi-modal/data/image-caption/test/caption_1k/test_imgs_rename",
        "query2": OUTPUT_DIR / "life_query2images.jsonl",
        "image2": OUTPUT_DIR / "life_image2queries.jsonl",
    },
]


def default_query_info():
    return {
        "is_main_subject": None,
        "importance_score": None,
        "location": "",
        "analysis": "",
    }


def convert_one(input_path: Path, root: str, query2_path: Path, image2_path: Path):
    query2images = defaultdict(list)
    image2queries = {}

    with input_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if not isinstance(record, dict) or len(record) != 1:
                continue
            query, images = next(iter(record.items()))
            if not isinstance(query, str) or not isinstance(images, list):
                continue

            clean_query = query.strip()
            for image in images:
                if not isinstance(image, str) or not image.strip():
                    continue
                image = image.strip()
                info = default_query_info()
                query2images[clean_query].append({
                    "image": image,
                    "root": root,
                    **info,
                })

                image2queries.setdefault(image, {
                    "image": image,
                    "root": root,
                    "queries": {},
                })
                image2queries[image]["queries"][clean_query] = default_query_info()

    for query, items in query2images.items():
        items.sort(key=lambda x: x["image"])
    image_records = []
    for image in sorted(image2queries.keys()):
        image_records.append({
            "image": image2queries[image]["image"],
            "root": image2queries[image]["root"],
            "queries": dict(sorted(image2queries[image]["queries"].items(), key=lambda x: x[0])),
        })

    query2_path.parent.mkdir(parents=True, exist_ok=True)
    with query2_path.open("w", encoding="utf-8") as f:
        for query in sorted(query2images.keys()):
            f.write(json.dumps({"query": query, "items": query2images[query]}, ensure_ascii=False) + "\n")

    with image2_path.open("w", encoding="utf-8") as f:
        for item in image_records:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"input            : {input_path}")
    print(f"query2images     : {query2_path}")
    print(f"image2queries    : {image2_path}")
    print(f"images           : {len(image_records)}")
    print(f"queries          : {len(query2images)}")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for spec in SPECS:
        if not spec["input"].exists():
            raise SystemExit(f"input not found: {spec['input']}")
        print(f"\n=== {spec['name']} ===")
        convert_one(
            input_path=spec["input"],
            root=spec["root"],
            query2_path=spec["query2"],
            image2_path=spec["image2"],
        )


if __name__ == "__main__":
    main()
