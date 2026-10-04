"""Token -> USD. Anthropic first-party list prices per 1M tokens (checked 2026-10-04).

Ignores prompt-caching discounts, so treat totals as an upper bound.
"""
PRICES_PER_MTOK = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


def cost_usd(model_id: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = PRICES_PER_MTOK.get(model_id, (0.0, 0.0))
    return round((input_tokens * price_in + output_tokens * price_out) / 1_000_000, 6)
