import json, os
import streamlit as st
from PIL import Image
import hashlib
from pathlib import Path


st.set_page_config(layout="wide")
st.title("Kirin 多模态数据浏览器")

# =========================================================
# 路径替换（完全不动）
# =========================================================

DIRS_WORKSPACE = [
    "/srv/workspace/Kirin_AI_Workspace/TMG_II",
]

DIRS_HAP_DATASETS = [
    "/srv/workspace/Kirin_AI_DataLake",
]

def add_replace_roots(*dir_roots_list):
    replace_roots = []
    for dir_roots in dir_roots_list:
        for dir_root in dir_roots:
            if os.path.exists(dir_root):
                for other_root in dir_roots:
                    if other_root != dir_root:
                        replace_roots.append((other_root, dir_root))
                break
        else:
            raise RuntimeError(f"No valid roots: {dir_roots}")
    return replace_roots

REPLACE_ROOTS = add_replace_roots(
    # DIRS_WORKSPACE,
    # DIRS_HAP_DATASETS,
)

def replace_path(path: str):
    for old, new in REPLACE_ROOTS:
        path = path.replace(old, new)
    return path

# =========================================================
# Dataset（完全不动）
# =========================================================

class Dataset:
    def __init__(self, jsonl_path: str, root_path: str = ""):
        self.jsonl = replace_path(jsonl_path)
        self.root = replace_path(root_path) if root_path else ""

# =========================================================
# Pools（单文件内置）
# =========================================================

PoolDirJsons   = [
    "./datasets_sharegpt"
]
PoolJsons      = [
]
PoolDirJsonls  = [
    "./outputs",
    "./outputs_steps",
    "./outputs_failed",
    "./test_outputs",
    "./test_outputs_steps",
    "./test_outputs_failed",
    "./cache",
]
PoolJsonls     = [
]

# =========================================================
# 工具函数（完全不动）
# =========================================================

def collect_files_recursively(root_dir, suffix):
    results = []
    for r, _, files in os.walk(root_dir):
        for f in files:
            if f.endswith(suffix):
                results.append(os.path.join(r, f))
    return results

# def contain_kws(path: str, kws):
#     s = path.lower()
#     for kw in kws:
#         if kw not in s:
#             return False
#     return True

    # return any(s in name for s in strings)

def contain_kws(name: str, strings):
    """
    OR over select_strings
    AND inside strings split by "+"
    """
    for s in strings:
        parts = s.split("+")
        if all(p in name for p in parts):
            return True
    return False


def parse_kw_input(raw: str):
    raw = (raw or "").strip().lower()
    if not raw or raw == "all":
        return []
    return [x for x in raw.replace(",", " ").split() if x]


