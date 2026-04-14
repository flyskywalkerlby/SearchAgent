from __future__ import annotations

import json

import colorful as cf

from module_task_processor.task_processor import FlowTaskProcessor


ALLOWED_TOP_LEVEL_KEYS = {"reason", "results"}
ALLOWED_ITEM_KEYS = {
    "analysis",
    "is_present",
    "location",
    "is_main_subject",
    "importance_score",
}


def _chunk_list(items: list[str], chunk_size: int) -> list[list[str]]:
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def _format_progress_bar(current: int, total: int, width: int = 20) -> str:
    if total <= 0:
        return "[{}]".format("-" * width)
    filled = int(width * current / total)
    filled = min(width, max(0, filled))
    return "[{}{}]".format("#" * filled, "-" * (width - filled))


def _strip_json_fence(text: str) -> tuple[str, bool]:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped, False

    lines = stripped.splitlines()
    if len(lines) < 3:
        return stripped, False
    if not lines[0].startswith("```") or lines[-1].strip() != "```":
        return stripped, False

    inner = "\n".join(lines[1:-1]).strip()
    return inner, True


def _parse_bool(value, field_name: str):
    if isinstance(value, bool):
        return value, None
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"true", "yes", "1"}:
            return True, None
        if low in {"false", "no", "0"}:
            return False, None
    return None, f"{field_name} 必须是 bool，实际是 {type(value).__name__}: {value}"


