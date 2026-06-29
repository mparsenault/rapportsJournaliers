"""Tests de mailer.py — httpx mocké, AUCUN appel réseau."""
import types

import pytest

import mailer


_CFG = {"tenant_id": "tid", "client_id": "cid", "client_secret": "sec",
        "sender": "rapports@elem.global", "default_recipients": "a@x.com"}


class _Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}
        self.text = "err"

    def json(self):
        return self._payload


class _FakeHttpx:
    """Compteur d'appels : 1er POST = jeton, suivants = sendMail."""
    def __init__(self):
        self.token_calls = 0
        self.send_calls = []

    def post(self, url, **kw):
        if url.endswith("/token"):
            self.token_calls += 1
            return _Resp(200, {"access_token": "TOK", "expires_in": 3600})
        self.send_calls.append((url, kw))
        return _Resp(202)


@pytest.fixture
def fake(monkeypatch):
    f = _FakeHttpx()
    monkeypatch.setattr(mailer, "httpx", f)
    monkeypatch.setattr(mailer, "_graph_config", lambda: dict(_CFG))
    mailer._reset_token_cache()
    return f


def test_send_mail_succes_et_payload(fake):
    ok, msg = mailer.send_mail("dest@x.com", "Sujet", "<p>Corps</p>",
                               "Rapport.xlsx", b"PK\x03\x04data")
    assert ok is True
    url, kw = fake.send_calls[0]
    assert url.endswith("/users/rapports@elem.global/sendMail")
    msg_body = kw["json"]["message"]
    assert msg_body["subject"] == "Sujet"
    assert msg_body["toRecipients"][0]["emailAddress"]["address"] == "dest@x.com"
    att = msg_body["attachments"][0]
    assert att["@odata.type"] == "#microsoft.graph.fileAttachment"
    assert att["name"] == "Rapport.xlsx"
    assert att["contentBytes"]   # base64 non vide
    assert "spreadsheetml" in att["contentType"]


def test_send_mail_destinataires_multiples_str(fake):
    ok, _ = mailer.send_mail("a@x.com; b@y.com", "S", "B", "f.xlsx", b"x")
    addrs = [r["emailAddress"]["address"]
             for r in fake.send_calls[0][1]["json"]["message"]["toRecipients"]]
    assert addrs == ["a@x.com", "b@y.com"]


def test_token_mis_en_cache(fake):
    mailer.send_mail("a@x.com", "S", "B", "f.xlsx", b"x")
    mailer.send_mail("a@x.com", "S", "B", "f.xlsx", b"x")
    assert fake.token_calls == 1      # jeton réutilisé


def test_destinataire_vide(fake):
    ok, msg = mailer.send_mail("", "S", "B", "f.xlsx", b"x")
    assert ok is False and "destinataire" in msg.lower()


def test_config_manquante(monkeypatch):
    def _boom():
        raise KeyError("graph")
    monkeypatch.setattr(mailer, "_graph_config", _boom)
    ok, msg = mailer.send_mail("a@x.com", "S", "B", "f.xlsx", b"x")
    assert ok is False and msg            # message non vide, pas d'exception


def test_echec_sendmail(monkeypatch):
    class _Bad(_FakeHttpx):
        def post(self, url, **kw):
            if url.endswith("/token"):
                return _Resp(200, {"access_token": "T", "expires_in": 3600})
            return _Resp(403)
    monkeypatch.setattr(mailer, "httpx", _Bad())
    monkeypatch.setattr(mailer, "_graph_config", lambda: dict(_CFG))
    mailer._reset_token_cache()
    ok, msg = mailer.send_mail("a@x.com", "S", "B", "f.xlsx", b"x")
    assert ok is False and "403" in msg
