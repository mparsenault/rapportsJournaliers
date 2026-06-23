# Sélection projets/activités depuis la BD — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer la saisie libre du projet et la liste statique d'activités par une sélection issue d'un snapshot Postgres alimenté périodiquement depuis SQL Server (Maestro/Qualifab).

**Architecture:** Un script de sync autonome copie le résultat de la requête SQL Server vers Postgres (rafraîchissement complet transactionnel). L'app Streamlit lit projets/activités depuis Postgres via une couche d'accès (`data_source.py`) et expose un menu déroulant projet → activités filtrées. Personnel/véhicules/autres restent dans `refdata.json`.

**Tech Stack:** Python, Streamlit (≥1.30), pandas, SQLAlchemy + psycopg2 (lecture app), pymssql + psycopg2 (sync), pytest, openpyxl (export inchangé).

## Global Constraints

- Base de code = **working tree** non commité d'`app.py` (réécriture « UX Dashboard tablette » : `view_dashboard` / `view_day_entry` / `view_reference`, `_legacy_day`, `build_workbook()` lisant `session_state`). NE PAS restaurer le HEAD.
- `streamlit>=1.30`, `pandas>=2.0`, `openpyxl>=3.1`, `Pillow>=10.0`, `pytest>=7.0`.
- Format de libellé d'activité conservé : `"CODE - Description"` (ou `"CODE"` si description vide) — l'export Excel en dépend.
- L'export Excel reste **inchangé** (stub « Synthèse » du working tree) ; tests d'export = smoke uniquement.
- Le personnel, les véhicules et les « autres projets » restent dans `refdata.json` (la requête ne les couvre pas).
- Connexion Postgres app via `st.connection("postgres", type="sql")` ; config dans `.streamlit/secrets.toml` (gitignored). Toute erreur de lecture → liste vide + message, jamais de plantage.
- Requête source EXACTE (ne pas modifier les filtres) :
  ```sql
  select p.ID_Project, p.Project_No, a.ActivityCode, a.Description
  from Projects.Projects p
  left join Projects.Activities a on p.ID_Project = a.ID_Project
  where p.ID_Company = 1 and p.transfer2Maestro = 1
    and p.maestroProjNo <> '' and p.ID_Tree <> -1
  ```
- Commandes de test : `.venv/bin/python -m pytest -q`.

---

### Task 1 : Branche de travail + baseline du working tree

Préserve la réécriture non commitée avant toute modification, pour des diffs propres ensuite.

**Files:**
- Modify (commit) : `app.py` (working tree, déjà modifié, non commité)

**Interfaces:**
- Consumes : rien.
- Produces : branche `feat/db-projets-activites` avec un commit baseline ; `app.py` du working tree préservé tel quel.

- [ ] **Step 1 : Créer la branche**

Run : `git switch -c feat/db-projets-activites`
Expected : `Switched to a new branch 'feat/db-projets-activites'`

- [ ] **Step 2 : Vérifier l'état**

Run : `git status --short`
Expected : une seule ligne ` M app.py` (le reste est déjà commité).

- [ ] **Step 3 : Commit baseline**

```bash
git add app.py
git commit -m "chore: baseline réécriture UX Dashboard tablette (working tree)"
```

- [ ] **Step 4 : Vérifier l'état de départ des tests (référence)**

Run : `.venv/bin/python -m pytest -q 2>&1 | tail -3`
Expected : `15 failed, 5 passed` (tests hérités du HEAD, obsolètes — corrigés à la Task 2).

---

### Task 2 : Re-baseline des tests existants vers l'API du working tree (sans BD)

Remet la suite au vert contre l'app actuelle, avant d'ajouter la BD. On remplace les tests modèle obsolètes et on réécrit les tests UI pour les vues du working tree (parties indépendantes de la BD ; les tests projet/activités viendront avec les tâches BD).

**Files:**
- Modify : `tests/test_model.py`
- Modify : `tests/test_ui.py`

