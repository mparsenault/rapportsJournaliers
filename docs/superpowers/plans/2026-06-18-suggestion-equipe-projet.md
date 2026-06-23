# Suggestion d'équipe par projet — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quand un projet est sélectionné, pré-remplir l'équipe (`config["personnel"]`) avec les employés ayant travaillé dessus la semaine précédente, à partir des feuilles de temps SQL Server synchronisées vers une table Neon `project_staff`.

**Architecture:** Le sync ajoute une requête feuilles-de-temps → table `project_staff(id_project, employee)`. L'app lit `data_source.get_project_staff(id_project)` et pré-remplit l'équipe au changement de projet. Le personnel `refdata.json` reste, en plus.

**Tech Stack:** Python, `pymssql`/`psycopg2` (sync), Streamlit 1.50 + SQLAlchemy (`st.connection`), pytest + AppTest.

## Global Constraints

- Base de code = working tree `app.py`, `sync_projects.py`, `data_source.py`.
- Table Neon : `project_staff (id_project integer not null, employee text not null, primary key (id_project, employee))` + `index idx_project_staff_project on project_staff(id_project)`. **Pas de clé étrangère** vers `projects`.
- Libellé employé = `"Prénom Nom (Métier)"`, ou `"Prénom Nom"` si métier vide/NULL. Même format que le personnel existant.
- `STAFF_QUERY` EXACTE (ne pas changer les filtres) — sélectionne `tsis.ID_Project, eu.FirstName, eu.LastName, o.Name as Occupation`, filtre `ID_Company=1`, `ID_Project <> ''`, et `WeekLastDay = (select max(WeekLastDay) ... where ID_Company=1 and WeekLastDay < cast(getdate() as date))`.
- Rafraîchissement complet **dans la même transaction** que projets/activités (delete + insert).
- `get_project_staff(id_project)` → `[]` si `id_project is None`, aucun résultat, ou base injoignable (même try/except que `get_activities`).
- Pré-remplissage : marqueur `st.session_state["staff_prefilled_for"]` ; au **changement** de projet, **remplace** `config["personnel"]` par les suggérés ; ne touche **jamais** `config["equipements"]`.
- Options du multiselect Personnel (vue config) = `sorted(set(ref["personnel"]) | set(get_project_staff(id_project)) | set(config["personnel"]))`.
- `refdata.json` et l'export Excel : **inchangés**.
- Tests **déterministes** : monkeypatcher les fonctions `data_source` (ne pas dépendre de la vraie base Neon, dont `.streamlit/secrets.toml` est présent sur cette machine).
- Tests : `.venv/bin/python -m pytest -q` ; sortie pristine, 0 failed.

## File Structure

- `sync_projects.py` — `STAFF_QUERY`, `staff_rows_to_payload`, `fetch_staff_rows`, `SCHEMA_DDL` (+ table), `write_payload` (+ staff), `main` (+ staff).
- `db/schema.sql` — ajout de la table `project_staff`.
- `data_source.py` — `get_project_staff`.
- `app.py` — pré-remplissage dans `view_dashboard` ; options Personnel dans la vue config.
- `tests/test_sync.py`, `tests/test_data_source.py`, `tests/test_ui.py` — nouveaux tests.

---

### Task 1 : Sync — table et requête feuilles de temps

**Files:**
- Modify: `sync_projects.py`
- Modify: `db/schema.sql`
- Modify: `tests/test_sync.py`

**Interfaces:**
- Produces: `staff_rows_to_payload(rows) -> list[(id_project:int, employee:str)]` (dédupliqué, trié) ; `fetch_staff_rows()` ; `write_payload(pg_url, projects, activities, staff)` (signature étendue) ; table `project_staff`.

- [ ] **Step 1 : Écrire les tests purs (échouent : fonction absente)**

Ajouter à `tests/test_sync.py` :

```python
def test_staff_rows_to_payload_formats_and_dedups():
    rows = [
        (1, "Jean", "Tremblay", "Électricien"),
        (1, "Jean", "Tremblay", "Électricien"),   # doublon
        (1, "Marie", "Roy", None),                 # métier NULL
        (2, "Luc", "Côté", ""),                    # métier vide
    ]
    assert sync_projects.staff_rows_to_payload(rows) == [
        (1, "Jean Tremblay (Électricien)"),
        (1, "Marie Roy"),
        (2, "Luc Côté"),
    ]


def test_staff_rows_to_payload_skips_missing_project():
    assert sync_projects.staff_rows_to_payload([(None, "X", "Y", "Z")]) == []


def test_staff_rows_to_payload_empty():
    assert sync_projects.staff_rows_to_payload([]) == []
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv/bin/python -m pytest tests/test_sync.py -q 2>&1 | tail -5`
Expected : FAIL (`AttributeError: ... has no attribute 'staff_rows_to_payload'`).

