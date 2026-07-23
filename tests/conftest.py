"""Small AstrBot API stubs used by the offline integration tests."""

from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path
from types import ModuleType, SimpleNamespace

PROJECT_PARENT = Path(__file__).resolve().parents[2]
if str(PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(PROJECT_PARENT))


class _Logger:
    def __init__(self) -> None:
        self.records: list[tuple[object, ...]] = []

    def warning(self, *args: object, **_kwargs: object) -> None:
        self.records.append(args)

    def info(self, *args: object, **_kwargs: object) -> None:
        self.records.append(args)


class _Plain:
    def __init__(self, text: str) -> None:
        self.text = text


class _Star:
    def __init__(self, context: object) -> None:
        self.context = context


class _AstrMessageEvent:
    pass


class _PlatformAdapterType(Enum):
    AIOCQHTTP = "aiocqhttp"


class _EventMessageType(Enum):
    GROUP_MESSAGE = "group"


def _passthrough_decorator(*_args: object, **_kwargs: object):
    def decorate(function):
        return function

    return decorate


astrbot = ModuleType("astrbot")
api = ModuleType("astrbot.api")
event = ModuleType("astrbot.api.event")
star = ModuleType("astrbot.api.star")
components = ModuleType("astrbot.api.message_components")

api.logger = _Logger()
event.AstrMessageEvent = _AstrMessageEvent
event.filter = SimpleNamespace(
    PlatformAdapterType=_PlatformAdapterType,
    EventMessageType=_EventMessageType,
    platform_adapter_type=_passthrough_decorator,
    event_message_type=_passthrough_decorator,
)
star.Context = object
star.Star = _Star
components.Plain = _Plain

astrbot.api = api
sys.modules.setdefault("astrbot", astrbot)
sys.modules.setdefault("astrbot.api", api)
sys.modules.setdefault("astrbot.api.event", event)
sys.modules.setdefault("astrbot.api.star", star)
sys.modules.setdefault("astrbot.api.message_components", components)