**Interfaces:**
- Consumes : `app._empty_day`, `app._day_total`, `app._day_columns`, `app._day_grid_df`, `app._grid_df_to_day(edited, day)`, `app._legacy_day(config, day) -> dict`, `app.HOUR_KEYS`, `app.JOURS` ; vues routées par `st.session_state.view` ∈ {`dashboard`,`config`,`reference`,`export`,`day_entry`}.
- Produces : suite verte.

- [ ] **Step 1 : Remplacer les tests modèle obsolètes**

Dans `tests/test_model.py`, SUPPRIMER `test_default_config_shape`, `test_roster_order_and_types`, `test_grid_df_to_day_roundtrip`, `test_day_to_legacy_maps_labels_to_keys`, `test_build_workbook_with_new_model`, `test_empty_and_weather_only_days_excluded`, `test_full_export_two_days` (et les imports `load_workbook`/`BytesIO` devenus inutiles). CONSERVER `test_empty_day_shape`, `test_day_total`, `test_day_columns`, `test_day_grid_df` et les helpers `_sample_config`/`_sample_day`. AJOUTER :

```python
def test_grid_df_to_day_roundtrip():
    config, day = _sample_config(), _sample_day()
    df = app._day_grid_df(config, day)
    df.loc[df["Ressource"] == "Roy", "960"] = 5.0
    app._grid_df_to_day(df, day)          # signature working tree : (edited, day)
    assert day["heures"]["Roy"] == {"960": 5.0}
    assert day["heures"]["Mathis"]["Excavation"] == 4.0
    assert day["prime"]["Mathis"] == 2.0
    assert day["commentaire_ligne"]["Mathis"] == "test"


def test_legacy_day_maps_labels_to_keys():
    leg = app._legacy_day(_sample_config(), _sample_day())   # renvoie un dict
    assert leg["headers"]["h0"] == "960"
    assert leg["headers"]["h1"] == "Excavation"
    assert leg["headers"]["a0"] == "P-77"
    pers, equip = leg["pers"], leg["equip"]
    for k in app.HOUR_KEYS:
        assert k in pers.columns and k in equip.columns
    # build_df du working tree inclut TOUT le roster (Roy sans données compris)
    assert list(pers["Nom"]) == ["Mathis", "Roy"]
    mathis = pers[pers["Nom"] == "Mathis"].iloc[0]
    assert mathis["h0"] == 8.0 and mathis["h1"] == 4.0 and mathis["a0"] == 2.0
    assert mathis["Prime"] == 2.0 and mathis["Commentaire"] == "test"
    assert list(equip["Véhicule"]) == ["Camion v1892"]
```

- [ ] **Step 2 : Réécrire `tests/test_ui.py` (UI indépendante de la BD)**

Remplacer TOUT le contenu de `tests/test_ui.py` par :

```python
import datetime

from streamlit.testing.v1 import AppTest


def _run():
    return AppTest.from_file("app.py", default_timeout=30).run()


def test_dashboard_is_default_view():
    at = _run()
    assert at.session_state["view"] == "dashboard"
    assert not at.exception


def test_navigation_to_config():
    at = _run()
    btn = [b for b in at.button if "Équipe" in b.label][0]
    btn.click().run()
    assert at.session_state["view"] == "config"


def test_navigation_to_reference():
    at = _run()
    btn = [b for b in at.button if "Références" in b.label][0]
    btn.click().run()
    assert at.session_state["view"] == "reference"


def test_config_roster_multiselects_present():
    at = _run()
    at.session_state["view"] = "config"
    at.run()
    labels = [m.label for m in at.multiselect]
    assert "Personnel" in labels and "Équipements" in labels


def test_setting_personnel_updates_config():
    at = _run()
    at.session_state["view"] = "config"
    at.run()
    pers = [m for m in at.multiselect if m.label == "Personnel"][0]
    opts = pers.options
    assert opts, "la liste de personnel de référence ne doit pas être vide"
    pers.set_value([opts[0]]).run()
    assert at.session_state["config"]["personnel"] == [opts[0]]


def test_export_view_generates_without_error():
    at = _run()
    at.session_state["view"] = "export"
    at.run()
    btns = [b for b in at.button if "Générer" in b.label]
    assert btns
    btns[0].click().run()
    assert not at.exception
```

