"""Reading Gemini's token counts from the shape the SDK actually returns.

The parser read ``usageMetadata`` and its camelCase fields, which is the REST
wire format. The SDK this deployment runs on returns ``usage_metadata`` with
snake_case fields, so every count came back zero and every result carried
"provider omitted usageMetadata" — a degradation naming something the provider
had in fact sent.

The cost of that is not cosmetic. Usage drives spend tracking and the budget
guard, so a deployment reading zero believes every investigation is free.

The fixtures below are the real payload, read from the provider with a real key.
Note what it says about a reasoning model: a hundred and six tokens of thought
for a one-token answer. A caller that budgets output alone budgets the visible
tenth of what it is buying.
"""

from __future__ import annotations

import pytest

from core.llm.providers.gemini import _parse_usage

pytestmark = pytest.mark.unit

#: Verbatim from google-genai 2.17, `model_dump(mode="json")`.
SDK_SHAPE = {
    "usage_metadata": {
        "prompt_token_count": 6,
        "candidates_token_count": 1,
        "thoughts_token_count": 106,
        "cached_content_token_count": None,
        "total_token_count": 113,
    }
}

#: The REST wire format, which the parser already handled.
REST_SHAPE = {
    "usageMetadata": {
        "promptTokenCount": 6,
        "candidatesTokenCount": 1,
        "thoughtsTokenCount": 106,
        "cachedContentTokenCount": 0,
    }
}


def test_the_counts_are_read_from_the_shape_the_sdk_returns() -> None:
    """The defect: this shape produced zeroes and a degradation saying the
    provider had sent nothing."""
    tokens = _parse_usage(SDK_SHAPE)

    assert not tokens.estimated
    assert tokens.input_tokens == 6
    assert tokens.output_tokens == 1
    assert tokens.reasoning_tokens == 106


def test_the_rest_shape_still_reads() -> None:
    """Both are live: the SDK path and a direct HTTP call reach the same parser."""
    tokens = _parse_usage(REST_SHAPE)

    assert not tokens.estimated
    assert tokens.input_tokens == 6
    assert tokens.reasoning_tokens == 106


def test_a_null_cached_count_is_not_read_as_a_number() -> None:
    """The SDK sends null rather than omitting the field, and int(None) raises."""
    tokens = _parse_usage(SDK_SHAPE)

    assert tokens.cached_input_tokens == 0


def test_cached_tokens_are_subtracted_from_the_prompt_count() -> None:
    """Both shapes fold the cached tokens into the prompt count, so the neutral
    fields overlap unless one is taken out of the other."""
    tokens = _parse_usage(
        {"usage_metadata": {"prompt_token_count": 100, "cached_content_token_count": 40}}
    )

    assert tokens.input_tokens == 60
    assert tokens.cached_input_tokens == 40


def test_a_response_carrying_no_usage_is_still_reported_as_estimated() -> None:
    """The degradation has to survive: a provider that really sent nothing must
    not be indistinguishable from one whose fields were misread."""
    assert _parse_usage({}).estimated
    assert _parse_usage({"usage_metadata": None}).estimated
