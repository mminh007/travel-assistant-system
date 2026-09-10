#!/usr/bin/env bash
# Phase 2.3 — AWQ + Chunked Prefill (reduces TTFT spike with long prompts)
MODEL="${VLLM_MODEL:-Qwen/Qwen2.5-7B-Instruct-AWQ}"
vllm serve "$MODEL" \
  --host 0.0.0.0 --port 8000 \
  --quantization awq_marlin \
  --enable-chunked-prefill \
  --max-num-batched-tokens 512 \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --enable-metrics \
  --served-model-name "$(basename $MODEL)"
