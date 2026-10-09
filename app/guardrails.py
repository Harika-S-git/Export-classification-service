"""Input guardrails for free-text fields; no LLM provider is enabled by default."""
import re

INJECTION_PATTERNS = (
    r"ignore (all |any |the )?(previous|prior|above) instructions",
    r"(reveal|print|show|leak) (the )?(system prompt|hidden prompt|secrets|api keys)",
    r"you are now (an? )?(admin|system|developer)",
    r"override (the )?(system|safety) (prompt|instructions|rules)",
    r"disregard (all |the )?(safety|previous|prior) (rules|instructions)",
    r"call (the )?(tool|function) .*without (verification|permission)",
)
TOXIC_PATTERNS = (r"\b(kill yourself|racial slur|terrorist threat)\b",)

def inspect_free_text(value: str | None) -> list[str]:
    """Return deterministic guardrail flags. This is not a general toxicity classifier."""
    if not value:
        return []
    normalized = re.sub(r"\s+", " ", value.casefold()).strip()
    flags = []
    if any(re.search(pattern, normalized) for pattern in INJECTION_PATTERNS):
        flags.append("prompt_injection")
    if any(re.search(pattern, normalized) for pattern in TOXIC_PATTERNS):
        flags.append("toxic_or_threatening_text")
    return flags
