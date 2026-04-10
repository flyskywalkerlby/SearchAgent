# vllm serve /srv/workspace/Kirin_AI_DataLake/models/Qwen3.5-122B-A10B/ \
python -m vllm.entrypoints.cli.main serve /srv/workspace/Kirin_AI_DataLake/models/Qwen3.5-122B-A10B/ \
  --host 0.0.0.0 \
  --port 8000 \
  --served-model-name qwen3.5-122b-a10b \
  --tensor-parallel-size 8 \
  --max-model-len 32768 \
  --reasoning-parser qwen3