def parse_path_input(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return []
    items = []
    for line in raw.replace(",", "\n").splitlines():
        s = line.strip()
        if s:
            items.append(s)
    return items


def looks_like_failed_jsonl(path: str):
    path = (path or "").replace("\\", "/").lower()
    return path.endswith(".failed.jsonl") or "/outputs_failed/" in path or path.startswith("outputs_failed/")


def get_record_kind(path: str, entry: dict):
    if looks_like_failed_jsonl(path):
        return "failed"
    if isinstance(entry, dict) and entry.get("reason") and entry.get("output") is None:
        return "failed"
    return "success"


def render_json_section(title: str, obj, expanded: bool = False):
    with st.expander(title, expanded=expanded):
        st.json(obj, expanded=True)


def build_section_map(entry: dict):
    output = entry.get("output")
    extra = entry.get("extra")
    outputs = entry.get("outputs")

    if isinstance(outputs, dict) and outputs:
        section_map = {
            "Final": output if output is not None else {},
            "Extra": extra if extra is not None else {},
        }
        for step_name in outputs.keys():
            section_map[step_name] = outputs.get(step_name, {})
        section_map["Raw"] = entry
        return section_map

    section_map = {}
    if output is not None:
        section_map["Final"] = output
    if extra is not None:
        section_map["Extra"] = extra
    section_map["Raw"] = entry
    return section_map


def get_default_sections(section_names):
    default_sections = [name for name in ["Final"] if name in section_names]
    if not default_sections:
        default_sections = section_names[:1]
    return default_sections


def get_output_sections(section_names):
    return [name for name in section_names if name not in {"Final", "Extra", "Raw"}]


def get_selected_sections(entry: dict):
    section_map = build_section_map(entry)
    section_names = list(section_map.keys())
    default_sections = get_default_sections(section_names)

    key = "section_select_global"
    if key not in st.session_state:
        st.session_state[key] = default_sections

    selected_sections = st.session_state.get(key, default_sections)
    selected_sections = [name for name in selected_sections if name in section_names]
    if not selected_sections:
        selected_sections = default_sections
        st.session_state[key] = selected_sections
    return section_map, selected_sections

# =========================================================
# ================== Pool 原始路径筛选 ====================
# =========================================================

def filter_paths_with_warn(paths, kws, pool_name, expect_dir=None):
    """
    paths: list[str] 原始路径列表
    kws: list[str] 关键词（空=不过滤）
    pool_name: 用于 warning 显示
    expect_dir:
      - True: 期望是目录
      - False: 期望是文件
      - None: 不强制
    """
    missing = []
    ok = []

    for p in paths:
        if not os.path.exists(p):
            missing.append(p)
            continue
        if expect_dir is True and (not os.path.isdir(p)):
            missing.append(p)
            continue
        if expect_dir is False and (not os.path.isfile(p)):
            missing.append(p)
            continue
        ok.append(p)

    if missing:
        st.warning(f"{pool_name} 有 {len(missing)} 个路径不存在或类型不匹配（已忽略）。")
        # 如需展开详情可取消注释
        st.write(missing)

    if kws:  # 只有非空才过滤（空=all）
        ok = [p for p in ok if contain_kws(p, kws)]
    if pool_name == "PoolDirJsonls":
        def _pool_dir_jsonls_key(p: str):
            s = p.replace("\\", "/").lower().rstrip("/")
            base = os.path.basename(s)
            if base == "outputs" or s == "outputs" or s.endswith("./outputs"):
                pri = 0
            elif base == "test_outputs" or "test_outputs" in s:
                pri = 1
            elif base == "outputs_failed" or "outputs_failed" in s:
                pri = 2
            elif base == "test_outputs_failed" or "test_outputs_failed" in s:
                pri = 3
            elif base == "outputs_steps" or "outputs_steps" in s:
                pri = 4
            elif base == "test_outputs_steps" or "test_outputs_steps" in s:
                pri = 5
            elif base == "cache" or s == "cache" or s.endswith("./cache"):
                pri = 6
            else:
                pri = 7
            return (pri, s)
        return sorted(ok, key=_pool_dir_jsonls_key)
    return sorted(ok)

REPLACE_RULES = [
    ("/srv/workspace/Kirin_AI_Workspace/TMG_II/", "<tmg2>/"),
    ("/srv/workspace/Kirin_AI_Workspace/TMG_II/l00931199/", "<lby>/"),
    # 以后可以继续加
]
REPLACE_RULES = sorted(REPLACE_ROOTS, key=lambda s: len(s), reverse=True)

def replace_all_by_rules(path: str, rules):
    for old, new in rules:
        path = path.replace(old, new)
    return path.lstrip("/")

def pool_row(pool_name, raw_paths, kw_key, sel_key, expect_dir=None):
    # [启用] [关键词] [下拉框]
    cols = st.columns([1, 3, 4, 12])

    with cols[0]:
        use_it = st.checkbox("用", value=True, key=f"use_{sel_key}")

    with cols[1]:
        kws = parse_kw_input(st.text_input(f"{pool_name} 关键词", key=kw_key))

    with cols[2]:
        extra_paths = parse_path_input(
            st.text_input(f"{pool_name} 附加路径", key=f"extra_{sel_key}")
        )

    if not use_it:
        with cols[3]:
            st.selectbox(pool_name, ["(未启用)"], disabled=True, key=f"{sel_key}_disabled_off")
        return []

    raw_paths = list(raw_paths) + extra_paths
    filtered = filter_paths_with_warn(raw_paths, kws, pool_name, expect_dir=expect_dir)

    with cols[3]:
        if not filtered:
            st.selectbox(pool_name, ["(空)"], disabled=True, key=f"{sel_key}_disabled_empty")
            return []
        else:
            # sel = st.selectbox(pool_name, filtered, key=sel_key)
            # return sel
            # 显示用：移除所有前缀
            label_to_path = {
                replace_all_by_rules(p, REPLACE_RULES): p
                for p in filtered
            }

            sel_label = st.selectbox(
                pool_name,
                list(label_to_path.keys()),
                key=sel_key
            )
            return label_to_path[sel_label]

    # return filtered

st.markdown("### 数据源选择（筛选的是 pool 原始路径）")

# ---------- PoolDirJsons ----------
# 4 个 pool（保持变量名不变，给后面汇总用）
sel_dir_jsons  = pool_row("PoolDirJsons",  PoolDirJsons,  "kw1", "sel_pooldirjsons",  expect_dir=True)
sel_jsons      = pool_row("PoolJsons",     PoolJsons,     "kw2", "sel_pooljsons",     expect_dir=False)
sel_dir_jsonls = pool_row("PoolDirJsonls", PoolDirJsonls, "kw3", "sel_pooldirjsonls", expect_dir=True)
sel_jsonls     = pool_row("PoolJsonls",    PoolJsonls,    "kw4", "sel_pooljsonls",    expect_dir=False)

# print(sel_dir_jsons)
# print(sel_jsons)
# print(sel_dir_jsonls)
# print(sel_jsonls)

# =========================================================
# <<< FIX >>> 统一从「筛选后的原始路径」生成 jsonl
# =========================================================

def parse_json_to_datasets(json_path):
    out = []
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for _, info in data.items():
        ann = info.get("annotation")
        if ann:
            out.append(Dataset(ann, info.get("root", "")))
    return out

all_datasets = []

# 来自 PoolDirJsons：选中一个目录 -> 递归所有 .json -> 解析出 jsonl
if sel_dir_jsons and os.path.isdir(sel_dir_jsons):
    for jp in collect_files_recursively(sel_dir_jsons, ".json"):
        try:
            all_datasets.extend(parse_json_to_datasets(jp))
        except Exception as e:
            st.warning(f"解析 json 失败: {jp}\n{e}")

# 来自 PoolJsons：选中一个 .json -> 直接解析出 jsonl
if sel_jsons and os.path.isfile(sel_jsons):
    try:
        all_datasets.extend(parse_json_to_datasets(sel_jsons))
    except Exception as e:
        st.warning(f"解析 json 失败: {sel_jsons}\n{e}")

# 来自 PoolDirJsonls：选中一个目录 -> 递归所有 .jsonl
if sel_dir_jsonls and os.path.isdir(sel_dir_jsonls):
    for jl in collect_files_recursively(sel_dir_jsonls, ".jsonl"):
        all_datasets.append(Dataset(jl, ""))


def json_array_to_jsonl(json_path, temp_dir="./temp"):
    assert json_path.endswith(".json")

    os.makedirs(temp_dir, exist_ok=True)

    # 文件名主体（可读）
    base = os.path.basename(json_path)

    # 用完整路径算 hash，保证唯一
    h = hashlib.md5(json_path.encode("utf-8")).hexdigest()[:8]

    jsonl_name = f"{base}__{h}.jsonl"
    jsonl_path = os.path.join(temp_dir, jsonl_name)

    # 如果 jsonl 已存在且比原 json 新，直接复用
    if os.path.exists(jsonl_path) and \
       os.path.getmtime(jsonl_path) >= os.path.getmtime(json_path):
        return jsonl_path

    # print("更新 jsonl")
    st.info("更新 jsonl")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, list), "json 必须是 array 格式"

    with open(jsonl_path, "w", encoding="utf-8") as w:
        for item in data:
            w.write(json.dumps(item, ensure_ascii=False) + "\n")

    return jsonl_path


