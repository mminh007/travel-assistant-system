#!/usr/bin/env bash
# Embedding model server — Qwen3-Embedding-4B
# NOTE: Embedding models do NOT use KV cache → no --kv-cache-dtype
#       No --quantization needed (8.5GB BF16 fits easily in 24GB GPU)
MODEL="${VLLM_EMBEDDING_MODEL:-Qwen/Qwen3-Embedding-4B}"
echo "[vLLM] Starting Embedding — Model: $MODEL"
vllm serve "$MODEL" \
  --host 0.0.0.0 --port 8001 \
  --task embedding \
  --dtype bfloat16 \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --max-num-seqs 128 \
  --disable-log-requests \
  --uvicorn-log-level warning \
  --served-model-name "$(basename $MODEL)"
