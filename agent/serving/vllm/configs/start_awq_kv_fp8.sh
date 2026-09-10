#!/usr/bin/env bash
# Phase 2.4 — AWQ + FP8 KV Cache (increases KV cache budget)
MODEL="${VLLM_MODEL:-Qwen/Qwen2.5-7B-Instruct-AWQ}"
vllm serve "$MODEL" \
  --host 0.0.0.0 --port 8000 \
  --quantization awq_marlin \
  --kv-cache-dtype fp8 \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --enable-metrics \
  --served-model-name "$(basename $MODEL)"
