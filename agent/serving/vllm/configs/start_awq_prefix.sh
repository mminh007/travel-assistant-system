#!/usr/bin/env bash
# Phase 2.2 — AWQ + Automatic Prefix Caching
MODEL="${VLLM_MODEL:-Qwen/Qwen2.5-7B-Instruct-AWQ}"
echo "[vLLM] Starting AWQ + Prefix Cache — Model: $MODEL"
vllm serve "$MODEL" \
  --host 0.0.0.0 \
  --port 8000 \
  --quantization awq_marlin \
  --enable-prefix-caching \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --enable-metrics \
  --served-model-name "$(basename $MODEL)"
