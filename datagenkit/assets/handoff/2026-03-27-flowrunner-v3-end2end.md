# Codex Handoff

日期：2026-03-27

## 当前结论

- 新统一 runner 已落地，名字是 `FlowRunner`
- `main.py` 现在通过 `runner_type: flow` 显式选择新 runner
- `is_flow_processor` 已删除
- 旧 `Runner / SplitRunner / SplitSeqRunner` 还保留，后续可以继续删
- `configs/v70/vtest/v3_end2end.yaml` 现在就是当前真实 `tukuformat v3` 本地联调入口
- 本地 `qwen3.5-4b` + FlowRunner + 真实四步链路已实际跑通 `8/8`
- 当前又基于新图片和新 `extra` 语义 rerun 过一轮，仍然是 `8/8`

## 这轮已经完成的事情

### 1. FlowRunner 链路

- 新文件：
  - `module_runner/flow_runner.py`
- 入口导出：
  - `module_runner/__init__.py`
- 入口分发：
  - `main.py`

`FlowRunner` 的核心执行方式：

1. processor 生成当前 step
2. runner 执行 `infer/local`
3. 调当前 step 的 `post_check`
4. 失败就 retry
5. 成功后交给 processor 更新 `flow_ctx`
6. 直到 processor 结束

## 2. 新 processor 协议

- `FlowTaskProcessor` 在：
  - `module_task_processor/task_processor.py`

目前关键接口：

- `init_flow_ctx`
- `prepare_current_step`
- `post_check_current_step`
- `consume_step_result`
- `build_final_record`

最终记录结构：

```json
{
  "raw_id": "...",
  "id": "...",
  "image": "...",
  "dataset_name": "...",
  "output": {...},
  "extra": {...},
  "outputs": {
    "step1": {...},
    "step2": {...},
    "step3": {...},
    "step4": {...}
  }
}
```

`extra` 当前语义：

- 单步 flow：保持扁平
- 多步 flow：按 step 聚合
- 空 extra 不会写 step key
- 若有全局 extra，则放到 `"_global"`

## 3. v3 端到端测试链路

### 真实 4B 端到端 processor

- `module_task_processor/processors/v70/vtest/v3_end2end_actual_processor.py`

当前流程：

- `step1`: 对齐原始 `v3 step1`
- `step2`: 对齐原始 `v3 step2`，保留 local skip-vlm 和 VLM 路径
- `step3`: 已接回原始 `v3 step3 route/fill/merge`
- `step4`: 对齐原始 `v3 step4`

当前重点：

- `step3` 不再走早期简化版 `CLASS_SCHEMA`
- 现在直接复用：
  - `module_task_processor/processors/v70/tukuformat/v3/qw35_122b_a10b/step3.py`
  - `prompts/v70/v3/schema_v3.4_rules.json`
- `step4` 额外修了一个真实 bug：
  - 之前未编号 tag（如 `<Built>`）会在主旨里漏检
  - 现在会被严格拦下

### 配置

- 当前真实主配置：
  - `configs/v70/vtest/v3_end2end.yaml`
- 历史 smoke 配置还在，但已不是主入口：
  - `configs/v70/vtest/v3_end2end_actual_qwen35_4b_smoke1.yaml`
  - `configs/v70/vtest/v3_end2end_actual_qwen35_4b.yaml`

### 已验证结果

- `configs/v70/vtest/v3_end2end.yaml`
  - 实际跑通
  - `done=8/8`
  - `err=0`
  - `retries=1`
  - 唯一一次重试是 `08_book` 的 `step3`，第一次输出了坏 key `"<K_KEYWORDS"`，被正常 `post_check` 拦下，第二次修正后通过
  - 已基于当前图片和当前 `extra` 逻辑重新 rerun，不是旧结果残留

输出文件：

- `outputs/v70/vtest/v3_end2end/v3_end2end.jsonl`

## 4. 本地 Qwen3.5-4B server

脚本：

- `servers/qwen35/qwen35_4b_novel2anime.sh`