- [ ] **Step 3 : Lancer toute la suite, vérifier le vert**

Run : `.venv/bin/python -m pytest -q 2>&1 | tail -3`
Expected : `0 failed` (tout passe).

- [ ] **Step 4 : Commit**

```bash
git add tests/test_model.py tests/test_ui.py
git commit -m "test: re-baseline des tests vers l'API du working tree"
```

---

### Task 3 : Couche d'accès `data_source.py` + dépendances app + config secrets

**Files:**
- Create : `data_source.py`
- Create : `tests/test_data_source.py`
- Modify : `requirements.txt`
- Create : `.streamlit/secrets.toml.example`
- Modify : `.gitignore`

**Interfaces:**
- Consumes : `st.connection("postgres", type="sql").query(...)`.
- Produces :
  - `activity_label(code, desc) -> str`
  - `filter_known(selected, options) -> list`
  - `projects_from_df(df) -> list[(int, str)]`
  - `activity_labels_from_df(df) -> list[str]`
  - `_connection()` (point d'injection pour tests)
  - `get_projects() -> list[(int, str)]`
  - `get_activities(id_project) -> list[str]`

- [ ] **Step 1 : Écrire les tests (échouent : module absent)**

Créer `tests/test_data_source.py` :

```python
import pandas as pd

import data_source


def test_activity_label_with_description():
    assert data_source.activity_label("C01", "Excavation") == "C01 - Excavation"


def test_activity_label_without_description():
    assert data_source.activity_label("C01", "") == "C01"
    assert data_source.activity_label("C01", None) == "C01"


def test_filter_known_keeps_order_and_drops_unknown():
    assert data_source.filter_known(["b", "x", "a"], ["a", "b", "c"]) == ["b", "a"]


def test_projects_from_df():
    df = pd.DataFrame({"id_project": [2, 1], "project_no": ["P-2", "P-1"]})
    assert data_source.projects_from_df(df) == [(2, "P-2"), (1, "P-1")]


def test_activity_labels_from_df():
    df = pd.DataFrame({"activity_code": ["C01", "C02"], "description": ["A", ""]})
    assert data_source.activity_labels_from_df(df) == ["C01 - A", "C02"]


def test_get_activities_none_returns_empty():
    assert data_source.get_activities(None) == []


class _FakeConn:
    def __init__(self, df):
        self._df = df

    def query(self, sql, **kwargs):
        return self._df


def test_get_projects_happy(monkeypatch):
    df = pd.DataFrame({"id_project": [1], "project_no": ["P-1"]})
    monkeypatch.setattr(data_source, "_connection", lambda: _FakeConn(df))
    assert data_source.get_projects() == [(1, "P-1")]


def test_get_projects_unreachable_returns_empty(monkeypatch):
    def boom():
        raise RuntimeError("no db")
    monkeypatch.setattr(data_source, "_connection", boom)
    assert data_source.get_projects() == []


def test_get_activities_happy(monkeypatch):
    df = pd.DataFrame({"activity_code": ["C01"], "description": ["X"]})
    monkeypatch.setattr(data_source, "_connection", lambda: _FakeConn(df))
    assert data_source.get_activities(1) == ["C01 - X"]
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv/bin/python -m pytest tests/test_data_source.py -q 2>&1 | tail -5`
Expected : FAIL (`ModuleNotFoundError: No module named 'data_source'`).

- [ ] **Step 3 : Implémenter `data_source.py`**

```python
"""Accès aux données projets/activités, lues depuis Postgres (cloud).

Les projets et activités proviennent d'un snapshot Postgres alimenté
périodiquement par sync_projects.py (source : SQL Server / Maestro). Le
personnel, les véhicules et les « autres projets » restent dans refdata.json.
"""
import streamlit as st

_PROJECTS_SQL = "select id_project, project_no from projects order by project_no"
_ACTIVITIES_SQL = (
    "select activity_code, description from activities "
    "where id_project = :pid order by activity_code"
)


def activity_label(code, desc):
    """Libellé d'activité : 'CODE - Description' (ou 'CODE' si description vide)."""
    code = (code or "").strip()
    desc = (desc or "").strip()
    return f"{code} - {desc}" if desc else code


def filter_known(selected, options):
    """Retire de `selected` les valeurs absentes de `options` (ordre préservé)."""
    allowed = set(options)
    return [s for s in selected if s in allowed]


def projects_from_df(df):
    """DataFrame(id_project, project_no) -> list[(int, str)]."""
    return [(int(r.id_project), str(r.project_no)) for r in df.itertuples(index=False)]


def activity_labels_from_df(df):
    """DataFrame(activity_code, description) -> list[str] de libellés."""
    return [activity_label(r.activity_code, r.description)
            for r in df.itertuples(index=False)]


def _connection():
    return st.connection("postgres", type="sql")


def get_projects():
    """Liste (id_project, project_no) triée. [] si la base est injoignable."""
    try:
        df = _connection().query(_PROJECTS_SQL, ttl=600)
        return projects_from_df(df)
    except Exception:
        return []


def get_activities(id_project):
    """Libellés d'activités du projet, triés. [] si aucun / base injoignable."""
    if id_project is None:
        return []
    try:
        df = _connection().query(_ACTIVITIES_SQL, params={"pid": int(id_project)}, ttl=600)
        return activity_labels_from_df(df)
    except Exception:
        return []
```

- [ ] **Step 4 : Lancer, vérifier le vert**

Run : `.venv/bin/python -m pytest tests/test_data_source.py -q 2>&1 | tail -3`
Expected : `9 passed`.

- [ ] **Step 5 : Déclarer les dépendances et la config**

Remplacer `requirements.txt` par :

```
streamlit>=1.30
openpyxl>=3.1
pandas>=2.0
Pillow>=10.0
SQLAlchemy>=2.0
psycopg2-binary>=2.9
pytest>=7.0
```

Créer `.streamlit/secrets.toml.example` :

```toml
# Copier vers .streamlit/secrets.toml (gitignored) puis remplir.
[connections.postgres]
url = "postgresql+psycopg2://user:pass@host:5432/dbname"
```

Ajouter à la fin de `.gitignore` :

```
.streamlit/secrets.toml
.env
```

- [ ] **Step 6 : Vérifier que toute la suite reste verte**

Run : `.venv/bin/python -m pytest -q 2>&1 | tail -3`
Expected : `0 failed`.

- [ ] **Step 7 : Commit**

```bash
git add data_source.py tests/test_data_source.py requirements.txt .streamlit/secrets.toml.example .gitignore
git commit -m "feat: couche d'accès Postgres pour projets/activités"
```

---

### Task 4 : Script de sync `sync_projects.py` + schéma + deps de sync

**Files:**
- Create : `sync_projects.py`
- Create : `db/schema.sql`
- Create : `requirements-sync.txt`
- Create : `tests/test_sync.py`

**Interfaces:**
- Consumes : variables d'env `SQLSERVER_HOST/DB/USER/PASSWORD`, `POSTGRES_URL` ; `pymssql`, `psycopg2` (importés à l'intérieur des fonctions I/O — pas requis pour tester `rows_to_payload`).
- Produces : `sync_projects.rows_to_payload(rows) -> (projects, activities)` ; `fetch_source_rows()` ; `write_payload(pg_url, projects, activities)` ; `main()`.

