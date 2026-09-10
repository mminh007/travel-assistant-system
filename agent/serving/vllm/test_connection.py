"""Sanity check: verify connection to the vLLM instance (vast.ai or local)."""
import openai
import os
import sys

base_url = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
model = os.environ.get("VLLM_MODEL", "Qwen2.5-7B-Instruct")

print(f"Testing connection to: {base_url}")
print(f"Model: {model}")

client = openai.OpenAI(base_url=base_url, api_key="EMPTY")

# 1. Check /models endpoint
try:
    models = client.models.list()
    print(f"✅ Models available: {[m.id for m in models.data]}")
except Exception as e:
    print(f"❌ /models failed: {e}")
    sys.exit(1)

# 2. Quick completion test
try:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Say 'vLLM OK' and nothing else."}],
        max_tokens=10,
        temperature=0.0,
    )
    print(f"✅ Completion OK: '{response.choices[0].message.content}'")
except Exception as e:
    print(f"❌ Completion failed: {e}")
    sys.exit(1)

# 3. Streaming test
try:
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Count 1 to 5."}],
        max_tokens=20,
        stream=True,
    )
    tokens = [chunk.choices[0].delta.content or "" for chunk in stream]
    print(f"✅ Streaming OK: '{''.join(tokens)}'")
except Exception as e:
    print(f"❌ Streaming failed: {e}")
    sys.exit(1)

print("\n✅ All checks passed — vLLM endpoint is ready.")
