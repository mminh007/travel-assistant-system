#!/usr/bin/env bash
# ==============================================================================
# Script to configure and verify Hugging Face connectivity on vast.ai / remote server
# ==============================================================================

# 1. Provide your Hugging Face Access Token here (or export HF_TOKEN before running)
# Get your token at: https://huggingface.co/settings/tokens (Read permission is sufficient)
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

# Accelerate model download speed (if hf_transfer is installed)
export HF_HUB_ENABLE_HF_TRANSFER=1

# Optional: If your server encounters network timeouts reaching huggingface.co, uncomment below:
# export HF_ENDPOINT="https://hf-mirror.com"

echo "=== 1. Checking HTTPS connection to Hugging Face ==="
curl -I -s --connect-timeout 5 https://huggingface.co > /dev/null
if [ $? -eq 0 ]; then
    echo "✅ HTTPS connection to huggingface.co successful!"
else
    echo "❌ Failed to connect to huggingface.co!"
    echo "💡 Tip: Try enabling the mirror by running: export HF_ENDPOINT='https://hf-mirror.com'"
fi

echo ""
echo "=== 2. Logging in via Hugging Face CLI ==="
if command -v huggingface-cli &> /dev/null; then
    if [ "$HF_TOKEN" != "your_hf_token_here" ] && [ -n "$HF_TOKEN" ]; then
        huggingface-cli login --token "$HF_TOKEN" --add-to-git-credential
        echo "✅ Token saved to ~/.cache/huggingface/token"
    else
        echo "⏭️  Skipping CLI login: no valid token provided."
    fi
else
    echo "⚠️  huggingface-cli not found (run: pip install -U 'huggingface_hub[cli]')"
fi

echo ""
echo "=== 3. Verifying access to model Qwen/Qwen2.5-7B-Instruct-AWQ ==="
python3 -c "
import os
import urllib.request
token = os.environ.get('HF_TOKEN', '')
headers = {'Authorization': f'Bearer {token}'} if token and token != 'your_hf_token_here' else {}
url = 'https://huggingface.co/api/models/Qwen/Qwen2.5-7B-Instruct-AWQ'
req = urllib.request.Request(url, headers=headers)
try:
    with urllib.request.urlopen(req, timeout=10) as response:
        if response.status == 200:
            print('✅ Authenticated model access for Qwen/Qwen2.5-7B-Instruct-AWQ successfully!')
except Exception as e:
    print(f'❌ Model verification failed: {e}')
"

echo ""
echo "=== Done! To apply HF_TOKEN to your current shell session ==="
echo "Run:"
echo "    source $0"
echo "Or add it permanently to ~/.bashrc:"
echo "    echo 'export HF_TOKEN=\"$HF_TOKEN\"' >> ~/.bashrc"
