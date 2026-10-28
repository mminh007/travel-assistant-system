#!/usr/bin/env bash
# Phase 2.5 — Speculative Decoding (draft model or prompt lookup ngram)
set -euo pipefail
MAIN_MODEL="${VLLM_MODEL:-Qwen/Qwen2.5-3B-Instruct-AWQ}"
DRAFT_MODEL="${VLLM_DRAFT_MODEL:-Qwen/Qwen2.5-0.5B-Instruct-AWQ}"
PORT="${VLLM_PORT:-8080}"
SPEC_TOKENS="${SPEC_TOKENS:-5}"
echo "[vLLM] Starting Speculative Decoding — Main: $MAIN_MODEL | Draft: $DRAFT_MODEL | k=$SPEC_TOKENS"
vllm serve "$MAIN_MODEL" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --dtype float16 \
  --quantization awq_marlin \
  --speculative-config "{\"model\": \"$DRAFT_MODEL\", \"num_speculative_tokens\": $SPEC_TOKENS}" \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.50 \
  --no-enable-prefix-caching \
  --served-model-name "$MAIN_MODEL" "$(basename "$MAIN_MODEL")"
