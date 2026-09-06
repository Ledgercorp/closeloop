import pytest

from tests.confirmation_support import (
    TEST_CONFIRMATION_AUDIENCE,
    TEST_CONFIRMATION_ISSUER,
    TEST_CONFIRMATION_SECRET,
)


@pytest.fixture(autouse=True)
def trusted_confirmation_test_environment(monkeypatch):
    """Enable only the explicit test confirmation authority during pytest runs."""

    monkeypatch.setenv("CLOSELOOP_CONFIRMATION_SECRET", TEST_CONFIRMATION_SECRET)
    monkeypatch.setenv("CLOSELOOP_CONFIRMATION_ISSUER", TEST_CONFIRMATION_ISSUER)
    monkeypatch.setenv("CLOSELOOP_CONFIRMATION_AUDIENCE", TEST_CONFIRMATION_AUDIENCE)
