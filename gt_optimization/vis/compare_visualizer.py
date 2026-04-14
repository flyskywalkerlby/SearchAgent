import json
import os
from pathlib import Path

import streamlit as st


st.set_page_config(layout="wide")

ROOT_BY_JSONL = {
    "card_20251218_q2i_manucheck.jsonl": "/srv/workspace/Kirin_AI_Workspace/AIC_I/g30064845/VLM/Chinese-CLIP/datasets/from_tuku_test_3k_together/card",
    "test_imgs_rename_20251209_q2i_supplement_removelowSim_0.2.jsonl": "/srv/workspace/Kirin_AI_Workspace/TMG_II/s00913809/projects/multi-modal/data/image-caption/test/caption_1k/test_imgs_rename",
}

WORKSPACE_DIR = Path(__file__).resolve().parents[2]
GT_DIR = WORKSPACE_DIR / "gt_optimization" / "gt"
OUTPUTS_DIR = WORKSPACE_DIR / "datagenkit" / "outputs"
CACHE_DIR = WORKSPACE_DIR / "datagenkit" / "cache"


st.title("JSONL Compare Visualizer")


def collect_jsonl_files(root_dirs):
    files = []
    for root_dir in root_dirs:
        if not root_dir.exists():
            continue
        for path in sorted(root_dir.rglob("*.jsonl")):
            files.append(path)
    return files


def infer_root(path: Path, record: dict) -> str:
    if isinstance(record, dict):
        root = record.get("root")
        if isinstance(root, str) and root.strip():
            return root
        output = record.get("output")
        if isinstance(output, dict):
            out_root = output.get("root")
            if isinstance(out_root, str) and out_root.strip():
                return out_root
    return ROOT_BY_JSONL.get(path.name, "")


def load_image_query_map(path: Path):
    image_to_queries = {}
    image_to_query_results = {}
    image_to_root = {}
    image_order = []
    meta = {"records": 0, "skipped": 0, "kind": "unknown"}

    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            meta["records"] += 1

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                meta["skipped"] += 1
                continue

            if isinstance(record, dict) and len(record) == 1:
                query, images = next(iter(record.items()))
                if isinstance(query, str) and isinstance(images, list):
                    meta["kind"] = "query_to_images"
                    root = infer_root(path, record)
                    for image in images:
                        if not isinstance(image, str) or not image.strip():
                            continue
                        image = image.strip()
                        if image not in image_to_queries:
                            image_order.append(image)
                        image_to_queries.setdefault(image, set()).add(query)
                        if root and image not in image_to_root:
                            image_to_root[image] = root
                    continue

            if isinstance(record, dict):
                output = record.get("output")
                if isinstance(output, dict):
                    image = output.get("image")
                    matched_queries = output.get("matched_queries")
                    if isinstance(image, str) and isinstance(matched_queries, list):
                        meta["kind"] = "image_to_queries"
                        root = infer_root(path, record)
                        image = image.strip()
                        if image not in image_to_queries:
                            image_order.append(image)
                        image_to_queries.setdefault(image, set())
                        for query in matched_queries:
                            if isinstance(query, str) and query.strip():
                                image_to_queries.setdefault(image, set()).add(query.strip())
                        if root and image not in image_to_root:
                            image_to_root[image] = root
                        continue

                    query_results = output.get("query_results")
                    if isinstance(image, str) and isinstance(query_results, dict):
                        meta["kind"] = "image_to_query_results"
                        root = infer_root(path, record)
                        image = image.strip()
                        if image not in image_to_queries:
                            image_order.append(image)
                        image_to_queries.setdefault(image, set())
                        image_to_query_results.setdefault(image, {})
                        for query, result in query_results.items():
                            if not isinstance(query, str) or not query.strip() or not isinstance(result, dict):
                                continue
                            clean_query = query.strip()
                            image_to_query_results[image][clean_query] = result
                            if result.get("is_present") is True:
                                image_to_queries.setdefault(image, set()).add(clean_query)
                        if root and image not in image_to_root:
                            image_to_root[image] = root
                        continue

            meta["skipped"] += 1

    image_to_queries = {
        image: sorted(queries)
        for image, queries in image_to_queries.items()
    }
    return image_to_queries, image_to_query_results, image_to_root, meta, image_order


@st.cache_data(show_spinner=False)
def cached_load(path_str: str):
    return load_image_query_map(Path(path_str))


@st.cache_data(show_spinner=False)
def cached_load_v3(path_str: str):
    return load_image_query_map(Path(path_str))


def path_label(path: Path) -> str:
    try:
        return str(path.relative_to(WORKSPACE_DIR))
    except ValueError:
        return str(path)


def render_query_block(title: str, queries: list[str]):
    st.markdown(f"#### {title}")
    st.write(f"{len(queries)} queries")
    if queries:
        st.code("\n".join(queries), language="text")
    else:
        st.caption("empty")


