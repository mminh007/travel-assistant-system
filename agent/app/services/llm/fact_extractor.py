# app/services/llm/fact_extractor.py
from pydantic import BaseModel, Field
from typing import List, Literal
from langchain_core.messages import SystemMessage, HumanMessage

class FactItem(BaseModel):
    category: Literal["user_preference", "verified_knowledge", "system_constraint"] = Field(
        description="Classify the fact archetype profile context."
    )
    text: str = Field(description="The isolated factual insight extracted cleanly out of the transcript.")
    semantic_anchors: List[str] = Field(
        default_factory=list, 
        description="3 predictable query sentences a human user might provide to look for this exact fact again."
    )
    importance: float = Field(default=0.5)

class LongTermFacts(BaseModel):
    facts: List[FactItem] = Field(default_factory=list)

class FactExtractor:
    def __init__(self, llm_model):
        self.memory_llm = llm_model
        try:
            model_name = getattr(self.memory_llm, "model_name", "") or getattr(self.memory_llm, "model", "")
            if any(tag in str(model_name).lower() for tag in ["3b", "1.5b", "0.5b", "mini", "7b"]):
                self.structured_llm = self.memory_llm.with_structured_output(LongTermFacts, method="json_mode")
            else:
                self.structured_llm = self.memory_llm.with_structured_output(LongTermFacts)
            self._use_structured = True
        except Exception:
            self.structured_llm = self.memory_llm
            self._use_structured = False
        
        self.prompt_instruction = (
            "You are an elite enterprise long-term memory extraction agent.\n"
            "Filter out greeting noise, trivial conversation turns, or failed code snippets.\n"
            "Isolate and structure permanent core insights. Always fulfill the semantic_anchors array parameter."
        )

    async def extract(self, chat_history_messages: list) -> LongTermFacts | None:
        """Analyze the conversation and extract key information."""
        conversation_text = ""
        valid_messages = [msg for msg in chat_history_messages if msg.type in ["human", "ai"]]

        # Only take the last 4 messages to optimize the context window
        for msg in valid_messages[-4:]: 
            role = "User" if msg.__class__.__name__ == "HumanMessage" else "AI"
            conversation_text += f"{role}: {msg.content}\n"

        if not conversation_text.strip():
            return None
            
        if getattr(self, "_use_structured", True):
            try:
                extracted_data = await self.structured_llm.ainvoke([
                    SystemMessage(content=self.prompt_instruction),
                    HumanMessage(content=conversation_text)
                ])
                if extracted_data is not None:
                    return extracted_data
            except Exception:
                pass  # Fall through to manual JSON extraction below

        import json
        resp = await self.memory_llm.ainvoke([
            SystemMessage(content=self.prompt_instruction + 
                '\n\nOutput a valid JSON object matching this schema: {"facts": [{"category": "user_preference", "text": "...", "semantic_anchors": ["..."], "importance": 0.5}]}'),
            HumanMessage(content=conversation_text)
        ])
        try:
            content = resp.content.strip()
            if "```" in content:
                content = content.replace("```json", "").replace("```", "").strip()
            data = json.loads(content)
            return LongTermFacts(**data)
        except Exception:
            return None