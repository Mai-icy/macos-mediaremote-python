"""Errors raised by the Python wrapper (cancellation remains CancelledError)."""


class MediaRemoteError(Exception):
    """Base class for runtime failures."""


class UnsupportedPlatformError(MediaRemoteError):
    """The bundled helper requires macOS and system Perl."""


class ProtocolError(MediaRemoteError):
    """Malformed, oversized or unexpected upstream output."""


class HelperError(MediaRemoteError):
    """Helper could not start, or exited unsuccessfully."""

    def __init__(self, message: str, *, returncode: int | None = None, stderr: str = ""):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


class HelperTimeoutError(MediaRemoteError, TimeoutError):
    """Command or initial stream snapshot timed out; helper has been closed."""

    def __init__(self, message: str, *, stderr: str = ""):
        super().__init__(message)
        self.stderr = stderr
