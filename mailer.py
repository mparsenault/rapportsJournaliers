"""Envoi de courriels via Microsoft Graph (client credentials).

`send_mail` ne lève jamais : toute erreur est renvoyée dans (False, message).
Le jeton applicatif est mis en cache en mémoire jusqu'à ~60 s avant expiration.
"""
import base64
import time

import httpx
import streamlit as st

_XLSX_CT = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_GRAPH = "https://graph.microsoft.com/v1.0"
_token_cache = {"value": None, "exp": 0.0}


def _reset_token_cache():
    _token_cache["value"] = None
    _token_cache["exp"] = 0.0


def _graph_config():
    """Lit la section [graph] des secrets ; lève KeyError si absente."""
    cfg = st.secrets["graph"]
    return {k: cfg[k] for k in
            ("tenant_id", "client_id", "client_secret", "sender", "default_recipients")}


def _recipients(to):
    if isinstance(to, str):
        items = [x.strip() for x in to.split(";")]
    else:
        items = [str(x).strip() for x in (to or [])]
    return [x for x in items if x]


def _get_token(cfg):
    now = time.time()
    if _token_cache["value"] and now < _token_cache["exp"]:
        return _token_cache["value"]
    url = f"https://login.microsoftonline.com/{cfg['tenant_id']}/oauth2/v2.0/token"
    resp = httpx.post(url, data={
        "grant_type": "client_credentials",
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "scope": "https://graph.microsoft.com/.default",
    }, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"jeton Graph refusé (HTTP {resp.status_code})")
    data = resp.json()
    _token_cache["value"] = data["access_token"]
    _token_cache["exp"] = now + max(0, int(data.get("expires_in", 3600)) - 60)
    return _token_cache["value"]


def send_mail(to, subject, html_body, attachment_name, attachment_bytes, sender=None):
    """Envoie un courriel avec une pièce jointe. Renvoie (ok, message).

    `sender` : boîte d'envoi (UPN). Si fourni, le courriel part de cette boîte
    (ex. la personne connectée) ; sinon, on retombe sur `[graph].sender`.
    """
    recipients = _recipients(to)
    if not recipients:
        return False, "Aucun destinataire fourni."
    try:
        cfg = _graph_config()
    except Exception:
        return False, "Configuration [graph] manquante dans les secrets."
    from_mailbox = sender or cfg["sender"]
    try:
        token = _get_token(cfg)
        message = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": a}} for a in recipients],
            "attachments": [{
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": attachment_name,
                "contentType": _XLSX_CT,
                "contentBytes": base64.b64encode(attachment_bytes).decode("ascii"),
            }],
        }
        url = f"{_GRAPH}/users/{from_mailbox}/sendMail"
        resp = httpx.post(url, headers={"Authorization": f"Bearer {token}"},
                          json={"message": message, "saveToSentItems": True}, timeout=30)
        if resp.status_code not in (200, 202):
            return False, f"Échec de l'envoi (HTTP {resp.status_code})."
        return True, "Courriel envoyé ✓"
    except Exception as exc:  # noqa: BLE001
        return False, f"Échec de l'envoi : {exc}"
