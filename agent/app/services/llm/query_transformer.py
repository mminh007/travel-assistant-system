# app/services/llm/query_transformer.py
from langchain_core.prompts import ChatPromptTemplate
from app.core.logger import setup_app_logger
from app.graph.config import get_llm_instance, invoke_llm_with_limit

logger = setup_app_logger("QueryTransformer")

transform_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an information retrieval optimizer. Convert the user's latest message and short context into a single, clean, highly effective search query for vector search or search engines. Output ONLY the query, no explanations."),
    ("human", "Context: {context}\nLatest Message: {latest_message}")
])

async def transform_user_query(latest_message: str, history_summary: str = "", config=None) -> str:
    """Transform the user's latest message into an optimized search query."""
    # TIER 1: Fast & Cheap (Router) dynamically loaded
    llm_tier1_fast = get_llm_instance(tier=1, config=config)
    
    messages = transform_prompt.format_messages(context=history_summary, latest_message=latest_message)
    response = await invoke_llm_with_limit(1, llm_tier1_fast, messages, config=config)
    optimized_query = str(response.content).strip().strip('"')
    logger.info(f"==> [Query Transformation] '{latest_message[:30]}...' -> '{optimized_query}'")
    return optimized_query