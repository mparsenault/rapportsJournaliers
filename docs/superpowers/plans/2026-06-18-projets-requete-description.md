# Nouvelle requête projets + description — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Élargir la requête source des projets (ne plus en manquer) et afficher la description du projet dans le menu déroulant (« Project_No — Description »).

**Architecture:** La requête sync passe à 5 colonnes (ajout `p.Description`) ; `projects` gagne une colonne `description` ; `rows_to_payload` renvoie des projets en 3-uplets ; `data_source.get_projects` renvoie `(id, no, desc)` ; le selectbox affiche `"no — desc"`.

**Tech Stack:** Python, `pymssql`/`psycopg2` (sync), Streamlit 1.50 + SQLAlchemy, pytest + AppTest.

## Global Constraints

- Base de code = working tree (`sync_projects.py`, `data_source.py`, `app.py`).
- `SOURCE_QUERY` EXACTE : `select p.ID_Project, p.Project_No, p.Description, a.ActivityCode, a.Description from Projects.Projects p left join Projects.Activities a on p.ID_Project = a.ID_Project where p.ID_Company = 1 and p.Valid = 1 and p.Project_No like '08%'`.
- Table `projects` : `(id_project integer primary key, project_no text not null, description text)` + `alter table projects add column if not exists description text;` (migration table existante).
- `rows_to_payload` : `projects` = `list[(id_project, project_no, description)]` ; `activities` = `list[(id_project, activity_code, activity_description)]` (inchangé).
- `get_projects() -> list[(id_project:int, project_no:str, description:str)]` ; description NULL/absente → `""`.
- Libellé selectbox = `f"{project_no} — {description}"` (tiret cadratin « — »), ou `project_no` seul si description vide. On stocke toujours `proj["no"]` = `project_no` et `proj["id_project"]`.
- Activités (format `"Code - Description"`), `project_staff`, saisie et export : **inchangés**. L'export utilise `proj["no"]`.
- Tests déterministes (monkeypatch des fonctions `data_source`).
- Tests : `.venv/bin/python -m pytest -q` ; sortie pristine, 0 failed.

## File Structure

- `sync_projects.py` — `SOURCE_QUERY`, `SCHEMA_DDL` (+ description + alter), `rows_to_payload` (3-uplets), `write_payload` (insert 3 colonnes).
- `db/schema.sql` — colonne `description` + alter.
- `data_source.py` — `_PROJECTS_SQL`, `projects_from_df`, `get_projects`.
- `app.py` — `view_dashboard` (libellé selectbox).
- `tests/test_sync.py`, `tests/test_data_source.py`, `tests/test_ui.py`.

---

### Task 1 : Sync — requête + description dans `projects`

**Files:**
- Modify: `sync_projects.py`
- Modify: `db/schema.sql`
- Modify: `tests/test_sync.py`

**Interfaces:**
- Produces: `rows_to_payload(rows)` renvoie `projects: list[(id_project, project_no, description)]`, `activities: list[(id_project, activity_code, activity_description)]`.

- [ ] **Step 1 : Mettre à jour les tests `rows_to_payload` (échouent : forme à 2-uplets attendue)**

Dans `tests/test_sync.py`, REMPLACER les 4 tests `test_rows_to_payload_*` par :

```python
def test_rows_to_payload_dedups_projects():
    rows = [
        (1, "P-1", "Projet 1", "C01", "A"),
        (1, "P-1", "Projet 1", "C02", "B"),
        (2, "P-2", "Projet 2", "C03", "C"),
    ]
    projects, activities = sync_projects.rows_to_payload(rows)
    assert projects == [(1, "P-1", "Projet 1"), (2, "P-2", "Projet 2")]
    assert activities == [(1, "C01", "A"), (1, "C02", "B"), (2, "C03", "C")]


def test_rows_to_payload_skips_null_activity():
    projects, activities = sync_projects.rows_to_payload([(3, "P-3", "Projet 3", None, None)])
    assert projects == [(3, "P-3", "Projet 3")]
    assert activities == []


def test_rows_to_payload_skips_blank_activity_code():
    projects, activities = sync_projects.rows_to_payload([(4, "P-4", "Projet 4", "   ", "desc")])
    assert projects == [(4, "P-4", "Projet 4")]
    assert activities == []


def test_rows_to_payload_empty():
    assert sync_projects.rows_to_payload([]) == ([], [])
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv/bin/python -m pytest tests/test_sync.py -q 2>&1 | tail -6`
Expected : FAIL (`rows_to_payload` actuel attend 4 colonnes / renvoie des 2-uplets).

