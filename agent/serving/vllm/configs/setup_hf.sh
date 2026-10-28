#!/usr/bin/env bash
# ==============================================================================
# Script to configure and verify Hugging Face connectivity on vast.ai / remote server
# ==============================================================================

# 1. Hugging Face Access Token
HF_TOKEN="${HF_TOKEN:-your_hf_token_here}"

if [ "$HF_TOKEN" = "your_hf_token_here" ] || [ -z "$HF_TOKEN" ]; then
    echo "⚠️  WARNING: HF_TOKEN is not set!"
    echo "Please run: export HF_TOKEN='hf_xxxxxxxxxxxxxxxxxxxxxxxx'"
    echo "Or update the HF_TOKEN variable directly inside this script."
    echo ""
fi

# Export environment variables for vLLM & transformers
export HF_TOKEN="$HF_TOKEN"
export HUGGING_FACE_HUB_TOKEN="$HF_TOKEN"

# Support Hugging Face Mirror (default to mirror if huggingface.co is unreachable)
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"

# Accelerate model download speed (if hf_transfer is installed)
export HF_HUB_ENABLE_HF_TRANSFER=1

echo "=== 1. Checking HTTPS connection to $HF_ENDPOINT ==="
curl -I -s --connect-timeout 5 "$HF_ENDPOINT" > /dev/null
if [ $? -eq 0 ]; then
    echo "✅ HTTPS connection to $HF_ENDPOINT successful!"
else
    echo "❌ Failed to connect to $HF_ENDPOINT!"
    echo "💡 Tip: Try running: export HF_ENDPOINT='https://hf-mirror.com'"
fi

echo ""
echo "=== 2. Logging in via Hugging Face CLI ==="
if command -v hf &> /dev/null; then
    if [ "$HF_TOKEN" != "your_hf_token_here" ] && [ -n "$HF_TOKEN" ]; then
        hf auth login --token "$HF_TOKEN"
        echo "✅ Token saved via hf auth login"
    else
        echo "⏭️  Skipping CLI login: no valid token provided."
    fi
elif command -v huggingface-cli &> /dev/null; then
    if [ "$HF_TOKEN" != "your_hf_token_here" ] && [ -n "$HF_TOKEN" ]; then
        huggingface-cli login --token "$HF_TOKEN" --add-to-git-credential
        echo "✅ Token saved to ~/.cache/huggingface/token"
    else
        echo "⏭️  Skipping CLI login: no valid token provided."
    fi
else
    echo "⚠️  Hugging Face CLI not found"
fi

echo ""
echo "=== 3. Verifying access to model Qwen/Qwen2.5-3B-Instruct-AWQ via $HF_ENDPOINT ==="
python3 -c "
import os
import urllib.request
token = os.environ.get('HF_TOKEN', '')
endpoint = os.environ.get('HF_ENDPOINT', 'https://hf-mirror.com').rstrip('/')
headers = {'Authorization': f'Bearer {token}'} if token and token != 'your_hf_token_here' else {}
url = f'{endpoint}/api/models/Qwen/Qwen2.5-3B-Instruct-AWQ'
req = urllib.request.Request(url, headers=headers)
try:
    with urllib.request.urlopen(req, timeout=10) as response:
        if response.status == 200:
            print(f'✅ Authenticated model access for Qwen/Qwen2.5-3B-Instruct-AWQ successfully via {endpoint}!')
except Exception as e:
    print(f'❌ Model verification failed: {e}')
"

echo ""
echo "=== Done! Environment is ready for vLLM ==="
