# DataGenKit

一个面向图像任务的数据生成框架。当前默认执行模型是 `FlowRunner`，任务形态通过 processor 定义。

## 核心概念

- `input_loader`：定义怎么读数据
- `prompt`：定义当前 step 用什么提示词
- `processor`：定义 step 流程、prompt 组织、post check、最终输出结构
- `FlowRunner`：统一执行单步、多步、split、多步端到端

## 当前支持的输入形式

- `root`
- `meta`
- `jsonl`
- `jsonl_dir`
- `path2info_json`
- `list_of_path2info_json`

当前 example 已覆盖：

- `root`
- `path2info_json`

其余输入形式框架已支持，但本仓库默认不再附带业务化样例。

输入样例统一放在：

- [module_input_loaders/examples](./module_input_loaders/examples)

其中包含：

- `images/`：`root` 示例
- `meta_sample.json` + `meta_annotation.jsonl`：`meta` 示例
- `jsonl_sample.jsonl`：`jsonl` 示例
- `jsonl_dir/`：`jsonl_dir` 示例
- `path2info_sample.json`：`path2info_json` 示例
- `list_of_path2info_sample.json`：`list_of_path2info_json` 示例

## 运行方式

```bash
python main.py --config <config路径>
```

常用参数：

- `--rerun`：删除旧结果后重跑
- `--resume`：继续旧结果
- `--select_datasets xxx yyy`：只跑指定 dataset_name
- `--ignore_datasets xxx yyy`：排除指定 dataset_name
- `--max_step N`：只跑到第 N 步
- `--start_step N`：从第 N 步开始

## Runner

当前默认且唯一推荐的 runner 是 `FlowRunner`。

- `runner_type` 默认就是 `flow`
- 一般不需要显式写
- 如果后续扩展更复杂 runner，参数名仍然保留

## Example 目录说明

### 1. 最小单步示例

配置：

- [example_simple_local.yaml](./configs/examples/example_simple_local.yaml)

对应文件：

- [example_flow_processor.py](./module_task_processor/processors/examples/example_flow_processor.py)
- [local_example_entry.py](./module_task_processor/processors/examples/local_example_entry.py)
- [caption_flow.yaml](./prompts/examples/caption_flow.yaml)

运行：

```bash
python main.py --config ./configs/examples/example_simple_local.yaml
```

### 2. add_info 示例

这个示例演示如何把额外信息注入 prompt。

配置：

- [example_add_info_local.yaml](./configs/examples/example_add_info_local.yaml)

输入数据：

- [path2info_sample.json](./module_input_loaders/examples/path2info_sample.json)

说明：

- 这个例子使用 `path2info_json`
- 每条样本会带上 `data["info"]`
- processor 会把 `info` 拼成 `{{EXTRA_INFO_BLOCK}}`

运行：

```bash
python main.py --config ./configs/examples/example_add_info_local.yaml
```

### 3. Flow 多步示例

单步：

- [example_flow_one_step_local.yaml](./configs/examples/example_flow_one_step_local.yaml)

多步串行：

- [example_flow_multi_step_local.yaml](./configs/examples/example_flow_multi_step_local.yaml)

带 split 的流程：

- [example_flow_split_local.yaml](./configs/examples/example_flow_split_local.yaml)

对应 prompt：

- [flow_examples.yaml](./prompts/examples/flow_examples.yaml)

运行：

```bash
python main.py --config ./configs/examples/example_flow_one_step_local.yaml
python main.py --config ./configs/examples/example_flow_multi_step_local.yaml
python main.py --config ./configs/examples/example_flow_split_local.yaml
```

### 4. prompt 版本切换示例

配置：

- [example_vn.yaml](./configs/examples/example_vn.yaml)

对应 prompt：

- [v1.yaml](./prompts/examples/v1.yaml)
- [v2.yaml](./prompts/examples/v2.yaml)

说明：

- 只有显式写成 `vN` 的字符串才会被 `--gt_version` 替换
- 不写 `vN` 的字段不会动
- 当前实现会递归处理整个 config，所以 `prompt_type`、`output_dir`、`extra` 等字段都可以统一使用这个占位符

运行：

```bash
python main.py --config ./configs/examples/example_vn.yaml --gt_version 1
python main.py --config ./configs/examples/example_vn.yaml --gt_version 2
```

## 如何定义一个新的 Flow processor

最少需要实现这些方法：

- `get_max_step_count`
- `prepare_current_step`
- `post_check_current_step`
- `consume_step_result`

参考：

- [example_flow_processor.py](./module_task_processor/processors/examples/example_flow_processor.py)

如果任务需要：

- 动态 step 切换
- split item 循环
- 依赖前一步输出构造下一步 prompt

就直接在 processor 里做，不需要再新增 runner。

## 输出结构

标准输出记录会包含：

```json
{
  "raw_id": 0,
  "id": "00000000",
  "image": "sample.png",
  "dataset_name": "example",
  "output": {},
  "extra": {},
  "outputs": {
    "step1": {},
    "step2": {}
  }
}
```

说明：

- `output`：最终输出
- `outputs`：每一步的中间结果
- `extra`：各 step 附加信息

## 提示

- 如果你要接真实模型，只需要把 example config 里的 `model` 段替换掉
- 如果你要扩 add_info，优先让输入数据本身携带 `info`，不要把私有数据池逻辑写死到 example 里
