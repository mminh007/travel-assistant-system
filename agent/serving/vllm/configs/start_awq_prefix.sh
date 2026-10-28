#!/usr/bin/env bash
# Phase 2.2 — AWQ + Automatic Prefix Caching
set -euo pipefail
MODEL="${VLLM_MODEL:-Qwen/Qwen2.5-3B-Instruct-AWQ}"
PORT="${VLLM_PORT:-8080}"
echo "[vLLM] Starting AWQ + Prefix Cache — Model: $MODEL on port $PORT"
vllm serve "$MODEL" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --dtype float16 \
  --quantization awq_marlin \
  --enable-prefix-caching \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.50 \
  --served-model-name "$MODEL" "$(basename "$MODEL")"
