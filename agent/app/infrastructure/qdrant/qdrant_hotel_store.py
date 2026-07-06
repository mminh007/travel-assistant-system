import asyncio
import uuid
from typing import Optional
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance, PointStruct,
    SparseVectorParams, SparseVector,
    Prefetch, Filter, FieldCondition, MatchValue, Range,
    FusionQuery, Fusion, ScalarQuantization, ScalarQuantizationConfig, ScalarType,
    PayloadSchemaType, TextIndexParams, TokenizerType
)
from app.core.logger import setup_app_logger
from app.core.settings import settings
from fastembed import SparseTextEmbedding

logger = setup_app_logger("QdrantHotelStore")

class QdrantHotelStore:
    """
    Dedicated Qdrant store for hotels_collection.
    Completely isolated from memory/cache stores.
    Indexes: city (KEYWORD), star_rating (INTEGER), min_price (FLOAT), location (GEO).
    """
    def __init__(self):
        self.client = QdrantClient(
            host=settings.qdrant.server_host,
            port=settings.qdrant.server_port,
        )
        self.sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")

    def _ensure_hotel_collection(self, dense_dim: int):
        """Creates hotels_collection with appropriate indexes for the Hotel domain."""
        if self.client.collection_exists(settings.qdrant.hotels_collection_name):
            return

        self.client.create_collection(
            collection_name=settings.qdrant.hotels_collection_name,
            vectors_config={
                "text-dense": VectorParams(
                    size=dense_dim,
                    distance=Distance.COSINE,
                    on_disk=True,
                    quantization_config=ScalarQuantization(
                        scalar=ScalarQuantizationConfig(
                            type=ScalarType.INT8,
                            quantile=0.99,
                            always_ram=True
                        )
                    )
                )
            },
            sparse_vectors_config={
                "text-sparse": SparseVectorParams(modifier=None)
            }
        )

        # ─── Hotel-specific Payload Indexes ───
        self.client.create_payload_index(
            collection_name=settings.qdrant.hotels_collection_name,
            field_name="city",
            field_schema=PayloadSchemaType.KEYWORD
        )
        self.client.create_payload_index(
            collection_name=settings.qdrant.hotels_collection_name,
            field_name="star_rating",
            field_schema=PayloadSchemaType.INTEGER
        )
        self.client.create_payload_index(
            collection_name=settings.qdrant.hotels_collection_name,
            field_name="min_price",
            field_schema=PayloadSchemaType.FLOAT
        )
        # GEO index - required for GeoRadius filter
        self.client.create_payload_index(
            collection_name=settings.qdrant.hotels_collection_name,
            field_name="location",
            field_schema=PayloadSchemaType.GEO
        )
        # Full-text index for semantic BM25 sparse search
        self.client.create_payload_index(
            collection_name=settings.qdrant.hotels_collection_name,
            field_name="document",
            field_schema=TextIndexParams(
                type="text",
                tokenizer=TokenizerType.WORD,
                min_token_len=2,
                max_token_len=20,
                lowercase=True
            )
        )

        logger.info(f"==> [HotelStore] Created '{settings.qdrant.hotels_collection_name}' with Hotel indexes: city, star_rating, min_price, location (GEO).")

    async def upsert_hotel(self, hotel_id: str, document: str, dense_embedding: list[float], metadata: dict):
        """Upserts a hotel point into Qdrant. Uses hotel_id (Guid) as original_id."""
        await asyncio.to_thread(self._ensure_hotel_collection, len(dense_embedding))

        sparse_list = list(self.sparse_model.embed([document]))
        sparse = sparse_list[0]

        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, hotel_id))
        point = PointStruct(
            id=point_id,
            vector={
                "text-dense": dense_embedding,
                "text-sparse": SparseVector(
                    indices=sparse.indices.tolist(),
                    values=sparse.values.tolist()
                )
            },
            payload={
                "document": document,
                "hotel_id": hotel_id,
                **metadata,
                "original_id": hotel_id
            }
        )

        await asyncio.to_thread(
            self.client.upsert,
            collection_name=settings.qdrant.hotels_collection_name,
            points=[point]
        )
        logger.info(f"==> [HotelStore] Upserted hotel {hotel_id}.")

    async def delete_hotel(self, hotel_id: str):
        """Deletes hotel from Qdrant by hotel_id."""
        delete_filter = Filter(must=[
            FieldCondition(key="hotel_id", match=MatchValue(value=hotel_id))
        ])
        await asyncio.to_thread(
            self.client.delete,
            collection_name=settings.qdrant.hotels_collection_name,
            points_selector=delete_filter
        )
        logger.info(f"==> [HotelStore] Deleted hotel {hotel_id}.")

    async def hybrid_search_hotels(
        self,
        query_text: str,
        dense_embedding: list[float],
        top_k: int = 5,
        city: Optional[str] = None,
        min_stars: Optional[int] = None,
        max_price: Optional[float] = None,
    ) -> list[dict]:
        """
        Hybrid search Hotel (Dense + BM25 Sparse + RRF).
        Supports hard pre-filtering by city, star_rating, max_price.
        No user_id filtering as hotels_collection is shared data.
        """
        exists = await asyncio.to_thread(self.client.collection_exists, settings.qdrant.hotels_collection_name)
        if not exists:
            return []

        # ─── Build Pre-filter ───
        conditions = []
        if city:
            conditions.append(FieldCondition(key="city", match=MatchValue(value=city)))
        if min_stars:
            conditions.append(FieldCondition(key="star_rating", range=Range(gte=min_stars)))
        if max_price:
            conditions.append(FieldCondition(key="min_price", range=Range(lte=max_price)))

        qdrant_filter = Filter(must=conditions) if conditions else None

        # ─── Sparse Vector ───
        sparse_list = list(self.sparse_model.embed([query_text]))
        sparse = sparse_list[0]
        query_sparse = SparseVector(
            indices=sparse.indices.tolist(),
            values=sparse.values.tolist()
        )

        prefetch = [
            Prefetch(query=query_sparse, using="text-sparse", limit=top_k * 2),
            Prefetch(query=dense_embedding, using="text-dense", limit=top_k * 2),
        ]

        results = await asyncio.to_thread(
            self.client.query_points,
            collection_name=settings.qdrant.hotels_collection_name,
            prefetch=prefetch,
            query=FusionQuery(fusion=Fusion.RRF),
            query_filter=qdrant_filter,
            limit=top_k
        )

        hotels = []
        for p in results.points:
            hotels.append({
                "hotel_id": p.payload.get("hotel_id"),
                "document": p.payload.get("document", ""),
                "name": p.payload.get("name"),
                "city": p.payload.get("city"),
                "star_rating": p.payload.get("star_rating"),
                "min_price": p.payload.get("min_price"),
                "amenities": p.payload.get("amenities", []),
                "score": p.score
            })

        logger.info(f"==> [HotelStore] Found {len(hotels)} hotels for query: '{query_text}'")
        return hotels
