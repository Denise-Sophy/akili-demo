"""Mask PII and secrets before data leaves the MCP server for a model.

Principle: minimise what reaches the model instead of trusting the model not to repeat it.
Names are deliberately kept (owners are needed to answer "who owns this?").
"""
import re

PATTERNS = [
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("SECRET", re.compile(r"\b(?:sk|pk|xox[abpr])-[A-Za-z0-9_-]{10,}\b")),
    # Needs a +country code or a leading 0, so dates like 2026-10-05 are left alone.
    ("PHONE", re.compile(r"(?<![\w-])(?:\+\d{1,3}[\s-]?|0)\d{3}[\s-]?\d{3}[\s-]?\d{3,4}(?![\w-])")),
    ("NATIONAL_ID", re.compile(r"\bID[:\s#]*\d{7,9}\b", re.IGNORECASE)),
]


def redact_text(text: str) -> str:
    for label, pattern in PATTERNS:
        text = pattern.sub(f"[{label}_REDACTED]", text)
    return text


def redact(value):
    """Recursively redact strings inside dicts/lists; other types pass through."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    return value
