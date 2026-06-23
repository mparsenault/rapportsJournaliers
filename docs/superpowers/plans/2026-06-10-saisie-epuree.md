# Saisie épurée — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refondre la page « Saisie hebdomadaire » de `app.py` : configuration de la semaine (équipe/équipements/responsable/quart) définie une fois, sélecteur de jour sticky, et une seule grille combinée Personnel+Équipement où l'on ne saisit que les heures ; les activités restent choisies par jour. L'export Excel reste inchangé via un adaptateur de compatibilité.

**Architecture :** Le nouvel état en session sépare une `config` de semaine (roster stable) des `jours` (heures par ressource/colonne, activités par jour). Des fonctions pures construisent la DataFrame de la grille et la réécrivent, et un adaptateur `_day_to_legacy` reconstruit les structures historiques (`headers`/`pers`/`equip`) que tout le code d'export consomme déjà. L'UI passe des 7 onglets à un `st.segmented_control` (un seul jour rendu).

**Tech Stack :** Python 3.9, Streamlit 1.50 (`st.data_editor`, `st.segmented_control`, `streamlit.testing.v1.AppTest`), pandas, openpyxl. Tests : pytest (logique pure) + AppTest (UI). Le tout dans le venv `.venv`.

**Référence spec :** `docs/superpowers/specs/2026-06-10-saisie-epuree-design.md`

---

## File Structure

