#!/usr/bin/env bash
# Phase 2.4 — Production vast.ai Config: AWQ + Prefix Caching + Chunked Prefill
# Co-located on 1x RTX 3090 (24GB VRAM) alongside Qwen3-Embedding-4B (0.44 VRAM).
# NOTE: On RTX 3090 (Ampere, SM86), KV cache dtype defaults to 'auto' (FP16) because native
# FP8 KV cache requires Ada/Hopper (SM89+). Override with KV_CACHE_DTYPE=fp8 on L4/4090/H100.
set -euo pipefail
MODEL="${VLLM_MODEL:-Qwen/Qwen2.5-7B-Instruct-AWQ}"
PORT="${VLLM_PORT:-18000}"
KV_DTYPE="${KV_CACHE_DTYPE:-auto}"
GPU_UTIL="${VLLM_GPU_UTIL:-0.50}"
echo "[vLLM] Starting Production LLM — Model: $MODEL | port=$PORT | max-len=4096 | gpu-util=$GPU_UTIL | kv-dtype=$KV_DTYPE"

# TOOL PARSER NOTE:
# Official vLLM and Alibaba Qwen documentation requires '--tool-call-parser hermes' for all
# Qwen/Qwen2.5-* models (chat template in tokenizer_config.json implements Hermes tool use standard).
# '--enable-auto-tool-choice' is mandatory when clients send 'tool_choice="auto"'.
vllm serve "$MODEL" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --dtype float16 \
  --quantization awq_marlin \
  --kv-cache-dtype "$KV_DTYPE" \
  --max-model-len 4096 \
  --gpu-memory-utilization "$GPU_UTIL" \
  --enable-chunked-prefill \
  --max-num-batched-tokens 512 \
  --enable-prefix-caching \
  --max-num-seqs 64 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --served-model-name "$MODEL" "$(basename "$MODEL")"
