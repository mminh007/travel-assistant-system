# Agent Cognitive Engine — Graph Architecture V2

> **Directory path:** `agent/app/graph/`  
> **Framework:** LangGraph (`StateGraph`)  
> **Entry point:** `workflow.py → compiled_graph`  
> **State schema:** `state.py → AgentState`

---

## Table of Contents

1. [Overview of Architecture V2 (Upgraded)](#1-overview-of-architecture-v2-upgraded)
2. [AgentState — State Schema](#2-agentstate--state-schema)
3. [Node Registry](#3-node-registry)
4. [Detailed Node Descriptions](#4-detailed-node-descriptions)
5. [Workflow & Detailed Routing Flows](#5-workflow--detailed-routing-flows)
6. [Advanced Optimization Mechanisms in V2](#6-advanced-optimization-mechanisms-in-v2)
7. [Safeguards & Hard Limits](#7-safeguards--hard-limits)
8. [LLM Tiers & Caching Strategy](#8-llm-tiers--caching-strategy)

---

## 1. Overview of Architecture V2 (Upgraded)

The **Cognitive Graph V2** architecture has been comprehensively upgraded to address the limitations of the V1 version related to **context drift**, **infinite loops**, and **data extraction errors (JSON decode errors)**.

Core improvements include:
*   **Separation of Content Generation & Extraction:** The Executor generates results in free-form Markdown, then a separate extraction node (`finding_extractor`) uses Function Calling (Tier 1) to extract structured data. This completely eliminates executor JSON parsing errors.
*   **Context Sandboxing:** Clears intermediate messages of previous tasks before moving to a new task using `RemoveMessage`. Important discoveries are distilled into `findings` and passed to the next task via the system prompt to prevent context overflow.
*   **Consolidated Evaluator:** Merges Criticism and Reflection into a single Node (`evaluator_agent`), improving workflow speed and reducing LLM costs.
*   **Reporting Engine:** The `final_synthesizer` node aggregates findings and raw results from all completed tasks to write a complete report. Supports multi-language with the `detected_language` field.

---

## 2. AgentState — State Schema

All data passed between nodes is managed through `AgentState` (`TypedDict`). LangGraph manages immutability.

```text
AgentState
├── messages            → Main conversation stream (add_messages reducer)
├── user_id             → User identification ID
├── session_id          → Working session ID
│
├── ── PHASE 1: GUARDRAIL & INTENT CLASSIFICATION ──────────────
├── is_in_domain        → True if travel request, False if off-topic
├── intent_category     → Intent classification ("hotel_booking" | "flight_booking" | "travel_faq" | "itinerary_planning" | "out_of_domain")
├── complexity          → Complexity level ("low" | "medium" | "high")
├── objective           → General overarching objective
├── detected_language   → Language of the query (e.g., "English", "Vietnamese")
│
├── ── PHASE 2: WORKFLOW MEMORY (PROCEDURAL STATE) ──────────────
├── tasks               → List of structured tasks:
│                         List[{
│                           "id": int, 
│                           "desc": str, 
│                           "status": "pending" | "completed", 
│                           "result": str (Raw detailed markdown),
│                           "findings": List[Finding] (Structured statements + confidence)
│                         }]
├── current_task_id     → ID of the currently executing sub-task
│
├── ── PHASE 3: LOOP MANAGEMENT & SAFEGUARDS ────────────────────
├── iteration_count     → Number of ReAct loops executed for the current task (max 8)
├── tool_call_count     → Total number of tools called throughout the graph (max 10)
├── action_history      → List of MD5 hashes of tool calls to prevent duplicate calls
├── rework_count        → Number of reworks from Evaluator -> Executor (max 2)
│
├── ── EVALUATION MEMORY ─────────────────────────────────────────
├── evaluator_feedback  → Detailed feedback from the consolidated Evaluator
├── evaluator_notes     → Corrective action notes from the Evaluator
├── needs_rework        → Boolean indicating if the executor needs to redo the work
├── final_answer        → (Reserved) Final synthesized answer
│
├── ── CONTENT/EXTRACTION PIPELINE STATE ─────────────────────────
├── raw_executor_output → Text summary string or raw markdown
├── extracted_findings  → List of structured findings List[Finding]
│
└── ── CACHING ───────────────────────────────────────────────────
    └── cache_hit       → (Optional) cache status
```

---

## 3. Node Registry

| # | Node Name | Main Function | LLM Tier Used | Node Type |
|---|---|---|---|---|
| 0 | `input_guardrail` | Classify user intent, determine language, reject off-topic queries. | Tier 1 (Fast - `gpt-4o-mini`) | Async Node |
| 1 | `planner` | Decompose complex travel objectives into a sequence of 2-4 sub-tasks. | Tier 2 (Balanced - `gpt-4o`) | Async Node |
| 2 | `direct_executor_init` | Initialize state for the bypass flow when complexity='low' (No LLM used). | *(No LLM used)* | Async Node |
| 3 | `travel_react_agent` | ReAct Executor processing travel queries, returns free-form Markdown. | Tier 2 (Balanced - `gpt-4o`) | Async Node |
| 4 | `out_of_domain` | Handle non-travel related queries by declining politely. | *(No LLM used)* | Async Node |
| 5 | `action_tracker` | Interceptor that hashes tools and increments counters before the tool runs. | *(No LLM used)* | Async Node |
| 6 | `tools` | Execute MCP tool calls requested by the executor. | *(External)* | ToolNode |
| 7 | `finding_extractor` | Read executor's text output to extract structured `result_summary` and `findings`. | Tier 1 (Fast - `gpt-4o-mini`) | Async Node |
| 8 | `evaluator_agent` | Evaluate Executor based on 4 metrics (Tools, Evidence, Citations, Freshness) & make rework decisions. | Tier 2 (Balanced - `gpt-4o`) | Async Node |
| 9 | `task_manager` | Save extraction results, mark tasks, perform Context Sandboxing. | *(No LLM used)* | Async Node |
| 10 | `final_synthesizer` | Synthesize all tasks/findings into a single report according to the `detected_language`. | Tier 2 (Balanced - `gpt-4o`) | Async Node |

---

## 4. Detailed Node Descriptions

### 4.1. `input_guardrail` Node
*   **Source file:** `nodes.py → node_input_guardrail()`
*   **Position:** Graph Entry Point.
*   **Characteristics:** Uses **Structured Output** (`with_structured_output`).
*   **Responsibilities:**
    1. Read the user's latest message & the `workflow.md` principles file.
    2. Analyze: `is_in_domain`, `complexity`, `intent_category`, `objective`, and `detected_language`.
*   **Fallback:** Returns a safe structure with `is_in_domain=True`, `complexity='low'`.

---

### 4.2. `planner` Node
*   **Source file:** `nodes.py → node_planner_agent()`
*   **Execution condition:** Runs when `complexity = "medium"` or `"high"`.
*   **Responsibilities:**
    1. Decompose the objective into 2-4 sequential sub-tasks.

---

### 4.3. `direct_executor_init` Node
*   **Source file:** `nodes.py → node_direct_executor_init()`
*   **Execution condition:** Runs when `complexity = "low"`.
*   **Responsibilities:**
    1. Create a single task containing the original prompt.
    2. Set `iteration_count=0`, `tool_call_count=0`, `rework_count=0`.

---

### 4.4. Executor Node (`travel_react_agent`)
*   **Source file:** `nodes.py → node_travel_react_agent()`
*   **Function:** Specialists handling tasks through the **ReAct (Reason-and-Act)** loop.
*   **Operating mechanism:**
    1. Uses a System Message providing context, `intent_instructions`, and the chain of findings from the previous task.
    2. **Bind Tools:** Returns an `AIMessage` containing tool calls or free-form Markdown responses (not forced to output JSON).

> [!NOTE]
> The `travel_react_agent` node applies the **Critic Before Tool** principle. Returns free-form responses to avoid JSON Parse errors.

---

### 4.5. `action_tracker` Node and `tools` Node
*   **Source file:** `workflow.py → action_tracker_node()` and `ToolNode(mcp_tools)`
*   **Responsibilities:**
    *   `action_tracker`: Interceptor hashing tools + parameters into MD5 and incrementing `tool_call_count`. Prevents Duplicate Tool Calls.
    *   `tools`: Node executing MCP tools.

---

### 4.6. `finding_extractor` Node
*   **Source file:** `nodes.py → node_finding_extractor()`
*   **Responsibilities:**
    1. Receives raw text input (free-form Markdown) from the Executor.
    2. Uses Structured Output (Tier 1 - cheap cost) to output into 2 fields: `result_summary` and `findings`.
    3. Writes to State: `raw_executor_output` and `extracted_findings`. This saves the system from critical JSONDecodeError issues.

---

### 4.7. `evaluator_agent` Node
*   **Source file:** `nodes.py → node_evaluator_agent()`
*   **Responsibilities:**
    1. Analyzes `raw_executor_output` and `extracted_findings` against the `objective`.
    2. Scores from 1 to 10 on 4 aspects: `tool_quality_score`, `evidence_quality_score`, `citation_quality_score`, `freshness_score`.
    3. Makes a `needs_rework` decision and outputs accompanying `actionable_advice`. Updates `rework_count`.

---

### 4.8. `task_manager` Node
*   **Source file:** `nodes.py → node_task_manager()`
*   **Responsibilities:**
    1. Updates the current task to `"completed"` with data from `raw_executor_output` & `extracted_findings`.
    2. **Context Sandboxing:** Injects `RemoveMessage` to clear all intermediate ReAct messages of the completed task, keeping only the original prompt.
    3. Resets extraction state (`raw_executor_output`, `extracted_findings`) and counters.
    4. Routes to the next task or `final_synthesizer`.

---

### 4.9. `final_synthesizer` Node
*   **Source file:** `nodes.py → node_final_synthesizer()`
*   **Responsibilities:**
    1. Aggregates discrete results (findings, results) from the entire workflow memory.
    2. Generates a fluent Markdown response in the language matching `detected_language`.
    3. Instructed not to wrap output in \`\`\`markdown blocks.

---

## 5. Workflow & Detailed Routing Flows

### 5.1. Overview Workflow Diagram

```mermaid
graph TD
    Start([User Message]) --> IG[input_guardrail]
    
    %% Guardrail Gate
    IG -- is_in_domain = False --> OOD[out_of_domain]
    OOD --> End([END])
    
    IG -- is_in_domain = True, complexity = low --> DEI[direct_executor_init]
    IG -- is_in_domain = True, complexity = med/high --> PL[planner]
    
    %% Direct Init & Planner routing to Executors
    DEI --> TRA[travel_react_agent]
    PL --> TRA
    
    %% ReAct Tool Hooks
    TRA --> ETH[evaluate_tool_hooks]
    
    %% Hooks Branches
    ETH --> |execute_tools| AT[action_tracker]
    AT --> TL[tools]
    TL -- route_back_to_agent --> TRA
    
    %% Extraction & Evaluation Pipeline
    ETH --> |finding_extractor| FE[finding_extractor]
    FE --> EA[evaluator_agent]
    
    %% Rework Gate
    EA -- route_from_evaluator --> |needs_rework=True & rework < max| TRA
    EA -- route_from_evaluator --> |needs_rework=False OR rework >= max| TM[task_manager]
    
    %% Task Manager Loop
    TM -- route_from_task_manager --> |next task pending| TRA
    TM -- route_from_task_manager --> |all tasks completed| FS[final_synthesizer]
    
    FS --> End([END])
```

### 5.2. Conditional Edges Map

The rules for state transitions between nodes are strictly defined in code:

1.  **After `input_guardrail` (`route_from_guardrail`):**
    *   `is_in_domain = False` $\rightarrow$ routes to `out_of_domain`.
    *   `is_in_domain = True` and `complexity = low` $\rightarrow$ routes to `direct_executor_init`.
    *   `is_in_domain = True` and `complexity = medium`/`high` $\rightarrow$ routes to `planner`.
2.  **After `planner` and `direct_executor_init`:** $\rightarrow$ `travel_react_agent`.
3.  **After Executor (`evaluate_tool_hooks`):**
    *   If there's a tool call request $\rightarrow$ goes to `action_tracker` $\rightarrow$ `tools`.
    *   If no tool is called, or Hard Limits are exceeded (Max loops, Budget, Duplicate) $\rightarrow$ forwards to get results at `finding_extractor`.
4.  **After `finding_extractor`:** $\rightarrow$ always goes to `evaluator_agent`.
5.  **After `evaluator_agent` (`route_from_evaluator`):**
    *   If `needs_rework` is True and `rework_count < MAX_REWORK_CYCLES` $\rightarrow$ loops back to `travel_react_agent` for corrections.
    *   If no rework is needed or limit exceeded $\rightarrow$ goes to `task_manager`.
6.  **After `task_manager` (`route_from_task_manager`):**
    *   If there's a `"pending"` task remaining $\rightarrow$ loops back to `travel_react_agent`.
    *   If all tasks are completed $\rightarrow$ goes to `final_synthesizer`.

---

## 6. Advanced Optimization Mechanisms in V2

### 6.1. Separation of Content Generation and Information Extraction

Because the Executor uses the ReAct loop, forcing the LLM to return structured formats via `.with_structured_output()` while maintaining tool-calling capability is the root cause of errors.
V2 completely solves this issue with a 2-phase flow:
1. **Generation Phase:** `travel_react_agent` acts as a free-form React Agent, calling tools and returning plain text (Markdown).
2. **Extraction Phase:** `finding_extractor` makes a Tier 1 LLM call, utilizing Function Calling to parse the Markdown into `result_summary` and a chain of `findings`. Formatting stability is 100% guaranteed.

### 6.2. Context Sandboxing (Absolute Context Isolation)

When a ReAct task runs, it generates multiple Thought and Action turns (up to thousands of tokens).
**How Sandboxing works:**
1. When `task_manager` detects the completion of a task and transitions to a new one, it returns a `RemoveMessage` array to clear the generated intermediate messages, restoring the conversation stream to a clean state.
2. At the next Task, the `_build_task_context` function scans workflow memory (`state.tasks`), aggregates the findings of the completed task, and injects them into the new Agent's System Prompt Context.
=> The LLM retains prior knowledge without context overflow, reducing Hallucinations.

---

## 7. Safeguards & Hard Limits

At the routing node `evaluate_tool_hooks`, the system enforces 3 safeguards, and at `route_from_evaluator` it applies 1 safeguard:

| Limit | Constant Name | Purpose | Action when triggered |
|---|---|---|---|
| **Max Iterations** | `MAX_ITERATIONS = 8` | Maximum number of Thought-Action turns per task. | Stops ReAct flow, routes to `finding_extractor`. |
| **Max Tool Calls** | `MAX_TOOL_CALLS = 10` | Maximum tool calls throughout the Session. | Stops ReAct flow, routes to `finding_extractor`. |
| **Duplicate Tools** | Hash Function (MD5) | Prevents repeatedly calling 1 tool with the same parameters. | Stops ReAct flow, routes to `finding_extractor`. |
| **Max Reworks** | `MAX_REWORK_CYCLES = 2` | Prevents the Evaluator from forcing too many re-dos. | Forcibly saves the current task (routes to `task_manager`). |

---

## 8. LLM Tiers & Caching Strategy

The V2 version provides automatic fallback capabilities, dynamically adjusting between OpenAI & Anthropic (Claude) providers through runtime dynamic configuration (`get_llm_instance`).

```text
                     ┌───────────────────────────────┐
                     │           USER PROMPT         │
                     └───────────────┬───────────────┘
                                     │
                 ┌───────────────────┼───────────────────┐
                 ▼                   ▼                   ▼
            [TIER 1 - Fast]     [TIER 2 - Balanced]  [TIER 3 - Reasoning]
             gpt-4o-mini /       gpt-4o /            o1-mini /
             claude-3-haiku      claude-3-5-sonnet   claude-3-opus
                 │                   │                   │
            Intent Classify      General Executor       Deep Research
            Finding Extraction   Planner & Evaluator    Complex Math
            Vision Detection     Synthesizer            Deep Machine Learning
```

### 8.1. Dynamic LLM Factory (`get_llm_instance` / `get_structured_llm`)

The dynamic factory handles configuration resolution:
1.  **Provider Resolution:** Prioritizes reading `llm_provider` (`openai` or `claude`) config from `RunnableConfig`.
2.  **Model Mapping:** Automatically maps Tiers to their respective models based on the provider.
3.  **Cache Fingerprinting:** Uses a Fingerprint (Hash combining API key + model + config setting) to automate the `_LLM_INSTANCE_CACHE` lifecycle without manual TTL (Cache Staleness Fix).

### 8.2. `O(1)` Performance Optimized Caching Structure

The system provides 3 caches to prevent latency (cold start):
1.  **Entity Cache (`_LLM_INSTANCE_CACHE`):** Reuses Base Models for requests with the same tenant/API key.
2.  **Structured Bound Cache (`_STRUCTURED_LLM_CACHE`):** Caches compilations of Pydantic Schemas `with_structured_output` to prevent continuous internal JSON Schema re-compilation.
3.  **Tool Bound Cache (`_BOUND_LLM_CACHE`):** The `get_cached_bound_llm` function maps Domain Tools once per model & API Key.
