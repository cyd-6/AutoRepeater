from __future__ import annotations

import asyncio

import pytest
from astrbot_plugin_onebot_repeater.repeater import (
    DecisionFormatError,
    GroupRepeater,
    normalize_text,
    parse_decision_json,
)


def test_normalize_collapses_all_whitespace() -> None:
    assert normalize_text(" \t你好\n\n 世界\r\n ") == "你好 世界"
    assert normalize_text("  \n\t ") == ""


@pytest.mark.asyncio
async def test_distinct_senders_reach_threshold() -> None:
    repeater = GroupRepeater(trigger_count=4)
    for sender in ("1", "2", "3"):
        assert await repeater.observe("g", sender, "hello") is None

    trigger = await repeater.observe("g", "4", "hello")
    assert trigger is not None
    assert trigger.text == "hello"


@pytest.mark.asyncio
async def test_same_sender_does_not_increase_count() -> None:
    repeater = GroupRepeater(trigger_count=2)
    assert await repeater.observe("g", "1", "hello") is None
    assert await repeater.observe("g", "1", " hello ") is None
    assert await repeater.observe("g", "2", "hello") is not None


@pytest.mark.asyncio
async def test_different_empty_and_non_text_messages_break_chain() -> None:
    repeater = GroupRepeater(trigger_count=2)
    assert await repeater.observe("g", "1", "same") is None
    assert await repeater.observe("g", "2", "different") is None
    assert await repeater.observe("g", "3", "same") is None
    assert await repeater.observe("g", "4", "   ") is None
    assert await repeater.observe("g", "5", "same") is None
    assert await repeater.observe("g", "6", is_text=False) is None
    assert await repeater.observe("g", "7", "same") is None
    assert await repeater.observe("g", "8", "same") is not None


@pytest.mark.asyncio
async def test_groups_are_isolated() -> None:
    repeater = GroupRepeater(trigger_count=2)
    assert await repeater.observe("a", "1", "same") is None
    assert await repeater.observe("b", "2", "same") is None
    assert await repeater.observe("a", "3", "same") is not None
    assert await repeater.observe("b", "4", "same") is not None


@pytest.mark.asyncio
async def test_trigger_fires_only_once_until_chain_changes() -> None:
    repeater = GroupRepeater(trigger_count=2)
    assert await repeater.observe("g", "1", "same") is None
    assert await repeater.observe("g", "2", "same") is not None
    assert await repeater.observe("g", "3", "same") is None
    assert await repeater.observe("g", "4", "other") is None
    assert await repeater.observe("g", "5", "same") is None
    assert await repeater.observe("g", "6", "same") is None


@pytest.mark.asyncio
async def test_latest_repeated_text_is_not_repeated_after_chain_break() -> None:
    repeater = GroupRepeater(trigger_count=2)
    assert await repeater.observe("g", "1", "same") is None
    assert await repeater.observe("g", "2", "same") is not None

    assert await repeater.observe("g", "3", "other") is None
    assert await repeater.observe("g", "4", "same") is None
    assert await repeater.observe("g", "5", "same") is None

    # A different text can still trigger and becomes the new remembered output.
    assert await repeater.observe("g", "6", "other") is None
    assert await repeater.observe("g", "7", "other") is not None


@pytest.mark.asyncio
async def test_concurrent_arrivals_produce_one_trigger() -> None:
    repeater = GroupRepeater(trigger_count=4)
    await repeater.observe("g", "1", "same")
    await repeater.observe("g", "2", "same")

    results = await asyncio.gather(
        repeater.observe("g", "3", "same"),
        repeater.observe("g", "4", "same"),
        repeater.observe("g", "5", "same"),
    )
    assert sum(result is not None for result in results) == 1


def test_parse_valid_decision_json() -> None:
    assert parse_decision_json('{"should_respond": true}') is True
    assert parse_decision_json('{"should_respond": false}') is False


def test_parse_fenced_decision_json() -> None:
    assert parse_decision_json('```json\n{"should_respond": true}\n```') is True


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        '{"should_respond": tru}',
        '[{"should_respond": true}]',
        '{"should_respond": true} trailing',
    ],
)
def test_parse_invalid_decision_json(raw: str) -> None:
    with pytest.raises(DecisionFormatError):
        parse_decision_json(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "{}",
        '{"answer": true}',
        '{"should_respond": "true"}',
        '{"should_respond": true, "reason": "x"}',
    ],
)
def test_parse_missing_or_non_strict_fields(raw: str) -> None:
    with pytest.raises(DecisionFormatError):
        parse_decision_json(raw)
