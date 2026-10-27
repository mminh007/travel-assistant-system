"""
Master benchmark runner — executes vLLM & Embedding benchmark suites.

Usage:
  VLLM_BASE_URL=http://<vast-ip>:<port>/v1 \
  VLLM_EMBEDDING_BASE_URL=http://<vast-ip>:<embed-port>/v1 \
  VLLM_MODEL=Qwen/Qwen2.5-7B-Instruct-AWQ \
  VLLM_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-4B \
  BENCHMARK_SUITE=capacity \
    python -m serving.vllm.benchmarks.run_all

Available BENCHMARK_SUITE values:
  baseline, quant, prefix_cache, chunked_prefill, spec_decoding, capacity, all
"""
import asyncio
import os

SUITE = os.environ.get("BENCHMARK_SUITE", "capacity")


async def main():
    print(f"\n{'=' * 68}")
    print(f"  vLLM Benchmark Runner — Suite: {SUITE.upper()}")
    print(f"{'=' * 68}\n")

    if SUITE in ("baseline", "all"):
        print("── Running: Baseline ──")
        from serving.vllm.benchmarks.baseline_benchmark import main as baseline
        await baseline()

    if SUITE in ("quant", "all"):
        print("\n── Running: Quantization (AWQ-INT4) ──")
        from serving.vllm.benchmarks.quant_benchmark import main as quant
        await quant()

    if SUITE in ("prefix_cache", "all"):
        print("\n── Running: Prefix Cache (Cold vs Warm RAG Prefix) ──")
        from serving.vllm.benchmarks.prefix_cache_test import run_prefix_cache_test
        await run_prefix_cache_test()

    if SUITE in ("chunked_prefill", "all"):
        print("\n── Running: Chunked Prefill (Mixed Decode + Long Prefill) ──")
        from serving.vllm.benchmarks.chunked_prefill_test import main as chunked
        await chunked()

    if SUITE in ("spec_decoding", "all"):
        print("\n── Running: Speculative Decoding ──")
        from serving.vllm.benchmarks.spec_decoding_test import main as spec
        await spec()

    if SUITE in ("capacity", "all"):
        print("\n── Running: Capacity, KV Preemption & Co-located Embedding Stress Test ──")
        from serving.vllm.benchmarks.capacity_stress_test import main as capacity
        await capacity()

    print(f"\n{'=' * 68}")
    print("  Benchmarks complete. Results saved in serving/vllm/results/")
    print(f"{'=' * 68}\n")


if __name__ == "__main__":
    asyncio.run(main())