class ImageMultiQueryStep2FlowProcessor(FlowTaskProcessor):
    def __init__(self, cfg):
        super().__init__(cfg)
        self.extra_cfg = cfg.get("extra", {}) or {}
        self.query_batch_size = int(self.extra_cfg.get("query_batch_size", cfg.get("query_batch_size", 20)) or 20)
        if self.query_batch_size <= 0:
            raise ValueError("query_batch_size 必须大于 0")

    def _load_queries_from_sample(self, data) -> list[str]:
        output = data.get("output") if isinstance(data, dict) else None
        if not isinstance(output, dict):
            raise ValueError("step2 输入样本缺少 output dict")

        matched_queries = output.get("matched_queries")
        if isinstance(matched_queries, list):
            queries = []
            seen = set()
            for query in matched_queries:
                if not isinstance(query, str):
                    continue
                query = query.strip()
                if not query or query in seen:
                    continue
                seen.add(query)
                queries.append(query)
            return queries

        query_results = output.get("query_results")
        if isinstance(query_results, dict):
            queries = []
            for query in query_results.keys():
                if isinstance(query, str) and query.strip():
                    queries.append(query.strip())
            return queries

        raise ValueError("step2 输入样本缺少 matched_queries 或 query_results")

    def get_max_step_count(self) -> int | None:
        return 1

    def init_flow_ctx(self, img_path, data, runtime):
        flow_ctx = super().init_flow_ctx(img_path, data, runtime)
        query_list = self._load_queries_from_sample(data)
        flow_ctx["runtime"]["query_batches"] = _chunk_list(query_list, self.query_batch_size)
        flow_ctx["runtime"]["batch_idx"] = 0
        flow_ctx["runtime"]["query_results"] = {}
        return flow_ctx

    def prepare_current_step(self, flow_ctx, img_path, data, runtime):
        rt = flow_ctx["runtime"]
        batch_idx = rt["batch_idx"]
        query_batches = rt["query_batches"]

        if batch_idx >= len(query_batches):
            flow_ctx["output"] = {
                "image": data["image"],
                "root": data["root"],
                "query_results": rt["query_results"],
            }
            flow_ctx["finished"] = True
            return None

        batch_queries = query_batches[batch_idx]
        total_batches = len(query_batches)
        current_batch = batch_idx + 1
        if current_batch == 1 or current_batch % 10 == 0 or current_batch == total_batches:
            progress_bar = _format_progress_bar(current_batch, total_batches)
            print(
                cf.cyan(
                    f"{progress_bar} image={data.get('image')} batch={current_batch}/{total_batches} queries={len(batch_queries)}"
                )
            )

        prompt = self.get_prompt("prompt_image_multi_query_step2")
        prompt = prompt.replace("{{QUERY_LIST}}", "\n".join(f"- {query}" for query in batch_queries))
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

        text, fenced = _strip_json_fence(text)
        if fenced:
            print(cf.yellow("WARN: 输出使用了 markdown 代码块包裹，已自动去掉 ```json / ``` 后继续解析。"))

        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            return False, (
                f"JSON解析错误: {e}。"
                "请直接输出 JSON 对象本体，不要添加 ```json 代码块、解释文字或其它前后缀。"
            ), None

        if not isinstance(obj, dict):
            return False, f"输出必须是 dict，实际是 {type(obj).__name__}", None

        extra_top_level_keys = set(obj.keys()) - ALLOWED_TOP_LEVEL_KEYS
        if extra_top_level_keys:
            return False, f"顶层存在未定义字段: {sorted(extra_top_level_keys)}", None
        if "results" not in obj:
            return False, "缺少 results", None

        results = obj["results"]
        if not isinstance(results, dict):
            return False, f"results 必须是 dict，实际是 {type(results).__name__}", None

        batch_queries = step_info["batch_queries"]
        expected_set = set(batch_queries)
        actual_set = set(results.keys())
        if actual_set != expected_set:
            missing = sorted(expected_set - actual_set)
            extra = sorted(actual_set - expected_set)
            if missing:
                return False, f"results 缺少 query: {missing[:5]}", None
            if extra:
                return False, f"results 多出 query: {extra[:5]}", None

        normalized = {}
        for query in batch_queries:
            item = results[query]
            if not isinstance(item, dict):
                return False, f"query={query} 的结果必须是 dict，实际是 {type(item).__name__}", None

            extra_item_keys = set(item.keys()) - ALLOWED_ITEM_KEYS
            if extra_item_keys:
                return False, f"query={query} 存在未定义字段: {sorted(extra_item_keys)}", None
            missing_item_keys = ALLOWED_ITEM_KEYS - set(item.keys())
            if missing_item_keys:
                return False, f"query={query} 缺少字段: {sorted(missing_item_keys)}", None

            analysis = item.get("analysis")
            location = item.get("location")
            if not isinstance(analysis, str) or not analysis.strip():
                return False, f"query={query} 的 analysis 必须是非空字符串", None
            if not isinstance(location, str):
                return False, f"query={query} 的 location 必须是字符串", None

            is_present, err = _parse_bool(item.get("is_present"), f"query={query} 的 is_present")
            if err:
                return False, err, None
            is_main_subject, err = _parse_bool(item.get("is_main_subject"), f"query={query} 的 is_main_subject")
            if err:
                return False, err, None

            importance_score = item.get("importance_score")
            try:
                importance_score = int(importance_score)
            except Exception:
                return False, f"query={query} 的 importance_score 必须是整数", None
            if importance_score < 0 or importance_score > 3:
                return False, f"query={query} 的 importance_score 必须在 0-3 之间", None

            if not is_present:
                if is_main_subject:
                    return False, f"query={query} 不存在时 is_main_subject 必须为 false", None
                if importance_score != 0:
                    return False, f"query={query} 不存在时 importance_score 必须为 0", None
            else:
                if not location.strip():
                    return False, f"query={query} 存在时 location 不能为空", None
                if importance_score == 0:
                    return False, f"query={query} 存在时 importance_score 不能为 0", None

            normalized[query] = {
                "analysis": analysis.strip(),
                "is_present": is_present,
                "location": location.strip(),
                "is_main_subject": is_main_subject,
                "importance_score": importance_score,
            }

        checked = {
            "reason": str(obj.get("reason", "") or "").strip(),
            "results": normalized,
        }
        return True, None, checked

    def consume_step_result(self, flow_ctx, step_info, checked_output, raw_text, data, runtime):
        merged_output = flow_ctx["outputs"].setdefault(
            "split_query_batch",
            {"reason": "", "results": {}},
        )
        if checked_output.get("reason"):
            merged_output["reason"] = checked_output["reason"]
        merged_output.setdefault("results", {}).update(checked_output["results"])

        flow_ctx["runtime"]["query_results"].update(checked_output["results"])
        flow_ctx["runtime"]["batch_idx"] += 1
