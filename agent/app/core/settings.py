# core/settings.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, BaseModel, Field

class NineRouterSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="NINE_ROUTER_", extra="ignore")
    
    api_key: SecretStr = "nine-router-key"  # 9Router manages real keys
    base_url: str = "http://localhost:20128/v1"
    
    # ─── LLM TIER CONFIGURATION ───
    # Tier 1: High-speed, ultra-low cost. Used for routing, classification, and background data extraction.
    tier1_fast_model: str = "gpt-4o-mini" 
    tier1_temperature: float = 0.0
    
    # Tier 2: Balanced cost/performance. Used for general software engineering and standard chat.
    tier2_balanced_model: str = "gpt-4o" 
    tier2_temperature: float = 0.3
    
    # Tier 3: High-reasoning, expensive. Reserved strictly for complex academic analysis and vision matrix calculations.
    tier3_reasoning_model: str = "o1-mini" 
    
    # Node specific
    fact_check_temperature: float = 0.0
    
    # ─── TOKEN GOVERNANCE ───
    max_completion_tokens: int = 1024  
    max_context_tokens: int = 8192

class VllmSettings(BaseSettings):
    """
    Configuration for vLLM self-hosted on vast.ai.
    Activate by setting: LLM_PROVIDER=vllm in .env

    Vast.ai deployment runs TWO separate vLLM processes:
      - Process 1 (LLM)       : port 8000 — serves the chat/reasoning model
      - Process 2 (Embedding) : port 8001 — serves the embedding model

    vLLM exposes an OpenAI-compatible API:
      - Chat:      POST /v1/chat/completions  (ChatOpenAI)
      - Embedding: POST /v1/embeddings        (OpenAIEmbeddings)

    ⚠️ PORT CONFIGURATION WARNING:
    The agent API server runs on port 8080 to avoid conflicts with default vLLM port 8000.
    If you change agent port back to 8000, VLLM_BASE_URL MUST point to a DIFFERENT HOST 
    (e.g., vast.ai remote URL). Never run vLLM on the same host:port as the agent API server.
    """
    model_config = SettingsConfigDict(env_file=".env", env_prefix="VLLM_", extra="ignore")

    # ─── PROCESS 1: LLM Server (port 8080) ───
    # vast.ai endpoint: http://<host>:<mapped_port>/v1
    base_url: str = "http://localhost:8080/v1"

    # Must match --served-model-name when launching vLLM
    model: str = "Qwen/Qwen2.5-3B-Instruct-AWQ"

    # vLLM doesn't require a real API key
    api_key: SecretStr = SecretStr("EMPTY")

    # Tier mapping — if empty, fallback to self.model
    tier1_fast_model: str = ""
    tier2_balanced_model: str = ""
    tier3_reasoning_model: str = ""
    tier1_temperature: float = 0.0
    tier2_temperature: float = 0.3
    tier3_temperature: float = 0.5

    # Must match --max-model-len of the vLLM instance
    max_completion_tokens: int = 1024
    max_context_tokens: int = 4096

    # ─── PROCESS 2: Embedding Server (port 8081) ───
    # vast.ai endpoint: http://<host>:<mapped_port>/v1
    embedding_base_url: str = "http://localhost:8081/v1"

    # Must match --served-model-name of the embedding vLLM process
    # Qwen3-Embedding-4B outputs 2560 dims; chosen for quality over 0.6B (1024 dims)
    embedding_model: str = "Qwen/Qwen3-Embedding-4B"

    # vLLM embedding server also uses a dummy key
    embedding_api_key: SecretStr = SecretStr("EMPTY")

# Redis configuration for short-term memory management and session state caching
class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="REDIS_", extra="ignore")
    url: str = "redis://localhost:6379/0"
    ttl: int = 3600

