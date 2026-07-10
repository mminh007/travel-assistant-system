# app/mcp/local_tools.py
from langchain_core.tools import tool
from app.bootstrap.container import container
from app.services.llm.query_transformer import transform_user_query

@tool
async def search_hotel_database(
    query: str,
    location: str = None,
    min_stars: int = None,
    max_price: float = None
) -> str:
    """
    Sử dụng tool này để tìm kiếm thông tin chi tiết về khách sạn (địa chỉ, giá, loại phòng, tiện ích)
    trong cơ sở dữ liệu nội bộ.

    Args:
        query: Từ khóa hoặc câu hỏi (ví dụ: "khách sạn 5 sao có hồ bơi").
        location: (Tùy chọn) Thành phố hoặc khu vực (ví dụ: "Nha Trang", "Đà Nẵng").
        min_stars: (Tùy chọn) Số sao tối thiểu (1-5).
        max_price: (Tùy chọn) Giá tối đa mỗi đêm (VND).
    """
    raw_query = f"{query} tại {location}" if location else query
    optimized_query = await transform_user_query(raw_query)

    if not container._initialized:
        await container.initialize()

    # Call hotel_store directly, avoiding HybridRetriever which hardcodes user_id filter
    dense_embedding = await container.embedding_provider.embed(optimized_query)
    hotels = await container.hotel_store.hybrid_search_hotels(
        query_text=optimized_query,
        dense_embedding=dense_embedding,
        top_k=5,
        city=location,
        min_stars=min_stars,
        max_price=max_price,
    )

    if not hotels:
        return "Không tìm thấy khách sạn phù hợp. Hãy thử thay đổi tiêu chí tìm kiếm."

    lines = []
    for h in hotels:
        price_str = f"{h['min_price']:,.0f} VND/đêm" if h.get("min_price") else "Liên hệ"
        lines.append(
            f"🏨 **{h['name']}** ({h.get('star_rating', '?')}★) — {h.get('city', '')}\n"
            f"   Giá từ: {price_str}\n"
            f"   {h['document']}"
        )

    return "\n\n".join(lines)

# List of local tools to be exported
LOCAL_TOOLS = [search_hotel_database]
