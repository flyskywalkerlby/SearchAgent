import json
import os
from pathlib import Path

import streamlit as st


st.set_page_config(layout="wide")

WORKSPACE_DIR = Path(__file__).resolve().parents[2]
GT_OPT_DIR = WORKSPACE_DIR / "gt_optimization"
RAW_DIR = GT_OPT_DIR / "gt_raw"
REFINE_DIRS = sorted(
    [
        p for p in GT_OPT_DIR.iterdir()
        if p.is_dir() and p.name.startswith("gt_refine")
    ],
    key=lambda p: p.name,
)
DATA_DIRS = [RAW_DIR, *REFINE_DIRS]


st.title("GT Visualizer")


def collect_files(mode: str):
    suffix = "_query2images.jsonl" if mode == "query2" else "_image2queries.jsonl"
    files = []
    for root_dir in DATA_DIRS:
        if not root_dir.exists():
            continue
        for path in sorted(root_dir.glob(f"*{suffix}")):
            files.append(path)
    return files


def path_label(path: Path) -> str:
    try:
        return str(path.relative_to(WORKSPACE_DIR))
    except ValueError:
        return str(path)


def load_query2_file(path: Path):
    query_order = []
    query_map = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            query = record.get("query")
            items = record.get("items")
            if not isinstance(query, str) or not isinstance(items, list):
                continue
            query_order.append(query)
            query_map[query] = items
    return {"order": query_order, "map": query_map}


def load_image2_file(path: Path):
    image_order = []
    image_map = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            image = record.get("image")
            root = record.get("root", "")
            queries = record.get("queries")
            if not isinstance(image, str) or not isinstance(queries, dict):
                continue
            image_order.append(image)
            image_map[image] = {
                "root": root,
                "queries": queries,
            }
    return {"order": image_order, "map": image_map}


def build_item_caption(item: dict) -> str:
    image = str(item.get("image", "") or "")
    extras = []
    if item.get("is_main_subject") is True:
        extras.append("main")
    score = item.get("importance_score")
    if score is not None:
        extras.append(f"score={score}")
    if extras:
        return f"{image} | {' | '.join(extras)}"
    return image


def render_query2_block(title: str, items: list[dict], columns_per_row: int):
    st.markdown(f"#### {title}")
    st.write(f"{len(items)} images")
    if not items:
        st.caption("empty")
        return

    cols = st.columns(columns_per_row)
    for idx, item in enumerate(items):
        image = str(item.get("image", "") or "")
        root = str(item.get("root", "") or "")
        image_path = os.path.join(root, image) if root else image
        with cols[idx % columns_per_row]:
            if root and os.path.exists(image_path):
                st.image(image_path, caption=build_item_caption(item), width="stretch")
            else:
                st.error(f"❌ {image}")
                if root:
                    st.caption(root)


def render_image2_block(title: str, queries: dict):
    st.markdown(f"#### {title}")
    st.write(f"{len(queries)} queries")
    if not queries:
        st.caption("empty")
        return

    lines = []
    for idx, (query, info) in enumerate(sorted(queries.items(), key=lambda x: x[0]), start=1):
        info = info if isinstance(info, dict) else {}
        lines.append(f"[{idx}] {query}")
        lines.append(
            "  is_main_subject={} | importance_score={} | location={}".format(
                info.get("is_main_subject"),
                info.get("importance_score"),
                info.get("location", ""),
            )
        )
        analysis = str(info.get("analysis", "") or "")
        if analysis:
            lines.append(f"  analysis: {analysis}")
        lines.append("")
    st.code("\n".join(lines).rstrip(), language="text")


mode = st.selectbox("Mode", ["query2", "image2"])
all_files = collect_files(mode)
options = {path_label(p): p for p in all_files}

if not options:
    st.warning("没有找到可用文件")
    st.stop()

selected_labels = st.multiselect("Files", list(options.keys()))
if not selected_labels:
    st.info("请选择至少一个文件")
    st.stop()

selected_paths = [options[label] for label in selected_labels]
selected_data = []
for label, path in zip(selected_labels, selected_paths):
    data = load_query2_file(path) if mode == "query2" else load_image2_file(path)
    data["label"] = label
    selected_data.append(data)

anchor = selected_data[0]
query_search_key = "visual_query_search"
image_search_key = "visual_image_search"
query_cols_key = "visual_query_columns_per_row"
image_ratio_key = "visual_image_text_ratio"

if query_search_key not in st.session_state:
    st.session_state[query_search_key] = ""
if image_search_key not in st.session_state:
    st.session_state[image_search_key] = ""
if query_cols_key not in st.session_state:
    st.session_state[query_cols_key] = 4
if image_ratio_key not in st.session_state:
    st.session_state[image_ratio_key] = 2

if mode == "query2":
    filter_text = str(st.session_state.get(query_search_key, "")).strip().lower()
    columns_per_row = int(st.session_state.get(query_cols_key, 4))
    image_text_ratio = 0
