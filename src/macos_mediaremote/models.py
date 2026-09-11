"""Typed snapshots; normalized times use seconds, raw preserves upstream units."""
from dataclasses import dataclass
import json
import math
from types import MappingProxyType
from typing import Any, Mapping

from .errors import ProtocolError


def decode_json(data: bytes) -> Any:
    def invalid_constant(value):
        raise ValueError(f"Non-finite JSON number: {value}")
    try:
        return json.loads(data.decode("utf-8"), parse_constant=invalid_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ProtocolError("Invalid UTF-8 or JSON from helper") from exc


@dataclass(frozen=True, slots=True)
class NowPlaying:
    bundle_identifier: str | None
    playing: bool | None
    title: str | None
    artist: str | None
    album: str | None
    duration: float | None
    elapsed_time: float | None
    timestamp: float | None
    playback_rate: float | None
    raw: Mapping[str, Any]


def parse_snapshot(payload: Any) -> NowPlaying | None:
    if payload is None or payload == {}:
        return None
    if not isinstance(payload, dict):
        raise ProtocolError("Snapshot must be an object or null")

    def string(key):
        value = payload.get(key)
        if value is not None and not isinstance(value, str):
            raise ProtocolError(f"{key} must be a string or null")
        return value

    def number(key, scale=1):
        value = payload.get(key)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ProtocolError(f"{key} must be numeric or null")
        try:
            value = value / scale
            if not math.isfinite(value):
                raise ValueError()
        except (ValueError, OverflowError) as exc:
            raise ProtocolError(f"{key} must be finite") from exc
        return value

    playing = payload.get("playing")
    if playing is not None and not isinstance(playing, bool):
        raise ProtocolError("playing must be boolean or null")
    return NowPlaying(
        bundle_identifier=string("bundleIdentifier"), playing=playing,
        title=string("title"), artist=string("artist"), album=string("album"),
        duration=number("durationMicros", 1_000_000),
        elapsed_time=number("elapsedTimeMicros", 1_000_000),
        timestamp=number("timestampEpochMicros", 1_000_000),
        playback_rate=number("playbackRate"), raw=MappingProxyType(dict(payload)),
    )


def parse_event(data: bytes) -> NowPlaying | None:
    event = decode_json(data)
    if (not isinstance(event, dict) or event.get("type") != "data"
            or event.get("diff") is not False or not isinstance(event.get("payload"), dict)):
        raise ProtocolError("Expected a complete data event (stream --no-diff)")
    return parse_snapshot(event["payload"])
