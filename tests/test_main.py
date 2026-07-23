from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import astrbot.api.message_components as Comp
import pytest
from astrbot_plugin_onebot_repeater.main import OneBotRepeater


@dataclass
class PlainResult:
    text: str


@dataclass
class AgentRequest:
    prompt: str
    conversation: object


class FakeConversationManager:
    def __init__(self) -> None:
        self.conversation = object()
        self.current_id: str | None = "conversation-id"

    async def get_curr_conversation_id(self, umo: str) -> str | None:
        assert umo == "aiocqhttp:GroupMessage:100"
        return self.current_id

    async def new_conversation(self, umo: str) -> str:
        assert umo == "aiocqhttp:GroupMessage:100"
        self.current_id = "new-conversation-id"
        return self.current_id

    async def get_conversation(
        self, umo: str, conversation_id: str, *, create_if_not_exists: bool
    ) -> object:
        assert umo == "aiocqhttp:GroupMessage:100"
        assert conversation_id == self.current_id
        assert create_if_not_exists is True
        return self.conversation


class FakeContext:
    def __init__(self, verdict: str = '{"should_respond": false}') -> None:
        self.verdict = verdict
        self.llm_calls: list[dict[str, Any]] = []
        self.provider_requests: list[str] = []
        self.conversation_manager = FakeConversationManager()
        self.llm_error: Exception | None = None
        self.llm_delay = 0.0

    async def get_current_chat_provider_id(self, umo: str) -> str:
        self.provider_requests.append(umo)
        return "session-model"

    async def llm_generate(self, **kwargs: Any) -> SimpleNamespace:
        self.llm_calls.append(kwargs)
        if self.llm_delay:
            await asyncio.sleep(self.llm_delay)
        if self.llm_error:
            raise self.llm_error
        return SimpleNamespace(completion_text=self.verdict)


class FakeEvent:
    def __init__(self, sender_id: str, text: str, timeline: list[str]) -> None:
        self._sender_id = sender_id
        self.message_str = text
        self.message_obj = SimpleNamespace(message=[Comp.Plain(text)])
        self.unified_msg_origin = "aiocqhttp:GroupMessage:100"
        self.timeline = timeline
        self.agent_requests: list[AgentRequest] = []

    def get_messages(self) -> list[object]:
        return self.message_obj.message

    def get_group_id(self) -> str:
        return "100"

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_self_id(self) -> str:
        return "bot"

    def plain_result(self, text: str) -> PlainResult:
        self.timeline.append("repeat")
        return PlainResult(text)

    def request_llm(self, *, prompt: str, conversation: object) -> AgentRequest:
        self.timeline.append("agent")
        request = AgentRequest(prompt, conversation)
        self.agent_requests.append(request)
        return request


def make_plugin(context: FakeContext, **overrides: object) -> OneBotRepeater:
    config: dict[str, object] = {
        "trigger_count": 4,
        "history_count": 20,
        "decision_timeout": 30.0,
        "decision_model": "",
        "group_whitelist": [],
    }
    config.update(overrides)
    return OneBotRepeater(context, config)


async def drain(generator) -> list[object]:
    return [item async for item in generator]


async def prime_three(plugin: OneBotRepeater, timeline: list[str]) -> None:
    for sender in ("1", "2", "3"):
        assert await drain(plugin.on_group_message(FakeEvent(sender, " hi ", timeline))) == []


@pytest.mark.asyncio
async def test_fourth_member_repeats_before_verdict_call() -> None:
    timeline: list[str] = []
    context = FakeContext('{"should_respond": false}')
    plugin = make_plugin(context)
    await prime_three(plugin, timeline)

    generator = plugin.on_group_message(FakeEvent("4", "\thi\n", timeline))
    first = await anext(generator)
    assert first == PlainResult("hi")
    assert timeline == ["repeat"]
    assert context.llm_calls == []

    with pytest.raises(StopAsyncIteration):
        await anext(generator)
    assert len(context.llm_calls) == 1


@pytest.mark.asyncio
async def test_false_verdict_sends_only_repeat() -> None:
    timeline: list[str] = []
    context = FakeContext('{"should_respond": false}')
    plugin = make_plugin(context)
    await prime_three(plugin, timeline)

    outputs = await drain(plugin.on_group_message(FakeEvent("4", "hi", timeline)))
    assert outputs == [PlainResult("hi")]
    assert timeline == ["repeat"]


@pytest.mark.asyncio
async def test_true_verdict_yields_agent_request_bound_to_conversation() -> None:
    timeline: list[str] = []
    context = FakeContext('{"should_respond": true}')
    plugin = make_plugin(context)
    await prime_three(plugin, timeline)
    event = FakeEvent("4", "hi", timeline)

    outputs = await drain(plugin.on_group_message(event))
    assert outputs[0] == PlainResult("hi")
    assert isinstance(outputs[1], AgentRequest)
    assert outputs[1].conversation is context.conversation_manager.conversation
    assert timeline == ["repeat", "agent"]


@pytest.mark.asyncio
async def test_model_failure_keeps_repeat_and_does_not_crash() -> None:
    timeline: list[str] = []
    context = FakeContext()
    context.llm_error = RuntimeError("provider unavailable")
    plugin = make_plugin(context)
    await prime_three(plugin, timeline)

    outputs = await drain(plugin.on_group_message(FakeEvent("4", "hi", timeline)))
    assert outputs == [PlainResult("hi")]


@pytest.mark.asyncio
async def test_model_timeout_keeps_repeat_and_does_not_crash() -> None:
    timeline: list[str] = []
    context = FakeContext()
    context.llm_delay = 0.1
    plugin = make_plugin(context, decision_timeout=0.01)
    await prime_three(plugin, timeline)

    outputs = await drain(plugin.on_group_message(FakeEvent("4", "hi", timeline)))
    assert outputs == [PlainResult("hi")]


@pytest.mark.asyncio
async def test_bot_self_message_is_ignored_without_breaking_chain() -> None:
    timeline: list[str] = []
    context = FakeContext()
    plugin = make_plugin(context, trigger_count=2)

    assert await drain(plugin.on_group_message(FakeEvent("1", "hi", timeline))) == []
    assert await drain(plugin.on_group_message(FakeEvent("bot", "other", timeline))) == []
    outputs = await drain(plugin.on_group_message(FakeEvent("2", "hi", timeline)))
    assert outputs == [PlainResult("hi")]
