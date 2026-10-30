import pytest

from app.applications.errors import InvalidStatusTransitionError
from app.applications.transitions import ALLOWED, TERMINAL, check_transition
from app.models.enums import ApplicationStatus as S


def test_table_covers_every_status():
    assert set(ALLOWED) == set(S)
    assert TERMINAL == {S.REJECTED, S.WITHDRAWN}


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (S.INTERESTED, S.APPLIED),
        (S.PREPARING, S.INTERESTED),
        (S.APPLIED, S.INTERVIEW),
        (S.INTERVIEW, S.ASSESSMENT),
        (S.OFFER, S.WITHDRAWN),
        (S.ASSESSMENT, S.OFFER),
    ],
)
def test_allowed(a, b):
    check_transition(a, b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (S.INTERESTED, S.OFFER),
        (S.INTERESTED, S.INTERVIEW),
        (S.APPLIED, S.PREPARING),
        (S.OFFER, S.APPLIED),
        (S.REJECTED, S.APPLIED),
        (S.WITHDRAWN, S.INTERESTED),
        (S.APPLIED, S.APPLIED),
    ],
)
def test_rejected(a, b):
    with pytest.raises(InvalidStatusTransitionError):
        check_transition(a, b)


def test_terminal_message_mentions_terminal():
    with pytest.raises(InvalidStatusTransitionError, match="terminal"):
        check_transition(S.REJECTED, S.APPLIED)
