from typing import Dict, Any, List, Literal, Optional
from pydantic import BaseModel, Field

class InputGuardrailOutput(BaseModel):
    is_in_domain: bool = Field(description="True if the request is related to travel, flights, hotels, or travel FAQs. False otherwise.")
    intent_category: Literal["hotel_booking", "travel_faq", "itinerary_planning", "system_navigation_faq", "out_of_domain", "ambiguous"] = Field(description="The category of the user's request.")
    complexity: str = Field(description="Level of complexity: 'low', 'medium', 'high'.")
    objective: str = Field(description="The overarching execution objective for the Planner.")
    detected_language: str = Field(description="The detected language of the user's prompt (e.g., 'English', 'Vietnamese', 'Spanish').")
    rationale: str = Field(description="Internal chain-of-thought justification.")
    confidence: float = Field(default=1.0, description="Confidence score 0.0-1.0 for the intent classification.")
    ambiguity_reason: Optional[str] = Field(default=None, description="If confidence < 0.7, explain what is ambiguous.")

class TaskItem(BaseModel):
    id: int = Field(description="Unique incremental ID for the task.")
    description: str = Field(description="Clear, actionable description of the sub-task.")

class PlannerOutput(BaseModel):
    tasks: List[TaskItem] = Field(description="List of sequential tasks required to fulfill the user's travel request.")

class Finding(BaseModel):
    statement: str = Field(description="A concise factual statement.")
    evidence: Optional[str] = Field(default=None, description="Evidence or citation supporting this statement.")
    confidence: float = Field(description="Confidence level in this finding (0.0 to 1.0).")

class ExecutorOutput(BaseModel):
    """
    Schema used exclusively by node_finding_extractor (not by executor nodes directly).
    Executor nodes now produce free-form Markdown; this schema is applied in a
    dedicated downstream extraction step to avoid JSON formatting failures.
    """
    result_summary: str = Field(description="A concise 1-3 sentence summary of the main answer or result.")
    findings: List[Finding] = Field(description="Key factual findings extracted from the executor's response.")

class EvaluatorOutput(BaseModel):
    objective_met: bool = Field(description="Assess if the executor fully achieved the initial objective.")
    tool_quality_score: int = Field(description="Score (1-10) evaluating the appropriate use of tools and context.")
    evidence_quality_score: int = Field(description="Score (1-10) evaluating the strength of evidence supporting the findings.")
    citation_quality_score: int = Field(description="Score (1-10) evaluating proper source citations.")
    freshness_score: int = Field(description="Score (1-10) evaluating the recency/freshness of the information.")
    feedback: str = Field(description="Detailed feedback synthesizing the evaluations into a final verdict.")
    needs_rework: bool = Field(description="Determine if the executor needs to rerun based on the critic's severity.")
    actionable_advice: str = Field(description="Strict, actionable instructions for the executor or synthesis notes if passing.")

class FactCheckResult(BaseModel):
    is_consistent: bool = Field(description="True if the extracted findings are fully consistent with the raw tool observations. False if there are contradictions.")
    consistency_score: float = Field(description="0.0 = completely contradictory, 1.0 = completely consistent")
    contradictions: List[str] = Field(description="List of factual contradictions discovered, if any.")
    ungrounded_claims: List[str] = Field(description="List of claims that are not grounded in the tool observations.")
