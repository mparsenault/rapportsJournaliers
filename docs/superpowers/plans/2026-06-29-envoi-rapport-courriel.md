# Envoi du rapport Excel par courriel — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre, depuis la saisie journalière, d'envoyer par courriel le rapport Excel de la journée affichée (un clic = une journée = un fichier `.xlsx` = un courriel), avec une vraie mise en page Excel d'une journée.

**Architecture:** Deux nouveaux modules. `excel_report.py` (présentation Excel) construit les classeurs ; il importe `app` pour la mise en forme des données (`_legacy_day` reste dans `app`). `mailer.py` envoie via Microsoft Graph (client credentials, jeton mis en cache). `app.py` importe `excel_report` **paresseusement** (import dans les vues) pour éviter tout import circulaire ; `mailer` ne dépend pas d'`app`.

**Tech Stack:** Python, Streamlit, openpyxl, httpx, Microsoft Graph API, pytest.

## Global Constraints

- Python 3.9 en local (serveur Tornado) **et** ≥ 3.10 sur Streamlit Cloud (Starlette) : tout code doit tourner sur les deux.
- `httpx` doit devenir une dépendance **inconditionnelle** (aujourd'hui réservée à `python_version >= "3.10"`).
- `excel_report.py` n'est **jamais** importé au niveau module de `app.py` (import paresseux dans les fonctions de vue) — sinon import circulaire avec `import app` dans `excel_report.py`.
- `mailer.send_mail` ne **lève jamais** : toute erreur (config, jeton, réseau, Graph) est capturée et renvoyée dans `(False, message)`.
- Les tests `mailer` n'effectuent **aucun appel réseau** (`httpx` mocké).
- Une journée est « remplie » ssi `app._day_total(day) > 0`.
- Réutiliser les styles Excel et les helpers de données existants ; ne pas dupliquer `_legacy_day`.
- Couleurs Ondel : teal `0999AA`. Titre Excel : « RAPPORT JOURNALIER — ONDEL ».
- Section secrets : `[graph]` avec `tenant_id`, `client_id`, `client_secret`, `sender`, `default_recipients`.

---

### Task 1 : Module `excel_report.py` — mise en page d'une journée + classeur hebdo

Construit la vraie sortie Excel. Déplace les styles Excel et `_add_logo` hors de `app.py`, supprime l'ancien `_build_synthese`/`build_workbook` (qui n'écrivaient aucune donnée), et branche le téléchargement de `view_export` sur la nouvelle génération.

**Files:**
- Create: `excel_report.py`
- Create: `tests/test_excel_report.py`
- Modify: `app.py` (retirer le bloc styles Excel `_TEAL`..`_HOURS_FMT` lignes ~77-94 ; retirer `_add_logo` ~478-488, `_build_synthese` ~490-499, `build_workbook` ~501-507 ; modifier `view_export` ~1493-1499)

**Interfaces:**
- Consumes (depuis `app`) : `JOURS`, `QUART_NAMES`, `LOGO_PATH`, `fr_date_long(d)`, `_legacy_day(quart)`, `_day_total(day)`, `_quart_total(quart)`, `_day_quart_names(day)`, `HOUR_KEYS`.
- Produces :
  - `build_day_workbook(projet: dict, jour_name: str, day: dict, exported_by: str = "") -> io.BytesIO`
  - `build_week_workbook(projet: dict, jours: dict, jours_order: list[str], exported_by: str = "") -> io.BytesIO`
  - `build_day_email(projet: dict, jour_name: str, day: dict, exported_by: str = "") -> tuple[str, str, str, bytes]` → `(subject, html_body, filename, xlsx_bytes)` (utilisé par la Task 3)

- [ ] **Step 1 : Écrire les tests qui échouent**

Créer `tests/test_excel_report.py` :

