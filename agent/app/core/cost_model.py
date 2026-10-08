# app/core/cost_model.py
"""
Provider-aware token cost model.

Prices are in USD per 1M tokens (input/output).
- nine_router: uses the proxied model's upstream pricing
- vllm: self-hosted — compute cost is infrastructure cost, not per-token
- claude: Anthropic direct pricing

Update prices here when upstream providers change rates.
"""

# Model-level pricing: (input_usd_per_1m, output_usd_per_1m)
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI models (via 9Router)
    "gpt-4o-mini":    (0.15,  0.60),
    "gpt-4o":         (5.00,  15.00),
    "o1-mini":        (3.00,  12.00),
    "o1":             (15.00, 60.00),
    # Anthropic models (via 9Router or direct)
    "claude-3-5-haiku-20241022":  (0.80,  4.00),
    "claude-3-5-sonnet-20241022": (3.00,  15.00),
    "claude-3-opus-20240229":     (15.00, 75.00),
    # vLLM (self-hosted) — infrastructure cost, not API cost
    "vllm":           (0.0, 0.0),
}

_VLLM_SENTINEL = "vllm"

def get_token_cost(model_name: str, input_tokens: int, output_tokens: int) -> tuple[float, float, float]:
    """
    Returns (cost_input, cost_output, cost_total) in USD.
    Falls back to 0.0 for unknown models (logs warning handled by caller).
    """
    pricing = _MODEL_PRICING.get(model_name)

    if pricing is None:
        # Unknown model — return zero rather than wrong estimate
        return 0.0, 0.0, 0.0

    price_in, price_out = pricing
    cost_in  = input_tokens  * price_in  / 1_000_000
    cost_out = output_tokens * price_out / 1_000_000
    return cost_in, cost_out, cost_in + cost_out

def is_self_hosted(model_name: str) -> bool:
    """True for vLLM — cost should not be tracked as API spend."""
    return model_name == _VLLM_SENTINEL
