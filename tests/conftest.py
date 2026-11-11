"""Shared pytest fixtures. pytest loads this file automatically."""

import pytest

from leavedesk.domain.notifications import EmailNotifier, InAppNotifier
from leavedesk.domain.service import LeaveService
from tests.helpers import build_service


@pytest.fixture
def service() -> LeaveService:
    """A fresh service with no notifiers, built anew for every test."""
    return build_service()


@pytest.fixture
def email() -> EmailNotifier:
    return EmailNotifier()


@pytest.fixture
def in_app() -> InAppNotifier:
    return InAppNotifier()
