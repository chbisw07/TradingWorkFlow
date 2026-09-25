"""Bounded per-process login budget; never trusts forwarded client headers."""

from collections import OrderedDict
from threading import Lock
from time import monotonic


class LoginLimit:
    def __init__(self) -> None:
        self._attempts: OrderedDict[str, tuple[float, int]] = OrderedDict()
        self._lock = Lock()

    def allow(self, peer: str) -> bool:
        now = monotonic()
        with self._lock:
            started, count = self._attempts.pop(peer, (now, 0))
            if now - started >= 60:
                started, count = now, 0
            self._attempts[peer] = (started, count + 1)
            if len(self._attempts) > 1024:
                self._attempts.popitem(last=False)
            return count < 60
