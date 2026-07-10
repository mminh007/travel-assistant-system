# app/services/user_config_service.py
import json
import app.core.logger as logger
from app.core.helpers.crypto_helper import decrypt_value

log = logger.setup_app_logger("UserConfigService")

async def load_user_llm_config(user_id: str, redis_client) -> dict:
    """
    Loads and decrypts user LLM provider config from Redis.
    Returns a dictionary with:
    - llm_provider: str | None
    - api_key: str | None
    - use_default_key: bool
    """
    user_config = {}
    if not redis_client:
        return user_config
        
    try:
        user_config_data = await redis_client.get(f"user_config:{user_id}")
        if user_config_data:
            parsed_config = json.loads(user_config_data)
            
            # Extract basic settings
            user_config["llm_provider"] = parsed_config.get("llm_provider")
            user_config["use_default_key"] = parsed_config.get("use_default_key", False)
            
            # Extract and decrypt API key
            stored_api_key = parsed_config.get("api_key")
            if stored_api_key:
                decrypted_key = decrypt_value(stored_api_key)
                if decrypted_key is None:
                    log.warning(f"[SecurityConfig] Stored api_key could not be decrypted for user={user_id} - falling back to default")
                else:
                    user_config["api_key"] = decrypted_key
    except Exception as e:
        log.error(f"Failed to parse user config from Redis for user {user_id}: {e}")
        
    return user_config
