CUDA_VISIBLE_DEVICES=0 \
python3 -m vllm.entrypoints.openai.api_server \
  --model /srv/workspace/Kirin_AI_DataLake/models/InternVL3_5/InternVL3_5-8B \
  --served-model-name internvl3_5_8b \
  --tensor-parallel-size 1 \
  --max-model-len 8192 \
  --max-num-batched-tokens 8192 \
  --mm-encoder-tp-mode data \
  --limit-mm-per-prompt.video 0 \
  --host 0.0.0.0 \
  --port 9000 \
  --dtype bfloat16 \
  --gpu-memory-utilization 0.9 \
  --max-num-seqs 8 \
  --trust-remote-code