- [ ] **Step 1 : Écrire les tests (échouent : module absent)**

Créer `tests/test_sync.py` :

```python
import sync_projects


def test_rows_to_payload_dedups_projects():
    rows = [
        (1, "P-1", "C01", "A"),
        (1, "P-1", "C02", "B"),
        (2, "P-2", "C03", "C"),
    ]
    projects, activities = sync_projects.rows_to_payload(rows)
    assert projects == [(1, "P-1"), (2, "P-2")]
    assert activities == [(1, "C01", "A"), (1, "C02", "B"), (2, "C03", "C")]


def test_rows_to_payload_skips_null_activity():
    projects, activities = sync_projects.rows_to_payload([(3, "P-3", None, None)])
    assert projects == [(3, "P-3")]
    assert activities == []


def test_rows_to_payload_skips_blank_activity_code():
    projects, activities = sync_projects.rows_to_payload([(4, "P-4", "   ", "desc")])
    assert projects == [(4, "P-4")]
    assert activities == []


def test_rows_to_payload_empty():
    assert sync_projects.rows_to_payload([]) == ([], [])
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv/bin/python -m pytest tests/test_sync.py -q 2>&1 | tail -5`
Expected : FAIL (`ModuleNotFoundError: No module named 'sync_projects'`).

- [ ] **Step 3 : Créer `db/schema.sql`**

