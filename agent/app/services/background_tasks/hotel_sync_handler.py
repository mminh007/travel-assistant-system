# app/services/background_tasks/hotel_sync_handler.py   
import json
import aio_pika
from app.core.logger import setup_app_logger
from app.bootstrap.container import container

logger = setup_app_logger("HotelSyncHandler")

def _build_document(data: dict) -> str:
    """
    Static template string - avoids using AI to prevent hallucination.
    Combines all important keywords for BM25 + Dense matching.
    """
    name = data.get("name", "")
    star = data.get("star_rating", "")
    city = data.get("city", "")
    address = data.get("address", "")
    amenities = ", ".join(data.get("amenities", []))
    description = data.get("description", "")

    room_parts = []
    for rt in data.get("room_types", []):
        room_parts.append(
            f"{rt.get('name', '')} (max {rt.get('max_occupancy', '')} people) "
            f"price {rt.get('price_per_night', 0):,}/night"
        )
    rooms_str = "; ".join(room_parts) if room_parts else "No room information"

    return (
        f"Hotel {name}, {star} stars, located in {city}, "
        f"address: {address}. "
        f"Amenities include: {amenities}. "
        f"Available rooms: {rooms_str}. "
        f"Additional info: {description}"
    )

async def process_hotel_sync_message(message: aio_pika.IncomingMessage):
    try:
        async with message.process():
            payload = json.loads(message.body.decode())
            action = payload.get("action_type")    # Create | Update | Delete
            hotel_id = payload.get("hotel_id")
            data = payload.get("data", {})

            logger.info(f"==> [HotelSync] Received action='{action}' for hotel_id={hotel_id}")

            if not container._initialized:
                await container.initialize()

            if action == "Delete":
                await container.hotel_store.delete_hotel(hotel_id)
                logger.info(f"==> [HotelSync] Deleted hotel {hotel_id} from Qdrant.")

            elif action in ("Create", "Update"):
                # 1. Build document text from template string
                document = _build_document(data)

                # 2. Calculate min_price from room_types
                prices = [rt.get("price_per_night", 0) for rt in data.get("room_types", [])]
                min_price = min(prices) if prices else 0.0

                # 3. Embed document -> Dense Vector
                dense_embedding = await container.embedding_provider.embed(document)

                # 4. Metadata (not embedded, used for filtering)
                metadata = {
                    "name": data.get("name"),
                    "city": data.get("city"),
                    "star_rating": data.get("star_rating"),
                    "min_price": float(min_price),
                    "location": {
                        "lat": data.get("latitude", 0.0),
                        "lon": data.get("longitude", 0.0)
                    },
                    "amenities": data.get("amenities", [])
                }

                await container.hotel_store.upsert_hotel(hotel_id, document, dense_embedding, metadata)
                logger.info(f"==> [HotelSync] Upserted hotel '{data.get('name')}' into Qdrant.")

    except Exception as e:
        logger.error(f"❌ [HotelSync] Failed to process message: {e}")
