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


def normalize_image_key(image: str, root: str = "") -> str:
    image = str(image or "").strip().replace("\\", "/")
    root = str(root or "").strip().replace("\\", "/").rstrip("/")
    if not image:
        return ""
    if root and image.startswith(root + "/"):
        image = image[len(root) + 1:]
    image = image.lstrip("./")
    if "/" in image:
        image = Path(image).name
    return image


def init_view_data():
    return {
        "image_map": {},
        "queries_by_image": {},
        "query_results_by_image": {},
        "roots": {},
        "image_order": [],
        "meta": {"records": 0, "skipped": 0, "kind": "unknown"},
    }


def register_image(view_data, image: str, root: str):
    if image not in view_data["image_map"]:
        view_data["image_order"].append(image)
    view_data["image_map"][image] = True
    view_data["queries_by_image"].setdefault(image, set())
    if root and image not in view_data["roots"]:
        view_data["roots"][image] = root


def add_queries(view_data, image: str, queries):
    if not isinstance(queries, list):
        return
    for query in queries:
        if isinstance(query, str) and query.strip():
            view_data["queries_by_image"][image].add(query.strip())


def pick_top_level_queries(record: dict):
    for key in ("candidate_queries", "new_queries", "old_queries"):
        value = record.get(key)
        if isinstance(value, list):
            return value
    return []


def parse_gt_record(path: Path, record: dict, view_data) -> bool:
    if not (isinstance(record, dict) and len(record) == 1):
        return False

    query, images = next(iter(record.items()))
    if not isinstance(query, str) or not isinstance(images, list):
        return False

    root = infer_root(path, record)
    view_data["meta"]["kind"] = "query_to_images"
    for image in images:
        if not isinstance(image, str) or not image.strip():
            continue
        image = normalize_image_key(image, root)
        if not image:
            continue
        register_image(view_data, image, root)
        view_data["queries_by_image"][image].add(query.strip())
    return True


def parse_output_record(path: Path, record: dict, view_data) -> bool:
    output = record.get("output")
    if not isinstance(output, dict):
        return False

    root = infer_root(path, record)
    image = output.get("image") or record.get("image")
    if not isinstance(image, str) or not image.strip():
        return False
    image = normalize_image_key(image, root)
    if not image:
        return False

    matched_queries = output.get("matched_queries")
    if isinstance(matched_queries, list):
        view_data["meta"]["kind"] = "image_to_queries"
        register_image(view_data, image, root)
        add_queries(view_data, image, matched_queries)
        return True

    query_results = output.get("query_results")
    if not isinstance(query_results, dict):
        legacy_results = output.get("results")
        if isinstance(legacy_results, dict):
            query_results = legacy_results
    if isinstance(query_results, dict):
        view_data["meta"]["kind"] = "image_to_query_results"
        register_image(view_data, image, root)
        view_data["query_results_by_image"].setdefault(image, {})
        for query, result in query_results.items():
            if not isinstance(query, str) or not query.strip() or not isinstance(result, dict):
                continue
            clean_query = query.strip()
            view_data["query_results_by_image"][image][clean_query] = result
            if result.get("is_present") is True:
                view_data["queries_by_image"][image].add(clean_query)
        return True

    return False


def parse_top_level_image_record(path: Path, record: dict, view_data) -> bool:
    image = record.get("image")
    if not isinstance(image, str) or not image.strip():
        return False

    root = infer_root(path, record)
    image = normalize_image_key(image, root)
    if not image:
        return False

    if view_data["meta"]["kind"] == "unknown":
        view_data["meta"]["kind"] = "image_records"
    register_image(view_data, image, root)
    add_queries(view_data, image, pick_top_level_queries(record))
    return True


def load_compare_data(path: Path):
    view_data = init_view_data()

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            view_data["meta"]["records"] += 1

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                view_data["meta"]["skipped"] += 1
                continue

            if parse_gt_record(path, record, view_data):
                continue
            if parse_output_record(path, record, view_data):
                continue
            if parse_top_level_image_record(path, record, view_data):
                continue

            view_data["meta"]["skipped"] += 1

    view_data["queries_by_image"] = {
        image: sorted(queries)
        for image, queries in view_data["queries_by_image"].items()
    }
    return view_data

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



def compute_diff_stats(old_map, new_map, new_present_images, visible_image_ids):
    old_images = set(old_map.keys())
    new_images = set(new_present_images)
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
old_data = load_compare_data(old_path)

new_data = []
for label in new_labels:
    path = Path(new_options[label])
    data = load_compare_data(path)
    data["label"] = label
    data["path"] = path
    new_data.append(data)

show_only_diff = st.checkbox("Only show images with diffs", value=False)
show_overall_results = st.checkbox("Show overall results", value=False)
image_filter = st.text_input("Filter image id contains", value="").strip().lower()

image_ids = list(old_data["image_order"])

if image_filter:
    image_ids = [image for image in image_ids if image_filter in image.lower()]

if show_only_diff and new_data:
    filtered = []
    for image in image_ids:
        old_queries = set(old_data["queries_by_image"].get(image, []))
        keep_any_diff = False
        for item in new_data:
            new_queries = set(item["queries_by_image"].get(image, []))
            if old_queries != new_queries:
                keep_any_diff = True
                break
        if keep_any_diff:
            filtered.append(image)
    image_ids = filtered

st.caption(
    f"Old images: {len(old_data['image_map'])} | "
    f"Visible images: {len(image_ids)} | "
    f"Old records: {old_data['meta']['records']} | skipped: {old_data['meta']['skipped']}"
)

for item in new_data:
    common = len(set(old_data["image_map"].keys()) & set(item["image_map"].keys()))
    st.caption(
        f"New: {item['label']} | images: {len(item['image_map'])} | "
        f"common_with_old: {common} | skipped: {item['meta']['skipped']}"
    )

if show_overall_results and new_data:
    st.markdown("### Overall Results")
    for item in new_data:
        stats = compute_diff_stats(
            old_data["queries_by_image"],
            item["queries_by_image"],
            item["image_map"].keys(),
            image_ids,
        )
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
old_queries = old_data["queries_by_image"].get(image_id, [])
image_root = old_data["roots"].get(image_id, "")
image_path = os.path.join(image_root, image_id) if image_root else image_id

st.markdown(f"### Image: {image_id}")

top_cols = st.columns([1.1, 1.4])
with top_cols[0]:
    if image_root and os.path.exists(image_path):
        st.image(image_path, caption=image_id, width="stretch")
    else:
        st.error(f"❌ {image_id}")
        if image_root:
            st.caption(image_root)

with top_cols[1]:
    render_query_block(f"Old: {old_label}", old_queries)
    for item in new_data:
        st.divider()
        present_in_new = image_id in item["image_map"]
        new_queries = item["queries_by_image"].get(image_id, [])
        new_query_results = item["query_results_by_image"].get(image_id, {})
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
            st.warning(
                f"状态：new 中不存在该图片，可能还没处理到，或者处理失败。图片路径：{image_path}"
            )
