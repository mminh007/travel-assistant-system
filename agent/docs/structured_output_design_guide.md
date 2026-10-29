# Architectural Guide: Structured Output Design & Model Tiering

- **Target Audience:** Backend AI Engineers, System Architects
- **Applicable Frameworks:** LangChain, vLLM, OpenAI API, Anthropic Claude API
- **Repository Context:** `travel-assistant-system`

---

## 1. Overview & Core Philosophy

In production multi-agent architectures, agents interact with other agents, databases, and message brokers (e.g., Redis, RabbitMQ, gRPC) via **Data Contracts**. 

These Data Contracts are defined as **Pydantic Schemas** (e.g., `InputGuardrailOutput`, `EvaluatorOutput`, `FactCheckResult`). 

A common misconception is:
> *"Does the Pydantic schema need to be rewritten whenever we switch from a 3B model to a 27B or 70B model?"*

**The answer is NO.**
* **The Pydantic Schema (Business Contract) is invariant:** It represents your application domain logic and database entities.
* **What changes across model sizes is the Extraction Strategy & Enforcement Mechanism:** How we constrain the LLM to adhere to that schema, how we allocate token budgets, and how much schema complexity the model can reliably handle in a single step.

---

## 2. Demystifying `with_structured_output()`

`with_structured_output(schema)` is **NOT a native API function** of OpenAI or Anthropic. 

It is an abstraction method provided by **LangChain** (`BaseChatModel.with_structured_output`) designed to unify different provider-specific formatting interfaces into a single developer call.

```
+-------------------------------------------------------------------------------+
|                        LangChain Abstraction Layer                            |
|             llm.with_structured_output(schema, method="...")                  |
+-------------------------------------------------------------------------------+
           |                                     |                         |
           v                                     v                         v
+-----------------------+              +-------------------+     +------------------+
|   OpenAI API (Cloud)  |              | Anthropic (Cloud) |     |  vLLM (Hosted)   |
| method:               |              | method:           |     | method:          |
| 1. json_schema        |              | 1. tool_use       |     | 1. json_mode     |
| 2. function_calling   |              | 2. system prompt  |     | 2. function_call |
| 3. json_mode          |              |    + prefill      |     | 3. guided_json   |
+-----------------------+              +-------------------+     +------------------+
```

### 2.1. How Providers Implement Structured Outputs Under the Hood

#### 1. OpenAI (Cloud)
* **Function Calling (`method="function_calling"`):** Sends `tools=[{"type": "function", "function": schema}]` and `tool_choice={"type": "function", "function": {"name": schema_name}}`.
* **Structured Outputs (`method="json_schema"`):** Available on GPT-4o, GPT-4o-mini. OpenAI enforces a strict grammar-constrained sampling engine at the sampler level (`response_format={"type": "json_schema", "json_schema": {"strict": True, "schema": ...}}`). 100% adherence guaranteed.
* **JSON Mode (`method="json_mode"`):** Sets `response_format={"type": "json_object"}`. Requires the word `"JSON"` in the prompt. LangChain parses the resulting text via `JsonOutputParser`.

#### 2. Anthropic (Cloud)
* Anthropic models natively support **Tool Use**. LangChain translates the schema into an Anthropic tool definition.
* Claude 3 / 3.5 models excel at tool invocation and emit well-formed JSON tool input arguments with minimal failure rates.

#### 3. vLLM (Self-Hosted / Open-Source Models)
* vLLM provides an OpenAI-compatible HTTP server (`/v1/chat/completions`).
* When LangChain calls `ChatOpenAI.with_structured_output()`, it **defaults to `method="function_calling"`**.
* **The Failure Mode on Small Models (e.g. Qwen2.5-3B):**
  - vLLM requires `--enable-auto-tool-choice` and `--tool-call-parser <parser_name>`.
  - Small models (3B) often fail to emit the exact tool call delimiters required by the parser.
  - Or the model generates internal reasoning tokens (e.g. `<think>` tokens) and outputs `finish_reason='stop'` with an empty content string (`content=''`) and empty tools (`tool_calls=[]`).
  - LangChain receives `content=''` without `tool_calls` and throws:
    ```text
    Structured Output response does not have a 'parsed' field nor a 'refusal' field.
    ```

---

## 3. The Architectural Matrix by Model Parameter Size

