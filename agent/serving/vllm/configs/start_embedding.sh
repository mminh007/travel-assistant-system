#!/usr/bin/env bash
# Embedding model server — Qwen/Qwen3-Embedding-4B (2560 dims)
# Co-located on 1x RTX 3090 (24GB VRAM) with LLM server (~13.2 GB / 53.8% VRAM).
# Available VRAM: ~11.35 GB (46.18%).
# Uses 0.44 GPU memory (~10.8 GB) — covers 4B BF16 weights (~7.6 GB) + CUDA graph (~0.26 GB)
# + KV cache (~1.02 GB, needed min 0.56 GB for max-len 4096) with ~537 MB safety buffer.
set -euo pipefail
MODEL="${VLLM_EMBEDDING_MODEL:-Qwen/Qwen3-Embedding-4B}"
PORT="${VLLM_EMBEDDING_PORT:-10100}"
GPU_UTIL="${VLLM_EMBEDDING_GPU_UTIL:-0.44}"
MAX_LEN="${VLLM_EMBEDDING_MAX_LEN:-4096}"
echo "[vLLM] Starting Embedding — Model: $MODEL | port=$PORT | max-len=$MAX_LEN | gpu-util=$GPU_UTIL"
vllm serve "$MODEL" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --runner pooling \
  --dtype bfloat16 \
  --max-model-len "$MAX_LEN" \
  --gpu-memory-utilization "$GPU_UTIL" \
  --max-num-seqs 128 \
  --served-model-name "$MODEL" "$(basename "$MODEL")"