- [ ] **Step 3 : Remplacer `SOURCE_QUERY` et adapter `SCHEMA_DDL`**

Remplacer la constante `SOURCE_QUERY` par :

```python
SOURCE_QUERY = """
select p.ID_Project, p.Project_No, p.Description, a.ActivityCode, a.Description
from Projects.Projects p
left join Projects.Activities a
  on p.ID_Project = a.ID_Project
where p.ID_Company = 1
  and p.Valid = 1
  and p.Project_No like '08%'
"""
```

Dans `SCHEMA_DDL`, le bloc `create table if not exists projects (...)` devient (ajout `description` + `alter`) :

```sql
create table if not exists projects (
    id_project integer primary key,
    project_no text not null,
    description text
);
alter table projects add column if not exists description text;
```

(laisser `activities` / `project_staff` inchangés)

- [ ] **Step 4 : Réécrire `rows_to_payload`**

```python
def rows_to_payload(rows):
    """rows: (id_project, project_no, project_description, activity_code, activity_description).

    Renvoie (projects, activities) :
      projects   : list[(id_project, project_no, description)] dédup, trié par id_project
      activities : list[(id_project, activity_code, activity_description)] (code non vide)
    """
    projects = {}
    activities = []
    for id_project, project_no, proj_desc, code, act_desc in rows:
        projects.setdefault(id_project, (project_no, proj_desc))
        if code is not None and str(code).strip() != "":
            activities.append((id_project, code, act_desc))
    proj_list = [(pid, no, desc) for pid, (no, desc) in sorted(projects.items())]
    return proj_list, activities
```

- [ ] **Step 5 : Adapter l'insertion dans `write_payload`**

Dans `write_payload`, remplacer le bloc `if projects:` par :

```python
        if projects:
            cur.executemany(
                "insert into projects (id_project, project_no, description) values (%s, %s, %s)",
                projects,
            )
```

(les blocs `activities` et `staff` restent inchangés)

- [ ] **Step 6 : Mettre à jour `db/schema.sql`**

Dans `db/schema.sql`, le bloc `create table if not exists projects (...)` devient :

```sql
create table if not exists projects (
    id_project integer primary key,
    project_no text not null,
    description text
);
alter table projects add column if not exists description text;
```

- [ ] **Step 7 : Lancer les tests, vérifier le vert**

Run : `.venv/bin/python -m pytest tests/test_sync.py -q 2>&1 | tail -3`
Expected : tous verts.

- [ ] **Step 8 : Commit**

```bash
git add sync_projects.py db/schema.sql tests/test_sync.py
git commit -m "feat: requête projets élargie + description (sync + schéma)"
```

---

### Task 2 : Accès app — `get_projects` avec description

**Files:**
- Modify: `data_source.py`
- Modify: `tests/test_data_source.py`

**Interfaces:**
- Produces: `get_projects() -> list[(id_project:int, project_no:str, description:str)]` ; `projects_from_df(df)` idem.

- [ ] **Step 1 : Mettre à jour les tests (échouent : 2-uplets attendus)**

Dans `tests/test_data_source.py`, REMPLACER `test_projects_from_df` et `test_get_projects_happy` par :

