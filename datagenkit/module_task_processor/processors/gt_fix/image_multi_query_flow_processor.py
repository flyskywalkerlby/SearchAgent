from __future__ import annotations

import json
from pathlib import Path

from module_task_processor.task_processor import FlowTaskProcessor


def _chunk_list(items: list[str], chunk_size: int) -> list[list[str]]:
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


class ImageMultiQueryFlowProcessor(FlowTaskProcessor):
    def __init__(self, cfg):
        super().__init__(cfg)
        self.extra_cfg = cfg.get("extra", {}) or {}
        self.query_list = self._load_query_list()
        self.query_batch_size = int(self.extra_cfg.get("query_batch_size", cfg.get("query_batch_size", 20)) or 20)
        if self.query_batch_size <= 0:
            raise ValueError("query_batch_size 必须大于 0")

    def _load_query_list(self) -> list[str]:
        raw_paths = self.extra_cfg.get("query_jsonl_paths", self.cfg.get("query_jsonl_paths"))
        if isinstance(raw_paths, str):
            raw_paths = [raw_paths]
        if not isinstance(raw_paths, list) or not raw_paths:
            raise ValueError("query_jsonl_paths 必须是非空列表")

        queries = []
        seen = set()
        for raw_path in raw_paths:
            path = Path(raw_path).expanduser().resolve()
            if not path.exists():
                raise FileNotFoundError(f"query jsonl 不存在: {path}")
            with path.open("r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    if not isinstance(obj, dict) or len(obj) != 1:
                        raise ValueError(f"{path}:{line_no} 需要是单 key dict")
                    query = next(iter(obj.keys())).strip()
                    if not query or query in seen:
                        continue
                    seen.add(query)
                    queries.append(query)

        if not queries:
            raise ValueError("没有加载到任何 query")
        return queries

    def get_max_step_count(self) -> int | None:
        return 1

    def init_flow_ctx(self, img_path, data, runtime):
        flow_ctx = super().init_flow_ctx(img_path, data, runtime)
        flow_ctx["runtime"]["query_batches"] = _chunk_list(self.query_list, self.query_batch_size)
        flow_ctx["runtime"]["batch_idx"] = 0
        flow_ctx["runtime"]["matched_queries"] = []
        return flow_ctx

    def prepare_current_step(self, flow_ctx, img_path, data, runtime):
        rt = flow_ctx["runtime"]
        batch_idx = rt["batch_idx"]
        query_batches = rt["query_batches"]

        if batch_idx >= len(query_batches):
            flow_ctx["output"] = {
                "image": data["image"],
                "root": data["root"],
                "matched_queries": rt["matched_queries"],
            }
            flow_ctx["finished"] = True
            return None

        batch_queries = query_batches[batch_idx]
        numbered_lines = [
            f"- {query}"
            for query in batch_queries
        ]
        prompt = self.get_prompt("prompt_image_multi_query_match")
        prompt = prompt.replace("{{QUERY_LIST}}", "\n".join(numbered_lines))

        return {
            "step_name": "split_query_batch",
            "prompt": prompt,
            "batch_idx": batch_idx,
            "batch_queries": batch_queries,
        }

    def post_check_current_step(self, text, flow_ctx, step_info):
        text = (text or "").strip()
        if not text:
            return False, "输出为空", None

        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            return False, f"JSON解析错误: {e}", None

        if not isinstance(obj, dict):
            return False, f"输出必须是 dict，实际是 {type(obj).__name__}", None

        if "results" not in obj:
            return False, "缺少 results", None

        results = obj["results"]
        if not isinstance(results, list):
            return False, "results 必须是 list", None

        batch_queries = step_info["batch_queries"]
        expected_set = set(batch_queries)
        normalized = []
        seen = set()

        for item in results:
            if not isinstance(item, dict):
                return False, f"results 元素必须是 dict，实际是 {type(item).__name__}", None
            if "query" not in item or "is_match" not in item:
                return False, "results 元素缺少 query 或 is_match", None

            query = item["query"]
            is_match = item["is_match"]

            if not isinstance(query, str):
                return False, f"query 必须是 str，实际是 {type(query).__name__}", None
            if query not in expected_set:
                return False, f"query 不在当前 batch 中: {query}", None
            if query in seen:
                return False, f"query 重复返回: {query}", None
            seen.add(query)

            if isinstance(is_match, bool):
                pass
            elif isinstance(is_match, str):
                low = is_match.strip().lower()
                if low in {"true", "yes", "1"}:
                    is_match = True
                elif low in {"false", "no", "0"}:
                    is_match = False
                else:
                    return False, f"is_match 无法解析: {item['is_match']}", None
            else:
                return False, f"is_match 必须是 bool，实际是 {type(is_match).__name__}", None

            normalized.append({
                "query": query,
                "is_match": is_match,
            })

        if seen != expected_set:
            missing = sorted(expected_set - seen)
            extra = sorted(seen - expected_set)
            if missing:
                return False, f"results 缺少 query: {missing[:5]}", None
            if extra:
                return False, f"results 多出 query: {extra[:5]}", None

        checked = {
            "reason": str(obj.get("reason", "") or "").strip(),
            "results": normalized,
        }
        return True, None, checked

    def consume_step_result(self, flow_ctx, step_info, checked_output, raw_text, data, runtime):
        flow_ctx["outputs"].setdefault("split_query_batch", []).append(checked_output)

        for item in checked_output["results"]:
            if item["is_match"]:
                flow_ctx["runtime"]["matched_queries"].append(item["query"])

        flow_ctx["runtime"]["batch_idx"] += 1