```python
"""Tests de excel_report.py : on recharge le .xlsx produit et on vérifie le contenu."""
from datetime import date
from io import BytesIO

import openpyxl

import app
import excel_report


def _projet():
    return {"no": "12345", "id_project": 7, "semaine": date(2026, 6, 21),
            "adresse": "123 rue Principale", "lat": None, "lon": None}


def _day_rempli():
    q = app._empty_quart()
    q["personnel"] = ["Mathis Lajeunesse"]
    q["temp_am"] = 12.0
    q["conditions"] = ["Ensoleillé"]
    q["heures"] = {"Mathis Lajeunesse": {"Excavation": {"TR": 8.0, "TS": 1.0}}}
    q["prime"] = {"Mathis Lajeunesse": 25.0}
    return {"date": date(2026, 6, 22), "quarts": {"Jour": q}}


def _day_vide():
    return {"date": date(2026, 6, 22), "quarts": {"Jour": app._empty_quart()}}


def _all_text(ws):
    return "\n".join(
        str(c.value) for row in ws.iter_rows() for c in row if c.value not in (None, ""))


def test_build_day_workbook_une_feuille_et_entete():
    buf = excel_report.build_day_workbook(_projet(), "Lundi", _day_rempli(), "Test User")
    wb = openpyxl.load_workbook(buf)
    assert wb.sheetnames == ["Lundi"]
    txt = _all_text(wb["Lundi"])
    assert "RAPPORT JOURNALIER — ONDEL" in txt
    assert "12345" in txt                      # No Projet
    assert "Mathis Lajeunesse" in txt          # ligne de personnel
    assert "Exporté par Test User" in txt      # estampille


def test_build_day_workbook_heures_et_prime_presentes():
    buf = excel_report.build_day_workbook(_projet(), "Lundi", _day_rempli(), "")
    wb = openpyxl.load_workbook(buf)
    vals = [c.value for row in wb["Lundi"].iter_rows() for c in row]
    assert 8.0 in vals and 1.0 in vals     # TR et TS
    assert 25.0 in vals                    # prime


def test_build_day_workbook_jour_vide_sans_personnel():
    buf = excel_report.build_day_workbook(_projet(), "Lundi", _day_vide(), "")
    wb = openpyxl.load_workbook(buf)
    txt = _all_text(wb["Lundi"])
    assert "RAPPORT JOURNALIER — ONDEL" in txt
    assert "Mathis" not in txt


def test_build_week_workbook_une_feuille_par_jour_rempli():
    jours = {j: _day_vide() for j in app.JOURS}
    jours["Lundi"] = _day_rempli()
    jours["Mercredi"] = _day_rempli()
    buf = excel_report.build_week_workbook(_projet(), jours, app.JOURS, "")
    wb = openpyxl.load_workbook(buf)
    assert wb.sheetnames == ["Lundi", "Mercredi"]


def test_build_day_email_renvoie_sujet_nom_et_bytes():
    subject, html, filename, data = excel_report.build_day_email(
        _projet(), "Lundi", _day_rempli(), "Test User")
    assert "12345" in subject and "Lundi" in subject
    assert filename == "Rapport_12345_2026-06-22.xlsx"
    assert isinstance(data, bytes) and data[:2] == b"PK"   # signature zip/xlsx
    assert "Test User" in html
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `.venv/bin/python -m pytest tests/test_excel_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'excel_report'`.

- [ ] **Step 3 : Créer `excel_report.py`**

```python
"""Génération Excel des rapports journaliers (présentation).

La mise en forme des DONNÉES reste dans app.py (`_legacy_day`) ; ce module
construit les classeurs openpyxl. Il importe `app` ; app NE DOIT PAS importer
excel_report au niveau module (import paresseux dans les vues) pour éviter un
import circulaire.
"""
import base64
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

import app

# --- Styles Ondel (déplacés depuis app.py) -------------------------------
_TEAL = "0999AA"
_TEAL_DK = "077A88"
_BAND = "EEF8F9"
_GREY = "D9E2E4"
_THIN = Side(style="thin", color=_GREY)
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_F_TITLE = Font(name="Calibri", size=16, bold=True, color="FFFFFF")
_F_HEAD = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
_F_LABEL = Font(name="Calibri", size=10, bold=True, color=_TEAL_DK)
_F_TOTAL = Font(name="Calibri", size=10, bold=True, color="0E2A2E")
_FILL_TITLE = PatternFill("solid", fgColor=_TEAL)
_FILL_HEAD = PatternFill("solid", fgColor=_TEAL_DK)
_FILL_BAND = PatternFill("solid", fgColor=_BAND)
_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
_LEFT = Alignment(horizontal="left", vertical="center")
_RIGHT = Alignment(horizontal="right", vertical="center")
_HOURS_FMT = "0.00"