```python
def test_projects_from_df():
    df = pd.DataFrame({"id_project": [2, 1], "project_no": ["P-2", "P-1"],
                       "description": ["Deux", None]})
    assert data_source.projects_from_df(df) == [(2, "P-2", "Deux"), (1, "P-1", "")]


def test_get_projects_happy(monkeypatch):
    df = pd.DataFrame({"id_project": [1], "project_no": ["P-1"], "description": ["Projet 1"]})
    monkeypatch.setattr(data_source, "_connection", lambda: _FakeConn(df))
    assert data_source.get_projects() == [(1, "P-1", "Projet 1")]
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv/bin/python -m pytest tests/test_data_source.py -q 2>&1 | tail -6`
Expected : FAIL (forme 2-uplets / SQL sans `description`).

- [ ] **Step 3 : Adapter `_PROJECTS_SQL` et `projects_from_df`**

Remplacer la constante :

```python
_PROJECTS_SQL = "select id_project, project_no, description from projects order by project_no"
```

Remplacer `projects_from_df` par (NULL/NaN → `""`, sans importer pandas) :

```python
def projects_from_df(df):
    """DataFrame(id_project, project_no, description) -> list[(int, str, str)]."""
    out = []
    for r in df.itertuples(index=False):
        desc = r.description if isinstance(r.description, str) else ""
        out.append((int(r.id_project), str(r.project_no), desc))
    return out
```

(`get_projects` est inchangé : il appelle `projects_from_df` et renvoie déjà sa sortie.)

- [ ] **Step 4 : Lancer les tests, vérifier le vert**

Run : `.venv/bin/python -m pytest tests/test_data_source.py -q 2>&1 | tail -3`
Expected : tous verts.

- [ ] **Step 5 : Commit**

```bash
git add data_source.py tests/test_data_source.py
git commit -m "feat: get_projects renvoie la description du projet"
```

---

### Task 3 : Menu déroulant — libellé « Project_No — Description »

**Files:**
- Modify: `app.py` (`view_dashboard`)
- Modify: `tests/test_ui.py`

**Interfaces:**
- Consumes: `data_source.get_projects() -> [(id, no, desc)]` (Task 2).

