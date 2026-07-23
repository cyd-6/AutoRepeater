"""Pure repeater state and decision parsing logic.

This module deliberately has no AstrBot imports so its behavior can be tested
without a running bot or an LLM provider.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any

_WHITESPACE_RE = re.compile(r"\s+")
_CODE_FENCE_RE = re.compile(
    r"\A\s*```(?:json)?[ \t]*\r?\n?(?P<body>.*?)\r?\n?```\s*\Z",
    re.IGNORECASE | re.DOTALL,
)


def normalize_text(text: str) -> str:
    """Collapse whitespace and trim the result."""

    return _WHITESPACE_RE.sub(" ", text).strip()


class DecisionFormatError(ValueError):
    """Raised when a verdict is not the required strict JSON object."""


def parse_decision_json(raw: str) -> bool:
    """Parse ``{"should_respond": bool}``, optionally inside a code fence."""

    if not isinstance(raw, str):
        raise DecisionFormatError("裁决结果不是文本")

    match = _CODE_FENCE_RE.fullmatch(raw)
    payload = match.group("body") if match else raw
    try:
        value: Any = json.loads(payload)
    except (json.JSONDecodeError, TypeError) as exc:
        raise DecisionFormatError("裁决结果不是合法 JSON") from exc

    if not isinstance(value, dict) or set(value) != {"should_respond"}:
        raise DecisionFormatError("裁决 JSON 必须且只能包含 should_respond 字段")
    if not isinstance(value["should_respond"], bool):
        raise DecisionFormatError("should_respond 必须是布尔值")
    return value["should_respond"]


@dataclass(frozen=True, slots=True)
class RepetitionTrigger:
    """An immutable trigger snapshot returned while the group lock is held."""

    group_id: str
    text: str
    recent_texts: tuple[str, ...]


@dataclass(slots=True)
class _GroupState:
    recent_texts: deque[str]
    chain_text: str | None = None
    senders: set[str] = field(default_factory=set)
    triggered: bool = False
    last_repeated_text: str | None = None

    def reset_chain(self) -> None:
        self.chain_text = None
        self.senders.clear()
        self.triggered = False


class GroupRepeater:
    """Concurrency-safe, in-memory repetition state isolated by group."""

    def __init__(self, trigger_count: int = 4, history_count: int = 20) -> None:
        if trigger_count < 1:
            raise ValueError("trigger_count 必须大于等于 1")
        if history_count < 1:
            raise ValueError("history_count 必须大于等于 1")
        self.trigger_count = trigger_count
        self.history_count = history_count
        self._states: dict[str, _GroupState] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _state_for(self, group_id: str) -> _GroupState:
        state = self._states.get(group_id)
        if state is None:
            state = _GroupState(recent_texts=deque(maxlen=self.history_count))
            self._states[group_id] = state
        return state

    def _lock_for(self, group_id: str) -> asyncio.Lock:
        lock = self._locks.get(group_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[group_id] = lock
        return lock

    async def observe(
        self,
        group_id: str,
        sender_id: str,
        text: str = "",
        *,
        is_text: bool = True,
    ) -> RepetitionTrigger | None:
        """Observe one group message and return the single trigger, if any.

        Empty text and non-text messages reset only the consecutive chain. They
        are intentionally not added to the text history used by the LLM verdict.
        """

        async with self._lock_for(group_id):
            state = self._state_for(group_id)
            normalized = normalize_text(text) if is_text else ""

            if not is_text or not normalized:
                state.reset_chain()
                return None

            state.recent_texts.append(normalized)
            if state.chain_text != normalized:
                state.chain_text = normalized
                state.senders = {sender_id}
                state.triggered = False
            else:
                state.senders.add(sender_id)

            if len(state.senders) < self.trigger_count or state.triggered:
                return None

            state.triggered = True
            if state.last_repeated_text == normalized:
                return None
            state.last_repeated_text = normalized
            return RepetitionTrigger(
                group_id=group_id,
                text=normalized,
                recent_texts=tuple(state.recent_texts),
            )
