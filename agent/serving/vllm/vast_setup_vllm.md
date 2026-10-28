# 🚀 vLLM Deployment Guide on vast.ai

> **Goal:** Run 2 vLLM models concurrently on a single GPU RTX 3090 (24GB VRAM) on vast.ai with `--max-model-len 4096`, connecting with the locally running Booking Agent System + Prometheus/Grafana observability stack.
>
> | Model | Role | Internal Port | Context Len | `--gpu-memory-utilization` | Approx VRAM |
> |-------|------|---------------|-------------|----------------------------|-------------|
> | `Qwen/Qwen2.5-3B-Instruct-AWQ` | LLM (chat/reasoning) | 18000 (via 8000) | 4096 | `0.50` | ~2.2 GB weights + ~9.8 GB KV cache |
> | `Qwen/Qwen3-Embedding-4B` | Embedding (2560 dims) | 10100 | 4096 | `0.44` | ~8.0 GB weights + ~1.5 GB buffer |

---

## Step 1 — Generate SSH Key

> Skip this step if you already have an SSH key added to your vast.ai account.

```bash
# Open Git Bash, navigate to .ssh directory
cd ~/.ssh

# Generate a new key (name it id_ed25519_vast when prompted)
ssh-keygen -t ed25519 -C "email@gmail.com"
# → Enter file name: id_ed25519_vast
# → Passphrase: (Press Enter to leave empty)

# Add key to SSH agent
eval "$(ssh-agent -s)"
ssh-add id_ed25519_vast

# Copy public key content (paste to vast.ai dashboard → Account → SSH Keys)
cat id_ed25519_vast.pub
```

**On vast.ai:** Go to **Account** → **SSH Keys** → **Add SSH Key** → paste the public key content.

---

## Step 2 — Configure `~/.ssh/config`

```bash
# Open config file (creates new if not exists)
notepad ~/.ssh/config
```

Add the following configuration (replace `<SSH_HOST>` and `<SSH_PORT>` with actual values from vast.ai dashboard):

```ssh-config
# vast.ai — Booking Agent vLLM Server
Host vastai
    HostName <SSH_HOST>
    User root
    Port <SSH_PORT>
    IdentityFile ~/.ssh/id_ed25519_vast
```

> **Where to find the SSH Host & Port?** On the vast.ai dashboard → click your instance → tab **"Connect"** → inspect the line `ssh root@<SSH_HOST> -p <SSH_PORT>`.

---

## Step 3 — Connect via SSH

```bash
ssh vastai
```

---

## Step 4 — Upload vLLM Scripts to vast.ai

> Run from your **local PowerShell** (not inside the SSH session):

```powershell
scp `
    D:\proj\Booking\agent\serving\vllm\configs\start_awq_kv_fp8.sh `
    D:\proj\Booking\agent\serving\vllm\configs\start_embedding.sh `
    D:\proj\Booking\agent\serving\vllm\configs\setup_hf.sh `
    vastai:/root/
```

---

## Step 4.1 — Configure HF_TOKEN & Mirror

> Run inside the **vast.ai SSH workspace**:

```bash
# Export your Hugging Face access token
echo 'export HF_TOKEN="hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"' >> ~/.bashrc

# If server encounters network timeouts or 'Network is unreachable' to huggingface.co, enable mirror:
echo 'export HF_ENDPOINT="https://hf-mirror.com"' >> ~/.bashrc
source ~/.bashrc
```

---

## Step 4.2 — Verify & Clean GPU VRAM

Before launching models, always ensure GPU memory is clean:

```bash
# 1. Check GPU status and current VRAM usage
nvidia-smi

# 2. If memory is occupied by leftover/zombie processes, force kill them:
fuser -k -9 /dev/nvidia*

# 3. Verify VRAM is completely free (0MiB / 24576MiB)
nvidia-smi
```

---

## Step 5 — Start vLLM Servers on vast.ai

> Run inside the **SSH session**:

