#!/usr/bin/env bash
# Phase 1 — Baseline: FP16, no optimization
# Used to measure baseline metrics for comparison with optimizations
set -euo pipefail
MODEL="${VLLM_MODEL:-Qwen/Qwen2.5-7B-Instruct}"
echo "[vLLM] Starting BASELINE (FP16, no optimization) — Model: $MODEL"
vllm serve "$MODEL" \
  --host 0.0.0.0 \
  --port 8000 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.85 \
  --enable-metrics \
  --served-model-name "$(basename $MODEL)"