# 来自 PoolJsonls：选中一个 .jsonl -> 直接加入
if sel_jsonls and os.path.isfile(sel_jsonls):

    if sel_jsonls.endswith(".json"):
        sel_jsonls = json_array_to_jsonl(sel_jsonls)

    all_datasets.append(Dataset(sel_jsonls, ""))

# 去重 + root 继承（保留非空 root）
uniq = {}
for ds in all_datasets:
    k = ds.jsonl
    if k not in uniq:
        uniq[k] = ds
    else:
        if (not uniq[k].root) and ds.root:
            uniq[k].root = ds.root
all_datasets = list(uniq.values())

# =========================================================
# 第 5 个下拉框：所有 jsonl（唯一真正的选择）
# =========================================================

st.markdown("### 所有 JSONL（最终选择）")

r_jsonl = st.columns([1, 5])
with r_jsonl[0]:
    jsonl_kw = parse_kw_input(st.text_input("JSONL 关键词", key="kw_jsonl"))

if jsonl_kw:
    filtered_all_datasets = [ds for ds in all_datasets if contain_kws(ds.jsonl, jsonl_kw)]
else:
    filtered_all_datasets = all_datasets

# labels = [ds.jsonl for ds in filtered_all_datasets]

# with r_jsonl[1]:
#     if not labels:
#         st.selectbox("最终使用的 jsonl", ["(无可用 jsonl)"], disabled=True, key="sel_final_jsonl_disabled")
#         st.stop()
#     sel_final = st.selectbox("最终使用的 jsonl", labels, key="sel_final_jsonl")