def _add_logo(ws, height_px=58):
    import os
    if not os.path.exists(app.LOGO_PATH):
        return
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
    from openpyxl.drawing.xdr import XDRPositiveSize2D
    from openpyxl.utils.units import pixels_to_EMU
    img = XLImage(app.LOGO_PATH)
    w = round(292 / 280 * height_px)
    marker = AnchorMarker(col=0, colOff=pixels_to_EMU(12), row=0, rowOff=pixels_to_EMU(8))
    img.anchor = OneCellAnchor(_from=marker,
                               ext=XDRPositiveSize2D(pixels_to_EMU(w), pixels_to_EMU(height_px)))
    ws.add_image(img)


def _safe_title(name):
    """Titre de feuille Excel : ≤31 car., sans caractères interdits."""
    bad = '[]:*?/\\'
    return "".join(c for c in str(name) if c not in bad)[:31] or "Feuille"


def _write_row(ws, row, values, *, bold=False, fill=None, fmt=None):
    for col, val in enumerate(values, start=1):
        cell = ws.cell(row=row, column=col, value=val)
        cell.border = _BORDER
        cell.alignment = _LEFT if col == 1 else _CENTER
        if bold:
            cell.font = _F_HEAD if fill is _FILL_HEAD else _F_TOTAL
        if fill is not None:
            cell.fill = fill
        if fmt and isinstance(val, (int, float)):
            cell.number_format = fmt


def _build_day_sheet(ws, projet, jour_name, day, exported_by=""):
    """Écrit le rapport d'une journée dans la feuille `ws`."""
    ws.title = _safe_title(jour_name)
    _add_logo(ws)
    ws.column_dimensions["A"].width = 28

    ws.merge_cells("B1:H1")
    t = ws["B1"]
    t.value = "RAPPORT JOURNALIER — ONDEL"
    t.font = _F_TITLE
    t.fill = _FILL_TITLE

    d = day.get("date")
    date_txt = app.fr_date_long(d) if d else ""
    ws.cell(row=3, column=1, value="No Projet :").font = _F_LABEL
    ws.cell(row=3, column=2, value=str(projet.get("no") or ""))
    ws.cell(row=4, column=1, value="Date :").font = _F_LABEL
    ws.cell(row=4, column=2, value=f"{jour_name} {date_txt}".strip())
    ws.cell(row=5, column=1, value="Adresse :").font = _F_LABEL
    ws.cell(row=5, column=2, value=projet.get("adresse") or "")

    row = 7
    for qname in app._day_quart_names(day):
        quart = day["quarts"][qname]
        if app._quart_total(quart) <= 0:
            continue
        leg = app._legacy_day(quart)

        ws.cell(row=row, column=1, value=f"Quart : {qname}").font = _F_LABEL
        ws.cell(row=row, column=3,
                value=f"Resp. : {leg.get('responsable', '')}").font = _F_LABEL
        ws.cell(row=row, column=5,
                value=f"Temp. AM : {leg.get('temp_am')}  PM : {leg.get('temp_pm')}")
        ws.cell(row=row, column=7,
                value="Conditions : " + ", ".join(leg.get("conditions", [])))
        row += 1
        if leg.get("description"):
            ws.cell(row=row, column=1, value=f"Note : {leg['description']}")
            row += 1

        row = _write_table(ws, row, leg["headers"], leg["pers"], with_equip=True)
        row += 1
        row = _write_table(ws, row, leg["headers"], leg["equip"], with_equip=False)
        row += 2

    # Estampille (dernière écriture)
    last = ws.max_row + 2
    cell = ws.cell(row=last, column=1, value=f"Exporté par {exported_by or '—'}")
    cell.font = Font(name="Calibri", size=8, italic=True, color="6B7B7E")


def _write_table(ws, row, headers, df, *, with_equip):
    """Écrit un tableau (personnel ou équipement) ; renvoie la prochaine ligne libre.

    `headers` mappe les clés hX/aX -> libellés d'activité (vides à ignorer).
    `df` est le DataFrame produit par app._legacy_day (build_df)."""
    label_col = df.columns[0]                      # "Nom" ou "Véhicule"
    act_cols = [k for k in app.HOUR_KEYS if headers.get(k)]
    cols = [label_col] + act_cols + ["TR", "TS"]
    if with_equip:
        cols += ["Hrs Éq.", "Code Éq."]
    cols += ["Prime", "Commentaire"]

    titles = [label_col] + [headers[k] for k in act_cols] + cols[1 + len(act_cols):]
    _write_row(ws, row, titles, bold=True, fill=_FILL_HEAD)
    row += 1
    for _, rec in df.iterrows():
        values = [rec.get(c) for c in cols]
        _write_row(ws, row, values, fmt=_HOURS_FMT, fill=_FILL_BAND)
        row += 1
    return row


