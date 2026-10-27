#!/usr/bin/env bash
# Embedding model server — Qwen/Qwen3-Embedding-4B (2560 dims)
# Co-located on 1x RTX 3090 (24GB VRAM) with LLM server (0.50 VRAM).
# Uses 0.38 GPU memory (~9.1 GB) — sufficient for 4B BF16 weights (~8 GB) + activation buffer.
set -euo pipefail
MODEL="${VLLM_EMBEDDING_MODEL:-Qwen/Qwen3-Embedding-4B}"
PORT="${VLLM_EMBEDDING_PORT:-8081}"
GPU_UTIL="${VLLM_EMBEDDING_GPU_UTIL:-0.38}"
echo "[vLLM] Starting Embedding — Model: $MODEL | port=$PORT | max-len=4096 | gpu-util=$GPU_UTIL"
vllm serve "$MODEL" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --task embed \
  --dtype bfloat16 \
  --max-model-len 4096 \
  --gpu-memory-utilization "$GPU_UTIL" \
  --max-num-seqs 128 \
  --served-model-name "$MODEL" "$(basename "$MODEL")"