# DATASETS = [ds for ds in filtered_all_datasets if ds.jsonl == sel_final]

# 显示用 label -> Dataset 映射
label_to_ds = {
    replace_all_by_rules(ds.jsonl, REPLACE_RULES): ds
    for ds in filtered_all_datasets
}

labels = sorted(
    label_to_ds.keys(),
    key=lambda x: (
        1 if looks_like_failed_jsonl(label_to_ds[x].jsonl) else 0,
        x,
    ),
)

with r_jsonl[1]:
    if not labels:
        st.selectbox(
            "最终使用的 jsonl",
            ["(无可用 jsonl)"],
            disabled=True,
            key="sel_final_jsonl_disabled"
        )
        st.stop()
    sel_label = st.selectbox(
        "最终使用的 jsonl",
        labels,
        key="sel_final_jsonl"
    )

# 真正使用的 Dataset（路径仍然是原始绝对路径）
DATASETS = [label_to_ds[sel_label]]

# =========================================================
# ================== 下面全部不动 =========================
# =========================================================

@st.cache_resource
def get_tokenizer():
    model_path = "/srv/workspace/Kirin_AI_DataLake/models/InternVL3_5/InternVL3_5-1B/"
    model_path = replace_path(model_path)
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(
        model_path,
        trust_remote_code=True,
        use_fast=False,
    )

# TOK = get_tokenizer()

def get_line_offsets(path):
    off = []
    with open(path, "rb") as f:
        o = 0
        for line in f:
            off.append(o)
            o += len(line)
    return off

offsets_dict = {}
for ds in DATASETS:
    offsets_dict[ds.jsonl] = get_line_offsets(ds.jsonl)

line_offsets = offsets_dict[DATASETS[0].jsonl]
num_entries  = len(line_offsets)

# ---------- 最基本的上一个 / 下一个 ----------
if "entry_index" not in st.session_state:
    st.session_state.entry_index = 0

def goto_prev():
    st.session_state.entry_index = (st.session_state.entry_index - 1) % num_entries

def goto_next():
    st.session_state.entry_index = (st.session_state.entry_index + 1) % num_entries

def goto_idx(i: int):
    st.session_state.entry_index = max(0, min(int(i), num_entries - 1))

nav_prev, nav_mid, nav_idx, nav_next = st.columns([1, 1, 1, 1])
with nav_prev:
    st.button("⬅️ 上一个", on_click=goto_prev)
with nav_mid:
    st.markdown(f"**当前条目：{st.session_state.entry_index + 1} / {num_entries}**")
with nav_idx:
    idx = st.number_input(
        "跳转到条目",
        min_value=0,
        max_value=num_entries - 1,
        value=int(st.session_state.entry_index),
        step=1
    )
    if int(idx) != int(st.session_state.entry_index):
        goto_idx(int(idx))
        st.rerun()