def build_day_workbook(projet, jour_name, day, exported_by=""):
    wb = Workbook()
    _build_day_sheet(wb.active, projet, jour_name, day, exported_by)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def build_week_workbook(projet, jours, jours_order, exported_by=""):
    wb = Workbook()
    wb.remove(wb.active)
    for jour_name in jours_order:
        day = jours.get(jour_name) or {}
        if app._day_total(day) <= 0:
            continue
        ws = wb.create_sheet(title=_safe_title(jour_name))
        _build_day_sheet(ws, projet, jour_name, day, exported_by)
    if not wb.sheetnames:                       # aucune journée remplie
        wb.create_sheet(title="Vide")
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def build_day_email(projet, jour_name, day, exported_by=""):
    """Renvoie (subject, html_body, filename, xlsx_bytes) pour une journée."""
    no = str(projet.get("no") or "")
    d = day.get("date")
    date_iso = d.isoformat() if d else "sans-date"
    date_txt = app.fr_date_long(d) if d else ""
    subject = f"Rapport journalier — {no} — {date_txt} ({jour_name})"
    html_body = (
        f"<p>Bonjour,</p>"
        f"<p>Veuillez trouver ci-joint le rapport journalier du projet "
        f"<b>{no}</b> pour le <b>{jour_name} {date_txt}</b>.</p>"
        f"<p style='color:#6B7B7E;font-size:12px'>Exporté par {exported_by or '—'}.</p>"
    )
    filename = f"Rapport_{no}_{date_iso}.xlsx"
    data = build_day_workbook(projet, jour_name, day, exported_by).getvalue()
    return subject, html_body, filename, data
```

- [ ] **Step 4 : Retirer le code Excel déplacé de `app.py`**

Dans `app.py` :
1. Supprimer le bloc « Styles Excel » (`_TEAL = "0999AA"` jusqu'à `_HOURS_FMT = "0.00"`, lignes ~77-94). Vérifier d'abord par recherche qu'aucun de ces noms `_F_*`, `_FILL_*`, `_BORDER`, `_CENTER`, `_LEFT`, `_RIGHT`, `_HOURS_FMT`, `_BAND`, `_GREY`, `_THIN`, `_TEAL*` n'est utilisé ailleurs dans `app.py` :

Run: `grep -nE "_F_TITLE|_F_HEAD|_F_LABEL|_F_TOTAL|_FILL_TITLE|_FILL_HEAD|_FILL_BAND|_BORDER|_CENTER|_LEFT|_RIGHT|_HOURS_FMT|_TEAL|_BAND|_GREY|_THIN" app.py`
Expected : seules les définitions (lignes ~77-94) ressortent. Si un usage subsiste hors bloc, le déplacer aussi.

2. Supprimer les fonctions `_add_logo` (~478-488), `_build_synthese` (~490-499) et `build_workbook` (~501-507).
3. Les imports openpyxl en tête d'`app.py` (`from openpyxl import Workbook`, `from openpyxl.styles import ...`, `from openpyxl.utils import get_column_letter`) ne sont peut-être plus utilisés. Vérifier et retirer ceux devenus inutiles :

Run: `grep -nE "Workbook|PatternFill|get_column_letter|Alignment|Border|Font|Side" app.py`
Expected : ne garder que les imports encore référencés.

- [ ] **Step 5 : Brancher `view_export` sur `build_week_workbook`**

Remplacer le corps de `view_export` (~1493-1499) par :

```python
def view_export():
    import excel_report
    st.subheader("📥 Export Excel")
    with st.container(border=True):
        st.write("Le fichier Excel contient le détail de chaque journée remplie de la semaine.")
        if st.button("🚀 Générer le fichier Excel", type="primary", use_container_width=True):
            buf = excel_report.build_week_workbook(
                st.session_state.projet, st.session_state.jours, JOURS,
                exported_by=current_user()["name"])
            st.download_button(
                "⬇️ Télécharger .xlsx", buf,
                file_name=f"Rapport_{st.session_state.projet['no']}.xlsx",
                use_container_width=True)
