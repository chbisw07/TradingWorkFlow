"""Server-composed canonical instrument authority for OE-1 order creation.

Only trusted application wiring may bind a canonical reference resolver. Request
payloads and ordinary create calls cannot assert that an InstrumentIdentity is
authoritative. OE-2 must supply the server-side resolver at composition time.
"""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID
from weakref import WeakValueDictionary

from twf.discovery.domain import InstrumentIdentity


class CanonicalInstrumentResolver(Protocol):
    def resolve(self, instrument_id: UUID) -> InstrumentIdentity | None:
        """Look up the authoritative identity for an exact canonical UUID."""


@dataclass(frozen=True, init=False, slots=True, weakref_slot=True)
class TrustedCanonicalInstrumentAuthority:
    _resolver: CanonicalInstrumentResolver

    def resolve(self, instrument_id: UUID) -> InstrumentIdentity | None:
        if not self.is_issued():
            raise TypeError("Unissued canonical instrument authority")
        return self._resolver.resolve(instrument_id)

    def is_issued(self) -> bool:
        return _ISSUED_AUTHORITIES.get(id(self)) is self


_ISSUED_AUTHORITIES: WeakValueDictionary[int, TrustedCanonicalInstrumentAuthority] = (
    WeakValueDictionary()
)


def _bind_trusted_canonical_resolver(
    resolver: CanonicalInstrumentResolver,
) -> TrustedCanonicalInstrumentAuthority:
    """Internal composition capability; never bind a request-provided resolver."""
    if not callable(getattr(resolver, "resolve", None)):
        raise TypeError("Canonical resolver required")
    authority = object.__new__(TrustedCanonicalInstrumentAuthority)
    object.__setattr__(authority, "_resolver", resolver)
    _ISSUED_AUTHORITIES[id(authority)] = authority
    return authority
