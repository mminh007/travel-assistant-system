import time
from app.interfaces import EmbeddingProvider
from langchain_core.embeddings import Embeddings
from app.core.settings import settings
from app.core.metrics import EMBEDDING_DURATION_SECONDS

class EmbeddingProvider(EmbeddingProvider):
    def __init__(self, embedding_model: Embeddings):
        # Initialize Embeddings using central configuration settings
        # Supports OpenAIEmbeddings, GoogleGenerativeAIEmbeddings, etc.
        self.embeddings = embedding_model

    async def embed(self, text: str) -> list[float]:
        # Return a pure list of floats
        start_ts = time.perf_counter()
        try:
            vec = await self.embeddings.aembed_query(text)
            EMBEDDING_DURATION_SECONDS.labels(status="ok").observe(time.perf_counter() - start_ts)
            return vec
        except Exception:
            EMBEDDING_DURATION_SECONDS.labels(status="error").observe(time.perf_counter() - start_ts)
            raise