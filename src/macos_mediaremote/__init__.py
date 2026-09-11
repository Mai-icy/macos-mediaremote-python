"""Unofficial Python interface to ungive/mediaremote-adapter."""
from .client import Command, EventStream, MediaRemote
from .errors import (
    HelperError, HelperTimeoutError, MediaRemoteError, ProtocolError, UnsupportedPlatformError,
)
from .models import NowPlaying

__version__ = "0.1.0a1"
__all__ = [
    "MediaRemote", "NowPlaying", "EventStream", "Command", "MediaRemoteError",
    "HelperError", "HelperTimeoutError", "ProtocolError", "UnsupportedPlatformError",
]