```bash
# Grant execution permissions
chmod +x start_awq_kv_fp8.sh start_embedding.sh setup_hf.sh

# Run Hugging Face setup & verification
source setup_hf.sh

# Enable mouse scrolling in tmux (optional)
tmux set -g mouse on 2>/dev/null || true

# ── 1. Start LLM Server first (on clean GPU, VRAM util = 0.50) ──
VLLM_PORT=18000 VLLM_GPU_UTIL=0.50 \
  nohup bash start_awq_kv_fp8.sh > llm.log 2>&1 &

# Follow LLM log — wait until "Application startup complete" (~2-3 mins)
tail -f llm.log

# ── 2. Start Embedding Server (after LLM is fully up, VRAM util = 0.44) ──
# Note: Modern vLLM uses --runner pooling instead of deprecated --task embed
VLLM_EMBEDDING_PORT=10100 VLLM_EMBEDDING_GPU_UTIL=0.44 \
  nohup bash start_embedding.sh > embedding.log 2>&1 &

# Follow Embedding log
tail -f embedding.log

# Verify that both servers are healthy and responding internally
curl http://localhost:18000/v1/models
curl http://localhost:10100/v1/models
```

> ⚠️ **First-time model download** takes ~5-10 minutes via `hf-mirror.com`. Using `tmux` prevents termination if your SSH session disconnects.

---

## Step 6 — Get Port Mappings from vast.ai

### Method 1: Check directly in SSH session (Recommended)

Run inside your vast.ai SSH terminal:

```bash
env | grep -iE "port|mapping|portal|host|vast"
```

Look for lines in the format `VAST_TCP_PORT_<INTERNAL>=<EXTERNAL>`:

```text
VAST_TCP_PORT_8000=40439   → Portal proxies 8000 to internal 18000 (LLM external port)
VAST_TCP_PORT_10100=40132  → Embedding external port
VAST_TCP_PORT_22=40002     → SSH port
```

### Method 2: Check on vast.ai Dashboard

Navigate to vast.ai dashboard → click your instance → tab **"Connect"** or **"Port Mappings"**:

```
Internal         →  External
18000 (via 8000) →  XXXXX   ← used for VLLM_BASE_URL
10100            →  YYYYY   ← used for VLLM_EMBEDDING_BASE_URL
```

---

## Step 7 — Update Local `.env`

Open `D:\proj\Booking\agent\.env` and configure:

```bash
# ── CRITICAL: Switch provider to vllm ──
LLM_PROVIDER=vllm

# ── vLLM Endpoints (replace <SSH_HOST> and external ports) ──
VLLM_BASE_URL=http://<SSH_HOST>:40439/v1
VLLM_EMBEDDING_BASE_URL=http://<SSH_HOST>:40132/v1
VLLM_MODEL=Qwen/Qwen2.5-3B-Instruct-AWQ
VLLM_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-4B
VLLM_API_KEY=EMPTY
VLLM_MAX_COMPLETION_TOKENS=1024
VLLM_MAX_CONTEXT_TOKENS=8192

# ── Prometheus scrape targets (host:port, without http:// scheme) ──
VLLM_METRICS_HOST=<SSH_HOST>:40439
VLLM_EMBEDDING_METRICS_HOST=<SSH_HOST>:40132
```

> ⚠️ **Qdrant Collections Notice:** When setting `LLM_PROVIDER=vllm`, the system automatically switches to dedicated collections (`long_term_memory_vllm`, `hotels_collection_vllm`) because Qwen3-Embedding-4B outputs **2560 dimensions** (different from nine_router which uses **1536 dimensions**). These collections are created automatically on the agent's first startup.

---

## Step 8 — Start Local Docker Services

```powershell
cd D:\proj\Booking\agent

# Create Docker network (one-time setup)
docker network create agent_network

# Launch all system services
docker compose up -d

# Inspect agent_api logs to confirm successful vLLM connection
docker compose logs -f agent_api
```

---

## Step 9 — Verify Entire System

