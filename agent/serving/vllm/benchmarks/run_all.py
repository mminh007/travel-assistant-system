"""
Master benchmark runner — executes the entire experiment matrix.

Requires: vLLM instance running with the corresponding config.
Usage:
  # 1. Start vLLM with the desired test config:
  bash serving/vllm/configs/start_awq_prefix.sh

  # 2. Run the corresponding benchmark:
  VLLM_BASE_URL=http://localhost:8000/v1 \
  VLLM_MODEL=Qwen2.5-7B-Instruct-AWQ \
  BENCHMARK_SUITE=prefix_cache \
    python -m serving.vllm.benchmarks.run_all

Available BENCHMARK_SUITE values:
  baseline, quant, prefix_cache, chunked_prefill, spec_decoding, all
"""
import asyncio
import os
import sys

SUITE = os.environ.get("BENCHMARK_SUITE", "baseline")


async def main():
    print(f"\n{'='*60}")
    print(f"  vLLM Benchmark Runner — Suite: {SUITE.upper()}")
    print(f"{'='*60}\n")

    if SUITE in ("baseline", "all"):
        print("── Running: Baseline (FP16) ──")
        from serving.vllm.benchmarks.baseline_benchmark import main as baseline
        await baseline()

    if SUITE in ("quant", "all"):
        print("\n── Running: Quantization (AWQ) ──")
        from serving.vllm.benchmarks.quant_benchmark import main as quant
        await quant()

    if SUITE in ("prefix_cache", "all"):
        print("\n── Running: Prefix Cache ──")
        from serving.vllm.benchmarks.prefix_cache_test import run_prefix_cache_test
        await run_prefix_cache_test()

    if SUITE in ("chunked_prefill", "all"):
        print("\n── Running: Chunked Prefill ──")
        from serving.vllm.benchmarks.chunked_prefill_test import main as chunked
        await chunked()

    if SUITE in ("spec_decoding", "all"):
        print("\n── Running: Speculative Decoding ──")
        from serving.vllm.benchmarks.spec_decoding_test import main as spec
        await spec()

    print(f"\n{'='*60}")
    print("  All benchmarks complete. Results in serving/vllm/results/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
