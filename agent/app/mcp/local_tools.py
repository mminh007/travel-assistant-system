# app/mcp/local_tools.py
from langchain_core.tools import tool
from app.bootstrap.container import container
from app.services.query_transformer import transform_user_query

@tool
async def search_hotel_database(query: str, location: str = None) -> str:
    """
    Sử dụng tool này để tìm kiếm thông tin chi tiết về khách sạn (địa chỉ, giá, loại phòng, tiện ích) 
    hoặc thông tin du lịch trong cơ sở dữ liệu nội bộ.
    
    Args:
        query: Từ khóa hoặc câu hỏi tìm kiếm (ví dụ: "khách sạn 5 sao có hồ bơi", "tên khách sạn X").
        location: (Tùy chọn) Địa điểm cụ thể (ví dụ: "Nha Trang", "đảo Hòn Tre").
    """
    # Combine query and location for the transformer
    raw_query = f"{query} tại {location}" if location else query
    
    # Enhance the query using the unused query_transformer
    optimized_query = await transform_user_query(raw_query)
    
    # Ensure container is initialized
    if not container.hybrid_search:
        await container.initialize()
        
    # Search the vector database
    # "system" is used as a generic user_id since this is an internal agent call
    results = await container.hybrid_search.retrieve("system", optimized_query, collection="travel_knowledge")
    
    if not results or results.strip() == "":
        return "Không tìm thấy thông tin phù hợp trong cơ sở dữ liệu nội bộ. Hãy thử mở rộng phạm vi tìm kiếm hoặc dùng web search."
        
    return results

# List of local tools to be exported
LOCAL_TOOLS = [search_hotel_database]