```

- [ ] **Step 6 : Lancer la suite et vérifier le vert**

Run: `.venv/bin/python -m pytest tests/test_excel_report.py tests/test_smoke.py tests/test_model.py -v`
Expected : PASS (y compris `import app` toujours fonctionnel).

- [ ] **Step 7 : Commit**

```bash
git add excel_report.py tests/test_excel_report.py app.py
git commit -m "feat(excel): mise en page d'une journée + classeur hebdo rempli

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2 : Module `mailer.py` — envoi via Microsoft Graph

Envoi serveur (client credentials) avec jeton mis en cache. Aucun appel réseau dans les tests (`httpx` mocké).

**Files:**
- Create: `mailer.py`
- Create: `tests/test_mailer.py`
- Modify: `requirements.txt` (httpx inconditionnel)
- Modify: `.streamlit/secrets.toml.example` (section `[graph]`)

**Interfaces:**
- Produces : `send_mail(to, subject: str, html_body: str, attachment_name: str, attachment_bytes: bytes) -> tuple[bool, str]` — `to` accepte `str` (séparés par `;`) ou `list[str]`.

- [ ] **Step 1 : Écrire les tests qui échouent**

Créer `tests/test_mailer.py` :

```python
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
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `.venv/bin/python -m pytest tests/test_mailer.py -v`
Expected : FAIL — `ModuleNotFoundError: No module named 'mailer'`.

- [ ] **Step 3 : Créer `mailer.py`**

```python
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


def send_mail(to, subject, html_body, attachment_name, attachment_bytes):
    """Envoie un courriel avec une pièce jointe. Renvoie (ok, message)."""
    recipients = _recipients(to)
    if not recipients:
        return False, "Aucun destinataire fourni."
    try:
        cfg = _graph_config()
    except Exception:
        return False, "Configuration [graph] manquante dans les secrets."
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
        url = f"{_GRAPH}/users/{cfg['sender']}/sendMail"
        resp = httpx.post(url, headers={"Authorization": f"Bearer {token}"},
                          json={"message": message, "saveToSentItems": True}, timeout=30)
        if resp.status_code not in (200, 202):
            return False, f"Échec de l'envoi (HTTP {resp.status_code})."
        return True, "Courriel envoyé ✓"
    except Exception as exc:  # noqa: BLE001
        return False, f"Échec de l'envoi : {exc}"
```

- [ ] **Step 4 : Lancer les tests `mailer` et vérifier le vert**

Run: `.venv/bin/python -m pytest tests/test_mailer.py -v`
Expected : PASS (6 tests).

- [ ] **Step 5 : `httpx` inconditionnel dans `requirements.txt`**

Remplacer la ligne `httpx ; python_version >= "3.10"` (et son commentaire) par une dépendance simple. Le résultat doit contenir, sans condition :

```
httpx
```

(Garder Authlib conditionnel ; seul `httpx` devient inconditionnel car `mailer` l'utilise aussi en local Python 3.9.)

- [ ] **Step 6 : Section `[graph]` dans `secrets.toml.example`**

Ajouter à la fin de `.streamlit/secrets.toml.example` :

```toml

# Envoi de courriels via Microsoft Graph (client credentials).
# Nécessite la permission APPLICATION Mail.Send (consentement admin) et une
# boîte d'envoi `sender`. Voir docs/superpowers/specs/2026-06-29-envoi-rapport-courriel-design.md
[graph]
tenant_id = "<tenant_id>"
client_id = "<app_client_id>"
client_secret = "<app_client_secret>"
sender = "rapports@elem.global"
default_recipients = "destinataire@elem.global"
```

- [ ] **Step 7 : Commit**

```bash
git add mailer.py tests/test_mailer.py requirements.txt .streamlit/secrets.toml.example
git commit -m "feat(mail): envoi de rapport via Microsoft Graph (client credentials)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3 : Bouton « Envoyer par courriel » dans la saisie journalière

Popover à côté de « 💾 Enregistrer » qui envoie la journée affichée.

