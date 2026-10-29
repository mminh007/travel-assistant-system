# app/bootstrap/container.py
from app.infrastructure.embedding_provider import EmbeddingProvider
from app.infrastructure.qdrant import QdrantMemoryStore, QdrantSemanticCache, QdrantVectorStore, QdrantHotelStore
from app.services import MemoryService, MemoryWorker
from app.services import FactExtractor
from app.retrieval import HybridRetriever
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_anthropic import ChatAnthropic
from app.core.settings import settings
from app.core.logger import setup_app_logger
import redis.asyncio as redis_async
import asyncio

logger = setup_app_logger("Container")


def _resolve_default_provider() -> str:
    """
    Determine the system-level default provider from settings.
    - "vllm"       : self-hosted vLLM on vast.ai (LLM + Embedding both self-hosted)
    - "nine_router": OpenAI-compatible proxy (default)
    - "claude"     : Anthropic Claude (fallback when nine_router key absent)
    """
    if settings.llm_provider == "vllm":
        return "vllm"
    if settings.nine_router.api_key:
        return "nine_router"
    return "claude"


def _resolve_cache_model_version(provider: str) -> str:
    """
    Derive a stable, human-readable version tag from the active LLM model name.
    This tag is embedded into every cached entry so that upgrading the LLM model
    automatically bypasses all stale cache entries — zero manual invalidation.
    """
    if provider == "vllm":
        return settings.vllm.model
    if provider == "claude":
        return settings.claude.tier2_balanced_model
    return settings.nine_router.tier2_balanced_model


def _resolve_active_collections() -> tuple[str, str]:
    """
    Returns the Qdrant (memory_collection, hotels_collection) pair for the
    active provider.  vLLM uses separate collection names because Qwen3-Embedding-4B
    produces 2560-dim vectors — incompatible with the 1536-dim nine_router collections.
    """
    if settings.llm_provider == "vllm":
        return (
            settings.qdrant.vllm_collection_name,
            settings.qdrant.vllm_hotels_collection_name,
        )
    return (
        settings.qdrant.collection_name,
        settings.qdrant.hotels_collection_name,
    )


def _resolve_default_embedding(provider: str):
    """
    Create the embedding model instance based on the active provider.

    - vllm      : OpenAIEmbeddings → vLLM embedding server (port 8001)
                  Model: Qwen3-Embedding-4B (2560 dims)
    - nine_router / claude: OpenAIEmbeddings → 9Router proxy
                  Model: text-embedding-3-small (1536 dims)

    Embedding MUST remain fixed per deployment to keep vector spaces compatible.
    Provider switch requires using a different Qdrant collection (see _resolve_active_collections).
    """
    if provider == "vllm":
        api_key = settings.vllm.embedding_api_key.get_secret_value()
        if (not api_key or api_key == "EMPTY") and settings.vllm.api_key:
            api_key = settings.vllm.api_key.get_secret_value()
        model = settings.vllm.embedding_model
        logger.info(f"==> [Container] Using vLLM embedding model: {model} (via {settings.vllm.embedding_base_url})")
        return OpenAIEmbeddings(
            model=model,
            openai_api_key=api_key,
            base_url=settings.vllm.embedding_base_url,
        )

    # nine_router / claude — both route through 9Router for embedding
    api_key = settings.nine_router.api_key.get_secret_value() if settings.nine_router.api_key else None
    logger.info("==> [Container] Using OpenAI-compatible embedding model via 9Router")
    return OpenAIEmbeddings(
        model="text-embedding-3-small",
        openai_api_key=api_key,
        base_url=settings.nine_router.base_url
    )


def _resolve_default_memory_llm(provider: str):
    """
    Create the memory LLM instance (used by FactExtractor) based on the active provider.
    This is a background job — not per-user — so it always uses the cheapest/fastest tier.

    - vllm      : ChatOpenAI → vLLM LLM server (port 8000), tier-1 model or base model
    - claude    : ChatAnthropic → Anthropic tier-1 model
    - nine_router: ChatOpenAI → 9Router proxy, tier-1 model
    """
    if provider == "vllm":
        model = settings.vllm.tier1_fast_model or settings.vllm.model
        api_key = settings.vllm.api_key.get_secret_value()
        logger.info(f"==> [Container] Using vLLM memory LLM: {model} (via {settings.vllm.base_url})")
        return ChatOpenAI(
            model=model,
            temperature=0,
            api_key=api_key,
            base_url=settings.vllm.base_url,
            extra_body={"reasoning_effort": "none"},
        )

    if provider == "claude":
        api_key = settings.claude.api_key.get_secret_value() if settings.claude.api_key else None
        model = settings.claude.tier1_fast_model
        logger.info(f"==> [Container] Using Claude memory LLM: {model}")
        return ChatAnthropic(
            model=model, temperature=0,
            api_key=api_key
        )

    # nine_router: OpenAI-compatible proxy
    api_key = settings.nine_router.api_key.get_secret_value() if settings.nine_router.api_key else None
    model = settings.nine_router.tier1_fast_model
    logger.info(f"==> [Container] Using 9Router memory LLM: {model}")
    return ChatOpenAI(
        model=model, temperature=0,
        api_key=api_key, base_url=settings.nine_router.base_url
    )


class Container:

    def __init__(self):
        self.memory_service = None
        self.memory_worker = None
        self.embedding_provider = None
        self.vector_store = None
        self.memory_store = None
        self.hotel_store = None
        self.extractor = None
        self.semantic_cache = None
        self.hybrid_search = None
        self.redis_client = None
        self._initialized = False
        self._init_lock = asyncio.Lock()

    async def initialize(self):
        async with self._init_lock:
            if self._initialized:
                return
            
            self.redis_client = redis_async.from_url(settings.redis.url)

            # Dynamically resolve embedding + memory LLM from .env default
            default_provider = _resolve_default_provider()
            logger.info(f"==> [Container] Resolved system default provider: {default_provider}")

            embedding_model = _resolve_default_embedding(default_provider)
            memory_llm = _resolve_default_memory_llm(default_provider)

            self.embedding_provider = EmbeddingProvider(embedding_model)

            self.vector_store = QdrantVectorStore()

            self.memory_store = QdrantMemoryStore(
                vector_store=self.vector_store,
                embedding_provider=self.embedding_provider
            )

            # ─── Derive LLM model version for semantic cache versioning ───
            # Changing the LLM in .env automatically invalidates stale cache entries.
            cache_model_version = _resolve_cache_model_version(default_provider)
            logger.info(f"==> [Container] Semantic cache version anchor: '{cache_model_version}'")

            self.semantic_cache = QdrantSemanticCache(
                self.vector_store,
                self.embedding_provider,
                model_version=cache_model_version
            )

            self.memory_service = MemoryService(self.memory_store)

            self.extractor = FactExtractor(memory_llm)

            self.memory_worker = MemoryWorker(
                memory_service=self.memory_service,
                extractor=self.extractor
            )

            self.hybrid_search = HybridRetriever(
                embedding_provider=self.embedding_provider,
                vector_store=self.vector_store
            )

            self.hotel_store = QdrantHotelStore()
            logger.info("==> [Container] QdrantHotelStore initialized.")
            
            self._initialized = True

    async def shutdown(self):
        if self.redis_client:
            await self.redis_client.aclose()

container = Container()