模型路径：

- `/mnt/d/Novel2Anime/models/llm/Qwen3.5-4B`

启动命令：

```bash
bash servers/qwen35/qwen35_4b_novel2anime.sh
```

检查命令：

```bash
curl http://127.0.0.1:8000/v1/models
curl http://127.0.0.1:8000/health
```

## 5. 一个关键坑

`Qwen3.5-4B` 默认可能只返回 `reasoning`，而 `message.content` 为 `null`。

表现：

- 服务端 `200 OK`
- 但 step1 看起来像“输出为空”

现在的处理方式：

1. 配置中显式加：

```yaml
model:
  extra_body:
    chat_template_kwargs:
      enable_thinking: false
```

2. `module_clients/transports/openai_client.py`
   - 读取 `cfg.max_tokens`
   - 不再把 `reasoning` 当正文兜底
   - 如果 `content` 为空，就按正常错误链路暴露，避免掩盖工程问题

## 6. smoke / mock 测试

文件：

- `module_task_processor/processors/vsmoke/flow_runner_smoke_processor.py`
- `module_task_processor/processors/vsmoke/local_entry.py`
- `prompts/vsmoke/flow_smoke.yaml`

配置：

- `configs/vsmoke/flow_runner_one_step.yaml`
- `configs/vsmoke/flow_runner_multi_step.yaml`
- `configs/vsmoke/flow_runner_split_step.yaml`

用途：

- 不依赖真实模型
- 验证 `FlowRunner` 单步、多步、split 基础链路

另外，单步 / 多步 smoke 现在也用来验证 `extra` 行为：

- 单步：`extra` 保持扁平
- 多步：`extra` 按 step 聚合

## 7. README

README 已补充：

- `FlowRunner` 的用途
- `runner_type: flow` 配置示例
- 本地 4B server 启动方式
- 单图 smoke / 5 图真实测试命令
- `enable_thinking: false` 的说明
- 失败产物输出到 `outputs_failed`
- `extra` 的新语义
- `vis/visualizer_data.py` 的当前能力

## 8. Git 状态

这一轮已经提交并 push：

- commit: `07f81f9`
- message: `Add FlowRunner and end-to-end local VLM tests`

## 9. 近期新增能力

1. 失败产物现在会在 flush 阶段按 `final_file` 写入：
   - `outputs_failed/.../*.failed.jsonl`
   - `outputs_failed/.../*.failed.summary.json`
2. `rerun=True` 时会清理对应失败产物
3. `vis/visualizer_data.py` 已适配：
   - `outputs_failed`
   - `Final / Extra / step outputs / Raw`
   - 单条记录内多选区块并排看
4. `FlowTaskProcessor.extra` 现在支持：
   - 单步扁平
   - 多步按 step 聚合

## 10. 下次继续时建议优先做什么

1. 继续收 prompt 质量，尤其是 `step3` / `step4` 的小模型遵循
2. 逐步把旧 `split / splitseq` 场景迁到 `FlowRunner`
3. 视需要裁剪 `v3_end2end` 里过大的 `step3 extra`（如 `subclass_map / allowed_schema`）
4. 等迁移完成后，再删旧 runner

## 11. 快速恢复命令

### 启动 server

```bash
bash servers/qwen35/qwen35_4b_novel2anime.sh
```

### 跑当前真实 v3

```bash
python main.py --config ./configs/v70/vtest/v3_end2end.yaml
```

### 跑单图 smoke

```bash
python main.py --config ./configs/v70/vtest/v3_end2end_actual_qwen35_4b_smoke1.yaml
```

### 跑 5 图真实测试

```bash
python main.py --config ./configs/v70/vtest/v3_end2end_actual_qwen35_4b.yaml
```

### 跑本地 mock smoke

```bash
python main.py --config ./configs/vsmoke/flow_runner_one_step.yaml
python main.py --config ./configs/vsmoke/flow_runner_multi_step.yaml
python main.py --config ./configs/vsmoke/flow_runner_split_step.yaml
```