- `app.py` — fichier unique de l'app (l'app est mono-fichier ; on conserve ce choix existant). Sections touchées :
  - `init_state` / `_empty_day` (≈ l.66-99) — nouveau modèle + `config`.
  - **Nouvelles fonctions pures** (modèle/grille/adaptateur) ajoutées près des calculs (≈ après l.113).
  - `build_workbook` (l.258) — branché sur l'adaptateur.
  - `page_saisie` (l.738), `_render_day` (l.770), `_show_totals` (l.853), `grid_editor` (l.118) — réécrits/supprimés.
  - `_fill_week_weather` (l.672) — adapté (écrit l'état des jours + purge les clés de widgets).
  - CSS `_CSS` (≈ l.917+) — style sticky du sélecteur de jour.
  - `_render_day` weather widgets — pilotés par `session_state`.
- `tests/test_model.py` — tests des fonctions pures (modèle, grille, adaptateur, export).
- `tests/test_ui.py` — tests AppTest (config, sélecteur de jour, grille, météo).
- `pytest.ini` — config pytest (`pythonpath = .`).

---

## Task 0: Outillage projet (git, pytest, tests)

**Files:**
- Create: `pytest.ini`
- Create: `tests/__init__.py` (vide)
- Modify: `requirements.txt`

- [ ] **Step 1: Initialiser git (si l'utilisateur le souhaite) et ignorer les artefacts**

Run:
```bash
cd /Users/marie-pierarsenault/Downloads/RJ
git init
printf '.venv/\n__pycache__/\n*.pyc\n.superpowers/\n.pytest_cache/\ndemo.xlsx\nprobe.py\ncheck.py\n' > .gitignore
git add -A && git commit -m "chore: init repo (app Rapport Journalier Ondel)"
```
Expected : dépôt créé, premier commit. (Si l'utilisateur refuse git, sauter les `git commit` de tout le plan.)

- [ ] **Step 2: Installer pytest dans le venv**

Run:
```bash
.venv/bin/pip install pytest
```
Expected : `Successfully installed pytest-...`

- [ ] **Step 3: Ajouter pytest aux dépendances de dev**

Modify `requirements.txt` — ajouter à la fin :
```
pytest>=7.0
```

- [ ] **Step 4: Créer la config pytest**

Create `pytest.ini` :
```ini
[pytest]
pythonpath = .
testpaths = tests
```

- [ ] **Step 5: Créer le paquet de tests**

Create `tests/__init__.py` (fichier vide).

- [ ] **Step 6: Vérifier que `import app` fonctionne sous pytest**

Create `tests/test_smoke.py` :
```python
def test_import_app():
    import app
    assert hasattr(app, "JOURS")
    assert app.JOURS[0] == "Dimanche"
```

Run: `.venv/bin/pytest tests/test_smoke.py -q`
Expected : 1 passed.

- [ ] **Step 7: Commit**

```bash
git add pytest.ini tests/ requirements.txt .gitignore
git commit -m "chore: add pytest tooling and smoke test"
```

---

## Task 1: Nouveau modèle de données (`config` + `_empty_day`)

**Files:**
- Modify: `app.py` — `init_state` (l.66-73), `_empty_day` (l.76-99)
- Test: `tests/test_model.py`

- [ ] **Step 1: Écrire le test du modèle vide**

Create `tests/test_model.py` :
```python
import app


def test_empty_day_shape():
    d = app._empty_day()
    assert d["date"] is None
    assert d["activites"] == []
    assert d["autres"] == []
    assert d["heures"] == {}
    assert d["prime"] == {}
    assert d["commentaire_ligne"] == {}
    for k in ("responsable", "quart", "description", "commentaires", "revu_par"):
        assert d[k] == ""
    assert d["conditions"] == []
    assert d["temp_am"] is None and d["temp_pm"] is None


def test_default_config_shape():
    c = app._default_config()
    assert c == {"responsable": "", "quart": "", "personnel": [], "equipements": []}
```

- [ ] **Step 2: Lancer le test (échec attendu)**

Run: `.venv/bin/pytest tests/test_model.py -q`
Expected : FAIL — `_default_config` n'existe pas / `_empty_day` n'a pas les nouvelles clés.

- [ ] **Step 3: Réécrire `_empty_day` et ajouter `_default_config`**

Dans `app.py`, remplacer toute la fonction `_empty_day` (l.76-99) par :
```python
def _default_config():
    return {"responsable": "", "quart": "", "personnel": [], "equipements": []}


def _empty_day():
    return {
        "date": None,
        "description": "",
        "responsable": "",     # vide => hérite de config au rendu/export
        "quart": "",
        "temp_am": None,
        "temp_pm": None,
        "conditions": [],
        "activites": [],       # activités choisies pour CE jour (<= 7)
        "autres": [],          # autres projets pour CE jour (<= 4)
        "heures": {},          # {ressource: {libellé_colonne: float}}
        "prime": {},           # {ressource: float}
        "commentaire_ligne": {},  # {ressource: str}
        "commentaires": "",
        "revu_par": "",
    }
```

- [ ] **Step 4: Mettre à jour `init_state` pour la `config`**

Dans `app.py`, remplacer `init_state` (l.66-73) par :
```python
def init_state():
    if "ref" not in st.session_state:
        st.session_state.ref = _load_refdata_file()
    if "projet" not in st.session_state:
        st.session_state.projet = {"no": "", "semaine": date.today(), "adresse": ""}
    st.session_state.projet.setdefault("adresse", "")
    if "config" not in st.session_state:
        st.session_state.config = _default_config()
    if "jours" not in st.session_state:
        st.session_state.jours = {j: _empty_day() for j in JOURS}
```

- [ ] **Step 5: Lancer les tests (succès attendu)**

Run: `.venv/bin/pytest tests/test_model.py -q`
Expected : 2 passed.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_model.py
git commit -m "feat: new weekly-config data model (config + per-day hours dict)"
```

---

## Task 2: Fonctions pures — colonnes du jour, roster, grille

**Files:**
- Modify: `app.py` — ajouter après `col_totals` (après l.112)
- Test: `tests/test_model.py`

- [ ] **Step 1: Écrire les tests des helpers de grille**

Ajouter à `tests/test_model.py` :
```python
import pandas as pd


def _sample_config():
    return {"responsable": "M.", "quart": "Jour",
            "personnel": ["Mathis", "Roy"], "equipements": ["Camion v1892"]}


def _sample_day():
    d = app._empty_day()
    d["activites"] = ["Excavation"]
    d["autres"] = ["P-77"]
    d["heures"] = {"Mathis": {"960": 8.0, "Excavation": 4.0, "P-77": 2.0},
                   "Camion v1892": {"960": 8.0}}
    d["prime"] = {"Mathis": 2.0}
    d["commentaire_ligne"] = {"Mathis": "test"}
    return d


def test_day_columns():
    d = _sample_day()
    assert app._day_columns(d) == ["960", "Excavation", "P-77"]


def test_roster_order_and_types():
    r = app._roster(_sample_config())
    assert r == [("Mathis", "P"), ("Roy", "P"), ("Camion v1892", "E")]


def test_day_grid_df():
    df = app._day_grid_df(_sample_config(), _sample_day())
    assert list(df.columns) == ["Ressource", "Type", "960", "Excavation",
                                "P-77", "Prime", "Total", "Commentaire"]
    assert list(df["Ressource"]) == ["Mathis", "Roy", "Camion v1892"]
    mathis = df[df["Ressource"] == "Mathis"].iloc[0]
    assert mathis["Type"] == "👷"
    assert mathis["960"] == 8.0 and mathis["Excavation"] == 4.0
    assert mathis["Prime"] == 2.0
    assert mathis["Total"] == 14.0          # heures seules : 8+4+2 (hors prime)
    assert mathis["Commentaire"] == "test"
    camion = df[df["Ressource"] == "Camion v1892"].iloc[0]
    assert camion["Type"] == "🚜"
    assert camion["Total"] == 8.0


def test_grid_df_to_day_roundtrip():
    config, day = _sample_config(), _sample_day()
    df = app._day_grid_df(config, day)
    # simule une édition : Roy travaille 5 h sur 960
    df.loc[df["Ressource"] == "Roy", "960"] = 5.0
    out = app._empty_day()
    out["activites"], out["autres"] = day["activites"], day["autres"]
    app._grid_df_to_day(df, config, out)
    assert out["heures"]["Roy"] == {"960": 5.0}
    assert out["heures"]["Mathis"]["Excavation"] == 4.0
    assert out["prime"]["Mathis"] == 2.0
    assert out["commentaire_ligne"]["Mathis"] == "test"
    # une ressource sans heures ni prime ni commentaire n'apparaît pas
    assert "Camion v1892" in out["heures"]  # avait 960=8
```

- [ ] **Step 2: Lancer (échec attendu)**

Run: `.venv/bin/pytest tests/test_model.py -q`
Expected : FAIL — `_day_columns` etc. non définis.

- [ ] **Step 3: Implémenter les helpers**

Dans `app.py`, ajouter après `col_totals` (après l.112) :
```python
FIXED_COL = "960"        # 1re colonne d'heures, toujours présente


def _day_columns(day):
    """Colonnes d'heures affichées pour ce jour : 960 + activités + autres."""
    return [FIXED_COL] + list(day["activites"]) + list(day["autres"])


def _roster(config):
    """Liste ordonnée (libellé, type) ; type 'P' = personnel, 'E' = équipement."""
    return ([(n, "P") for n in config.get("personnel", [])]
            + [(e, "E") for e in config.get("equipements", [])])


def _row_hours(hours_map, cols):
    """Somme des heures (hors prime) pour les colonnes données."""
    return float(sum(float(hours_map.get(c) or 0) for c in cols))


def _day_grid_df(config, day):
    """DataFrame pour la grille combinée du jour (lignes = roster)."""
    cols = _day_columns(day)
    rows = []
    for name, typ in _roster(config):
        h = day["heures"].get(name, {})
        row = {"Ressource": name, "Type": "👷" if typ == "P" else "🚜"}
        for c in cols:
            row[c] = h.get(c)
        row["Prime"] = day["prime"].get(name)
        row["Total"] = _row_hours(h, cols)
        row["Commentaire"] = day["commentaire_ligne"].get(name, "")
        rows.append(row)
    columns = ["Ressource", "Type"] + cols + ["Prime", "Total", "Commentaire"]
    return pd.DataFrame(rows, columns=columns)


def _grid_df_to_day(edited, config, day):
    """Réécrit heures/prime/commentaire_ligne du jour depuis la grille éditée."""
    cols = _day_columns(day)
    heures, prime, comm = {}, {}, {}
    for _, r in edited.iterrows():
        name = r["Ressource"]
        hh = {}
        for c in cols:
            v = pd.to_numeric(r.get(c), errors="coerce")
            if pd.notna(v) and float(v) != 0:
                hh[c] = float(v)
        if hh:
            heures[name] = hh
        p = pd.to_numeric(r.get("Prime"), errors="coerce")
        if pd.notna(p) and float(p) != 0:
            prime[name] = float(p)
        cm = r.get("Commentaire")
        if isinstance(cm, str) and cm.strip():
            comm[name] = cm
    day["heures"], day["prime"], day["commentaire_ligne"] = heures, prime, comm
    return day
```

- [ ] **Step 4: Lancer (succès attendu)**

Run: `.venv/bin/pytest tests/test_model.py -q`
Expected : tous passent.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_model.py
git commit -m "feat: pure helpers for combined day grid (columns, roster, df build/writeback)"
```

---

## Task 3: Adaptateur d'export + branchement de `build_workbook`

**Files:**
- Modify: `app.py` — ajouter `_day_to_legacy` / `_legacy_day` après les helpers de Task 2 ; remplacer `build_workbook` (l.258-279)
- Test: `tests/test_model.py`

- [ ] **Step 1: Écrire les tests de l'adaptateur + export**

Ajouter à `tests/test_model.py` :
```python
from openpyxl import load_workbook
from io import BytesIO


def test_day_to_legacy_maps_labels_to_keys():
    headers, pers, equip = app._day_to_legacy(_sample_config(), _sample_day())
    assert headers["h0"] == "960"
    assert headers["h1"] == "Excavation"
    assert headers["a0"] == "P-77"
    # toutes les clés d'heures existent dans les DataFrames
    for k in app.HOUR_KEYS:
        assert k in pers.columns and k in equip.columns
    assert list(pers["Nom"]) == ["Mathis", "Roy"]
    assert list(equip["Véhicule"]) == ["Camion v1892"]
    mathis = pers[pers["Nom"] == "Mathis"].iloc[0]
    assert mathis["h0"] == 8.0 and mathis["h1"] == 4.0 and mathis["a0"] == 2.0
    assert mathis["Prime"] == 2.0 and mathis["Commentaire"] == "test"


def test_build_workbook_with_new_model():
    config = _sample_config()
    jours = {j: app._empty_day() for j in app.JOURS}
    mardi = jours["Mardi"]
    import datetime
    mardi["date"] = datetime.date(2026, 6, 9)
    mardi["activites"] = ["Excavation"]
    mardi["heures"] = {"Mathis": {"960": 8.0, "Excavation": 4.0},
                       "Camion v1892": {"960": 8.0}}
    proj = {"no": "P-1", "semaine": datetime.date(2026, 6, 7), "adresse": ""}
    buf = app.build_workbook(proj=proj, jours=jours, config=config)
    wb = load_workbook(BytesIO(buf.getvalue()))
    assert "Synthèse" in wb.sheetnames
    assert "Mardi" in wb.sheetnames           # jour rempli présent
    assert "Dimanche" not in wb.sheetnames     # jour vide exclu
```

- [ ] **Step 2: Lancer (échec attendu)**

Run: `.venv/bin/pytest tests/test_model.py -q`
Expected : FAIL — `_day_to_legacy` non défini ; `build_workbook` ne prend pas `config`.

- [ ] **Step 3: Implémenter l'adaptateur**

Dans `app.py`, ajouter après `_grid_df_to_day` :
```python
def _day_to_legacy(config, day):
    """Reconstruit (headers, pers, equip) au format historique attendu par
    l'export Excel, à partir du nouveau modèle."""
    acts = list(day["activites"])[:7]
    autres = list(day["autres"])[:4]
    headers = {f"h{i}": "" for i in range(8)}
    headers.update({f"a{i}": "" for i in range(4)})
    headers["h0"] = "960"
    label_to_key = {FIXED_COL: "h0"}
    for i, lbl in enumerate(acts):
        headers[f"h{i + 1}"] = lbl
        label_to_key[lbl] = f"h{i + 1}"
    for i, lbl in enumerate(autres):
        headers[f"a{i}"] = lbl
        label_to_key[lbl] = f"a{i}"

    def build_df(resources, label_col):
        recs = []
        for name in resources:
            h = day["heures"].get(name, {})
            rec = {label_col: name}
            for k in HOUR_KEYS:
                rec[k] = None
            for label, key in label_to_key.items():
                if label in h:
                    rec[key] = float(h[label])
            rec["Prime"] = day["prime"].get(name)
            rec["Commentaire"] = day["commentaire_ligne"].get(name, "")
            recs.append(rec)
        cols = [label_col] + HOUR_KEYS + ["Prime", "Commentaire"]
        return pd.DataFrame(recs, columns=cols)

    pers = build_df(config.get("personnel", []), "Nom")
    equip = build_df(config.get("equipements", []), "Véhicule")
    return headers, pers, equip


def _legacy_day(config, day):
    """Jour au format historique (champs scalaires + headers/pers/equip)."""
    headers, pers, equip = _day_to_legacy(config, day)
    return {
        "date": day.get("date"),
        "description": day.get("description", ""),
        "responsable": day.get("responsable") or config.get("responsable", ""),
        "quart": day.get("quart") or config.get("quart", ""),
        "temp_am": day.get("temp_am"),
        "temp_pm": day.get("temp_pm"),
        "conditions": day.get("conditions", []),
        "headers": headers,
        "pers": pers,
        "equip": equip,
        "commentaires": day.get("commentaires", ""),
        "revu_par": day.get("revu_par", ""),
    }
```

- [ ] **Step 4: Brancher `build_workbook` sur l'adaptateur**

Remplacer `build_workbook` (l.258-279) par :
```python
def build_workbook(proj=None, jours=None, config=None):
    from openpyxl import Workbook

    if proj is None:
        proj = st.session_state.projet
    if jours is None:
        jours = st.session_state.jours
    if config is None:
        config = st.session_state.config

    legacy = {j: _legacy_day(config, jours[j]) for j in JOURS}

    wb = Workbook()
    _build_synthese(wb.active, proj, legacy)
    for jour in JOURS:
        if not _day_has_data(legacy[jour]):
            continue
        ws = wb.create_sheet(jour)
        _build_day_sheet(ws, jour, legacy[jour], proj)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
```

- [ ] **Step 5: Lancer (succès attendu)**

Run: `.venv/bin/pytest tests/test_model.py -q`
Expected : tous passent.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_model.py
git commit -m "feat: export adapter bridging new model to existing Excel export"
```

---

## Task 4: Section « Configuration de la semaine » (UI)

**Files:**
- Modify: `app.py` — `page_saisie` (l.738-768)
- Test: `tests/test_ui.py`

- [ ] **Step 1: Écrire le test AppTest de la config**

Create `tests/test_ui.py` :
```python
from streamlit.testing.v1 import AppTest


def _run():
    return AppTest.from_file("app.py", default_timeout=30).run()


def test_week_config_widgets_present():
    at = _run()
    labels = [m.label for m in at.multiselect]
    assert "👷 Équipe (personnel)" in labels
    assert "🚜 Équipements / véhicules" in labels
    ti_labels = [t.label for t in at.text_input]
    assert "Responsable (défaut semaine)" in ti_labels


def test_setting_roster_updates_config():
    at = _run()
    equipe = [m for m in at.multiselect if m.label == "👷 Équipe (personnel)"][0]
    opts = equipe.options
    assert opts, "la liste de personnel de référence ne doit pas être vide"
    equipe.set_value([opts[0]]).run()
    assert at.session_state["config"]["personnel"] == [opts[0]]
```

- [ ] **Step 2: Lancer (échec attendu)**

Run: `.venv/bin/pytest tests/test_ui.py -q`
Expected : FAIL — widgets de config absents.

- [ ] **Step 3: Réécrire le haut de `page_saisie` avec la config de semaine**

Remplacer le corps de `page_saisie` (l.738-768) par la version ci-dessous. Elle conserve la ligne projet + météo existante, ajoute la config de semaine, puis appelle le rendu par jour (implémenté en Task 5) :
```python
def page_saisie():
    proj = st.session_state.projet
    config = st.session_state.config
    ref = st.session_state.ref

    with st.container(border=True):
        c1, c2 = st.columns([2, 1])
        proj["no"] = c1.text_input("No Projet", proj["no"])
        proj["semaine"] = c2.date_input("Semaine du", proj["semaine"])
        c2.caption("Les dates des 7 jours se remplissent automatiquement "
                   "(Dimanche = la date choisie).")
        _apply_week_dates(proj["semaine"])

        a1, a2 = st.columns([3, 1])
        proj["adresse"] = a1.text_input(
            "Adresse du chantier", proj.get("adresse", ""),
            placeholder="ex. 1234 rue Principale, Trois-Rivières, QC",
            help="Sert à remplir automatiquement la météo des 7 jours "
                 "(l'adresse est envoyée à OpenStreetMap et Open-Meteo).")
        a2.markdown("<div style='height:1.8rem'></div>", unsafe_allow_html=True)
        if a2.button("🌦️ Remplir la météo", width="stretch"):
            with st.spinner("Récupération de la météo…"):
                level, msg = _fill_week_weather(proj, st.session_state.jours)
            getattr(st, level)(msg)

    filled = bool(config["personnel"] or config["equipements"])
    with st.expander("⚙️ Configuration de la semaine", expanded=not filled):
        st.caption("Équipe, équipements et valeurs par défaut — définis une "
                   "seule fois pour les 7 jours. Les activités se choisissent "
                   "par jour, plus bas.")
        e1, e2 = st.columns(2)
        config["personnel"] = e1.multiselect(
            "👷 Équipe (personnel)", ref["personnel"],
            default=[p for p in config["personnel"] if p in ref["personnel"]],
            key="cfg_personnel")
        config["equipements"] = e2.multiselect(
            "🚜 Équipements / véhicules", ref["vehicules"],
            default=[v for v in config["equipements"] if v in ref["vehicules"]],
            key="cfg_equipements")
        r1, r2 = st.columns(2)
        config["responsable"] = r1.text_input(
            "Responsable (défaut semaine)", config["responsable"],
            key="cfg_resp")
        config["quart"] = r2.selectbox(
            "Quart de travail (défaut semaine)", QUARTS,
            index=QUARTS.index(config["quart"]) if config["quart"] in QUARTS else 0,
            key="cfg_quart")

    _day_selector_and_entry()
```

NOTE : `_day_selector_and_entry()` est défini en Task 5. Tant qu'il n'existe pas, ce test échouera à l'exécution de l'app ; définir un stub minimal temporaire juste après `page_saisie` pour que Task 4 tourne seule :
```python
def _day_selector_and_entry():
    pass
```
(Ce stub sera remplacé en Task 5.)

- [ ] **Step 4: Lancer (succès attendu)**

Run: `.venv/bin/pytest tests/test_ui.py -q`
Expected : 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_ui.py
git commit -m "feat: weekly configuration section (roster + defaults)"
```

---

## Task 5: Sélecteur de jour sticky + squelette de rendu du jour

**Files:**
- Modify: `app.py` — remplacer le stub `_day_selector_and_entry` ; ajouter le CSS sticky dans `_CSS`
- Test: `tests/test_ui.py`

> **Choix d'implémentation :** on utilise `st.radio(..., horizontal=True)` (et non `st.segmented_control`) pour le sélecteur de jour : `AppTest` le supporte pleinement (`at.radio`), et le CSS lui donne l'allure de pastilles segmentées. C'est une déviation assumée de la maquette (look identique, testabilité garantie).

- [ ] **Step 1: Écrire le test du sélecteur de jour**

Ajouter à `tests/test_ui.py` :
```python
def test_day_selector_present_and_default():
    at = _run()
    assert at.session_state["jour_actif"] == "Dimanche"


def test_switching_day_changes_active():
    at = _run()
    jour_radio = [r for r in at.radio if r.key == "jour_actif"][0]
    jour_radio.set_value("Mardi").run()
    assert at.session_state["jour_actif"] == "Mardi"
```

- [ ] **Step 2: Lancer (échec attendu)**

Run: `.venv/bin/pytest tests/test_ui.py::test_day_selector_present_and_default -q`
Expected : FAIL — pas de radio `jour_actif`.

- [ ] **Step 3: Implémenter `_day_selector_and_entry` (squelette)**

Remplacer le stub `_day_selector_and_entry` par :
```python
def _day_selector_and_entry():
    s1, s2 = st.columns([3, 1])
    jour = s1.radio("📌 Jour", JOURS, horizontal=True, key="jour_actif",
                    label_visibility="collapsed")
    day = st.session_state.jours[jour]
    total = _day_total(st.session_state.config, day)
    s2.metric("Total du jour", f"{total:.2f} h")

    _render_day(jour)
```

- [ ] **Step 4: Ajouter le helper `_day_total`**

Ajouter près des helpers de grille (après `_grid_df_to_day`) :
```python
def _day_total(config, day):
    """Total des heures (hors prime) de toutes les ressources du jour."""
    cols = _day_columns(day)
    return float(sum(_row_hours(h, cols) for h in day["heures"].values()))
```

- [ ] **Step 5: Ajouter le test du total au modèle**

Ajouter à `tests/test_model.py` :
```python
def test_day_total():
    assert app._day_total(_sample_config(), _sample_day()) == 22.0  # 8+4+2 + 8
```

- [ ] **Step 6: Style sticky du sélecteur (pastilles + collé en haut)**

Dans `app.py`, dans la chaîne `_CSS` (juste avant `</style>`), ajouter (noter les accolades doublées `{{ }}` car `_CSS` est une f-string) :
```css
/* Bloc contenant le sélecteur de jour : collé en haut */
div[data-testid="stHorizontalBlock"]:has(div[role="radiogroup"]) {{
    position: sticky; top: 0; z-index: 998;
    background: #fff; padding: .3rem 0; border-bottom: 1px solid #e3eef0;
}}
/* Allure « pastilles segmentées » pour le radio horizontal du jour */
div[role="radiogroup"] label {{
    border: 1px solid #cfe3e6; border-radius: 8px; padding: 2px 10px;
    margin-right: 4px;
}}
```

- [ ] **Step 7: Lancer les tests (succès attendu)**

Run: `.venv/bin/pytest tests/test_ui.py tests/test_model.py -q`
Expected : tous passent. (Le `_render_day` actuel reçoit toujours `jour` ; il sera réécrit en Task 6-7. S'il échoue à l'exécution sous AppTest à cause de l'ancien modèle, exécuter d'abord Task 6.)

- [ ] **Step 8: Commit**

```bash
git add app.py tests/test_ui.py tests/test_model.py
git commit -m "feat: sticky day selector with running day total"
```

---

## Task 6: Activités du jour + grille combinée (cœur de `_render_day`)

**Files:**
- Modify: `app.py` — réécrire `_render_day` (l.770-851), supprimer `grid_editor` (l.118-166) et `_show_totals` (l.853-857)
- Test: `tests/test_ui.py`

- [ ] **Step 1: Écrire le test de la grille combinée**

Ajouter à `tests/test_ui.py` :
```python
import app as appmod


def test_combined_grid_reflects_roster():
    at = _run()
    # configurer un roster
    eq = [m for m in at.multiselect if m.label == "👷 Équipe (personnel)"][0]
    p = eq.options[0]
    eq.set_value([p]).run()
    assert not at.exception, "l'app ne doit pas lever d'exception"
    # la grille calculée pour le jour actif contient la ressource
    config = at.session_state["config"]
    day = at.session_state["jours"][at.session_state["jour_actif"]]
    df = appmod._day_grid_df(config, day)
    assert p in list(df["Ressource"])


def test_activities_of_day_multiselect_present():
    at = _run()
    labels = [m.label for m in at.multiselect]
    assert "🏗️ Activités du jour" in labels
    assert "Autres projets du jour" in labels
```

- [ ] **Step 2: Lancer (échec attendu)**

Run: `.venv/bin/pytest tests/test_ui.py::test_activities_of_day_multiselect_present -q`
Expected : FAIL.

- [ ] **Step 3: Réécrire `_render_day`**

Remplacer toute la fonction `_render_day` (l.770-851) par :
```python
def _render_day(jour):
    day = st.session_state.jours[jour]
    config = st.session_state.config
    ref = st.session_state.ref

    # --- En-tête du jour (compact) -------------------------------------
    with st.container(border=True):
        st.markdown("##### 📅 En-tête du jour")
        h1, h2, h3 = st.columns(3)
        day["date"] = h1.date_input("Date", key=f"{jour}_date")
        st.session_state.setdefault(f"{jour}_resp", day["responsable"]
                                    or config["responsable"])
        day["responsable"] = h2.text_input("Responsable", key=f"{jour}_resp")
        _q_default = day["quart"] or config["quart"]
        day["quart"] = h3.selectbox(
            "Quart de travail", QUARTS,
            index=QUARTS.index(_q_default) if _q_default in QUARTS else 0,
            key=f"{jour}_quart")
        day["description"] = st.text_input("Description", day["description"],
                                           key=f"{jour}_desc")
        st.session_state.setdefault(f"{jour}_tam", day["temp_am"])
        st.session_state.setdefault(f"{jour}_tpm", day["temp_pm"])
        st.session_state.setdefault(f"{jour}_cond", day["conditions"])
        m1, m2, m3 = st.columns([1, 1, 3])
        day["temp_am"] = m1.number_input("Temp. A.M. (°C)", step=1.0,
                                         key=f"{jour}_tam", format="%.0f")
        day["temp_pm"] = m2.number_input("Temp. P.M. (°C)", step=1.0,
                                         key=f"{jour}_tpm", format="%.0f")
        day["conditions"] = m3.multiselect("Conditions atmosphériques",
                                           CONDITIONS, key=f"{jour}_cond")

    # --- Activités du jour + grille d'heures ---------------------------
    with st.container(border=True):
        st.markdown(f"##### 🕐 Heures — {jour}")
        ac1, ac2 = st.columns(2)
        day["activites"] = ac1.multiselect(
            "🏗️ Activités du jour", ref["activites"],
            default=[a for a in day["activites"] if a in ref["activites"]],
            max_selections=7, key=f"{jour}_acts")
        day["autres"] = ac2.multiselect(
            "Autres projets du jour", ref["autres_projets"],
            default=[a for a in day["autres"] if a in ref["autres_projets"]],
            max_selections=4, key=f"{jour}_autres")

        if not config["personnel"] and not config["equipements"]:
            st.info("Configure l'équipe et les équipements dans "
                    "« ⚙️ Configuration de la semaine » pour saisir les heures.")
        else:
            df = _day_grid_df(config, day)
            cols = _day_columns(day)
            colcfg = {
                "Ressource": st.column_config.TextColumn("Ressource",
                                                         disabled=True),
                "Type": st.column_config.TextColumn("Type", disabled=True,
                                                    width="small"),
                "Prime": st.column_config.NumberColumn("Prime", min_value=0,
                                                       step=0.5, format="%.2f"),
                "Total": st.column_config.NumberColumn("Total", disabled=True,
                                                       format="%.2f"),
                "Commentaire": st.column_config.TextColumn("Commentaire",
                                                           width="medium"),
            }
            for c in cols:
                lbl = "960" if c == FIXED_COL else c
                colcfg[c] = st.column_config.NumberColumn(
                    lbl, min_value=0, step=0.5, format="%.2f")
            edited = st.data_editor(
                df, column_config=colcfg, hide_index=True,
                num_rows="fixed", width="stretch", key=f"grid_{jour}")
            _grid_df_to_day(edited, config, day)
            _render_totals_row(config, day)

    # --- Commentaires & signature --------------------------------------
    with st.container(border=True):
        st.markdown("##### 📝 Commentaires & signature")
        day["commentaires"] = st.text_area(
            "Commentaires / plaintes / suggestions",
            day["commentaires"], key=f"{jour}_com")
        day["revu_par"] = st.text_input("Revu par", day["revu_par"],
                                        key=f"{jour}_revu")
```

- [ ] **Step 4: Ajouter `_render_totals_row` (ligne de totaux sous la grille)**

Ajouter après `_render_day` :
```python
def _render_totals_row(config, day):
    cols = _day_columns(day)
    sums = {c: 0.0 for c in cols}
    prime_sum = 0.0
    for h in day["heures"].values():
        for c in cols:
            sums[c] += float(h.get(c) or 0)
    for p in day["prime"].values():
        prime_sum += float(p or 0)
    total = sum(sums.values())
    parts = " · ".join(f"{('960' if c == FIXED_COL else c)} : {sums[c]:.2f}"
                       for c in cols)
    st.caption(f"**Totaux** — {parts} · Prime : {prime_sum:.2f} · "
               f"**Total jour : {total:.2f} h**")
```

- [ ] **Step 5: Supprimer `grid_editor` et `_show_totals` (code mort)**

Supprimer entièrement la fonction `grid_editor` (l.118-166) et la fonction `_show_totals` (l.853-857). Vérifier qu'aucun autre appel n'y subsiste :

Run: `grep -n "grid_editor\|_show_totals" app.py`
Expected : aucune occurrence.

- [ ] **Step 6: Lancer tous les tests UI + modèle**

Run: `.venv/bin/pytest tests/ -q`
Expected : tous passent.

- [ ] **Step 7: Vérifier le démarrage de l'app**

Run:
```bash
.venv/bin/streamlit run app.py --server.headless true --server.port 8620 >/tmp/st.log 2>&1 &
sleep 6
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8620/
grep -iE "error|traceback|exception" /tmp/st.log | grep -v "No runtime" || echo "OK aucune erreur"
kill %1 2>/dev/null
```
Expected : `200` et `OK aucune erreur`.

- [ ] **Step 8: Commit**

```bash
git add app.py tests/
git commit -m "feat: per-day activities picker + combined Personnel/Équipement grid"
```

---

## Task 7: Adapter le remplissage météo au nouveau rendu

**Files:**
- Modify: `app.py` — `_fill_week_weather` (l.672-718)
- Test: `tests/test_ui.py`

- [ ] **Step 1: Écrire le test météo de bout en bout (réseau réel)**

Ajouter à `tests/test_ui.py` :
```python
import datetime
import pytest


def test_weather_fill_sets_selected_day_widgets():
    at = AppTest.from_file("app.py", default_timeout=60).run()
    sem = [d for d in at.date_input if d.label == "Semaine du"][0]
    sem.set_value(datetime.date(2026, 6, 7)).run()
    adr = [t for t in at.text_input if t.label == "Adresse du chantier"][0]
    adr.set_value("450 rue Adanac, Beauport, QC").run()
    btn = [b for b in at.button if "météo" in b.label][0]
    try:
        btn.click().run()
    except Exception:
        pytest.skip("réseau indisponible pour la météo")
    # Dimanche est le jour actif par défaut → ses champs sont renseignés
    assert at.session_state["Dimanche_tam"] is not None
    assert at.session_state["Dimanche_cond"]  # liste non vide
```

- [ ] **Step 2: Lancer (peut échouer si l'ancien `_fill_week_weather` écrit des clés inexistantes)**

Run: `.venv/bin/pytest tests/test_ui.py::test_weather_fill_sets_selected_day_widgets -q`
Expected : FAIL ou comportement incohérent (les clés de widgets des jours non rendus n'existent pas).

- [ ] **Step 3: Adapter `_fill_week_weather`**

Dans `app.py`, dans la boucle de `_fill_week_weather` (l.672-718), remplacer le bloc d'écriture (les trois `if w[...]` qui font `day[...] = ...` puis `st.session_state[...] = ...`) par une écriture de l'état du jour + purge des clés de widgets, afin que CHAQUE jour se re-amorce depuis l'état au prochain affichage :
```python
        if w["temp_am"] is not None:
            day["temp_am"] = float(w["temp_am"])
        if w["temp_pm"] is not None:
            day["temp_pm"] = float(w["temp_pm"])
        if w["conditions"]:
            day["conditions"] = w["conditions"]
        for suffix in ("_tam", "_tpm", "_cond"):
            st.session_state.pop(f"{jour}{suffix}", None)
        filled += 1
```
(Le `jour` de la boucle est la clé du dict `jours` ; comme seuls les widgets du jour affiché existent, `pop(..., None)` est sans risque pour les autres.)

- [ ] **Step 4: Lancer (succès attendu, sinon skip réseau)**

Run: `.venv/bin/pytest tests/test_ui.py::test_weather_fill_sets_selected_day_widgets -q`
Expected : PASS (ou SKIP si réseau indisponible).

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_ui.py
git commit -m "fix: weather fill writes per-day state and resets day widgets"
```

---

## Task 8: Régression d'export & nettoyage final

**Files:**
- Test: `tests/test_model.py`
- Modify: `app.py` — retirer `TEMPLATE_PATH` si inutilisé

- [ ] **Step 1: Test de régression — un export complet réaliste**

Ajouter à `tests/test_model.py` :
```python
def test_full_export_two_days():
    import datetime
    config = {"responsable": "M. Côté", "quart": "Jour",
              "personnel": ["Mathis", "Roy"], "equipements": ["Camion v1892"]}
    jours = {j: app._empty_day() for j in app.JOURS}
    lun = jours["Lundi"]
    lun["date"] = datetime.date(2026, 6, 8)
    lun["activites"] = ["Excavation"]
    lun["heures"] = {"Mathis": {"960": 8.0, "Excavation": 4.0},
                     "Roy": {"960": 8.0}, "Camion v1892": {"960": 8.0}}
    lun["prime"] = {"Mathis": 1.5}
    lun["commentaire_ligne"] = {"Mathis": "heures supp"}
    lun["commentaires"] = "RAS"
    mar = jours["Mardi"]
    mar["date"] = datetime.date(2026, 6, 9)
    mar["heures"] = {"Roy": {"960": 7.5}}
    proj = {"no": "P-2026", "semaine": datetime.date(2026, 6, 7), "adresse": ""}
    buf = app.build_workbook(proj=proj, jours=jours, config=config)
    wb = load_workbook(BytesIO(buf.getvalue()))
    assert wb.sheetnames[:1] == ["Synthèse"]
    assert "Lundi" in wb.sheetnames and "Mardi" in wb.sheetnames
    assert "Dimanche" not in wb.sheetnames
    # responsable hérité de la config visible sur la feuille Lundi
    lundi = wb["Lundi"]
    found = any(lundi.cell(r, c).value == "M. Côté"
                for r in range(1, 12) for c in range(1, 8))
    assert found
```

- [ ] **Step 2: Lancer (succès attendu)**

Run: `.venv/bin/pytest tests/test_model.py::test_full_export_two_days -q`
Expected : PASS.

- [ ] **Step 3: Retirer la constante inutilisée `TEMPLATE_PATH`**

Run: `grep -n "TEMPLATE_PATH" app.py`
Si la seule occurrence est sa définition (l.24), la supprimer. Sinon, laisser.

- [ ] **Step 4: Suite complète + démarrage app**

Run:
```bash
.venv/bin/pytest tests/ -q
.venv/bin/streamlit run app.py --server.headless true --server.port 8621 >/tmp/st.log 2>&1 &
sleep 6
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8621/
grep -iE "error|traceback|exception|use_container_width" /tmp/st.log | grep -v "No runtime" || echo "OK"
kill %1 2>/dev/null
```
Expected : tous les tests passent ; `200` ; `OK`.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_model.py
git commit -m "test: full export regression + remove unused TEMPLATE_PATH"
```

---

## Notes d'implémentation

- **Pourquoi `st.session_state.setdefault` pour temp/quart/conditions :** mécanique éprouvée dans le code actuel (dates, météo) — le widget lit la clé de session ; on n'écrit donc pas d'argument `value=` qui déclencherait l'avertissement « value + session_state ».
- **Total non « live » :** la colonne Total de `st.data_editor` se met à jour au rafraîchissement ; la ligne `_render_totals_row` (recalculée à chaque exécution) donne le repère fiable.
- **Limite 7 activités + 4 autres / jour :** imposée par `max_selections` sur les multiselects et par la capacité des emplacements `h1..h7` / `a0..a3` du gabarit d'export.
- **Sélecteur de jour :** `st.radio(horizontal=True)` plutôt que `st.segmented_control`, pour la testabilité `AppTest` ; CSS pour l'allure pastilles + sticky. Le sélecteur CSS `:has()` est supporté par les navigateurs récents ; en repli, le sélecteur reste fonctionnel, seulement non collé.
- **`AppTest` et `data_editor` :** l'accès programmatique à la valeur d'un `data_editor` via AppTest n'est pas fiable ; on teste donc la grille via la fonction pure `_day_grid_df` appliquée à l'état de session réel, et la justesse de l'export via les tests de `tests/test_model.py`.
