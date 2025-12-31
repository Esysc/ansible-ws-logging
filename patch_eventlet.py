# Lightweight helper to apply eventlet monkey_patch early via import.
# Importing this module at the top of other modules ensures the patch
# is applied without having executable statements before other imports
# in those modules (avoids flake8 E402 warnings).
try:
    from typing import Any, Protocol, cast

    import eventlet

    class _MonkeyPatch(Protocol):
        def __call__(
            self,
            os: bool = True,
            dns: bool = True,
            select: bool = True,
            socket: bool = True,
            thread: bool = True,
            time: bool = True,
            greenlet: bool = True,
            signal: bool = True,
            ssl: bool = True,
            **kwargs: Any,
        ) -> None: ...

    cast(_MonkeyPatch, eventlet.monkey_patch)()
except Exception:
    # Best-effort; if eventlet isn't available or patching fails, continue
    pass