# Qdrant configuration for vector storage management
class QdrantSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="QDRANT_", extra="ignore")

    # ─── nine_router / claude provider collections (text-embedding-3-small → 1536 dims) ───
    collection_name: str = "long_term_memory"
    hotels_collection_name: str = "hotels_collection"

    # ─── vLLM provider collections (Qwen3-Embedding-4B → 2560 dims) ───
    # Separate names prevent dimension-mismatch errors when switching providers.
    # The active collection is resolved at runtime by _resolve_active_collection().
    vllm_collection_name: str = "long_term_memory_vllm"
    vllm_hotels_collection_name: str = "hotels_collection_vllm"

    server_host: str = "localhost"
    server_port: str = "6333"

# RabbitMQ configuration for potential future message queue integrations (search for "RabbitMQSettings" in the codebase for usage contexts)
class RabbitMQSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RABBITMQ_", extra="ignore")
    url: str = "amqp://guest:guest@localhost:5672/"
    queue_name: str = "fact_extraction_queue"

# tool for Tavily integration (placeholder for future expansion) (search for "TavilySettings" in the codebase for usage contexts)
class TavilySettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TAVILY_", extra="ignore")
    api_key: SecretStr | None = None
    max_token_budget: int = 2000

# Logs configuration for application-wide logging management
class LogsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="LOGS_", extra="ignore")
    dir: str = "./logs"
    max_bytes: int = 5242880
    backup_count: int = 5

# MCP configuration for securing tool execution
class McpSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MCP_", extra="ignore")
    jwt_secret: SecretStr | None = None

# Security configuration for AI response signatures and handshake keys
class SecuritySettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SECURITY_", extra="ignore")
    
    # ECDSA SECP256R1 Private Key for signing AI Response Receipts
    ai_receipt_private_key: SecretStr
    
    # ECDSA SECP256R1 Public Key for B2B client verification
    ai_receipt_public_key: str
    
    # AES-256-GCM symmetric keys for encrypting user configs in Redis
    redis_encryption_key: SecretStr | None = None
    redis_encryption_old_key: SecretStr | None = None

class NodeTokenLimits(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="NODE_MAX_TOKENS_", extra="ignore")
    input_guardrail: int = 500  # Increased from 150 to 500 to prevent JSON truncation
    support_agent: int = 500
    planner_agent: int = 600
    travel_react_agent: int = 800
    finding_extractor: int = 400
    fact_checker: int = 1000  # Increased from 300 to 1000 to prevent JSON truncation
    evaluator_agent: int = 400
    final_synthesizer: int = 1000
    clarification_agent: int = 200

class GrpcSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="GRPC_", extra="ignore")
    tls_enabled: bool = False
    tls_cert_path: str = ""
    tls_key_path: str = ""
    tls_ca_cert_path: str = ""

class Settings(BaseSettings):
    """Unified application configuration manager grouping domain-specific sub-models.

    Supported LLM providers (llm_provider field):
      - "nine_router" (default): OpenAI-compatible proxy routing through 9Router.
        Embedding: text-embedding-3-small (1536 dims) via nine_router.
      - "vllm": Self-hosted vLLM on vast.ai running TWO processes:
          Process 1 — LLM inference (e.g. Qwen2.5-3B-Instruct-AWQ) on port 8000
          Process 2 — Embedding   (e.g. Qwen3-Embedding-4B, 2560 dims) on port 8001
        Both processes expose the OpenAI-compatible API.
        Qdrant uses dedicated collections (vllm_collection_name) to avoid
        dimension-mismatch with the nine_router collections.
    """
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    llm_provider: str = "nine_router"   # "nine_router" | "vllm"
    vllm: VllmSettings = Field(default_factory=VllmSettings)
    nine_router: NineRouterSettings = Field(default_factory=NineRouterSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    rabbitmq: RabbitMQSettings = Field(default_factory=RabbitMQSettings)
    logs: LogsSettings = Field(default_factory=LogsSettings)
    tavily: TavilySettings = Field(default_factory=TavilySettings)
    mcp: McpSettings = Field(default_factory=McpSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    node_limits: NodeTokenLimits = Field(default_factory=NodeTokenLimits)
    grpc: GrpcSettings = Field(default_factory=GrpcSettings)
    max_rework_cycles: int = 2  # Cap Critic/Evaluator rework loops per task (optimizing small 3B models)
    
@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()