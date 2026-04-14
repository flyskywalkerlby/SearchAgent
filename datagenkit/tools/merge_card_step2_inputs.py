import argparse
import json
from pathlib import Path


def format_id(i, w=5):
    try:
        return str(int(i)).zfill(w)
    except (ValueError, TypeError):
        return str(i)


def _append_query(image_to_queries, image_order, image, query):
    if image not in image_to_queries:
        image_to_queries[image] = []
        image_order.append(image)
    if query not in image_to_queries[image]:
        image_to_queries[image].append(query)


def load_image_query_map(path: Path):
    image_to_queries = {}
    image_order = []

    with path.open('r', encoding='utf-8') as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)

            if isinstance(record, dict) and len(record) == 1:
                query, images = next(iter(record.items()))
                if isinstance(query, str) and isinstance(images, list):
                    clean_query = query.strip()
                    for image in images:
                        if isinstance(image, str) and image.strip():
                            _append_query(image_to_queries, image_order, image.strip(), clean_query)
                    continue

            if isinstance(record, dict):
                output = record.get('output')
                if isinstance(output, dict):
                    image = output.get('image')
                    matched_queries = output.get('matched_queries')
                    if isinstance(image, str) and isinstance(matched_queries, list):
                        clean_image = image.strip()
                        for query in matched_queries:
                            if isinstance(query, str) and query.strip():
                                _append_query(image_to_queries, image_order, clean_image, query.strip())
                        continue

                    query_results = output.get('query_results')
                    if isinstance(image, str) and isinstance(query_results, dict):
                        clean_image = image.strip()
                        for query, result in query_results.items():
                            if not isinstance(query, str) or not query.strip() or not isinstance(result, dict):
                                continue
                            if result.get('is_present') is True:
                                _append_query(image_to_queries, image_order, clean_image, query.strip())
                        if clean_image not in image_to_queries:
                            image_to_queries[clean_image] = []
                            image_order.append(clean_image)
                        continue

            raise ValueError(f'无法解析记录: {path}:{line_no}')

    return image_to_queries, image_order


def merge_lists_keep_order(primary, secondary):
    merged = []
    seen = set()
    for item in list(primary) + list(secondary):
        if item not in seen:
            seen.add(item)
            merged.append(item)
    return merged


def main():
    parser = argparse.ArgumentParser(description='合并 card old/new 结果，生成 step2 候选输入')
    parser.add_argument('--old-jsonl', required=True)
    parser.add_argument('--new-jsonl', required=True)
    parser.add_argument('--root', required=True)
    parser.add_argument('--output-jsonl', required=True)
    parser.add_argument('--dataset-name', default='card_step2')
    args = parser.parse_args()

    old_path = Path(args.old_jsonl).expanduser().resolve()
    new_path = Path(args.new_jsonl).expanduser().resolve()
    output_path = Path(args.output_jsonl).expanduser().resolve()
    root = str(Path(args.root).expanduser().resolve())

    old_map, old_order = load_image_query_map(old_path)
    new_map, new_order = load_image_query_map(new_path)

    merged_image_order = merge_lists_keep_order(old_order, new_order)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_candidates = 0
    with output_path.open('w', encoding='utf-8') as f:
        for raw_id, image in enumerate(merged_image_order):
            old_queries = old_map.get(image, [])
            new_queries = new_map.get(image, [])
            candidate_queries = merge_lists_keep_order(old_queries, new_queries)
            overlap_queries = [q for q in old_queries if q in set(new_queries)]
            old_only_queries = [q for q in old_queries if q not in set(new_queries)]
            new_only_queries = [q for q in new_queries if q not in set(old_queries)]
            total_candidates += len(candidate_queries)

            rec = {
                'raw_id': raw_id,
                'id': format_id(raw_id),
                'image': image,
                'root': root,
                'dataset_name': args.dataset_name,
                'old_queries': old_queries,
                'new_queries': new_queries,
                'candidate_queries': candidate_queries,
                'overlap_queries': overlap_queries,
                'old_only_queries': old_only_queries,
                'new_only_queries': new_only_queries,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    print(f'old images         : {len(old_map)}')
    print(f'new images         : {len(new_map)}')
    print(f'merged images      : {len(merged_image_order)}')
    print(f'total candidates   : {total_candidates}')
    print(f'output jsonl       : {output_path}')


if __name__ == '__main__':
    main()
