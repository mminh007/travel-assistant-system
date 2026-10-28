#!/usr/bin/env bash
# Phase 2.3 — AWQ + Chunked Prefill (reduces ITL/TPOT spike during concurrent long prompts)
# Sweep CHUNK_SIZE=512 vs CHUNK_SIZE=4096 to benchmark chunked vs unchunked prefill
set -euo pipefail
MODEL="${VLLM_MODEL:-Qwen/Qwen2.5-3B-Instruct-AWQ}"
PORT="${VLLM_PORT:-8080}"
CHUNK_SIZE="${CHUNK_SIZE:-512}"
echo "[vLLM] Starting AWQ + Chunked Prefill (max-num-batched-tokens=$CHUNK_SIZE) — Model: $MODEL on port $PORT"
vllm serve "$MODEL" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --dtype float16 \
  --quantization awq_marlin \
  --enable-chunked-prefill \
  --max-num-batched-tokens "$CHUNK_SIZE" \
  --no-enable-prefix-caching \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.50 \
  --served-model-name "$MODEL" "$(basename "$MODEL")"
