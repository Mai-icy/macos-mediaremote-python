import pytest

from macos_mediaremote import ProtocolError
from macos_mediaremote.models import decode_json, parse_event, parse_snapshot


def test_times_unknown_and_missing_fields():
    state = parse_snapshot({"title": "音乐", "durationMicros": 1_234_567,
                            "elapsedTimeMicros": 250_000, "timestampEpochMicros": 1_700_000_000_500_000,
                            "playbackRate": 0.5, "futureField": {"anything": 3}})
    assert state.duration == 1.234567
    assert state.elapsed_time == 0.25
    assert state.timestamp == 1_700_000_000.5
    assert state.playback_rate == 0.5
    assert state.playing is None and state.bundle_identifier is None
    assert state.raw["durationMicros"] == 1_234_567
    assert state.raw["futureField"] == {"anything": 3}
    with pytest.raises(TypeError):
        state.raw["title"] = "other"


@pytest.mark.parametrize("payload", [None, {}])
def test_empty(payload):
    assert parse_snapshot(payload) is None


@pytest.mark.parametrize("payload", [[], 1, False, "text", {"playing": 1}, {"title": []},
                                    {"durationMicros": True}, {"elapsedTimeMicros": "3"},
                                    {"playbackRate": float("inf")}, {"durationMicros": 10**1000}])
def test_bad_types(payload):
    with pytest.raises(ProtocolError):
        parse_snapshot(payload)


@pytest.mark.parametrize("data", [b"\xff", b"{", b"NaN", b"Infinity", b"{}{}"])
def test_bad_json(data):
    with pytest.raises(ProtocolError):
        decode_json(data)


@pytest.mark.parametrize("data", [b"null", b'{}', b'{"type":"other","diff":false,"payload":{}}',
    b'{"type":"data","diff":true,"payload":{}}', b'{"type":"data","diff":0,"payload":{}}',
    b'{"type":"data","diff":false,"payload":null}'])
def test_bad_event(data):
    with pytest.raises(ProtocolError):
        parse_event(data)


def test_missing_title_and_null_values():
    state = parse_snapshot({"bundleIdentifier": "org.example.player", "playing": False, "title": None})
    assert state.title is None and state.playing is False
