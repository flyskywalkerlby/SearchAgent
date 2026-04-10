from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Build query->images GT from image->matched_queries outputs")
    parser.add_argument("--input", required=True, help="input output jsonl path")
    parser.add_argument("--output", required=True, help="output gt jsonl path")
    return parser.parse_args()


def main():
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    query_to_images = defaultdict(set)

    with input_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            record = json.loads(line)
            output = record.get("output") or {}
            image = output.get("image")
            matched_queries = output.get("matched_queries") or []

            if not isinstance(image, str):
                continue
            if not isinstance(matched_queries, list):
                continue

            for query in matched_queries:
                if isinstance(query, str) and query.strip():
                    query_to_images[query].add(image)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for query in sorted(query_to_images.keys()):
            images = sorted(query_to_images[query])
            f.write(json.dumps({query: images}, ensure_ascii=False) + "\n")

    print(f"done: {output_path}")
    print(f"queries: {len(query_to_images)}")


if __name__ == "__main__":
    main()