- [ ] **Step 3 : Ajouter `STAFF_QUERY` et étendre `SCHEMA_DDL` dans `sync_projects.py`**

Après la constante `SCHEMA_DDL`, ajouter :

```python
STAFF_QUERY = """
select distinct tsis.ID_Project, eu.FirstName, eu.LastName, o.Name as Occupation
from FDT.TimeSheetItemsStore tsis
left join HumanResources.Employees_U eu on eu.ID_Employee = tsis.ID_Employee
left join Reference.Occupation o on eu.ID_Occupation = o.ID_Occupation
where tsis.ID_Company = 1
  and tsis.ID_Project <> ''
  and tsis.WeekLastDay = (select max(WeekLastDay) from FDT.TimeSheetItemsStore
                          where ID_Company = 1 and WeekLastDay < cast(getdate() as date))
"""
```

Dans `SCHEMA_DDL`, ajouter (avant la fermeture `"""`, après l'index activities) :

```sql
create table if not exists project_staff (
    id_project integer not null,
    employee   text not null,
    primary key (id_project, employee)
);
create index if not exists idx_project_staff_project on project_staff(id_project);
```

- [ ] **Step 4 : Implémenter `staff_rows_to_payload` et `fetch_staff_rows`**

Après `rows_to_payload`, ajouter :

```python
def staff_rows_to_payload(rows):
    """rows: itérable de (id_project, first_name, last_name, occupation).

    Renvoie list[(id_project, employee)] dédupliquée et triée. Libellé employé :
    "Prénom Nom (Métier)", ou "Prénom Nom" si le métier est vide/NULL. Les lignes
    sans id_project (ou sans nom) sont ignorées.
    """
    seen = set()
    out = []
    for id_project, first, last, occupation in rows:
        if id_project is None:
            continue
        name = f"{(first or '').strip()} {(last or '').strip()}".strip()
        if not name:
            continue
        occ = (occupation or "").strip()
        label = f"{name} ({occ})" if occ else name
        key = (id_project, label)
        if key not in seen:
            seen.add(key)
            out.append((id_project, label))
    return sorted(out)
```

Après `fetch_source_rows`, ajouter :

```python
def fetch_staff_rows():
    import pymssql
    conn = pymssql.connect(
        server=os.environ["SQLSERVER_HOST"],
        user=os.environ["SQLSERVER_USER"],
        password=os.environ["SQLSERVER_PASSWORD"],
        database=os.environ["SQLSERVER_DB"],
    )
    try:
        cur = conn.cursor()
        cur.execute(STAFF_QUERY)
        return cur.fetchall()
    finally:
        conn.close()
```

- [ ] **Step 5 : Étendre `write_payload` et `main`**

Remplacer `write_payload` par (ajout du paramètre `staff` + delete/insert `project_staff`) :

```python
def write_payload(pg_url, projects, activities, staff):
    import psycopg2
    conn = psycopg2.connect(pg_url)
    try:
        cur = conn.cursor()
        cur.execute(SCHEMA_DDL)
        cur.execute("delete from activities;")
        cur.execute("delete from project_staff;")
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
        if staff:
            cur.executemany(
                "insert into project_staff (id_project, employee) values (%s, %s)",
                staff,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

Remplacer le corps de `main` par :

```python
def main():
    _load_dotenv()
    projects, activities = rows_to_payload(fetch_source_rows())
    staff = staff_rows_to_payload(fetch_staff_rows())
    write_payload(os.environ["POSTGRES_URL"], projects, activities, staff)
    print(f"Sync OK : {len(projects)} projets, {len(activities)} activités, "
          f"{len(staff)} affectations")
```

- [ ] **Step 6 : Mettre à jour `db/schema.sql`**

Ajouter à la fin de `db/schema.sql` :

```sql

create table if not exists project_staff (
    id_project integer not null,
    employee   text not null,
    primary key (id_project, employee)
);

create index if not exists idx_project_staff_project on project_staff(id_project);
```

- [ ] **Step 7 : Lancer les tests, vérifier le vert**

Run : `.venv/bin/python -m pytest tests/test_sync.py -q 2>&1 | tail -3`
Expected : tous verts (3 nouveaux inclus).

- [ ] **Step 8 : Commit**

```bash
git add sync_projects.py db/schema.sql tests/test_sync.py
git commit -m "feat: sync des affectations employé→projet (table project_staff)"
```

---

### Task 2 : Accès app `get_project_staff`

**Files:**
- Modify: `data_source.py`
- Modify: `tests/test_data_source.py`

**Interfaces:**
- Consumes: `_connection()` (existant).
- Produces: `get_project_staff(id_project) -> list[str]` (libellés triés ; `[]` si None / aucun / injoignable).

- [ ] **Step 1 : Écrire les tests (échouent : fonction absente)**

Ajouter à `tests/test_data_source.py` (la classe `_FakeConn` et `import pandas as pd` existent déjà) :

```python
def test_get_project_staff_none_returns_empty():
    assert data_source.get_project_staff(None) == []


def test_get_project_staff_happy(monkeypatch):
    df = pd.DataFrame({"employee": ["Jean Tremblay (Électricien)", "Marie Roy"]})
    monkeypatch.setattr(data_source, "_connection", lambda: _FakeConn(df))
    assert data_source.get_project_staff(1) == ["Jean Tremblay (Électricien)", "Marie Roy"]


def test_get_project_staff_unreachable_returns_empty(monkeypatch):
    def boom():
        raise RuntimeError("no db")
    monkeypatch.setattr(data_source, "_connection", boom)
    assert data_source.get_project_staff(1) == []
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv/bin/python -m pytest tests/test_data_source.py -q 2>&1 | tail -5`
Expected : FAIL (`AttributeError: ... has no attribute 'get_project_staff'`).

- [ ] **Step 3 : Implémenter `get_project_staff`**

Dans `data_source.py`, ajouter la constante SQL près des autres :

```python
_STAFF_SQL = "select employee from project_staff where id_project = :pid order by employee"
```

Et la fonction (après `get_activities`) :

```python
def get_project_staff(id_project):
    """Libellés d'employés ayant travaillé sur le projet (semaine précédente).

    [] si id_project None, aucun résultat, ou base injoignable.
    """
    if id_project is None:
        return []
    try:
        df = _connection().query(_STAFF_SQL, params={"pid": int(id_project)}, ttl=600)
        return [str(r.employee) for r in df.itertuples(index=False)]
    except Exception:
        return []
```

- [ ] **Step 4 : Lancer, vérifier le vert**

Run : `.venv/bin/python -m pytest tests/test_data_source.py -q 2>&1 | tail -3`
Expected : tous verts (3 nouveaux inclus).

- [ ] **Step 5 : Commit**

```bash
git add data_source.py tests/test_data_source.py
git commit -m "feat: data_source.get_project_staff (employés d'un projet)"
```

---

### Task 3 : Intégration UI — pré-remplissage + options Personnel

**Files:**
- Modify: `app.py` (`view_dashboard` ; bloc `view == "config"` dans `main`)
- Modify: `tests/test_ui.py`

**Interfaces:**
- Consumes: `data_source.get_project_staff(id_project)` (Task 2).

- [ ] **Step 1 : Écrire les tests (échouent contre l'app actuelle)**

Dans `tests/test_ui.py`, **modifier le helper** `_run_with_project` pour neutraliser le staff par défaut (tests déterministes, pas d'appel à la vraie base) — ajouter la ligne monkeypatch :

```python
def _run_with_project(monkeypatch, project_no="P-1", id_project=1):
    """Lance l'app avec un projet disponible ET sélectionné (sinon tout est grisé)."""
    import data_source
    monkeypatch.setattr(data_source, "get_projects", lambda: [(id_project, project_no)])
    monkeypatch.setattr(data_source, "get_project_staff", lambda pid: [])
    at = AppTest.from_file("app.py", default_timeout=30).run()
    sb = [s for s in at.selectbox if s.label == "Projet"][0]
    sb.set_value(project_no).run()
    return at
```

Puis ajouter les deux tests :

```python
def test_project_selection_prefills_team(monkeypatch):
    import data_source
    monkeypatch.setattr(data_source, "get_projects", lambda: [(1, "P-100")])
    monkeypatch.setattr(data_source, "get_project_staff",
                        lambda pid: ["Jean Tremblay (Électricien)"] if pid == 1 else [])
    at = _run()
    sb = [s for s in at.selectbox if s.label == "Projet"][0]
    sb.set_value("P-100").run()
    assert at.session_state["config"]["personnel"] == ["Jean Tremblay (Électricien)"]
    assert not at.exception


def test_config_personnel_options_include_suggested(monkeypatch):
    import data_source
    monkeypatch.setattr(data_source, "get_projects", lambda: [(1, "P-100")])
    monkeypatch.setattr(data_source, "get_project_staff",
                        lambda pid: ["Jean Tremblay (Électricien)"] if pid == 1 else [])
    at = _run()
    sb = [s for s in at.selectbox if s.label == "Projet"][0]
    sb.set_value("P-100").run()
    at.session_state["view"] = "config"
    at.run()
    pers = [m for m in at.multiselect if m.label == "Personnel"][0]
    assert "Jean Tremblay (Électricien)" in pers.options
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv/bin/python -m pytest tests/test_ui.py::test_project_selection_prefills_team -q 2>&1 | tail -6`
Expected : FAIL (l'équipe n'est pas pré-remplie — `config["personnel"]` reste vide).

- [ ] **Step 3 : Ajouter le pré-remplissage dans `view_dashboard`**

Dans `app.py`, juste après la ligne `projet_choisi = bool(proj.get("id_project"))`, insérer :

```python
        pid = proj.get("id_project")
        if pid is not None and st.session_state.get("staff_prefilled_for") != pid:
            suggested = data_source.get_project_staff(pid)
            if suggested:
                st.session_state.config["personnel"] = suggested
            st.session_state["staff_prefilled_for"] = pid
```

- [ ] **Step 4 : Mettre à jour les options du multiselect Personnel (vue config)**

Dans `main`, le bloc `elif st.session_state.view == "config":` contient :

```python
        st.session_state.config["personnel"] = st.multiselect("Personnel", st.session_state.ref["personnel"], default=st.session_state.config["personnel"])
```

Le remplacer par :

```python
        _pers_options = sorted(set(st.session_state.ref["personnel"])
                               | set(data_source.get_project_staff(st.session_state.projet.get("id_project")))
                               | set(st.session_state.config["personnel"]))
        st.session_state.config["personnel"] = st.multiselect("Personnel", _pers_options, default=st.session_state.config["personnel"])
```

(La ligne `Équipements` juste en dessous reste inchangée.)

- [ ] **Step 5 : Lancer les tests ciblés, vérifier le vert**

Run : `.venv/bin/python -m pytest tests/test_ui.py::test_project_selection_prefills_team tests/test_ui.py::test_config_personnel_options_include_suggested -q 2>&1 | tail -4`
Expected : 2 passed.

- [ ] **Step 6 : Lancer toute la suite**

Run : `.venv/bin/python -m pytest -q 2>&1 | tail -3`
Expected : 0 failed.

- [ ] **Step 7 : Commit**

```bash
git add app.py tests/test_ui.py
git commit -m "feat: pré-remplissage de l'équipe par projet (employés semaine précédente)"
```

---

## Self-Review (auteur du plan)

**Couverture du spec :**
- STAFF_QUERY + semaine précédente en SQL → Task 1 Step 3. ✓
- Table `project_staff` (PK composite, index, pas de FK) → Task 1 Steps 3, 6. ✓
- Libellé `"Prénom Nom (Métier)"` / sans parenthèses si vide → `staff_rows_to_payload` Task 1 Step 4 + tests. ✓
- Rafraîchissement complet, même transaction → `write_payload` Task 1 Step 5. ✓
- `get_project_staff` ([] sur None/aucun/injoignable) → Task 2. ✓
- Pré-remplissage avec marqueur, remplace au changement, équipements intacts → Task 3 Step 3. ✓
- Options Personnel = union → Task 3 Step 4. ✓
- Tests déterministes (monkeypatch, `_run_with_project` neutralise staff) → Task 3 Step 1. ✓
- refdata.json / export inchangés → aucune modif de ces fichiers. ✓

**Placeholders :** aucun (code complet).

**Cohérence des types :** `staff_rows_to_payload -> [(int,str)]`, `write_payload(..., staff)`, `get_project_staff -> [str]`, libellé identique entre sync et tests. Clé session `staff_prefilled_for`. Cohérents entre tâches.