with nav_next:
    st.button("➡️ 下一个", on_click=goto_next)



st.markdown("---")


def get_img_path(e):
    kind = get_record_kind("", e)
    if kind == "failed":
        path = e.get("path")
        if isinstance(path, str) and path.strip():
            return path

    for k in ["image", "img_path"]:
        if k in e:
            return e[k]
    return ""


def render_record(entry: dict, ds_jsonl: str):
    kind = get_record_kind(ds_jsonl, entry)

    top1, top2, top3 = st.columns([2, 2, 3])
    with top1:
        if kind == "failed":
            st.error("FAILED")
        else:
            st.success("SUCCESS")
    with top2:
        st.markdown(f"**dataset**: `{entry.get('dataset_name', '')}`")
    with top3:
        st.markdown(f"**id/raw_id**: `{entry.get('id', '')}` / `{entry.get('raw_id', '')}`")

    if kind == "failed":
        st.error(entry.get("reason", "未知失败原因"))
        render_json_section("Raw Record", entry, expanded=True)
        return

    section_map = build_section_map(entry)
    if "Raw" in section_map and len(section_map) > 1:
        section_names = list(section_map.keys())
        default_sections = get_default_sections(section_names)
        output_sections = get_output_sections(section_names)
        select_key = "section_select_global"

        if select_key not in st.session_state:
            st.session_state[select_key] = default_sections

        selected_sections = [
            name for name in st.session_state.get(select_key, default_sections)
            if name in section_names
        ]
        if not selected_sections:
            selected_sections = default_sections
            st.session_state[select_key] = selected_sections

        control_cols = st.columns([1, 1, 6])
        with control_cols[0]:
            if st.button("Select All", key="select_all_sections"):
                st.session_state[select_key] = section_names
                st.rerun()
        with control_cols[1]:
            if st.button("Select Outputs", key="select_output_sections"):
                st.session_state[select_key] = output_sections or default_sections
                st.rerun()
        with control_cols[2]:
            selected_sections = st.multiselect(
                "显示区块（可多选并排看）",
                section_names,
                default=selected_sections,
                key=select_key,
            )
        if not selected_sections:
            st.info("请至少选择一个区块。")
            return

        section_cols = st.columns(len(selected_sections))
        for col, section_name in zip(section_cols, selected_sections):
            with col:
                st.subheader(section_name)
                st.json(section_map[section_name], expanded=True)
        return

    for section_name, section_value in section_map.items():
        render_json_section(section_name, section_value, expanded=True)

entries = []
abs_img_paths = []

for ds in DATASETS:
    with open(ds.jsonl, "r", encoding="utf-8") as f:
        f.seek(offsets_dict[ds.jsonl][st.session_state.entry_index])
        e = json.loads(f.readline())
    entries.append(e)
    img_rel = get_img_path(e)
    root = ds.root or e.get("root", "")
    if isinstance(img_rel, str) and os.path.isabs(img_rel):
        abs_img_paths.append(img_rel)
    else:
        abs_img_paths.append(os.path.join(root, img_rel) if root and img_rel else img_rel)

img_path = abs_img_paths[0]
preview_section_map, preview_selected_sections = get_selected_sections(entries[0])
selected_count = len(preview_selected_sections)
if selected_count > 4:
    layout_ratio = [1, 3]
elif selected_count > 1:
    layout_ratio = [1, 2]
else:
    layout_ratio = [2, 3]

col1, col2 = st.columns(layout_ratio)

with col1:
    if img_path and os.path.exists(img_path):
        img = Image.open(img_path)
        st.image(img, width='stretch')
        st.info(img.size)
    else:
        st.info("无图片")

with col2:
    ds_path = DATASETS[0].jsonl
    st.caption(replace_all_by_rules(ds_path, REPLACE_RULES))
    render_record(entries[0], ds_path)


# ---------- 底部占位：避免页面太短导致布局把图片挤窄 ----------
st.markdown("<div style='height: 1200px;'></div>", unsafe_allow_html=True)
