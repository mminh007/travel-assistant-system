#!/usr/bin/env bash
# Phase 2.4 — AWQ + FP8 KV Cache + Chunked Prefill + Prefix Caching
# Best-effort config: maximises KV cache budget + throughput on a single GPU
MODEL="${VLLM_MODEL:-Qwen/Qwen2.5-7B-Instruct-AWQ}"
echo "[vLLM] Starting LLM — Model: $MODEL"
vllm serve "$MODEL" \
  --host 0.0.0.0 --port 8080 \
  --dtype float16 \
  --quantization awq_marlin \
  --kv-cache-dtype fp8 \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --enable-chunked-prefill \
  --max-num-batched-tokens 512 \
  --enable-prefix-caching \
  --max-num-seqs 64 \
  --served-model-name "$(basename $MODEL)"
