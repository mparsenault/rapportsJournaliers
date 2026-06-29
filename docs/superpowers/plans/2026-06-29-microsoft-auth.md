# Authentification Microsoft (Entra ID) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Réserver l'app Streamlit Rapports Journaliers Ondel aux comptes du tenant Microsoft ELEM, et utiliser l'identité connectée (responsable verrouillé, affichage utilisateur + déconnexion, traçage de l'auteur).

**Architecture:** Authentification OIDC native de Streamlit (`st.user` / `st.login` / `st.logout`) branchée sur Microsoft Entra ID en mono-tenant via `server_metadata_url`. Un portail dans `main()` exige la connexion avant tout rendu. L'identité (`st.user`) est lue par un helper pur `current_user()` réutilisé par l'affichage, le verrouillage du responsable, le traçage `saved_by` et l'estampille d'export.

**Tech Stack:** Python, Streamlit 1.50, Authlib (auth native), SQLAlchemy + Postgres (Neon), openpyxl, pytest.

## Global Constraints

- Streamlit `>=1.42` requis pour l'auth native ; l'app tourne en `1.50` — OK, ne pas downgrader.
- Nouvelle dépendance unique : `Authlib>=1.3.2`. Aucune librairie d'auth maison.
- Mono-tenant : `server_metadata_url` pointe sur l'autorité Entra du tenant ELEM (`.../login.microsoftonline.com/<tenant_id>/v2.0/...`) — seuls les comptes ELEM peuvent se connecter.
- Secrets dans la section `[auth]` de `.streamlit/secrets.toml` (gitignored) ; `secrets.toml.example` documente les clés **sans valeurs**.
- Les tests touchant Postgres réel ne sont pas reproductibles localement (cf. docstring de `tests/test_reports.py`) : couvrir la BD via assertions sur les chaînes DDL et signatures ; le portail/login relève de la vérification manuelle.
- Migrations BD idempotentes (`alter table ... add column if not exists ...`) ajoutées à `reports._DDL_STATEMENTS`, suivant le motif existant.
- Tout le texte d'UI reste en français.

---

## File Structure

- `requirements.txt` — ajout de `Authlib>=1.3.2`.
- `.streamlit/secrets.toml.example` — ajout de la section `[auth]` (clés sans valeurs).
- `README.md` — section « Authentification Microsoft » (prérequis Azure + secrets).
- `app.py` — helper `current_user()`, portail d'accès dans `main()`, affichage utilisateur + déconnexion dans l'en-tête, verrouillage du responsable, passage de `saved_by`, estampille d'export.
- `reports.py` — migration `saved_by` + paramètre `saved_by` dans `save_report`.
- `tests/test_auth.py` — tests du helper `current_user()`.
- `tests/test_reports.py` — test de la migration `saved_by`.

---

### Task 1: Dépendance + secrets + documentation Azure

**Files:**
- Modify: `requirements.txt`
- Modify: `.streamlit/secrets.toml.example`
- Modify: `README.md`

**Interfaces:**
- Consumes: rien.
- Produces: dépendance `Authlib` installable ; modèle de secrets `[auth]` documenté pour les tâches suivantes.

- [ ] **Step 1: Ajouter Authlib aux dépendances**

Ajouter cette ligne à `requirements.txt` (après `pytest>=7.0`) :

```
Authlib>=1.3.2
```

- [ ] **Step 2: Installer la dépendance**

Run: `.venv/bin/pip install -r requirements.txt`
Expected: `Authlib` installé sans erreur.

- [ ] **Step 3: Documenter les clés `[auth]` dans l'exemple de secrets**

Ajouter à la fin de `.streamlit/secrets.toml.example` :

```toml

# Authentification Microsoft Entra ID (OIDC natif Streamlit).
# Voir README « Authentification Microsoft » pour obtenir ces valeurs.
[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = ""   # chaîne aléatoire forte (ex. python -c "import secrets;print(secrets.token_urlsafe(48))")
client_id = ""
client_secret = ""
server_metadata_url = "https://login.microsoftonline.com/<tenant_id>/v2.0/.well-known/openid-configuration"
```

- [ ] **Step 4: Documenter la marche à suivre Azure dans le README**

Ajouter cette section au `README.md` (après la section « Base de données ») :

