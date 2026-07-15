import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.worker_main import process_message
import json

@pytest.mark.asyncio
async def test_worker_success():
    mock_msg = AsyncMock()
    mock_msg.body = json.dumps({
        "user_id": "u1",
        "session_id": "s1",
        "target_rag_domain": "general",
        "codename_process": "test"
    }).encode('utf-8')
    mock_msg.process.return_value.__aenter__.return_value = None
    mock_msg.process.return_value.__aexit__.return_value = None
    
    with patch("app.worker_main.AsyncRedisSaver"):
        with patch("app.graph.workflow.agent_graph.compile") as mock_compile:
            mock_graph = AsyncMock()
            mock_state = MagicMock()
            mock_state.values.get.return_value = ["fake_message"]
            mock_graph.aget_state.return_value = mock_state
            mock_compile.return_value = mock_graph
            
            with patch("app.worker_main.MemoryWorker") as mock_memory_worker_class:
                mock_memory_worker = AsyncMock()
                mock_memory_worker_class.return_value = mock_memory_worker
                
                # Also mock container so it doesn't fail accessing container.memory_service
                with patch("app.worker_main.container"):
                    await process_message(mock_msg)
                
                mock_msg.ack.assert_called_once()
                mock_msg.reject.assert_not_called()
                mock_memory_worker.process_extraction_task.assert_called_once_with("u1", "general", ["fake_message"])

@pytest.mark.asyncio
async def test_worker_failure():
    mock_msg = AsyncMock()
    mock_msg.body = json.dumps({
        "user_id": "u1",
        "session_id": "s1"
    }).encode('utf-8')
    mock_msg.process.return_value.__aenter__.return_value = None
    mock_msg.process.return_value.__aexit__.return_value = None
    
    with patch("app.worker_main.AsyncRedisSaver"):
        with patch("app.graph.workflow.agent_graph.compile") as mock_compile:
            mock_graph = AsyncMock()
            mock_state = MagicMock()
            mock_state.values.get.return_value = ["fake_message"]
            mock_graph.aget_state.return_value = mock_state
            mock_compile.return_value = mock_graph
            
            with patch("app.worker_main.MemoryWorker") as mock_memory_worker_class:
                mock_memory_worker = AsyncMock()
                mock_memory_worker.process_extraction_task.side_effect = Exception("Extraction failed")
                mock_memory_worker_class.return_value = mock_memory_worker
                
                with patch("app.worker_main.container"):
                    await process_message(mock_msg)
                
                mock_msg.reject.assert_called_once_with(requeue=False)
                mock_msg.ack.assert_not_called()
