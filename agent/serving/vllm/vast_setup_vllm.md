# 🚀 vLLM Deployment Guide on vast.ai

> **Goal:** Run 2 vLLM models on a single GPU RTX 3090 (24GB VRAM) on vast.ai, connecting with the locally running Booking Agent System.
>
> | Model | Role | Internal Port | VRAM |
> |-------|------|---------------|------|
> | `Qwen/Qwen2.5-7B-Instruct-AWQ` | LLM (chat/reasoning) | 8080 | ~6.5 GB |
> | `Qwen/Qwen3-Embedding-4B` | Embedding (2560 dims) | 8081 | ~8.5 GB |

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

Add the following configuration (replace `<SSH_PORT>` with the actual SSH port from the vast.ai dashboard):

```ssh-config
# vast.ai — Booking Agent vLLM Server
Host vastai
    HostName <SSH_HOST>
    User root
    Port <SSH_PORT>
    IdentityFile ~/.ssh/id_ed25519_vast
```

> **Where to find the SSH Port?** On the vast.ai dashboard → click your instance → tab **"Connect"** → inspect the line `ssh root@... -p XXXXX`.

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

## Step 4.1 — Configure HF_TOKEN

> Run inside the **vast.ai SSH workspace**:

```bash
echo 'export HF_TOKEN="hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"' >> ~/.bashrc
source ~/.bashrc
```

---

## Step 5 — Start vLLM Servers on vast.ai

> Run inside the **SSH session**:

```bash
# Grant execution permissions
chmod +x start_awq_kv_fp8.sh start_embedding.sh setup_hf.sh

# Run Hugging Face setup & verification
source setup_hf.sh

# Optional: recommended to use tmux to persist background jobs
tmux new -s vllm

# Start LLM server (port 8080, background)
VLLM_MODEL=Qwen/Qwen2.5-7B-Instruct-AWQ \
  nohup bash start_awq_kv_fp8.sh > llm.log 2>&1 &

# Start Embedding server (port 8081, background)
VLLM_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-4B \
  nohup bash start_embedding.sh > embedding.log 2>&1 &

# Follow the log — wait for "Application startup complete" (~3-5 minutes)
tail -f llm.log

# Verify that both servers are healthy and responding
curl http://localhost:8080/v1/models
curl http://localhost:8081/v1/models
```

> ⚠️ **First-time model download** may take 10-20 minutes (~14GB in total). Using `tmux` prevents termination if your SSH session disconnects.

---

## Step 6 — Get Port Mappings from vast.ai Dashboard

Navigate to vast.ai dashboard → click your instance → tab **"Connect"** or **"Port Mappings"**:

```
Internal  →  External
8080      →  XXXXX   ← used for VLLM_BASE_URL
8081      →  YYYYY   ← used for VLLM_EMBEDDING_BASE_URL
```

---

## Step 7 — Update Local `.env`

Open `D:\proj\Booking\.env` and configure:

```bash
# ── CRITICAL: Switch provider to vllm ──
LLM_PROVIDER=vllm

# ── vLLM Endpoints (replace XXXXX/YYYYY with actual mapped external ports) ──
VLLM_BASE_URL=http://137.175.22.196:XXXXX/v1
VLLM_EMBEDDING_BASE_URL=http://137.175.22.196:YYYYY/v1
VLLM_MODEL=Qwen/Qwen2.5-7B-Instruct-AWQ
VLLM_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-4B
VLLM_API_KEY=EMPTY

# ── Prometheus scrape targets (host:port, no scheme) ──
VLLM_METRICS_HOST=137.175.22.196:XXXXX
VLLM_EMBEDDING_METRICS_HOST=137.175.22.196:YYYYY
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
# 1. Verify vLLM LLM server
curl http://137.175.22.196:XXXXX/v1/models

# 2. Verify vLLM Embedding server
curl http://137.175.22.196:YYYYY/v1/models

# 3. Verify FastAPI agent health
curl http://localhost:8080/health

# 4. Access Grafana dashboard
# → http://localhost:3001  (admin / admin)

# 5. Check Prometheus targets — verify vllm-llm and vllm-embedding are UP
# → http://localhost:9090/targets
```

---

## Summary of Startup Sequence

```
[vast.ai]  Upload scripts → Setup HF_TOKEN → Start vLLM LLM (port 8080) → Start Embedding (port 8081)
               ↓ wait for models to load (~5-20 minutes)
[local]    Update .env (LLM_PROVIDER=vllm + external URLs + ports)
               ↓
[local]    docker network create agent_network  (initial setup)
               ↓
[local]    docker compose up -d
               ↓
[verify]   /v1/models + /health + Grafana + Prometheus targets
```

---

## Troubleshooting

| Issue                                  | Cause                                 | Solution                                                              |
| -------------------------------------- | ------------------------------------- | --------------------------------------------------------------------- |
| `Connection refused` to vLLM           | Server has not started or wrong port  | Check `tail -f llm.log` on vast.ai                                    |
| Grafana has no data                    | Prometheus cannot scrape vLLM metrics | Check target status at `http://localhost:9090/targets`                |
| Qdrant dimension mismatch error        | Using old collection from nine_router | Set `LLM_PROVIDER=vllm` → system auto-switches to `_vllm` collections |
| SSH disconnected during model download | Session timeout                       | Use `tmux new -s vllm` before running start scripts                   |
| `nohup` process killed                 | vast.ai instance restarted or OOM     | Re-run Step 5 after logging in via SSH                                |
