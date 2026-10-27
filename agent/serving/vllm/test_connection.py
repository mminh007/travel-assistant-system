"""Sanity check: verify connection to both vLLM LLM & Embedding servers (vast.ai or local)."""
import openai
import os
import sys

base_url = os.environ.get("VLLM_BASE_URL", "http://localhost:8080/v1")
embed_base_url = os.environ.get("VLLM_EMBEDDING_BASE_URL", "http://localhost:8081/v1")
model = os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-7B-Instruct-AWQ")
embed_model = os.environ.get("VLLM_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-4B")

print(f"Testing LLM connection      : {base_url} (model={model})")
print(f"Testing Embedding connection: {embed_base_url} (model={embed_model})")

client = openai.OpenAI(base_url=base_url, api_key="EMPTY")
embed_client = openai.OpenAI(base_url=embed_base_url, api_key="EMPTY")

# 1. Check LLM /models endpoint
try:
    models = client.models.list()
    print(f"[OK] LLM models available: {[m.id for m in models.data]}")
except Exception as e:
    print(f"[FAIL] LLM /models failed: {e}")
    sys.exit(1)

# 2. Quick completion test
try:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Say 'vLLM OK' and nothing else."}],
        max_tokens=10,
        temperature=0.0,
    )
    print(f"[OK] Completion OK: '{response.choices[0].message.content}'")
except Exception as e:
    print(f"[FAIL] Completion failed: {e}")
    sys.exit(1)

# 3. Streaming test
try:
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Count 1 to 5."}],
        max_tokens=20,
        stream=True,
    )
    tokens = [chunk.choices[0].delta.content or "" for chunk in stream if chunk.choices]
    print(f"[OK] Streaming OK: '{''.join(tokens)}'")
except Exception as e:
    print(f"[FAIL] Streaming failed: {e}")
    sys.exit(1)

# 4. Embedding test (2560 dims for Qwen/Qwen3-Embedding-4B)
try:
    emb = embed_client.embeddings.create(
        model=embed_model,
        input="Khách sạn 5 sao gần biển Đà Nẵng",
    )
    dim = len(emb.data[0].embedding)
    print(f"[OK] Embedding OK: vector dim={dim} (expected 2560 for Qwen3-Embedding-4B)")
except Exception as e:
    print(f"[WARN] Embedding check failed (optional if running LLM-only test): {e}")

print("\n[OK] All checks completed — vLLM endpoints are ready.")
