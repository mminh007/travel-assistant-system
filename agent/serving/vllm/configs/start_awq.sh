#!/usr/bin/env bash
# Phase 2.1 — AWQ INT4 Quantization (prefix cache disabled for pure quantization A/B)
set -euo pipefail
MODEL="${VLLM_MODEL:-Qwen/Qwen2.5-3B-Instruct-AWQ}"
PORT="${VLLM_PORT:-8080}"
echo "[vLLM] Starting AWQ-INT4 — Model: $MODEL on port $PORT"
vllm serve "$MODEL" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --dtype float16 \
  --quantization awq_marlin \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.50 \
  --no-enable-prefix-caching \
  --served-model-name "$MODEL" "$(basename "$MODEL")"
