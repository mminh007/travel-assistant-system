#!/usr/bin/env bash
# Phase 2.5 — Speculative Decoding (draft model)
MAIN_MODEL="${VLLM_MAIN_MODEL:-Qwen/Qwen2.5-7B-Instruct-AWQ}"
DRAFT_MODEL="${VLLM_DRAFT_MODEL:-Qwen/Qwen2.5-1.5B-Instruct}"
vllm serve "$MAIN_MODEL" \
  --host 0.0.0.0 --port 8000 \
  --quantization awq_marlin \
  --speculative-model "$DRAFT_MODEL" \
  --num-speculative-tokens "${SPEC_TOKENS:-5}" \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --enable-metrics \
  --served-model-name "$(basename $MAIN_MODEL)"
