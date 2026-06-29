"""Tests du helper d'identité current_user()."""
from types import SimpleNamespace

import app


def test_current_user_logged_in(monkeypatch):
    monkeypatch.setattr(
        app.st, "user",
        SimpleNamespace(is_logged_in=True, name="Marie Arsenault",
                        email="mparsenault@elem.global"),
    )
    assert app.current_user() == {
        "name": "Marie Arsenault", "email": "mparsenault@elem.global"}


def test_current_user_logged_out(monkeypatch):
    monkeypatch.setattr(
        app.st, "user", SimpleNamespace(is_logged_in=False))
    assert app.current_user() == {"name": "", "email": ""}


def test_current_user_missing_attrs(monkeypatch):
    monkeypatch.setattr(
        app.st, "user", SimpleNamespace(is_logged_in=True))
    assert app.current_user() == {"name": "", "email": ""}