```bash
# 1. Verify vLLM LLM server from local machine
curl http://<SSH_HOST>:40439/v1/models

# 2. Verify vLLM Embedding server from local machine
curl http://<SSH_HOST>:40132/v1/models

# 3. Verify FastAPI agent health
curl http://localhost:8080/health

# 4. Access Grafana dashboards
# → http://localhost:3001  (admin / admin)
#   - Dashboard 1: "vLLM — LLM & Embedding Monitor (vast.ai)" (KV Cache %, Preemptions, TTFT, ITL/TPOT, Queue, Prefix Cache)
#   - Dashboard 2: "Booking Agent — LangGraph & Hybrid RAG Monitor" (User TTFT, Node Latency, Token Governance, Semantic Cache, Qdrant RRF)

# 5. Check Prometheus targets — verify all 4 jobs (http-metrics, grpc-metrics, vllm-llm, vllm-embedding) are UP
# → http://localhost:9090/targets
```

---

## Step 10 — Run Capacity, KV Preemption & Load Benchmarks

```bash
# 1. Sanity check both vLLM endpoints (LLM + Embedding 2560 dims)
VLLM_BASE_URL=http://<SSH_HOST>:40439/v1 \
VLLM_EMBEDDING_BASE_URL=http://<SSH_HOST>:40132/v1 \
  python -m serving.vllm.test_connection

# 2. Run vLLM Capacity + Co-located Embedding Stress Test (concurrency 1 -> 32, tracks KV %, waiting queue, preemptions)
VLLM_BASE_URL=http://<SSH_HOST>:40439/v1 \
VLLM_EMBEDDING_BASE_URL=http://<SSH_HOST>:40132/v1 \
BENCHMARK_SUITE=capacity \
  python -m serving.vllm.benchmarks.run_all

# 3. Run End-to-End Agent + RAG SSE Load Test via k6 (streams results into Prometheus & Grafana)
docker compose --profile loadtest run --rm k6_load_test

# 4. Run End-to-End Agent gRPC Streaming Load Test via k6
K6_SCRIPT=grpc_stream_test.js docker compose --profile loadtest run --rm k6_load_test
```

---

## Summary of Startup Sequence

```
[vast.ai]  fuser -k -9 /dev/nvidia* (clean GPU) → nvidia-smi (verify 0MiB)
               ↓
[vast.ai]  Setup HF_TOKEN & mirror → Start LLM (port 18000, 0.50 VRAM)
               ↓ wait for LLM startup complete (~2-3 mins)
[vast.ai]  Start Embedding (port 10100, 0.44 VRAM, --runner pooling)
               ↓
[local]    env | grep -iE "port|vast" → Update .env (VLLM_BASE_URL, ports)
               ↓
[local]    docker compose up -d
               ↓
[verify]   /v1/models + /health + Grafana + Prometheus targets
```

---

## Troubleshooting

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| `No available memory for cache blocks` / `Available KV cache: -X GiB` | Leftover background process or wrong launch order | Run `fuser -k -9 /dev/nvidia*` $\rightarrow$ check `nvidia-smi` is 0MiB $\rightarrow$ start LLM first (`0.50`), wait for it, then start Embedding (`0.44`). |
| `[Errno 101] Network is unreachable` to huggingface.co | Hugging Face blocked in host network / datacenter | Run `export HF_ENDPOINT="https://hf-mirror.com"` in `~/.bashrc`. |
| `unrecognized arguments: --task embed` | vLLM v0.30+ changed embedding argument | Replace `--task embed` with `--runner pooling` in `start_embedding.sh`. |
| `sessions should be nested with care` | Already inside a tmux session | Do not run `tmux new`; use current window or press `Ctrl+B` then `c` to create a new tab. |
| Cannot scroll terminal in tmux | Mouse mode is disabled in tmux by default | Run `tmux set -g mouse on` or press `Ctrl+B` then `[` to enter scroll mode (`q` to exit). |
| `Connection refused` to vLLM | Server has not started or wrong port | Check `tail -f llm.log` or verify port mapping with `env \| grep -iE "port\|vast"`. |
| Grafana has no data | Prometheus cannot scrape vLLM metrics | Check target status at `http://localhost:9090/targets`. |
| Qdrant dimension mismatch error | Using old collection from nine_router | Set `LLM_PROVIDER=vllm` $\rightarrow$ system auto-switches to `_vllm` collections. |
| SSH disconnected during model download | Session timeout | Use `tmux` before running start scripts. |
