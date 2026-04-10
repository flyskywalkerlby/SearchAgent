import json

# ===== add_info =====
def _format_zh_en_info(info):
    if not isinstance(info, dict):
        raise ValueError(f"ze meta info 必须是 dict，实际是 {type(info).__name__}")

    if "zh" not in info or "en" not in info:
        raise ValueError(f"ze meta info 缺少 zh/en 字段: {info}")

    zh = str(info["zh"]).strip()
    en = str(info["en"]).strip()
    if not zh or not en:
        raise ValueError(f"ze meta info 的 zh/en 不能为空: {info}")

    return f"{zh} ({en})"


def _format_zh_en_info_list(info_list):
    if not isinstance(info_list, list):
        raise ValueError(f"ze meta info list 必须是 list，实际是 {type(info_list).__name__}")
    if not info_list:
        raise ValueError("ze meta info list 不能为空")

    parts = []
    for info in info_list:
        parts.append(_format_zh_en_info(info))
    return "、".join(parts)


def load_path_to_info(pools):
    path2meta = {}
    path2type = {}

    for file, meta_info_type in pools.items():
        with open(file, "r") as f:
            subpath2meta = json.load(f)

        path2meta = {**path2meta, **subpath2meta}
        path2type.update({path: meta_info_type for path in subpath2meta.keys()})

    # 过滤人像
    path2meta = {k: v for k, v in path2meta.items() if "renxiang" not in k}
    path2type = {k: v for k, v in path2type.items() if k in path2meta}

    print(f"{len(path2meta)}张图像包含 MetaInfo。")

    return path2meta, path2type


MetaPools = {
    "/srv/workspace/Kirin_AI_Workspace/TMG_II/l00931199/datasets/Captioner/DomainMetaOrganize/251220/card_aic_8k_path_to_meta.json": "contain",
    "/srv/workspace/Kirin_AI_Workspace/TMG_II/l00931199/datasets/Captioner/DomainMetaOrganize/251220/card_eaten_path_to_meta.json": "contain",
    "/srv/workspace/Kirin_AI_Workspace/TMG_II/l00931199/datasets/Captioner/DomainMetaOrganize/260313/card_260313_path_to_meta.json": "contain",
    "/srv/workspace/Kirin_AI_Workspace/TMG_II/l00931199/datasets/Captioner/DomainMetaOrganize/260320/card_260320_add3_path_to_meta.json": "contain",

    "/srv/workspace/Kirin_AI_Workspace/TMG_II/l00931199/datasets/Captioner/DomainMetaOrganize/251220/special_path_to_title.json": "title",

    "/srv/workspace/Kirin_AI_Workspace/TMG_II/l00931199/datasets/Captioner/DomainMetaOrganize/251220/cat_v3_path_to_meta.json": "contain",
    "/srv/workspace/Kirin_AI_Workspace/TMG_II/l00931199/datasets/Captioner/DomainMetaOrganize/251220/dog_v3_path_to_meta.json": "contain",
    "/srv/workspace/Kirin_AI_Workspace/TMG_II/s00913809/projects/multi-modal/data/image-caption/collect_imgs/landmark/landmark_imgs_from_tuku_v1/train_landmark_mapping.json": "contain",

    "/srv/workspace/Kirin_AI_Workspace/TMG_II/l00931199/datasets/Knowledge/Animals/Animals-10/animal10_path2info_train_zh_en.json": "contain_ze",
    "/srv/workspace/Kirin_AI_Workspace/TMG_II/l00931199/datasets/Knowledge/Animals/Birds/caltech-ucsd-birds-200-2011/birds200_path2info_train_zh_en.json": "contain_ze",
    "/srv/workspace/Kirin_AI_Workspace/TMG_II/l00931199/datasets/Knowledge/Animals/Birds/nabirds-dataset/nabirds_path2info_train_zh_en.json": "contain_ze",

    "/srv/workspace/Kirin_AI_Workspace/TMG_II/l00931199/datasets/Knowledge/Food/food101/food101_path2info_train_zh_en.json": "contain_ze",
    "/srv/workspace/Kirin_AI_Workspace/TMG_II/l00931199/datasets/Knowledge/Food/food15k/food15k_path2info_train_zh_en.json": "may_contain_ze",

    "/srv/workspace/Kirin_AI_Workspace/TMG_II/l00931199/datasets/Knowledge/Plants/Flowers/OxfordFlowers102/flowers_path2info_train_zh_en.json": "contain_ze",
    "/srv/workspace/Kirin_AI_Workspace/TMG_II/l00931199/datasets/Knowledge/Plants/plantnet300K/plantnet300K_path2info_train_zh_en.json": "contain_ze",

    "/srv/workspace/Kirin_AI_Workspace/TMG_II/l00931199/datasets/Knowledge/Daily/LVIS/lvis_path2info_train_zh_en.json": "contain_ze_list",
    "/srv/workspace/Kirin_AI_Workspace/TMG_II/l00931199/datasets/Knowledge/Daily/SUNRGBD_seg/sunrgbd_path2info_train_zh_en.json": "contain_ze_list",
}

Path2Meta, Path2MetaType = load_path_to_info(MetaPools)

def get_metainfo(image_path, dataset_name=None):
    info = Path2Meta.get(image_path)
    if not info:
        return ""

    meta_info_type = Path2MetaType.get(image_path)
    if meta_info_type == "contain":
        return f"这张图像中含有：{info}。"
    elif meta_info_type == "contain_ze":
        return f"这张图像中含有：{_format_zh_en_info(info)}。"
    elif meta_info_type == "contain_ze_list":
        return f"这张图像中含有：{_format_zh_en_info_list(info)}。"
    elif meta_info_type == "may_contain_ze":
        return f"这张图像中可能有：{_format_zh_en_info(info)}。"
    elif meta_info_type == "title":
        return f"这张图像的标题是：'{info}'。"
    raise ValueError(f"未知 meta_info_type: {meta_info_type}")

# ===== add_info END =====
