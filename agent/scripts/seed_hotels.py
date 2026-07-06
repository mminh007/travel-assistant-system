import asyncio
import pyodbc
import json
import sys
import os

# Add parent directory to path so we can import from app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.bootstrap.container import container
from app.services.hotel_sync_handler import _build_document

# Database connection details from appsettings.json
DB_CONNECTION_STRING = "Driver={ODBC Driver 17 for SQL Server};Server=PC-MINHNGUYENT;Database=BookingDb;UID=sa;PWD=Password@123;TrustServerCertificate=yes;"

def fetch_hotels_from_db():
    """Fetches all hotels and their room types from SQL Server."""
    hotels = []
    try:
        conn = pyodbc.connect(DB_CONNECTION_STRING)
        cursor = conn.cursor()

        # Get all hotels
        cursor.execute("""
            SELECT Id, Name, Description, Address, City, Country, 
                   StarRating, Latitude, Longitude, Amenities
            FROM Hotels
        """)
        
        hotel_rows = cursor.fetchall()
        
        for row in hotel_rows:
            hotel_id = str(row.Id)
            hotel = {
                "id": hotel_id,
                "name": row.Name,
                "description": row.Description,
                "address": row.Address,
                "city": row.City,
                "country": row.Country,
                "star_rating": row.StarRating,
                "latitude": float(row.Latitude) if row.Latitude else 0.0,
                "longitude": float(row.Longitude) if row.Longitude else 0.0,
                "amenities": json.loads(row.Amenities) if row.Amenities else [],
                "room_types": []
            }
            
            # Get room types for this hotel
            cursor.execute("""
                SELECT Name, Type, PricePerNight, MaxOccupancy
                FROM RoomTypes
                WHERE HotelId = ?
            """, hotel_id)
            
            room_rows = cursor.fetchall()
            for r_row in room_rows:
                hotel["room_types"].append({
                    "name": r_row.Name,
                    "type": r_row.Type,
                    "price_per_night": float(r_row.PricePerNight),
                    "max_occupancy": r_row.MaxOccupancy
                })
                
            hotels.append(hotel)
            
        conn.close()
        return hotels
    except Exception as e:
        print(f"Database error: {e}")
        return []

async def seed():
    print("Initializing Agent Container...")
    await container.initialize()
    
    print("Fetching hotels from SQL Server...")
    hotels = fetch_hotels_from_db()
    print(f"Found {len(hotels)} hotels.")

    for hotel in hotels:
        try:
            document = _build_document(hotel)
            
            prices = [rt.get("price_per_night", 0) for rt in hotel.get("room_types", [])]
            min_price = min(prices) if prices else 0.0
            
            dense_embedding = await container.embedding_provider.embed(document)

            metadata = {
                "name": hotel.get("name"),
                "city": hotel.get("city"),
                "star_rating": hotel.get("star_rating"),
                "min_price": float(min_price),
                "location": {"lat": hotel.get("latitude", 0.0), "lon": hotel.get("longitude", 0.0)},
                "amenities": hotel.get("amenities", [])
            }
            
            await container.hotel_store.upsert_hotel(
                hotel_id=hotel["id"], 
                document=document, 
                dense_embedding=dense_embedding, 
                metadata=metadata
            )
            print(f"  ✅ Seeded: {hotel['name']}")
        except Exception as e:
            print(f"  ❌ Error seeding {hotel.get('name')}: {e}")

    print(f"\n[Seed] Done. Processed {len(hotels)} hotels.")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(seed())
