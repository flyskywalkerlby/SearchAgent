# export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
python3 -m vllm.entrypoints.openai.api_server \
  --model  /srv/workspace/Kirin_AI_Workspace/AIC_XII/s00893293/models/Qwen3-VL-235B-A22B-Instruct-FP8 \
  --served-model-name qwen3_vl_moe \
  --tensor-parallel-size 8 \
  --max-model-len 8192 \
  --max-num-batched-tokens 8192 \
  --mm-encoder-tp-mode data \
  --limit-mm-per-prompt.video 0 \
  --enable-expert-parallel \
  --host 0.0.0.0 \
  --port 9002 \
  --dtype bfloat16 \
  --gpu-memory-utilization 0.85 \
  --quantization fp8 \
  --max-parallel-loading-workers 1 \
  --max-num-seqs 8