```sql
create table if not exists projects (
    id_project integer primary key,
    project_no text not null
);

create table if not exists activities (
    id_project    integer not null references projects(id_project) on delete cascade,
    activity_code text not null,
    description   text,
    primary key (id_project, activity_code)
);

create index if not exists idx_activities_project on activities(id_project);
```

- [ ] **Step 4 : Implémenter `sync_projects.py`**

```python
"""Sync projets/activités : SQL Server (Maestro/Qualifab) -> Postgres (cloud).

Rafraîchissement complet dans une transaction unique. À planifier (cron /
Azure Function / Tâche planifiée) LÀ où SQL Server est joignable.

Variables d'environnement requises :
  SQLSERVER_HOST, SQLSERVER_DB, SQLSERVER_USER, SQLSERVER_PASSWORD
  POSTGRES_URL   (forme libpq : postgresql://user:pass@host:5432/dbname)
"""
import os
import sys

SOURCE_QUERY = """
select p.ID_Project, p.Project_No, a.ActivityCode, a.Description
from Projects.Projects p
left join Projects.Activities a
  on p.ID_Project = a.ID_Project
where p.ID_Company = 1
  and p.transfer2Maestro = 1
  and p.maestroProjNo <> ''
  and p.ID_Tree <> -1
"""

SCHEMA_DDL = """
create table if not exists projects (
    id_project integer primary key,
    project_no text not null
);
create table if not exists activities (
    id_project    integer not null references projects(id_project) on delete cascade,
    activity_code text not null,
    description   text,
    primary key (id_project, activity_code)
);
create index if not exists idx_activities_project on activities(id_project);
"""


def rows_to_payload(rows):
    """rows: itérable de (id_project, project_no, activity_code, description).

    Renvoie (projects, activities) :
      projects   : list[(id_project, project_no)] dédupliqué, trié par id_project
      activities : list[(id_project, activity_code, description)] (code non vide)
    """
    projects = {}
    activities = []
    for id_project, project_no, code, desc in rows:
        projects.setdefault(id_project, project_no)
        if code is not None and str(code).strip() != "":
            activities.append((id_project, code, desc))
    return sorted(projects.items()), activities


def fetch_source_rows():
    import pymssql
    conn = pymssql.connect(
        server=os.environ["SQLSERVER_HOST"],
        user=os.environ["SQLSERVER_USER"],
        password=os.environ["SQLSERVER_PASSWORD"],
        database=os.environ["SQLSERVER_DB"],
    )
    try:
        cur = conn.cursor()
        cur.execute(SOURCE_QUERY)
        return cur.fetchall()
    finally:
        conn.close()


def write_payload(pg_url, projects, activities):
    import psycopg2
    conn = psycopg2.connect(pg_url)
    try:
        cur = conn.cursor()
        cur.execute(SCHEMA_DDL)
        cur.execute("delete from activities;")
        cur.execute("delete from projects;")
        if projects:
            cur.executemany(
                "insert into projects (id_project, project_no) values (%s, %s)",
                projects,
            )
        if activities:
            cur.executemany(
                "insert into activities (id_project, activity_code, description) "
                "values (%s, %s, %s)",
                activities,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    rows = fetch_source_rows()
    projects, activities = rows_to_payload(rows)
    write_payload(os.environ["POSTGRES_URL"], projects, activities)
    print(f"Sync OK : {len(projects)} projets, {len(activities)} activités")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"Sync FAILED : {exc}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 5 : Créer `requirements-sync.txt`**

```
pymssql>=2.2
psycopg2-binary>=2.9
```

- [ ] **Step 6 : Lancer, vérifier le vert**

Run : `.venv/bin/python -m pytest tests/test_sync.py -q 2>&1 | tail -3`
Expected : `4 passed`.

- [ ] **Step 7 : Commit**

```bash
git add sync_projects.py db/schema.sql requirements-sync.txt tests/test_sync.py
git commit -m "feat: script de sync SQL Server -> Postgres (rafraîchissement complet)"
```

---

### Task 5 : Menu déroulant projet dans le tableau de bord

**Files:**
- Modify : `app.py` (import `data_source` ; `init_state` ; `view_dashboard`)
- Modify : `tests/test_ui.py`

**Interfaces:**
- Consumes : `data_source.get_projects()`.
- Produces : `st.session_state.projet["id_project"]` (int | None) et `["no"]` (str) renseignés par le menu déroulant.

- [ ] **Step 1 : Écrire les tests (échouent : pas encore de selectbox « Projet »)**

Ajouter à `tests/test_ui.py` :

```python
def test_project_selectbox_lists_db_projects(monkeypatch):
    import data_source
    monkeypatch.setattr(data_source, "get_projects", lambda: [(1, "P-100"), (2, "P-200")])
    at = _run()
    sb = [s for s in at.selectbox if s.label == "Projet"][0]
    assert list(sb.options) == ["P-100", "P-200"]
    assert not at.exception


