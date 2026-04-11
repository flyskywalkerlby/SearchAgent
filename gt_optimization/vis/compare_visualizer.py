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


def collect_jsonl_files():
    files = []
    for root_dir in [GT_DIR, OUTPUTS_DIR, CACHE_DIR]:
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
    image_to_root = {}
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
                        for query in matched_queries:
                            if isinstance(query, str) and query.strip():
                                image_to_queries.setdefault(image, set()).add(query.strip())
                        if root and image not in image_to_root:
                            image_to_root[image] = root
                        continue

            meta["skipped"] += 1

    image_to_queries = {
        image: sorted(queries)
        for image, queries in image_to_queries.items()
    }
    return image_to_queries, image_to_root, meta


@st.cache_data(show_spinner=False)
def cached_load(path_str: str):
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


all_files = collect_jsonl_files()
file_options = {path_label(p): str(p) for p in all_files}

if not file_options:
    st.warning("没有找到可用 jsonl 文件")
    st.stop()

primary_label = st.selectbox("Primary JSONL", list(file_options.keys()))
secondary_labels = st.multiselect(
    "Secondary JSONLs",
    [label for label in file_options.keys() if label != primary_label],
)

primary_path = Path(file_options[primary_label])
primary_map, primary_roots, primary_meta = cached_load(str(primary_path))

secondary_data = []
for label in secondary_labels:
    path = Path(file_options[label])
    sec_map, sec_roots, sec_meta = cached_load(str(path))
    secondary_data.append({
        "label": label,
        "path": path,
        "map": sec_map,
        "roots": sec_roots,
        "meta": sec_meta,
    })

show_only_diff = st.checkbox("Only show images with diffs", value=False)
image_filter = st.text_input("Filter image id contains", value="").strip().lower()

image_ids = sorted(primary_map.keys())

if image_filter:
    image_ids = [image for image in image_ids if image_filter in image.lower()]

if show_only_diff and secondary_data:
    filtered = []
    for image in image_ids:
        primary_queries = set(primary_map.get(image, []))
        keep_any_diff = False
        for item in secondary_data:
            secondary_queries = set(item["map"].get(image, []))
            if primary_queries != secondary_queries:
                keep_any_diff = True
                break
        if keep_any_diff:
            filtered.append(image)
    image_ids = filtered

st.caption(
    f"Primary images: {len(primary_map)} | "
    f"Visible images: {len(image_ids)} | "
    f"Primary records: {primary_meta['records']} | skipped: {primary_meta['skipped']}"
)

for item in secondary_data:
    common = len(set(primary_map.keys()) & set(item["map"].keys()))
    st.caption(
        f"Secondary: {item['label']} | images: {len(item['map'])} | "
        f"common_with_primary: {common} | skipped: {item['meta']['skipped']}"
    )

if not image_ids:
    st.warning("没有可展示的图片")
    st.stop()

if "compare_idx" not in st.session_state:
    st.session_state.compare_idx = 0
if "compare_num_idx" not in st.session_state:
    st.session_state.compare_num_idx = 0
if "compare_slider_idx" not in st.session_state:
    st.session_state.compare_slider_idx = 0
if "compare_last_primary" not in st.session_state:
    st.session_state.compare_last_primary = None


def sync_widgets():
    st.session_state.compare_num_idx = st.session_state.compare_idx
    st.session_state.compare_slider_idx = st.session_state.compare_idx


def set_idx_from_num():
    st.session_state.compare_idx = int(st.session_state.compare_num_idx)
    st.session_state.compare_slider_idx = st.session_state.compare_idx


def set_idx_from_slider():
    st.session_state.compare_idx = int(st.session_state.compare_slider_idx)
    st.session_state.compare_num_idx = st.session_state.compare_idx


state_key = (primary_label, tuple(secondary_labels), show_only_diff, image_filter)
if st.session_state.compare_last_primary != state_key:
    st.session_state.compare_idx = 0
    st.session_state.compare_last_primary = state_key
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
primary_queries = primary_map.get(image_id, [])
image_root = primary_roots.get(image_id, "")
image_path = os.path.join(image_root, image_id) if image_root else image_id

st.markdown(f"### Image: {image_id}")

top_cols = st.columns([1.2, 1.8])
with top_cols[0]:
    if image_root and os.path.exists(image_path):
        st.image(image_path, caption=image_id, use_container_width=True)
    else:
        st.error(f"❌ {image_id}")
        if image_root:
            st.caption(image_root)

with top_cols[1]:
    render_query_block(f"Primary: {primary_label}", primary_queries)

if secondary_data:
    compare_cols = st.columns(max(1, len(secondary_data)))
    for idx, item in enumerate(secondary_data):
        secondary_queries = item["map"].get(image_id, [])
        primary_set = set(primary_queries)
        secondary_set = set(secondary_queries)
        keep = sorted(primary_set & secondary_set)
        add = sorted(secondary_set - primary_set)
        delete = sorted(primary_set - secondary_set)

        with compare_cols[idx]:
            st.markdown(f"#### Compare: {item['label']}")
            st.write(f"present: {'yes' if image_id in item['map'] else 'no'}")
            st.write(f"keep={len(keep)} add={len(add)} delete={len(delete)}")
            if keep:
                st.caption("keep")
                st.code("\n".join(keep), language="text")
            if add:
                st.caption("add")
                st.code("\n".join(add), language="text")
            if delete:
                st.caption("delete")
                st.code("\n".join(delete), language="text")
            if not keep and not add and not delete:
                st.caption("no diff")
