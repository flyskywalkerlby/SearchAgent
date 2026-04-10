vllm serve /srv/workspace/Kirin_AI_DataLake/models/Qwen3.5-4B/ \
  --host 0.0.0.0 \
  --port 8000 \
  --served-model-name qwen3.5-4b \
  --max-model-len 32768 \
  --reasoning-parser qwen3 \
  --gpu-memory-utilization 0.85