def test_selecting_project_sets_id(monkeypatch):
    import data_source
    monkeypatch.setattr(data_source, "get_projects", lambda: [(1, "P-100"), (2, "P-200")])
    at = _run()
    sb = [s for s in at.selectbox if s.label == "Projet"][0]
    sb.set_value("P-200").run()
    assert at.session_state["projet"]["id_project"] == 2
    assert at.session_state["projet"]["no"] == "P-200"


def test_dashboard_shows_error_when_db_unreachable(monkeypatch):
    import data_source
    monkeypatch.setattr(data_source, "get_projects", lambda: [])
    at = _run()
    assert any("projets" in (e.value or "").lower() for e in at.error)
    assert not at.exception
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv/bin/python -m pytest tests/test_ui.py::test_project_selectbox_lists_db_projects -q 2>&1 | tail -5`
Expected : FAIL (aucun selectbox « Projet »).

- [ ] **Step 3 : Ajouter l'import `data_source` dans `app.py`**

Sous `import streamlit as st` (ligne ~15), ajouter une ligne :

```python
import data_source
```

- [ ] **Step 4 : Ajouter `id_project` à l'état initial**

Dans `init_state`, remplacer la ligne :

```python
        st.session_state.projet = {"no": "", "semaine": date.today(), "adresse": "", "lat": None, "lon": None}
```

par :

```python
        st.session_state.projet = {"no": "", "id_project": None, "semaine": date.today(), "adresse": "", "lat": None, "lon": None}
```

- [ ] **Step 5 : Remplacer le champ texte par un menu déroulant**

Dans `view_dashboard`, remplacer :

```python
        proj["no"] = c1.text_input("Numéro de Projet", proj["no"])
```

par :

```python
        projects = data_source.get_projects()
        if not projects:
            c1.error("Impossible de charger les projets depuis la base.")
            proj["id_project"] = None
        else:
            labels = [no for _pid, no in projects]
            id_by_no = {no: pid for pid, no in projects}
            index = labels.index(proj["no"]) if proj["no"] in labels else None
            sel = c1.selectbox("Projet", labels, index=index,
                               placeholder="Choisir un projet…")
            proj["no"] = sel or ""
            proj["id_project"] = id_by_no.get(sel)