**Files:**
- Modify: `app.py` (barre d'actions de `view_day_entry`, ~1482-1491)
- Create: `tests/test_envoi_ui.py`

**Interfaces:**
- Consumes : `excel_report.build_day_email(projet, jour_name, day, exported_by)`, `mailer.send_mail(...)`, `app._day_total(day)`, `app.current_user()`.

- [ ] **Step 1 : Écrire le test qui échoue**

Le code de `view_day_entry` est déjà sous AppTest dans `tests/test_ui.py`. On vérifie ici que la fonction de vue contient le popover et qu'envoyer appelle `mailer.send_mail`. Comme l'UI exacte est difficile à piloter, on teste l'unité d'envoi extraite. Créer `tests/test_envoi_ui.py` :

```python
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
```

- [ ] **Step 2 : Lancer le test pour vérifier qu'il échoue**

Run: `.venv/bin/python -m pytest tests/test_envoi_ui.py -v`
Expected : FAIL — `AttributeError: module 'app' has no attribute 'mailer'` ou `envoyer_journee_par_courriel`.

- [ ] **Step 3 : Ajouter l'import et l'helper d'envoi dans `app.py`**

Ajouter en tête d'`app.py` (avec les autres imports de modules locaux comme `import reports`) :

```python
import mailer
```

(`mailer` ne dépend pas d'`app` : pas de cycle. On NE met PAS `import excel_report` au niveau module.)

Ajouter la fonction d'envoi (près de `save_report_from_state`) :

```python
def envoyer_journee_par_courriel(projet, jour_name, day, destinataires, exported_by):
    """Construit le .xlsx de la journée et l'envoie. Renvoie (ok, message)."""
    if _day_total(day) <= 0:
        return False, "Journée vide, rien à envoyer."
    import excel_report
    subject, html_body, filename, data = excel_report.build_day_email(
        projet, jour_name, day, exported_by)
    return mailer.send_mail(destinataires, subject, html_body, filename, data)
```

- [ ] **Step 4 : Lancer le test et vérifier le vert**

Run: `.venv/bin/python -m pytest tests/test_envoi_ui.py -v`
Expected : PASS (2 tests).

- [ ] **Step 5 : Ajouter le popover dans la barre d'actions de `view_day_entry`**

Remplacer le bloc des colonnes d'action (`sb1, sb2 = st.columns([3, 1] ...)` jusqu'au bouton Enregistrer, ~1482-1491) par :

```python
    sb1, sb2, sb3 = st.columns([3, 1, 1], vertical_alignment="center")
    if missing:
        sb1.info("Pour continuer, pensez à ajouter : " + ", ".join(missing) + ".")
    elif st.session_state.get("dirty"):
        sb1.warning("⚠️ Modifications non enregistrées — pensez à enregistrer avant de quitter.")
    else:
        sb1.caption("✓ Toutes les modifications sont enregistrées.")
    if sb2.button("💾 Enregistrer", use_container_width=True, type="primary", key=f"save_{jour}"):
        ok, msg = save_report_from_state()
        (st.success if ok else st.error)(msg)
    with sb3.popover("📧 Envoyer", use_container_width=True):
        day = st.session_state.jours[jour]
        if _day_total(day) <= 0:
            st.caption("Journée vide, rien à envoyer.")
        else:
            default_to = ""
            try:
                default_to = st.secrets["graph"]["default_recipients"]
            except Exception:
                pass
            to = st.text_input("Destinataire(s) (séparés par ;)", value=default_to,
                               key=f"mail_to_{jour}")
            if st.button("Envoyer le courriel", key=f"send_{jour}", type="primary"):
                ok, msg = envoyer_journee_par_courriel(
                    st.session_state.projet, jour, day, to, current_user()["name"])
                (st.success if ok else st.error)(msg)
```

Note : `jour` est la variable du jour courant déjà en portée dans `view_day_entry`.

- [ ] **Step 6 : Vérifier que l'app se charge toujours (smoke + UI)**

Run: `.venv/bin/python -m pytest tests/test_smoke.py tests/test_ui.py tests/test_envoi_ui.py -v`
Expected : PASS (l'app s'importe et se rend ; le bouton n'est pas déclenché sans secrets).

- [ ] **Step 7 : Suite complète**

Run: `.venv/bin/python -m pytest -q`
Expected : toute la suite au vert.

- [ ] **Step 8 : Commit**

```bash
git add app.py tests/test_envoi_ui.py
git commit -m "feat(ui): bouton Envoyer par courriel dans la saisie journalière

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Notes de vérification finale

- Lancer l'app localement et, avec une section `[graph]` valide dans `.streamlit/secrets.toml`, envoyer une journée de test pour confirmer la réception (vérification manuelle hors pytest — nécessite les prérequis Azure).
- Confirmer que `view_export` télécharge désormais un classeur **rempli** (une feuille par jour rempli).
