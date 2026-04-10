#!/usr/bin/env python3
import os
import argparse
import ast

# 需要排除的文件后缀
EXCLUDE_SUFFIXES = {".jpg", ".png", ".parquet"}

# 需要忽略的目录（可以写多个）
EXCLUDE_DIRS = {"outputs", "cache", ".git", "__pycache__"}


def get_public_api_from_pyfile(filepath):
    """
    从 .py 文件解析顶层函数（含 async）和类。
    返回带标注的字符串列表，如:
      foo() / bar(async) / MyClass(c)
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            src = f.read()
    except (OSError, UnicodeDecodeError):
        return []

    try:
        tree = ast.parse(src, filename=filepath)
    except SyntaxError:
        return []

    names = []
    for node in tree.body:
        # 普通函数
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            names.append(f"{node.name}()")

        # 异步函数 async def
        elif isinstance(node, ast.AsyncFunctionDef) and not node.name.startswith("_"):
            names.append(f"{node.name}(async)")

        # 类
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            names.append(f"{node.name}(cls)")

    return names


def print_tree(start_path, prefix="", show_funcs=False):
    try:
        items = sorted(os.listdir(start_path))
    except PermissionError:
        return

    # 过滤掉指定后缀、以 "_" 开头的文件/目录、需要忽略的目录
    items = [
        item for item in items
        if not (
            (item.startswith("_") and not item.startswith("__"))
            or any(item.lower().endswith(suf) for suf in EXCLUDE_SUFFIXES)
            or item in EXCLUDE_DIRS
        )
    ]

    for index, item in enumerate(items):
        path = os.path.join(start_path, item)
        connector = "└── " if index == len(items) - 1 else "├── "

        display_name = item

        # 对每个 .py 文件尾部附加可 import API
        if show_funcs and os.path.isfile(path) and item.endswith(".py"):
            names = get_public_api_from_pyfile(path)
            if names:
                display_name = f"{item}  [{', '.join(names)}]"

        print(prefix + connector + display_name)

        if os.path.isdir(path):
            extension = "    " if index == len(items) - 1 else "│   "
            print_tree(path, prefix + extension, show_funcs=show_funcs)


def main():
    parser = argparse.ArgumentParser(description="Print directory tree.")
    parser.add_argument(
        "--root",
        type=str,
        default="./",
        help="Root directory to start tree printing (default: current directory).",
    )
    parser.add_argument(
        "--print-f",
        dest="print_f",
        action="store_true",
        help="Print importable function/class names after each .py file.",
    )

    args = parser.parse_args()

    root_dir = args.root
    print(root_dir)
    print_tree(root_dir, show_funcs=args.print_f)


if __name__ == "__main__":
    main()