def render_query_results_block(title: str, query_results: dict[str, dict]):
    st.markdown(f"#### {title}")
    st.write(f"{len(query_results)} queries")
    if not query_results:
        st.caption("empty")
        return

    lines = []
    for idx, (query, result) in enumerate(query_results.items(), start=1):
        lines.append(f"[{idx}] {query}")
        lines.append(
            "  is_present={} | is_main_subject={} | importance_score={} | location={}".format(
                result.get("is_present"),
                result.get("is_main_subject"),
                result.get("importance_score"),
                result.get("location", ""),
            )
        )
        lines.append(f"  analysis: {result.get('analysis', '')}")
        lines.append("")
    st.code("\n".join(lines).rstrip(), language="text")



def compute_diff_stats(old_map, new_map, visible_image_ids):
    old_images = set(old_map.keys())
    new_images = set(new_map.keys())
    common_images = old_images & new_images
    missing_in_new_images = old_images - new_images
    new_only_images = new_images - old_images

    keep_pairs = 0
    add_pairs = 0
    delete_pairs = 0
    add_image_ids = []
    delete_image_ids = []

    for image in sorted(common_images):
        old_set = set(old_map.get(image, []))
        new_set = set(new_map.get(image, []))
        add_for_image = new_set - old_set
        delete_for_image = old_set - new_set
        keep_pairs += len(old_set & new_set)
        add_pairs += len(add_for_image)
        delete_pairs += len(delete_for_image)
        if add_for_image:
            add_image_ids.append(image)
        if delete_for_image:
            delete_image_ids.append(image)

    return {
        "old_images": len(old_images),
        "new_images": len(new_images),
        "common_images": len(common_images),
        "missing_in_new_images": len(missing_in_new_images),
        "new_only_images": len(new_only_images),
        "keep_pairs": keep_pairs,
        "add_pairs": add_pairs,
        "delete_pairs": delete_pairs,
        "add_image_count": len(add_image_ids),
        "delete_image_count": len(delete_image_ids),
        "add_image_ids": add_image_ids,
        "delete_image_ids": delete_image_ids,
        "add_image_idxs": [idx for idx, image in enumerate(visible_image_ids) if image in set(add_image_ids)],
        "delete_image_idxs": [idx for idx, image in enumerate(visible_image_ids) if image in set(delete_image_ids)],
    }


old_files = collect_jsonl_files([GT_DIR])
new_files = collect_jsonl_files([OUTPUTS_DIR, CACHE_DIR])
old_options = {path_label(p): str(p) for p in old_files}
new_options = {path_label(p): str(p) for p in new_files}

if not old_options:
    st.warning("没有找到可用的 old jsonl 文件")
    st.stop()

if not new_options:
    st.warning("没有找到可用的 new jsonl 文件")
    st.stop()

old_label = st.selectbox("Old JSONL", list(old_options.keys()))
new_labels = st.multiselect(
    "New JSONLs",
    list(new_options.keys()),
)

old_path = Path(old_options[old_label])
old_map, old_query_results_map, old_roots, old_meta, old_image_order = cached_load_v3(str(old_path))

new_data = []
for label in new_labels:
    path = Path(new_options[label])
    new_map, new_query_results_map, new_roots, new_meta, new_image_order = cached_load_v3(str(path))
    new_data.append({
        "label": label,
        "path": path,
        "map": new_map,
        "query_results_map": new_query_results_map,
        "roots": new_roots,
        "meta": new_meta,
        "image_order": new_image_order,
    })

show_only_diff = st.checkbox("Only show images with diffs", value=False)
show_overall_results = st.checkbox("Show overall results", value=False)
image_filter = st.text_input("Filter image id contains", value="").strip().lower()

image_ids = list(old_image_order)

if image_filter:
    image_ids = [image for image in image_ids if image_filter in image.lower()]

if show_only_diff and new_data:
    filtered = []
    for image in image_ids:
        old_queries = set(old_map.get(image, []))
        keep_any_diff = False
        for item in new_data:
            new_queries = set(item["map"].get(image, []))
            if old_queries != new_queries:
                keep_any_diff = True
                break
        if keep_any_diff:
            filtered.append(image)
    image_ids = filtered

st.caption(
    f"Old images: {len(old_map)} | "
    f"Visible images: {len(image_ids)} | "
    f"Old records: {old_meta['records']} | skipped: {old_meta['skipped']}"
)

for item in new_data:
    common = len(set(old_map.keys()) & set(item["map"].keys()))
    st.caption(
        f"New: {item['label']} | images: {len(item['map'])} | "
        f"common_with_old: {common} | skipped: {item['meta']['skipped']}"
    )