```

- [ ] **Step 6 : Lancer les tests UI, vérifier le vert**

Run : `.venv/bin/python -m pytest tests/test_ui.py -q 2>&1 | tail -3`
Expected : `0 failed`.

- [ ] **Step 7 : Commit**

```bash
git add app.py tests/test_ui.py
git commit -m "feat: menu déroulant projet alimenté par la base"
```

---

### Task 6 : Activités du jour filtrées par le projet sélectionné

**Files:**
- Modify : `app.py` (`view_day_entry`)
- Modify : `tests/test_ui.py`

**Interfaces:**
- Consumes : `data_source.get_activities(id_project)`, `data_source.filter_known(...)`, `st.session_state.projet["id_project"]`.
- Produces : multiselect « Activités » dont les options sont celles du projet courant.

- [ ] **Step 1 : Écrire le test (échoue : activités encore lues depuis refdata)**

Ajouter à `tests/test_ui.py` :

```python
def test_day_activities_come_from_db(monkeypatch):
    import data_source
    monkeypatch.setattr(data_source, "get_projects", lambda: [(1, "P-100")])
    monkeypatch.setattr(data_source, "get_activities",
                        lambda pid: ["C01 - Test"] if pid == 1 else [])
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["projet"] = {"no": "P-100", "id_project": 1,
                                  "semaine": datetime.date(2026, 6, 7),
                                  "adresse": "", "lat": None, "lon": None}
    at.session_state["active_day"] = "Lundi"
    at.session_state["view"] = "day_entry"
    at.run()
    acts = [m for m in at.multiselect if m.label == "Activités"][0]
    assert list(acts.options) == ["C01 - Test"]
    assert not at.exception
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv/bin/python -m pytest tests/test_ui.py::test_day_activities_come_from_db -q 2>&1 | tail -5`
Expected : FAIL (options issues de `ref["activites"]`, pas de la BD).

- [ ] **Step 3 : Lire les activités depuis la BD**

Dans `view_day_entry`, remplacer :

```python
        day["activites"] = st.multiselect("Activités", st.session_state.ref["activites"], default=day["activites"])
```

par :

```python
        acts = data_source.get_activities(st.session_state.projet.get("id_project"))
        day["activites"] = st.multiselect(
            "Activités", acts,
            default=data_source.filter_known(day["activites"], acts))
```

(La ligne `day["autres"] = st.multiselect("Autres", st.session_state.ref["autres_projets"], ...)` reste inchangée.)

- [ ] **Step 4 : Lancer toute la suite, vérifier le vert**

Run : `.venv/bin/python -m pytest -q 2>&1 | tail -3`
Expected : `0 failed`.

- [ ] **Step 5 : Commit**

```bash
git add app.py tests/test_ui.py
git commit -m "feat: activités du jour filtrées par le projet (depuis la base)"
```

---

### Task 7 : Retrait de l'onglet « Activités » des Références

Les activités viennent désormais de la base : on retire leur édition dans `refdata.json`.

**Files:**
- Modify : `app.py` (`view_reference`)
- Modify : `tests/test_ui.py`

**Interfaces:**
- Consumes : rien de nouveau.
- Produces : page Références sans onglet/zone « Activités ».

- [ ] **Step 1 : Écrire le test (échoue : zone « activites » encore présente)**

Ajouter à `tests/test_ui.py` :

```python
def test_reference_has_no_activities_tab():
    at = _run()
    at.session_state["view"] = "reference"
    at.run()
    labels = [t.label for t in at.text_area]
    assert "Liste activites" not in labels
    assert "Liste personnel" in labels
    assert not at.exception
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv/bin/python -m pytest tests/test_ui.py::test_reference_has_no_activities_tab -q 2>&1 | tail -5`
Expected : FAIL (`"Liste activites"` encore présent).

- [ ] **Step 3 : Retirer « Activités » de `view_reference`**

Dans `view_reference`, remplacer :

```python
    tabs = st.tabs(["Personnel", "Véhicules", "Activités", "Autres"])
    keys = ["personnel", "vehicules", "activites", "autres_projets"]
