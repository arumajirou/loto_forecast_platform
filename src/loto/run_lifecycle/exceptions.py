"""Domain exceptions for the durable run lifecycle foundation."""

from __future__ import annotations


class LifecycleError(Exception):
    """Base class for lifecycle failures."""


class LifecycleValidationError(LifecycleError):
    """Raised when strict lifecycle evidence validation fails."""


class TransitionRejected(LifecycleError):
    """Raised when the transition engine rejects a command."""


class OptimisticConcurrencyError(LifecycleError):
    """Raised when an expected revision does not match current state."""


class EventChainError(LifecycleError):
    """Raised when append-only event-chain integrity is invalid."""


class IdempotencyConflictError(LifecycleError):
    """Raised when one idempotency key is reused for another semantic payload."""


class LeaseError(LifecycleError):
    """Base class for lease and fencing failures."""


class LeaseExpiredError(LeaseError):
    """Raised when a lease operation is attempted after expiry."""


class LeaseOwnershipError(LeaseError):
    """Raised for wrong-owner, wrong-run, or wrong-lease mutations."""


class StaleFencingTokenError(LeaseError):
    """Raised when a stale worker presents an old fencing token."""


class RepositoryConflictError(LifecycleError):
    """Raised when an in-memory atomic commit detects conflicting state."""
