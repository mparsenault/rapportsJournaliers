"""
Fixtures partagées pour la suite de tests.

simulate_logged_in (autouse) : patche streamlit.user_info._get_user_info pour
que st.user.is_logged_in renvoie True dans tous les tests AppTest.
Sans ce patch, la garde d'accès OAuth arrête l'app avec st.stop() avant que
les tests puissent exercer l'UI.
"""
import unittest.mock as mock

import pytest


_MOCK_USER_INFO = {
    "is_logged_in": True,
    "name": "Test User",
    "email": "test@example.com",
}


@pytest.fixture(autouse=True)
def simulate_logged_in(monkeypatch):
    """Simule un utilisateur connecté pour tous les tests utilisant AppTest."""
    import streamlit.user_info as _ui
    monkeypatch.setattr(_ui, "_get_user_info", lambda: _MOCK_USER_INFO)