```

par :

```python
    tabs = st.tabs(["Personnel", "Véhicules", "Autres"])
    keys = ["personnel", "vehicules", "autres_projets"]
```

- [ ] **Step 4 : Lancer toute la suite, vérifier le vert**

Run : `.venv/bin/python -m pytest -q 2>&1 | tail -3`
Expected : `0 failed`.

- [ ] **Step 5 : Commit**

```bash
git add app.py tests/test_ui.py
git commit -m "feat: retrait de l'onglet Activités des Références (vient de la base)"
```

---

### Task 8 : Vérification finale + documentation

**Files:**
- Modify : `README.md`

**Interfaces:**
- Consumes : tout ce qui précède.
- Produces : suite verte + README à jour.

- [ ] **Step 1 : Lancer toute la suite**

Run : `.venv/bin/python -m pytest -q 2>&1 | tail -3`
Expected : `0 failed`, total = anciens tests conservés + nouveaux (data_source 9, sync 4, UI BD 4).

- [ ] **Step 2 : Mettre à jour `README.md`**

Dans la section « Contenu du dossier » / « Fonctionnement », remplacer la mention de `refdata.json` comme source des activités par :

```markdown
- `data_source.py` — lecture des **projets** et **activités** depuis Postgres
  (cloud), alimenté par `sync_projects.py`.
- `sync_projects.py` — sync périodique SQL Server (Maestro/Qualifab) → Postgres.
  À planifier là où SQL Server est joignable. Voir `db/schema.sql`.
- `refdata.json` — listes **personnel / véhicules / autres projets** uniquement.
```

Et ajouter une sous-section :

```markdown
## Base de données (projets / activités)

1. Provisionner une base Postgres (Supabase / Azure) et appliquer `db/schema.sql`.
2. Configurer l'accès de l'app : copier `.streamlit/secrets.toml.example` vers
   `.streamlit/secrets.toml` et renseigner l'URL de connexion.
3. Planifier `sync_projects.py` (cron / Azure Function / Tâche planifiée) avec
   les variables d'env `SQLSERVER_*` et `POSTGRES_URL` ; dépendances dans
   `requirements-sync.txt`.
```

- [ ] **Step 3 : Commit**

```bash
git add README.md
git commit -m "docs: README — source BD pour projets/activités + procédure de sync"
```

- [ ] **Step 4 : Récapituler la branche**

Run : `git log --oneline main..HEAD`
Expected : les commits des tâches 1→8, prêts pour une PR / un merge.

---

## Self-Review (auteur du plan)

**Couverture du spec :**
- Schéma Postgres → Task 4 (`db/schema.sql` + `SCHEMA_DDL`). ✓
- Script de sync (rafraîchissement complet transactionnel, `rows_to_payload`) → Task 4. ✓
- Couche d'accès `data_source.py` (get_projects/get_activities, cache via `ttl`, fallback erreur) → Task 3. ✓
- UX : selectbox projet → Task 5 ; activités filtrées + `filter_known` → Task 6. ✓
- Retrait onglet Activités → Task 7. ✓
- Re-baseline complet des tests → Task 2 (+ tests BD aux tasks 3-7). ✓
- Dépendances (app + sync) & secrets & .gitignore → Task 3 (app) / Task 4 (sync). ✓
- Export inchangé, testé en smoke → Task 2 (`test_export_view_generates_without_error`). ✓

**Cohérence des types :** `get_projects() -> list[(int,str)]`, `get_activities(id) -> list[str]`, `projet["id_project"]` int|None, `rows_to_payload -> (list[(int,str)], list[(int,str,str)])` — utilisés de façon cohérente entre tasks 3/4/5/6.

**Placeholders :** aucun (code complet à chaque étape).