else:
    filter_text = str(st.session_state.get(image_search_key, "")).strip().lower()
    columns_per_row = 1
    image_text_ratio = int(st.session_state.get(image_ratio_key, 2))
item_ids = list(anchor["order"])
if filter_text:
    item_ids = [x for x in item_ids if filter_text in x.lower()]

if not item_ids:
    st.warning("没有可展示的数据")
    st.stop()

state_key = (mode, tuple(selected_labels), filter_text)
if "visual_idx" not in st.session_state:
    st.session_state.visual_idx = 0
if "visual_num_idx" not in st.session_state:
    st.session_state.visual_num_idx = 0
if "visual_slider_idx" not in st.session_state:
    st.session_state.visual_slider_idx = 0
if "visual_last_state" not in st.session_state:
    st.session_state.visual_last_state = None


def sync_widgets():
    st.session_state.visual_num_idx = st.session_state.visual_idx
    st.session_state.visual_slider_idx = st.session_state.visual_idx


def set_idx_from_num():
    st.session_state.visual_idx = int(st.session_state.visual_num_idx)
    st.session_state.visual_slider_idx = st.session_state.visual_idx


def set_idx_from_slider():
    st.session_state.visual_idx = int(st.session_state.visual_slider_idx)
    st.session_state.visual_num_idx = st.session_state.visual_idx


if st.session_state.visual_last_state != state_key:
    st.session_state.visual_idx = 0
    st.session_state.visual_last_state = state_key
    sync_widgets()

st.session_state.visual_idx = max(0, min(st.session_state.visual_idx, len(item_ids) - 1))
sync_widgets()


def prev_item():
    st.session_state.visual_idx = max(0, st.session_state.visual_idx - 1)
    sync_widgets()


def next_item():
    st.session_state.visual_idx = min(len(item_ids) - 1, st.session_state.visual_idx + 1)
    sync_widgets()


nav_cols = st.columns([1, 1, 1, 1, 1])
with nav_cols[0]:
    st.button("◀ Prev", on_click=prev_item)
with nav_cols[1]:
    st.number_input(
        "Idx",
        min_value=0,
        max_value=len(item_ids) - 1,
        step=1,
        key="visual_num_idx",
        on_change=set_idx_from_num,
    )
with nav_cols[2]:
    st.slider(
        "Slider",
        min_value=0,
        max_value=len(item_ids) - 1,
        key="visual_slider_idx",
        on_change=set_idx_from_slider,
    )
with nav_cols[3]:
    st.write(f"**{st.session_state.visual_idx + 1} / {len(item_ids)}**")
with nav_cols[4]:
    st.button("Next ▶", on_click=next_item)


current_id = item_ids[st.session_state.visual_idx]

if mode == "query2":
    header_cols = st.columns([2.0, 1.5, 1.2])
    with header_cols[0]:
        st.markdown(f"### Query: {current_id}")
    with header_cols[1]:
        st.text_input("Search query", key=query_search_key)
    with header_cols[2]:
        columns_per_row = st.slider(
            "每行图片数（越小图越大）",
            min_value=1,
            max_value=10,
            key=query_cols_key,
            step=1,
        )
    for idx, data in enumerate(selected_data):
        if idx > 0:
            st.divider()
        items = data["map"].get(current_id)
        if items is None:
            st.warning(f"{data['label']} 中没有这个 query")
            continue
        render_query2_block(data["label"], items, columns_per_row)
else:
    anchor_rec = anchor["map"].get(current_id, {})
    image_root = str(anchor_rec.get("root", "") or "")
    image_path = os.path.join(image_root, current_id) if image_root else current_id

    header_cols = st.columns([2.0, 1.5, 1.2])
    with header_cols[0]:
        st.markdown(f"### Image: {current_id}")
    with header_cols[1]:
        st.text_input("Search image", key=image_search_key)
    with header_cols[2]:
        image_text_ratio = st.slider("图文比例", min_value=0, max_value=4, key=image_ratio_key, step=1)
    ratio_options = {
        0: [1.4, 1.0],
        1: [1.2, 1.2],
        2: [1.0, 1.4],
        3: [0.9, 1.7],
        4: [0.8, 2.0],
    }
    top_cols = st.columns(ratio_options.get(image_text_ratio, [1.0, 1.4]))
    with top_cols[0]:
        if image_root and os.path.exists(image_path):
            st.image(image_path, caption=current_id, width="stretch")
        else:
            st.error(f"❌ {current_id}")
            if image_root:
                st.caption(image_root)

    with top_cols[1]:
        for idx, data in enumerate(selected_data):
            if idx > 0:
                st.divider()
            rec = data["map"].get(current_id)
            if rec is None:
                st.warning(f"{data['label']} 中没有这张图")
                continue
            render_image2_block(data["label"], rec.get("queries", {}))