- [ ] **Step 1 : Mettre à jour le helper + les tests qui passent des projets (échouent contre l'app actuelle)**

Dans `tests/test_ui.py` :

**(a)** Remplacer le helper `_run_with_project` par (projets en 3-uplets + libellé) :

```python
def _run_with_project(monkeypatch, project_no="P-1", id_project=1, description="Projet 1"):
    """Lance l'app avec un projet disponible ET sélectionné (sinon tout est grisé)."""
    import data_source
    monkeypatch.setattr(data_source, "get_projects", lambda: [(id_project, project_no, description)])
    monkeypatch.setattr(data_source, "get_project_staff", lambda pid: [])
    at = AppTest.from_file("app.py", default_timeout=30).run()
    sb = [s for s in at.selectbox if s.label == "Projet"][0]
    label = f"{project_no} — {description}" if description else project_no
    sb.set_value(label).run()
    return at
```

**(b)** Remplacer `test_project_selectbox_lists_db_projects` et `test_selecting_project_sets_id` par :

```python
def test_project_selectbox_lists_db_projects(monkeypatch):
    import data_source
    monkeypatch.setattr(data_source, "get_projects",
                        lambda: [(1, "P-100", "Alpha"), (2, "P-200", "Beta")])
    monkeypatch.setattr(data_source, "get_project_staff", lambda pid: [])
    at = _run()
    sb = [s for s in at.selectbox if s.label == "Projet"][0]
    assert list(sb.options) == ["P-100 — Alpha", "P-200 — Beta"]
    assert not at.exception


def test_selecting_project_sets_id(monkeypatch):
    import data_source
    monkeypatch.setattr(data_source, "get_projects",
                        lambda: [(1, "P-100", "Alpha"), (2, "P-200", "Beta")])
    monkeypatch.setattr(data_source, "get_project_staff", lambda pid: [])
    at = _run()
    sb = [s for s in at.selectbox if s.label == "Projet"][0]
    sb.set_value("P-200 — Beta").run()
    assert at.session_state["projet"]["id_project"] == 2
    assert at.session_state["projet"]["no"] == "P-200"
```

**(c)** Dans `test_day_activities_come_from_db`, `test_project_selection_prefills_team` et `test_config_personnel_options_include_suggested`, la ligne `monkeypatch.setattr(data_source, "get_projects", lambda: [(1, "P-100")])` devient `lambda: [(1, "P-100", "Alpha")]`. Dans `test_project_selection_prefills_team` et `test_config_personnel_options_include_suggested`, le `sb.set_value("P-100")` devient `sb.set_value("P-100 — Alpha")`. (`test_day_activities_come_from_db` ne sélectionne pas via le selectbox — seul le tuple change.)

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv/bin/python -m pytest tests/test_ui.py::test_project_selectbox_lists_db_projects -q 2>&1 | tail -8`
Expected : FAIL (le selectbox liste encore `["P-100", "P-200"]`, et l'app plante au dépaquetage 3-uplets côté `view_dashboard`).

- [ ] **Step 3 : Réécrire le bloc projet dans `view_dashboard`**

Dans `app.py`, remplacer le bloc `if not projects: … else: …` du selectbox par :

```python
        projects = data_source.get_projects()
        if not projects:
            c1.error("Impossible de charger les projets depuis la base.")
            # proj["no"] est volontairement conservé (non vidé) pour restaurer la sélection à la reconnexion
            proj["id_project"] = None
        else:
            def _proj_label(no, desc):
                return f"{no} — {desc}" if desc else no
            labels = [_proj_label(no, desc) for _pid, no, desc in projects]
            by_label = {_proj_label(no, desc): (pid, no) for pid, no, desc in projects}
            current = next((lbl for lbl, (_pid, no) in by_label.items() if no == proj["no"]), None)
            index = labels.index(current) if current in labels else None
            sel = c1.selectbox("Projet", labels, index=index, placeholder="Choisir un projet…")
            if sel:
                proj["id_project"], proj["no"] = by_label[sel]
            else:
                proj["id_project"], proj["no"] = None, ""
```

(Le reste de `view_dashboard` — `projet_choisi`, pré-remplissage, « Semaine du », etc. — est inchangé.)

- [ ] **Step 4 : Lancer les tests ciblés, vérifier le vert**

Run : `.venv/bin/python -m pytest tests/test_ui.py::test_project_selectbox_lists_db_projects tests/test_ui.py::test_selecting_project_sets_id -q 2>&1 | tail -4`
Expected : 2 passed.

- [ ] **Step 5 : Lancer toute la suite**

Run : `.venv/bin/python -m pytest -q 2>&1 | tail -3`
Expected : 0 failed.

- [ ] **Step 6 : Commit**

```bash
git add app.py tests/test_ui.py
git commit -m "feat: menu projet affiche « Project_No — Description »"
```

---

## Self-Review (auteur du plan)

**Couverture du spec :**
- Requête élargie + `p.Description` → Task 1 Step 3. ✓
- Colonne `description` + `alter` (migration) → Task 1 Steps 3, 6. ✓
- `rows_to_payload` 3-uplets → Task 1 Step 4 + tests. ✓
- `write_payload` insert 3 colonnes → Task 1 Step 5. ✓
- `get_projects`/`projects_from_df` 3-uplets, NULL→"" → Task 2. ✓
- Libellé « no — desc », stocke no + id_project, restauration par no → Task 3 Step 3. ✓
- Mise à jour des tests touchés (sync, data_source, ui + helper) → Tasks 1-3. ✓
- Activités / project_staff / export inchangés → aucune modif de ces chemins. ✓

**Placeholders :** aucun (code complet).

**Cohérence des types :** `rows_to_payload -> ([(int,str,str)], [(int,str,str)])` ; `get_projects -> [(int,str,str)]` ; selectbox map `by_label -> (pid, no)`. Cohérents entre tâches.
