"""Test de l'helper d'envoi d'une journée (mailer mocké)."""
from datetime import date

import app


def _projet():
    return {"no": "12345", "id_project": 7, "semaine": date(2026, 6, 21),
            "adresse": "123 rue", "lat": None, "lon": None}


def _day_rempli():
    q = app._empty_quart()
    q["personnel"] = ["Mathis"]
    q["heures"] = {"Mathis": {"Excavation": {"TR": 8.0, "TS": 0.0}}}
    return {"date": date(2026, 6, 22), "quarts": {"Jour": q}}


def test_envoyer_journee_appelle_send_mail(monkeypatch):
    captured = {}

    def fake_send(to, subject, html, name, data):
        captured.update(to=to, subject=subject, name=name, data=data)
        return True, "Courriel envoyé ✓"

    monkeypatch.setattr(app.mailer, "send_mail", fake_send)
    ok, msg = app.envoyer_journee_par_courriel(
        _projet(), "Lundi", _day_rempli(), "dest@x.com", "Test User")
    assert ok is True
    assert captured["to"] == "dest@x.com"
    assert "Lundi" in captured["subject"]
    assert captured["name"] == "Rapport_12345_2026-06-22.xlsx"
    assert captured["data"][:2] == b"PK"


def test_envoyer_journee_vide_refuse(monkeypatch):
    monkeypatch.setattr(app.mailer, "send_mail",
                        lambda *a, **k: (True, "ne devrait pas être appelé"))
    vide = {"date": date(2026, 6, 22), "quarts": {"Jour": app._empty_quart()}}
    ok, msg = app.envoyer_journee_par_courriel(
        _projet(), "Lundi", vide, "dest@x.com", "Test User")
    assert ok is False and "vide" in msg.lower()
