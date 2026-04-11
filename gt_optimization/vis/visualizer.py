import streamlit as st
import json
import os

st.set_page_config(layout="wide")

ROOT_BY_JSONL = {
    "card_20251218_q2i_manucheck.jsonl": "/srv/workspace/Kirin_AI_Workspace/AIC_I/g30064845/VLM/Chinese-CLIP/datasets/from_tuku_test_3k_together/card",
    "test_imgs_rename_20251209_q2i_supplement_removelowSim_0.2.jsonl": "/srv/workspace/Kirin_AI_Workspace/TMG_II/s00913809/projects/multi-modal/data/image-caption/test/caption_1k/test_imgs_rename",
}
GT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "gt")

st.title("JSONL Visualizer")


def load_jsonl(file_path):
    data = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def sync_widgets():
    st.session_state.num_idx = st.session_state.idx
    st.session_state.slide_idx = st.session_state.idx


def set_idx_from_num():
    st.session_state.idx = int(st.session_state.num_idx)
    st.session_state.slide_idx = st.session_state.idx


def set_idx_from_slider():
    st.session_state.idx = int(st.session_state.slide_idx)
    st.session_state.num_idx = st.session_state.idx


jsonl_files = [f for f in os.listdir(GT_DIR) if f.endswith(".jsonl")]
selected_file = st.selectbox("Select JSONL file", jsonl_files)

if "idx" not in st.session_state:
    st.session_state.idx = 0
if "num_idx" not in st.session_state:
    st.session_state.num_idx = 0
if "slide_idx" not in st.session_state:
    st.session_state.slide_idx = 0
if "last_file" not in st.session_state:
    st.session_state.last_file = None

if selected_file:
    base_dir = ROOT_BY_JSONL.get(selected_file, "")
    file_path = os.path.join(GT_DIR, selected_file)
    data = load_jsonl(file_path)
    total = len(data)

    if total == 0:
        st.warning("当前文件为空")
        st.stop()

    # 切文件时重置
    if st.session_state.last_file != selected_file:
        st.session_state.idx = 0
        st.session_state.last_file = selected_file
        sync_widgets()

    # 防止越界
    st.session_state.idx = max(0, min(st.session_state.idx, total - 1))

    # 每轮渲染前，把两个控件同步到 idx
    sync_widgets()

    def prev_item():
        st.session_state.idx = max(0, st.session_state.idx - 1)
        sync_widgets()

    def next_item():
        st.session_state.idx = min(total - 1, st.session_state.idx + 1)
        sync_widgets()

    col1, col2, col3, col4, col5 = st.columns([1, 1, 1, 1, 1])

    with col1:
        st.button("◀ Prev", on_click=prev_item)

    with col2:
        st.number_input(
            "Idx",
            min_value=0,
            max_value=total - 1,
            step=1,
            key="num_idx",
            on_change=set_idx_from_num,
        )

    with col3:
        st.slider(
            "Slider",
            min_value=0,
            max_value=total - 1,
            key="slide_idx",
            on_change=set_idx_from_slider,
        )

    with col4:
        st.write(f"**{st.session_state.idx + 1} / {total}**")

    with col5:
        st.button("Next ▶", on_click=next_item)

    idx = st.session_state.idx
    item = data[idx]

    query = list(item.keys())[0]
    images = item[query]

    st.markdown(f"### Query: {query}")
    st.markdown(f"**{len(images)} images**")

    cols = st.columns(4)
    for i, img_name in enumerate(images):
        img_path = os.path.join(base_dir, img_name)
        with cols[i % 4]:
            if os.path.exists(img_path):
                st.image(img_path, caption=img_name, use_container_width=True)
            else:
                st.error(f"❌ {img_name}")
