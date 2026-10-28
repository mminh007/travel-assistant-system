#!/usr/bin/env bash
# Phase 1 — Baseline: FP16, no optimization (prefix cache disabled)
# Used to measure baseline metrics for comparison with AWQ & prefix/chunked optimizations
set -euo pipefail
MODEL="${VLLM_MODEL:-Qwen/Qwen2.5-3B-Instruct}"
PORT="${VLLM_PORT:-8080}"
echo "[vLLM] Starting BASELINE (FP16, no optimization) — Model: $MODEL on port $PORT"
vllm serve "$MODEL" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --dtype float16 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.50 \
  --no-enable-prefix-caching \
  --served-model-name "$MODEL" "$(basename "$MODEL")"