if show_overall_results and new_data:
    st.markdown("### Overall Results")
    for item in new_data:
        stats = compute_diff_stats(old_map, item["map"], image_ids)
        st.markdown(f"#### New: {item['label']}")
        cols = st.columns(10)
        labels = [
            ("old_images", "Old 图片"),
            ("new_images", "New 图片"),
            ("common_images", "共有图片"),
            ("missing_in_new_images", "New 缺失图片"),
            ("new_only_images", "New 独有图片"),
            ("keep_pairs", "Keep"),
            ("add_pairs", "Add"),
            ("delete_pairs", "Delete"),
            ("add_image_count", "Add 图片数"),
            ("delete_image_count", "Delete 图片数"),
        ]
        for col, (key, label) in zip(cols, labels):
            col.metric(label, stats[key])
        st.caption(f"Add 图片 idx: {stats['add_image_idxs']}")
        st.caption(f"Delete 图片 idx: {stats['delete_image_idxs']}")

if not image_ids:
    st.warning("没有可展示的图片")
    st.stop()

if "compare_idx" not in st.session_state:
    st.session_state.compare_idx = 0
if "compare_num_idx" not in st.session_state:
    st.session_state.compare_num_idx = 0
if "compare_slider_idx" not in st.session_state:
    st.session_state.compare_slider_idx = 0
if "compare_last_old" not in st.session_state:
    st.session_state.compare_last_old = None


def sync_widgets():
    st.session_state.compare_num_idx = st.session_state.compare_idx
    st.session_state.compare_slider_idx = st.session_state.compare_idx


def set_idx_from_num():
    st.session_state.compare_idx = int(st.session_state.compare_num_idx)
    st.session_state.compare_slider_idx = st.session_state.compare_idx


def set_idx_from_slider():
    st.session_state.compare_idx = int(st.session_state.compare_slider_idx)
    st.session_state.compare_num_idx = st.session_state.compare_idx


state_key = (old_label, tuple(new_labels), show_only_diff, image_filter)
if st.session_state.compare_last_old != state_key:
    st.session_state.compare_idx = 0
    st.session_state.compare_last_old = state_key
    sync_widgets()

st.session_state.compare_idx = max(0, min(st.session_state.compare_idx, len(image_ids) - 1))
sync_widgets()


def prev_item():
    st.session_state.compare_idx = max(0, st.session_state.compare_idx - 1)
    sync_widgets()


def next_item():
    st.session_state.compare_idx = min(len(image_ids) - 1, st.session_state.compare_idx + 1)
    sync_widgets()


nav_cols = st.columns([1, 1, 1, 1, 1])
with nav_cols[0]:
    st.button("◀ Prev", on_click=prev_item)
with nav_cols[1]:
    st.number_input(
        "Idx",
        min_value=0,
        max_value=len(image_ids) - 1,
        step=1,
        key="compare_num_idx",
        on_change=set_idx_from_num,
    )
with nav_cols[2]:
    st.slider(
        "Slider",
        min_value=0,
        max_value=len(image_ids) - 1,
        key="compare_slider_idx",
        on_change=set_idx_from_slider,
    )
with nav_cols[3]:
    st.write(f"**{st.session_state.compare_idx + 1} / {len(image_ids)}**")
with nav_cols[4]:
    st.button("Next ▶", on_click=next_item)

image_id = image_ids[st.session_state.compare_idx]
old_queries = old_map.get(image_id, [])
image_root = old_roots.get(image_id, "")
image_path = os.path.join(image_root, image_id) if image_root else image_id

st.markdown(f"### Image: {image_id}")

top_cols = st.columns([1.1, 1.4])
with top_cols[0]:
    if image_root and os.path.exists(image_path):
        st.image(image_path, caption=image_id, use_container_width=True)
    else:
        st.error(f"❌ {image_id}")
        if image_root:
            st.caption(image_root)

with top_cols[1]:
    render_query_block(f"Old: {old_label}", old_queries)
    for item in new_data:
        st.divider()
        present_in_new = image_id in item["map"] or image_id in item["query_results_map"]
        new_queries = item["map"].get(image_id, [])
        new_query_results = item["query_results_map"].get(image_id, {})
        old_set = set(old_queries)
        new_set = set(new_queries)
        if present_in_new:
            keep = sorted(old_set & new_set)
            add = sorted(new_set - old_set)
            delete = sorted(old_set - new_set)
        else:
            keep = []
            add = []
            delete = []

        if new_query_results:
            render_query_results_block(f"New: {item['label']}", new_query_results)
        else:
            render_query_block(f"New: {item['label']}", new_queries)
        diff_cols = st.columns([1, 1, 1])
        with diff_cols[0]:
            render_query_block("Keep", keep)
        with diff_cols[1]:
            render_query_block("Add", add)
        with diff_cols[2]:
            render_query_block("Delete", delete)
        if present_in_new:
            st.caption("状态：new 中存在该图片")
        else:
            st.warning("状态：new 中不存在该图片，可能还没处理到，或者处理失败")
