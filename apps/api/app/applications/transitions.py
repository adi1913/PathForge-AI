"""Application status lifecycle. Pure data + one check, so it is trivially unit-testable."""

from app.applications.errors import InvalidStatusTransitionError
from app.models.enums import ApplicationStatus as S

ALLOWED: dict[S, frozenset[S]] = {
    S.INTERESTED: frozenset({S.PREPARING, S.APPLIED, S.WITHDRAWN}),
    S.PREPARING: frozenset({S.INTERESTED, S.APPLIED, S.WITHDRAWN}),
    S.APPLIED: frozenset({S.ASSESSMENT, S.INTERVIEW, S.OFFER, S.REJECTED, S.WITHDRAWN}),
    S.ASSESSMENT: frozenset({S.INTERVIEW, S.OFFER, S.REJECTED, S.WITHDRAWN}),
    S.INTERVIEW: frozenset({S.ASSESSMENT, S.OFFER, S.REJECTED, S.WITHDRAWN}),
    S.OFFER: frozenset({S.REJECTED, S.WITHDRAWN}),
    S.REJECTED: frozenset(),
    S.WITHDRAWN: frozenset(),
}
TERMINAL = frozenset(s for s, targets in ALLOWED.items() if not targets)
SCHEDULABLE = frozenset({S.ASSESSMENT, S.INTERVIEW})


def check_transition(current: S, new: S) -> None:
    if current == new:
        raise InvalidStatusTransitionError(f"Application is already '{current.value}'")
    if new not in ALLOWED[current]:
        allowed = ", ".join(sorted(s.value for s in ALLOWED[current])) or "none (terminal status)"
        raise InvalidStatusTransitionError(
            f"Cannot move an application from '{current.value}' to '{new.value}'; allowed: {allowed}"
        )