| Dimension | Tier 1: Small (< 7B)<br>*(e.g., Qwen2.5-3B, Llama-3.2-3B, Phi-3)* | Tier 2: Mid-Range (7B – 14B)<br>*(e.g., Qwen2.5-7B/14B, Llama-3.1-8B)* | Tier 3: Large (≥ 27B) & Cloud<br>*(e.g., Qwen2.5-32B/72B, GPT-4o, Claude 3.5)* |
| :--- | :--- | :--- | :--- |
| **Tool Calling Reliability** | **Fragile / Brittle.** High probability of omitting tool calls or outputting empty content. | **Moderate to Good.** Reliable when prompt instructions are clear. | **Near Perfect (99%+).** Fully adheres to strict schemas. |
| **Recommended `method`** | **`method="json_mode"`** with schema in prompt, or guided regex/grammar. | **`method="function_calling"`** or **`method="json_mode"`**. | **`method="json_schema"`** (OpenAI) or native Function Calling. |
| **Schema Complexity** | **Flat schemas ONLY.** Max 3–5 primitive fields (`str`, `int`, `bool`, `List[str]`). | 1-level nested objects supported. Simple enums and optional fields. | Multi-level nested schemas, strict validations, union types, recursive objects. |
| **Prompt Template Rule** | **Mandatory Few-Shot / JSON Example.** Must explicitly show `{"key": "value"}` in prompt. | Schema definition in prompt or system message is sufficient. | Raw Pydantic schema passed to tool interface without extra prompting. |
| **Token Budget Cushion** | **High Overhead Needed.** Small models need 300–500 token buffers even for short JSONs to avoid `length limit`. | Standard token budget (400–600 tokens). | Optimal token budget; minimal formatting overhead. |
| **Failure Strategy** | **Graceful Fallback Mandatory.** Try/catch with fallback to raw message or default safe object. | Standard retry with exponential backoff. | Low-retry (1 retry sufficient). |

---

## 4. Concrete Examples: Designing Schemas for Different Model Tiers

### 4.1. Anti-Pattern: Complex Nested Schema on 3B Model
The following schema will frequently crash or be truncated when executed against `Qwen2.5-3B`:

```python
# ❌ ANTI-PATTERN FOR 3B: Deep nesting, complex metadata, heavy reasoning requirements
class ContradictionDetail(BaseModel):
    claim_id: int
    quote_from_ground_truth: str
    quote_from_executor: str
    severity: Literal["low", "medium", "critical"]
    mitigation_steps: List[str]

class FactCheckResult(BaseModel):
    is_consistent: bool
    summary_memo: str
    contradictions: List[ContradictionDetail]  # Nested object list
    confidence_matrix: Dict[str, float]       # Freeform key-value dictionary
```
*Why it fails on 3B:*
1. Token generation exceeds budget before closing JSON brackets (`finish_reason='length'`).
2. Small models lose structural coherence across deeply nested lists of objects.

### 4.2. Recommended Pattern: Flattened Schema for 3B Model
```python
# ✅ OPTIMIZED FOR 3B: Flat, primitive types, explicit and concise
class FactCheckResult(BaseModel):
    is_consistent: bool = Field(description="True if executor claims match tool observations")
    contradictions: List[str] = Field(default_factory=list, description="Concise list of identified contradictions")
    consistency_score: float = Field(default=1.0, description="Consistency score from 0.0 to 1.0")
```

When upgrading to **Qwen 27B+** or **GPT-4o**, you can enrich the schema with `ContradictionDetail` without breaking the consuming nodes if you design backward-compatible field aliases.

---

## 5. Implementation Strategy: Centralized LLM Factory Pattern

To prevent every individual graph node from having to know model-specific idiosyncrasies, encapsulate structured output compilation inside the central factory: [agent/app/graph/config.py](file:///d:/proj/Booking/agent/app/graph/config.py).

```python
def get_structured_llm(
    tier: int, 
    schema: Any, 
    config: RunnableConfig = None, 
    temperature: float = None
) -> Any:
    """
    Centralized Factory for Structured Output runnables.
    Dynamically adapts enforcement method based on model size and provider.
    """
    provider, provider_cfg, api_key_str = _resolve_provider_and_key(config)
    model_name, temperature = _resolve_tier_model_and_temp(tier, provider_cfg, temperature)
    
    base_llm = get_llm_instance(tier, config, temperature=temperature)
    
    # ─── ADAPTIVE ENFORCEMENT METHOD ───
    # If using local / self-hosted models <= 7B on vLLM, default to json_mode
    # to avoid empty tool_calls and parser crashes.
    model_lower = model_name.lower()
    is_small_model = any(tag in model_lower for tag in ["3b", "1.5b", "0.5b", "mini"])
    
    if provider == "vllm" and is_small_model:
        # json_mode guarantees model outputs text into 'content', parsed by JsonOutputParser
        return base_llm.with_structured_output(schema, method="json_mode")
    
    # For large models (14B, 27B, 72B) and cloud APIs (OpenAI/Claude)
    return base_llm.with_structured_output(schema)
```

---

## 6. Defensive Coding: Resilience & Fallbacks

Even with optimal configurations, network anomalies or model drift can produce unparseable responses. Every structured node must implement defensive fallbacks:

```python
try:
    result, usage = await invoke_llm_with_limit(
        tier=1,
        llm=structured_llm,
        messages=messages,
        config=config,
        max_tokens_override=settings.node_limits.guardrail,
        node_name="guardrail"
    )
except Exception as parse_err:
    logger.error(f"❌ [STRUCTURED PARSE FAILED] Falling back to default: {parse_err}")
    # Return a safe, domain-compliant default object to preserve pipeline continuity
    result = SafeDefaultOutput()
    usage = TokenUsage()
```

### Summary Checklist for Adding New Nodes
1. **Schema Check:** Is the schema flat and free of deeply nested structures if target model is < 7B?
2. **Token Headroom:** Is `node_max_tokens` set to at least **500** for structured nodes?
3. **Prompt Explicit:** Does the prompt explicitly demand JSON and provide a sample structure?
4. **Fallback Handled:** Does the node catch `OutputParserException` and fallback gracefully?
