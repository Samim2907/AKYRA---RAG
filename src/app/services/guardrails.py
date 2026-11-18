from __future__ import annotations

import re


class GuardrailError(ValueError):
    pass


def validate_question(question: str) -> str:
    cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", question).strip()
    if len(cleaned) < 3:
        raise GuardrailError("Question must contain at least three visible characters.")
    if len(cleaned) > 2000:
        raise GuardrailError("Question exceeds the 2,000-character limit.")
    # Reject common prompt-injection instructions rather than letting them enter generation context.
    if re.search(r"\b(ignore|reveal|override)\b.{0,40}\b(instruction|prompt|system)\b", cleaned, re.I):
        raise GuardrailError("The question contains unsupported instruction-like content.")
    return cleaned


def validate_answer(answer: str, citations_count: int) -> str:
    if not answer.strip():
        return "I could not form an answer from the indexed sources."
    if citations_count == 0:
        return "I could not find supporting content in the indexed sources."
    # Lightweight output safety check; use a specialist moderation service in production.
    if re.search(r"\b(kill yourself|racial slur)\b", answer, re.I):
        return "I cannot provide that response."
    return answer.strip()
