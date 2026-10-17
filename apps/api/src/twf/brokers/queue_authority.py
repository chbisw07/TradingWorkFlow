"""Internal worker capability, bound to a persisted AUTO entry and its account.

Not a request schema, login session, or general-purpose broker principal.
"""

from dataclasses import dataclass
from typing import TypeGuard
from uuid import UUID
from weakref import WeakValueDictionary

from twf.brokers.service import Principal


@dataclass(frozen=True)
class _QueuePrincipal(Principal):
    queue_entry_id: UUID
    account_id: UUID


_issued: WeakValueDictionary[int, _QueuePrincipal] = WeakValueDictionary()


def _issue(owner_id: UUID, entry_id: UUID, account_id: UUID) -> _QueuePrincipal:
    principal = _QueuePrincipal(owner_id, "", entry_id, account_id)
    _issued[id(principal)] = principal
    return principal


def _is_issued(principal: Principal) -> TypeGuard[_QueuePrincipal]:
    return type(principal) is _QueuePrincipal and _issued.get(id(principal)) is principal