```markdown
## Authentification Microsoft

L'accès est réservé aux comptes du tenant Microsoft ELEM via l'authentification
OIDC native de Streamlit branchée sur Microsoft Entra ID (mono-tenant).

### Enregistrer l'application dans Entra ID (admin)

1. Portail Azure → **Microsoft Entra ID → App registrations → New registration**.
2. **Redirect URI** (plateforme *Web*) :
   - `http://localhost:8501/oauth2callback` (développement)
   - `https://<ton-app>.streamlit.app/oauth2callback` (production)
3. Noter le **Application (client) ID** et le **Directory (tenant) ID**.
4. **Certificates & secrets → New client secret** : créer un secret, copier sa
   valeur (noter la date d'expiration pour la rotation).

### Configurer les secrets

- En local : copier les valeurs dans la section `[auth]` de
  `.streamlit/secrets.toml` (voir `secrets.toml.example`). Générer le
  `cookie_secret` avec `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- En production (Streamlit Community Cloud) : saisir les mêmes clés dans
  **Settings → Secrets**, avec `redirect_uri` pointant sur l'URL `.streamlit.app`.
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .streamlit/secrets.toml.example README.md
git commit -m "build: dépendance Authlib + secrets/docs auth Microsoft"
```

---

### Task 2: Helper `current_user()`

**Files:**
- Modify: `app.py` (ajouter le helper près des autres helpers de state, après `init_state`)
- Test: `tests/test_auth.py` (créer)

**Interfaces:**
- Consumes: `st.user` (objet Streamlit ; attributs `is_logged_in`, `name`, `email`).
- Produces: `current_user() -> dict` renvoyant `{"name": str, "email": str}`. Renvoie des chaînes vides si non connecté ou attributs absents. Utilisé par les tâches 3, 5 et 6.

- [ ] **Step 1: Écrire le test qui échoue**

Créer `tests/test_auth.py` :

```python
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
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `.venv/bin/python -m pytest tests/test_auth.py -v`
Expected: FAIL — `AttributeError: module 'app' has no attribute 'current_user'`.

- [ ] **Step 3: Implémenter le helper**

Ajouter dans `app.py`, juste après la fonction `init_state()` :

```python
def current_user():
    """Identité connectée : {"name", "email"}. Chaînes vides si non connecté."""
    user = getattr(st, "user", None)
    if user is None or not getattr(user, "is_logged_in", False):
        return {"name": "", "email": ""}
    return {
        "name": getattr(user, "name", "") or "",
        "email": getattr(user, "email", "") or "",
    }
```

- [ ] **Step 4: Lancer le test pour vérifier le succès**

Run: `.venv/bin/python -m pytest tests/test_auth.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_auth.py
git commit -m "feat: helper current_user() pour l'identité connectée"
```

---

### Task 3: Portail d'accès + en-tête (connexion / déconnexion)

**Files:**
- Modify: `app.py` (fonction `main()`, ~ligne 1448 ; bloc en-tête `ondel_header`)

**Interfaces:**
- Consumes: `current_user()` (Task 2), `st.user.is_logged_in`, `st.login()`, `st.logout()`.
- Produces: garde d'accès — aucun contenu de l'app n'est rendu tant que l'utilisateur n'est pas connecté.

**Note:** cette tâche est de l'intégration Streamlit (login OAuth réel) ; elle n'est pas couverte par les tests unitaires et se vérifie manuellement (Step 4).

- [ ] **Step 1: Ajouter le portail en tête de `main()`**

Dans `app.py`, au tout début de `main()` — juste après `st.set_page_config(...)` et **avant** `init_state()` — insérer :

```python
    if not st.user.is_logged_in:
        st.markdown(get_css(), unsafe_allow_html=True)
        uri = _logo_data_uri()
        with st.container(key="ondel_header"):
            _, c, _ = st.columns([1, 4, 1], vertical_alignment="center")
            c.markdown('<div class="ondel-title">RAPPORTS JOURNALIERS</div>',
                       unsafe_allow_html=True)
        st.markdown(
            f'<div style="text-align:center;margin:2rem 0;">'
            f'<img src="{uri}" style="height:64px;"></div>',
            unsafe_allow_html=True)
        st.info("Accès réservé aux employés ELEM. Connectez-vous avec votre compte Microsoft.")
        _, c, _ = st.columns([1, 2, 1])
        if c.button("🔑 Se connecter avec Microsoft", use_container_width=True,
                    type="primary"):
            st.login()
        st.stop()
```

- [ ] **Step 2: Afficher l'utilisateur + bouton déconnexion dans l'en-tête**

Dans `main()`, dans le bloc `with st.container(key="ondel_header"):`, remplacer la colonne droite existante :

```python
        b_r.markdown(f'<div class="logo-wrap"><span class="logo-chip"><img src="{uri}"></span></div>',
                     unsafe_allow_html=True)
```

par :

```python
        with b_r:
            user = current_user()
            st.markdown(
                f'<div class="logo-wrap"><span class="logo-chip"><img src="{uri}"></span></div>',
                unsafe_allow_html=True)
            st.caption(f"👤 {user['name'] or user['email']}")
            if st.button("Se déconnecter", key="hdr_logout", use_container_width=True):
                st.logout()
```

- [ ] **Step 3: Vérifier la non-régression des tests existants**

Run: `.venv/bin/python -m pytest -q`
Expected: tous les tests passent (le portail n'est pas couvert mais ne casse rien).

- [ ] **Step 4: Vérification manuelle**

Configurer `.streamlit/secrets.toml` (`[auth]`, Task 1), puis :
Run: `.venv/bin/streamlit run app.py`
Attendu :
- À l'ouverture, écran de connexion Ondel avec le bouton « Se connecter avec Microsoft ».
- Le bouton redirige vers Microsoft ; après login avec un compte ELEM, l'app s'affiche.
- L'en-tête montre le nom de l'utilisateur et un bouton « Se déconnecter » qui ramène à l'écran de connexion.

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: portail de connexion Microsoft + affichage utilisateur/déconnexion"
```

---

### Task 4: Colonne `saved_by` et paramètre dans `save_report`

**Files:**
- Modify: `reports.py` (`_DDL_STATEMENTS` ~ligne 28 ; `save_report` ~ligne 218 et l'upsert en-tête ~ligne 236-265)
- Test: `tests/test_reports.py`

**Interfaces:**
- Consumes: rien de neuf.
- Produces: `save_report(projet, config, jours, jours_order, saved_by=None)` — `saved_by` (str|None) persisté dans `reports.saved_by`. Le paramètre est **optionnel** pour ne pas casser les appels existants.

- [ ] **Step 1: Écrire le test qui échoue (migration présente)**

Ajouter dans `tests/test_reports.py` :

```python
def test_ddl_has_saved_by_migration():
    ddl = " ".join(reports._DDL_STATEMENTS)
    assert "reports add column if not exists saved_by" in ddl


def test_save_report_accepts_saved_by_param():
    import inspect
    sig = inspect.signature(reports.save_report)
    assert "saved_by" in sig.parameters
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `.venv/bin/python -m pytest tests/test_reports.py -k "saved_by" -v`
Expected: FAIL (migration absente, paramètre absent).

- [ ] **Step 3: Ajouter la migration idempotente**

Dans `reports.py`, ajouter à la liste `_DDL_STATEMENTS` (après les autres `alter table ... add column if not exists`) :

```python
    "alter table reports add column if not exists saved_by text",
```

- [ ] **Step 4: Ajouter le paramètre et le persister**

Dans `reports.py`, modifier la signature de `save_report` :

```python
def save_report(projet, config, jours, jours_order, saved_by=None):
```

Dans l'upsert de l'en-tête, ajouter la colonne `saved_by` :

- Liste des colonnes `insert into reports (...)` : ajouter `saved_by` avant `updated_at` →
  `(id_project, project_no, week_start, responsable, quart, adresse, lat, lon, saved_by, updated_at)`
- Liste `values (...)` : ajouter `:saved_by` avant `now()` →
  `(:idp, :no, :wk, :resp, :quart, :addr, :lat, :lon, :saved_by, now())`
- Bloc `do update set` : ajouter `saved_by = excluded.saved_by,` (avant `updated_at = now()`)
- Dict de paramètres : ajouter `"saved_by": saved_by or None,`

- [ ] **Step 5: Lancer les tests pour vérifier le succès**

Run: `.venv/bin/python -m pytest tests/test_reports.py -v`
Expected: PASS (incluant les 2 nouveaux tests ; les tests existants `test_save_report_*` passent toujours car `saved_by` est optionnel).

- [ ] **Step 6: Commit**

```bash
git add reports.py tests/test_reports.py
git commit -m "feat: colonne saved_by + paramètre saved_by dans save_report"
```

---

### Task 5: Verrouiller le responsable + tracer l'auteur (câblage app)

**Files:**
- Modify: `app.py` (`save_report_from_state` ~ligne 192 ; `view_day_entry` ~ligne 1260, après résolution de `quart`)

**Interfaces:**
- Consumes: `current_user()` (Task 2), `reports.save_report(..., saved_by=...)` (Task 4).
- Produces: à chaque sauvegarde, le `responsable` de tous les quarts vaut le nom de l'utilisateur connecté et `reports.saved_by` vaut son email. Le responsable est affiché en lecture seule dans la vue de saisie.

- [ ] **Step 1: Stamper responsable + saved_by à la sauvegarde**

Dans `app.py`, remplacer le corps de `save_report_from_state()` :

```python
def save_report_from_state():
    """Persiste le state courant vers Neon. Renvoie (ok, message)."""
    try:
        user = current_user()
        # Responsable verrouillé sur l'utilisateur connecté pour tous les quarts.
        for day in st.session_state.jours.values():
            for quart in day.get("quarts", {}).values():
                quart["responsable"] = user["name"]
        reports.save_report(
            st.session_state.projet, {},
            st.session_state.jours, JOURS,
            saved_by=user["email"],
        )
        st.session_state.dirty = False
        return True, "Rapport enregistré ✓"
    except Exception as exc:  # noqa: BLE001
        return False, f"Échec de l'enregistrement : {exc}"
```

- [ ] **Step 2: Afficher le responsable en lecture seule dans la vue de saisie**

Dans `app.py`, dans `view_day_entry()`, juste après `quart = day["quarts"][quart_name]` (~ligne 1262), insérer :

```python
    st.caption(f"👤 Responsable : {current_user()['name'] or '—'}")
```

- [ ] **Step 3: Vérifier la non-régression**

Run: `.venv/bin/python -m pytest -q`
Expected: tous les tests passent.

- [ ] **Step 4: Vérification manuelle**

Run: `.venv/bin/streamlit run app.py` (connecté avec un compte ELEM)
Attendu :
- La vue de saisie affiche « 👤 Responsable : <nom connecté> » (non éditable).
- Après « Enregistrer », la BD `reports.saved_by` contient l'email et `report_quarts.responsable` le nom connecté.

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: responsable verrouillé sur l'utilisateur connecté + traçage saved_by"
```

---

### Task 6: Estampille de l'exportateur dans l'Excel

**Files:**
- Modify: `app.py` (`_build_synthese` ~ligne 474, et son appel dans `build_workbook` ~ligne 481-485)

**Interfaces:**
- Consumes: `current_user()` (Task 2).
- Produces: la feuille « Synthèse » du `.xlsx` exporté porte une cellule de pied de page « Exporté par <nom> ».

- [ ] **Step 1: Passer l'exportateur à `_build_synthese`**

Dans `app.py`, modifier la signature :

```python
def _build_synthese(ws, proj, legacy_jours, exported_by=""):
```

et l'appel dans `build_workbook()` :

```python
    _build_synthese(wb.active, st.session_state.projet, legacy, current_user()["name"])
```

- [ ] **Step 2: Écrire l'estampille en pied de la Synthèse**

À la fin de `_build_synthese` (avant tout `return`), ajouter :

```python
    last = ws.max_row + 2
    cell = ws.cell(row=last, column=1, value=f"Exporté par {exported_by or '—'}")
    cell.font = Font(name="Calibri", size=8, italic=True, color="6B7B7E")
```

- [ ] **Step 3: Vérifier la non-régression**

Run: `.venv/bin/python -m pytest -q`
Expected: tous les tests passent.

- [ ] **Step 4: Vérification manuelle**

Run: `.venv/bin/streamlit run app.py` → vue Export → télécharger le `.xlsx`.
Attendu : la feuille « Synthèse » contient en bas « Exporté par <nom connecté> ».

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: estampille de l'exportateur dans l'export Excel"
```

---

## Notes d'exécution

- Les tâches 1, 2 et 4 sont entièrement testables/automatisables. Les tâches 3, 5 et 6 ont une part d'intégration Streamlit/Excel vérifiée manuellement (le dépôt suit déjà cette convention : pas de tests unitaires sur la BD réelle ni l'UI).
- Pré-requis pour les vérifications manuelles : une app Entra enregistrée et `.streamlit/secrets.toml` rempli (Task 1).
