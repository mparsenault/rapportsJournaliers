# Saisie par employé : activités TR/TS et équipement par employé — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faire de la saisie d'un quart un modèle entièrement par employé : chaque employé choisit ses activités (TR/TS) et porte ses codes d'équipement + un total d'heures équipement ; remplacer la grille matricielle AgGrid par des cartes par ressource.

**Architecture:** L'état du quart conserve `heures` mais ses valeurs deviennent `{activité: {"TR": float, "TS": float}}` ; on ajoute `equip_codes` et `equip_hours` par employé. La sélection d'activités vit dans `heures` (clés). L'UI Config perd la carte « Activités » ; l'UI Saisie devient une carte (`st.expander`) par ressource. La persistance Postgres ajoute `report_hours.hours_ts` (le `hours` existant = TR) et `report_lines.equip_hours` / `equip_codes`.

**Tech Stack:** Python, Streamlit (widgets natifs : `st.multiselect`, `st.pills`, `st.number_input`, `st.expander`), SQLAlchemy + Postgres (Neon), pytest + `streamlit.testing.v1.AppTest`.

## Global Constraints

- Python/Streamlit existant ; ne pas introduire de nouvelle dépendance. On **retire** `st_aggrid` de la vue Saisie (l'import devient inutile — voir Task 6).
- Convention de seed des widgets du fichier : **ne jamais** passer `default=`/`value=` calculé à un widget qui a aussi `key=` ; on seed `st.session_state[key]` une seule fois (si la clé est absente) puis on lit la valeur de retour. Pour `st.number_input`, suivre le motif existant des températures : `st.session_state.setdefault(key, valeur_initiale)` puis `x = st.number_input(..., key=key)`.
- `report_hours.hours` = **temps régulier (TR)** ; `report_hours.hours_ts` = **temps supplémentaire (TS)**. Rétro-compatible : données existantes = TR, `hours_ts = 0`.
- Codes d'équipement = liste fixe : `[("C","Camion"),("N","Nacelle"),("É","Éch. Hyd."),("D","Détecteur"),("G","Grue"),("BT","Chariot élév.")]`. Plusieurs par employé. Un seul total d'heures équipement par employé.
- Les tests BD réels (SQL `text[]`/`serial`/`on conflict`) ne sont **pas** reproductibles en local (cf. `tests/test_reports.py`) ; les changements `save_report`/`load_report` sont vérifiés e2e contre Neon, pas par test unitaire.
- `pytest` doit passer : lancer `.venv/bin/python -m pytest -q` à chaque fin de tâche.

---

### Task 1: Modèle d'état + constante codes + helpers de total/activités

**Files:**
- Modify: `app.py` (constantes ~ligne 54-56 ; `_empty_quart` ~188-195 ; helpers `_resource_total`/`_quart_columns`/`_quart_total` ~300-365)
- Test: `tests/test_model.py`

**Interfaces:**
- Produces:
  - `app.EQUIP_CODES: list[tuple[str, str]]` et `app.EQUIP_CODE_VALUES: list[str]`
  - `app._equip_code_label(code: str) -> str` → `"C — Camion"`
  - `app._pair_total(pair: dict) -> float` → `TR + TS` d'un couple `{"TR","TS"}`
  - `app._resource_total(quart, name: str) -> float` (somme TR+TS sur les activités)
  - `app._quart_activities(quart) -> list[str]` (union triée des activités présentes dans `heures`)
  - `app._quart_total(quart) -> float`
  - `_empty_quart()` renvoie un dict contenant `"equip_codes": {}` et `"equip_hours": {}`
- Consumes: `quart["heures"]` au format `{employé: {activité: {"TR": float, "TS": float}}}`

- [ ] **Step 1: Écrire les tests (échec attendu)**

Remplacer dans `tests/test_model.py` le helper `_sample_quart` et les tests de total/colonnes par :

```python
def _sample_quart():
    q = app._empty_quart()
    q["personnel"] = ["Mathis", "Roy"]
    q["equipements"] = ["Camion v1892"]
    q["heures"] = {"Mathis": {"Excavation": {"TR": 4.0, "TS": 0.0},
                              "P-77": {"TR": 2.0, "TS": 1.0}},
                   "Camion v1892": {"Excavation": {"TR": 8.0, "TS": 0.0}}}
    q["prime"] = {"Mathis": 2.0}
    q["commentaire_ligne"] = {"Mathis": "test"}
    q["equip_codes"] = {"Mathis": ["C", "N"]}
    q["equip_hours"] = {"Mathis": 10.0}
    return q


def test_equip_codes_constant():
    assert app.EQUIP_CODE_VALUES == ["C", "N", "É", "D", "G", "BT"]
    assert app._equip_code_label("C") == "C — Camion"


def test_pair_total():
    assert app._pair_total({"TR": 4.0, "TS": 1.0}) == 5.0
    assert app._pair_total({}) == 0.0


def test_resource_total():
    q = _sample_quart()
    assert app._resource_total(q, "Mathis") == 7.0      # (4+0) + (2+1)
    assert app._resource_total(q, "Camion v1892") == 8.0
    assert app._resource_total(q, "Inconnu") == 0.0


def test_quart_total():
    assert app._quart_total(_sample_quart()) == 15.0    # 7 + 8


def test_quart_activities_union_sorted():
    assert app._quart_activities(_sample_quart()) == ["Excavation", "P-77"]
    assert app._quart_activities(app._empty_quart()) == []
```

Mettre à jour `test_empty_day_shape` pour inclure les nouveaux champs :

```python
def test_empty_day_shape():
    d = app._empty_day()
    assert d["date"] is None
    assert list(d["quarts"].keys()) == ["Jour"]
    q = d["quarts"]["Jour"]
    assert q["heures"] == {} and q["prime"] == {} and q["commentaire_ligne"] == {}
    assert q["equip_codes"] == {} and q["equip_hours"] == {}
    assert q["personnel"] == [] and q["equipements"] == []
    assert q["responsable"] == "" and q["description"] == ""
    assert q["conditions"] == []
    assert q["temp_am"] is None and q["temp_pm"] is None
```

Mettre à jour `test_day_total_sums_quarts` (format TR/TS) :

```python
def test_day_total_sums_quarts():
    d = _sample_day()
    d["quarts"]["Soir"] = app._empty_quart()
    d["quarts"]["Soir"]["heures"] = {"Roy": {"Excavation": {"TR": 3.0, "TS": 0.0}}}
    assert app._day_total(d) == 18.0   # 15 (Jour) + 3 (Soir)
```

Supprimer `test_quart_columns` (le helper `_quart_columns` disparaît).

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `.venv/bin/python -m pytest tests/test_model.py -q`
Expected: FAIL (ex. `AttributeError: module 'app' has no attribute 'EQUIP_CODES'`, et erreurs de format sur les totaux).

- [ ] **Step 3: Implémenter**

Dans `app.py`, après `HOUR_KEYS` (ligne 56), ajouter la constante :

```python
EQUIP_CODES = [
    ("C", "Camion"), ("N", "Nacelle"), ("É", "Éch. Hyd."),
    ("D", "Détecteur"), ("G", "Grue"), ("BT", "Chariot élév."),
]
EQUIP_CODE_VALUES = [c for c, _ in EQUIP_CODES]
_EQUIP_CODE_LABELS = dict(EQUIP_CODES)


def _equip_code_label(code):
    return f"{code} — {_EQUIP_CODE_LABELS.get(code, code)}"
```

Dans `_empty_quart` (ligne 188-195), ajouter les deux champs :

```python
def _empty_quart():
    return {
        "responsable": "", "activites": [], "autres": [],
        "personnel": [], "equipements": [],
        "temp_am": None, "temp_pm": None, "conditions": [],
        "heures": {}, "prime": {}, "commentaire_ligne": {},
        "equip_codes": {}, "equip_hours": {},
        "description": "",
    }
```

Remplacer les helpers (lignes ~304-365). Retirer `_quart_columns` ; réécrire `_resource_total`/`_quart_total` ; ajouter `_pair_total` et `_quart_activities` :

```python
def _pair_total(pair):
    """Total d'un couple {'TR','TS'} -> float (0 si vide/invalide)."""
    pair = pair or {}
    return _to_hours(pair.get("TR")) + _to_hours(pair.get("TS"))

def _resource_total(quart, name):
    return float(sum(_pair_total(p) for p in quart["heures"].get(name, {}).values()))

def _quart_activities(quart):
    """Union triée des activités présentes (clés de heures, tous employés)."""
    acts = {a for acts in (quart.get("heures") or {}).values() for a in acts}
    return sorted(acts)

def _quart_total(quart):
    return float(sum(_resource_total(quart, r) for r in quart["heures"]))
```

Note : `_to_hours` est défini plus bas dans le fichier (ligne ~310) ; déplacer `_to_hours` **au-dessus** de `_pair_total` (juste après `_roster`) pour respecter l'ordre de définition, ou laisser `_pair_total`/`_resource_total` après `_to_hours`. Choisir l'ordre : `_roster`, `_to_hours`, `_pair_total`, `_resource_total`, `_quart_activities`, `_quart_total`.

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

Run: `.venv/bin/python -m pytest tests/test_model.py -q`
Expected: PASS (sauf `test_legacy_day_maps_labels_to_keys`, traité en Task 2 — il peut échouer ici ; le relancer après Task 2). Pour isoler : `.venv/bin/python -m pytest tests/test_model.py -q -k "not legacy"` → PASS.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_model.py
git commit -m "feat: modèle par employé (TR/TS, codes équipement) + helpers de total"
```

---

### Task 2: `_legacy_day` — TR/TS et champs équipement par employé

**Files:**
- Modify: `app.py` (`_legacy_day` ~373-408)
- Test: `tests/test_model.py` (`test_legacy_day_maps_labels_to_keys`)

**Interfaces:**
- Consumes: `_quart_activities` (Task 1), `_pair_total` (Task 1), `quart["equip_codes"]`, `quart["equip_hours"]`
- Produces: `_legacy_day(quart) -> dict` dont `pers` est un DataFrame avec, en plus des colonnes existantes, `"TR"`, `"TS"`, `"Hrs Éq."`, `"Code Éq."` ; les cellules d'activité (`h0..h7`,`a0..a3`) valent `TR+TS`.

- [ ] **Step 1: Écrire le test (échec attendu)**

Remplacer `test_legacy_day_maps_labels_to_keys` dans `tests/test_model.py` :

```python
def test_legacy_day_maps_labels_to_keys():
    leg = app._legacy_day(_sample_quart())
    assert leg["headers"]["h0"] == "Excavation"
    assert leg["headers"]["h1"] == "P-77"
    pers, equip = leg["pers"], leg["equip"]
    for k in app.HOUR_KEYS:
        assert k in pers.columns and k in equip.columns
    assert list(pers["Nom"]) == ["Mathis", "Roy"]
    mathis = pers[pers["Nom"] == "Mathis"].iloc[0]
    assert mathis["h0"] == 4.0          # Excavation : TR+TS = 4+0
    assert mathis["h1"] == 3.0          # P-77 : TR+TS = 2+1
    assert mathis["TR"] == 6.0 and mathis["TS"] == 1.0
    assert mathis["Hrs Éq."] == 10.0 and mathis["Code Éq."] == "C, N"
    assert mathis["Prime"] == 2.0 and mathis["Commentaire"] == "test"
    assert list(equip["Véhicule"]) == ["Camion v1892"]
    camion = equip[equip["Véhicule"] == "Camion v1892"].iloc[0]
    assert camion["h0"] == 8.0
```

(Note : l'union triée place « Excavation » en `h0` et « P-77 » en `h1` — l'ancien `a0` n'existe plus car `autres` est vide.)

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `.venv/bin/python -m pytest tests/test_model.py::test_legacy_day_maps_labels_to_keys -q`
Expected: FAIL.

- [ ] **Step 3: Implémenter**

Réécrire `_legacy_day` (lignes 373-408) :

```python
def _legacy_day(quart):
    acts = _quart_activities(quart)[:8]
    autres = list(quart["autres"])[:4]
    headers = {f"h{i}": "" for i in range(8)}
    headers.update({f"a{i}": "" for i in range(4)})
    label_to_key = {}
    for i, lbl in enumerate(acts):
        headers[f"h{i}"] = lbl
        label_to_key[lbl] = f"h{i}"
    for i, lbl in enumerate(autres):
        headers[f"a{i}"] = lbl
        label_to_key[lbl] = f"a{i}"

    def build_df(resources, label_col, with_equip=False):
        recs = []
        for name in resources:
            h = quart["heures"].get(name, {})
            rec = {label_col: name}
            for k in HOUR_KEYS:
                rec[k] = None
            for label, key in label_to_key.items():
                if label in h:
                    rec[key] = _pair_total(h[label])
            rec["TR"] = float(sum(_to_hours(p.get("TR")) for p in h.values()))
            rec["TS"] = float(sum(_to_hours(p.get("TS")) for p in h.values()))
            if with_equip:
                rec["Hrs Éq."] = quart["equip_hours"].get(name)
                rec["Code Éq."] = ", ".join(quart["equip_codes"].get(name, []))
            rec["Prime"] = quart["prime"].get(name)
            rec["Commentaire"] = quart["commentaire_ligne"].get(name, "")
            recs.append(rec)
        cols = [label_col] + HOUR_KEYS + ["TR", "TS"]
        if with_equip:
            cols += ["Hrs Éq.", "Code Éq."]
        cols += ["Prime", "Commentaire"]
        return pd.DataFrame(recs, columns=cols)

    return {
        "description": quart.get("description", ""),
        "responsable": quart.get("responsable", ""),
        "temp_am": quart.get("temp_am"), "temp_pm": quart.get("temp_pm"),
        "conditions": quart.get("conditions", []), "headers": headers,
        "pers": build_df(quart.get("personnel", []), "Nom", with_equip=True),
        "equip": build_df(quart.get("equipements", []), "Véhicule"),
    }
```

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

Run: `.venv/bin/python -m pytest tests/test_model.py -q`
Expected: PASS (tout le fichier).

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_model.py
git commit -m "feat: _legacy_day expose TR/TS et codes/Hrs équipement par employé"
```

---

### Task 3: Migrations de schéma (`report_hours.hours_ts`, `report_lines.equip_*`)

**Files:**
- Modify: `reports.py` (`_DDL_STATEMENTS`, après la ligne 142 `drop constraint ... report_lines_pkey`)
- Test: `tests/test_reports.py`

**Interfaces:**
- Produces: `reports._DDL_STATEMENTS` contient les 3 nouvelles instructions `alter table ... add column if not exists ...`.

- [ ] **Step 1: Écrire le test (échec attendu)**

Ajouter dans `tests/test_reports.py` :

```python
def test_ddl_has_tr_ts_and_equip_migrations():
    ddl = " ".join(reports._DDL_STATEMENTS)
    assert "report_hours add column if not exists hours_ts" in ddl
    assert "report_lines add column if not exists equip_hours" in ddl
    assert "report_lines add column if not exists equip_codes" in ddl
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `.venv/bin/python -m pytest tests/test_reports.py::test_ddl_has_tr_ts_and_equip_migrations -q`
Expected: FAIL (AssertionError).

- [ ] **Step 3: Implémenter**

Dans `reports.py`, juste après la ligne `"alter table report_lines drop constraint if exists report_lines_pkey",` (ligne 142) et avant le backfill `report_quart_resources`, ajouter :

```python
    # Heures : séparer temps régulier (hours, existant) et temps supplémentaire.
    # Rétro-compatible : les données existantes comptent comme du TR, hours_ts = 0.
    "alter table report_hours add column if not exists hours_ts numeric not null default 0",
    # Équipement rattaché à l'employé : total d'heures + liste de codes (C/N/É/D/G/BT).
    "alter table report_lines add column if not exists equip_hours numeric",
    "alter table report_lines add column if not exists equip_codes text[] not null default '{}'",
```

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

Run: `.venv/bin/python -m pytest tests/test_reports.py -q`
Expected: PASS (4 tests existants + le nouveau).

- [ ] **Step 5: Commit**

```bash
git add reports.py tests/test_reports.py
git commit -m "feat: migrations report_hours.hours_ts et report_lines.equip_hours/equip_codes"
```

---

### Task 4: Persistance `save_report` / `load_report` (TR/TS + équipement)

**Files:**
- Modify: `reports.py` (`save_report` ~252-282 ; `load_report` ~322-355)

**Interfaces:**
- Consumes: état du quart `{"heures": {emp: {act: {"TR","TS"}}}, "equip_codes": {emp:[...]}, "equip_hours": {emp: float}, "prime": {...}, "commentaire_ligne": {...}}`
- Produces: `load_report(...)` renvoie des quarts dont `heures[emp][act] = {"TR": float, "TS": float}`, plus `equip_codes` et `equip_hours` par employé.

> Pas de test unitaire (SQL Postgres non reproductible en local — cf. Global Constraints). Vérification = import sans erreur + tests existants verts + contrôle e2e contre Neon (Step 4).

- [ ] **Step 1: Modifier `save_report`**

Dans `reports.py`, à l'insertion du quart (~252-258), remplacer l'écriture de `acts` par l'**union** dérivée des heures. Remplacer :

```python
                     "acts": list(quart.get("activites") or []),
```
par :
```python
                     "acts": sorted({a for acts in (quart.get("heures") or {}).values() for a in acts}),
```

Remplacer la boucle `report_hours` (lignes 268-274) par :

```python
                for resource_name, acts in (quart.get("heures") or {}).items():
                    for activity_label, pair in (acts or {}).items():
                        tr = float((pair or {}).get("TR") or 0.0)
                        ts = float((pair or {}).get("TS") or 0.0)
                        if tr == 0.0 and ts == 0.0:
                            continue
                        s.execute(text("insert into report_hours "
                                       "(quart_id, resource_name, activity_label, hours, hours_ts) "
                                       "values (:q, :rn, :al, :h, :hts)"),
                                  {"q": quart_id, "rn": resource_name, "al": activity_label,
                                   "h": tr, "hts": ts})
```

Remplacer la boucle `report_lines` (lignes 275-282) par :

```python
                prime = quart.get("prime") or {}
                commentaire = quart.get("commentaire_ligne") or {}
                equip_hours = quart.get("equip_hours") or {}
                equip_codes = quart.get("equip_codes") or {}
                for resource_name in set(prime) | set(commentaire) | set(equip_hours) | set(equip_codes):
                    s.execute(text("insert into report_lines "
                                   "(quart_id, resource_name, prime, commentaire, equip_hours, equip_codes) "
                                   "values (:q, :rn, :p, :c, :eh, :ec)"),
                              {"q": quart_id, "rn": resource_name,
                               "p": float(prime[resource_name]) if resource_name in prime else None,
                               "c": commentaire.get(resource_name) or None,
                               "eh": float(equip_hours[resource_name]) if resource_name in equip_hours else None,
                               "ec": list(equip_codes.get(resource_name) or [])})
```

- [ ] **Step 2: Modifier `load_report`**

Remplacer la lecture des heures (lignes 330-335) par :

```python
                hrs = s.execute(
                    text("select resource_name, activity_label, hours, hours_ts "
                         "from report_hours where quart_id = :q"),
                    {"q": q["id"]}).mappings().all()
                heures = {}
                for h in hrs:
                    heures.setdefault(h["resource_name"], {})[h["activity_label"]] = {
                        "TR": float(h["hours"]), "TS": float(h["hours_ts"])}
```

Remplacer la lecture des lignes (lignes 336-340) par :

```python
                lines = s.execute(
                    text("select resource_name, prime, commentaire, equip_hours, equip_codes "
                         "from report_lines where quart_id = :q"),
                    {"q": q["id"]}).mappings().all()
                prime = {l["resource_name"]: float(l["prime"]) for l in lines if l["prime"] is not None}
                commentaire = {l["resource_name"]: l["commentaire"] for l in lines if l["commentaire"]}
                equip_hours = {l["resource_name"]: float(l["equip_hours"])
                               for l in lines if l["equip_hours"] is not None}
                equip_codes = {l["resource_name"]: list(l["equip_codes"])
                               for l in lines if l["equip_codes"]}
```

Ajouter `equip_codes`/`equip_hours` au dict du quart (bloc `quarts_dict[q["quart"]] = {...}`, ~344-355) :

```python
                    "heures": heures, "prime": prime, "commentaire_ligne": commentaire,
                    "equip_codes": equip_codes, "equip_hours": equip_hours,
```

- [ ] **Step 3: Vérifier l'import et les tests existants**

Run: `.venv/bin/python -c "import reports; print('ok')"`
Expected: `ok` (aucune erreur de syntaxe).

Run: `.venv/bin/python -m pytest tests/test_reports.py -q`
Expected: PASS.

- [ ] **Step 4: Vérification e2e (manuelle, contre Neon)**

Démarrer l'app, ouvrir une journée, saisir pour un employé : une activité avec TR et TS, des codes d'équipement et des heures équipement, puis **Enregistrer**. Recharger (changer de semaine puis revenir) et vérifier que TR/TS, codes et Hrs Éq. sont restitués. Noter le résultat dans le commit.

- [ ] **Step 5: Commit**

```bash
git add reports.py
git commit -m "feat: save/load TR/TS et équipement par employé"
```

---

### Task 5: Étape Configuration — retirer la carte Activités, ajuster les prérequis

**Files:**
- Modify: `app.py` (`view_day_entry`, étape config : bloc activités ~1088-1109 ; prérequis ~1257-1263)
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: rien de nouveau.
- Produces: à l'étape Config, plus de `st.multiselect` de clé `acts_{jour}_{quart}` ; le bouton `save_next_{jour}` est activé dès que **personnel + température** sont présents (l'activité n'est plus requise).

- [ ] **Step 1: Mettre à jour les tests (échec attendu)**

Dans `tests/test_ui.py` :

Le helper `_acts_pills` cible un widget qui n'existe plus à l'étape Config. Supprimer `_acts_pills` et toutes ses utilisations à l'étape config. Mettre à jour les tests suivants :

`test_save_and_navigate_advances_to_saisie` — retirer la ligne `_acts_pills(...).set_value(...)` :

```python
def test_save_and_navigate_advances_to_saisie(monkeypatch):
    import reports
    monkeypatch.setattr(reports, "save_report", lambda *a, **k: None)
    at = _open_day_for_entry(monkeypatch)   # personnel Alice présent
    # Prérequis désormais : personnel + température (plus d'activité en config).
    [n for n in at.number_input if n.key == "Lundi_Jour_temp_am"][0].set_value(5.0).run()
    [b for b in at.button if b.key == "save_next_Lundi"][0].click().run()
    assert at.session_state["day_entry_step"] == "saisie"
    assert at.session_state["dirty"] is False
    assert any(b.key == "back_config_Lundi" for b in at.button)
    assert any(b.key == "save_Lundi" for b in at.button)
    assert not at.exception
```

`test_save_next_disabled_until_requirements_met` — prérequis = personnel + température :

```python
def test_save_next_disabled_until_requirements_met(monkeypatch):
    at = _open_day_for_entry(monkeypatch, personnel=())   # rien de rempli
    assert [b for b in at.button if b.key == "save_next_Lundi"][0].disabled
    [t for t in at.text_input if t.key == "new_employee_Lundi_Jour"][0].set_value("Alice").run()
    [b for b in at.button if b.key == "add_manual_Lundi_Jour"][0].click().run()
    [n for n in at.number_input if n.key == "Lundi_Jour_temp_am"][0].set_value(12.0).run()
    assert not [b for b in at.button if b.key == "save_next_Lundi"][0].disabled
    assert not at.exception
```

`test_save_next_requires_temperature` — retirer l'activité :

```python
def test_save_next_requires_temperature(monkeypatch):
    at = _open_day_for_entry(monkeypatch, personnel=("Alice",))
    assert [b for b in at.button if b.key == "save_next_Lundi"][0].disabled  # temp vide
    [n for n in at.number_input if n.key == "Lundi_Jour_temp_am"][0].set_value(0.0).run()
    assert not [b for b in at.button if b.key == "save_next_Lundi"][0].disabled
    assert not at.exception
```

Supprimer `test_day_activities_come_from_db` et `test_multiselect_keeps_incremental_activities` (le multiselect d'activités quitte la config ; sa version par employé est testée en Task 6).

`test_add_quart_creates_second_quart` — remplacer les assertions sur `acts_Lundi_*` par une vérification basée sur les pills personnel (présentes en config) :

```python
def test_add_quart_creates_second_quart(monkeypatch):
    at = _open_day_for_entry(monkeypatch)
    assert list(at.session_state["jours"]["Lundi"]["quarts"].keys()) == ["Jour"]
    [b for b in at.button if b.key == "empty_quart_Lundi_Soir"][0].click().run()
    assert app_quarts(at, "Lundi") == ["Jour", "Soir"]
    # la vue bascule immédiatement sur le quart ajouté : le bouton de quart « Soir » est actif (primary)
    assert at.session_state["active_quart_Lundi"] == "Soir"
    assert any(b.key == "quart_pick_Lundi_Soir" for b in at.button)
    assert not at.exception
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `.venv/bin/python -m pytest tests/test_ui.py -q -k "save_and_navigate or save_next or add_quart_creates"`
Expected: FAIL (le multiselect `acts_*` existe encore en config, donc certains passent encore ; au minimum les tests référant `_acts_pills` supprimé provoquent une NameError → FAIL/erreur de collecte). L'objectif : après implémentation, ils passent.

- [ ] **Step 3: Implémenter — retirer la carte Activités**

Dans `view_day_entry` (étape config), remplacer le bloc des colonnes Activités/Météo. Actuellement (lignes 1088-1160) :

```python
        col_act, col_meteo = st.columns(2)

        with col_act:
            with st.container(border=True, key="acts_box"):
                ... (multiselect activités) ...

        with col_meteo:
            with st.container(border=True, key="meteo_card"):
                ... (météo) ...
```

Le devient (météo en pleine largeur, suppression complète de `acts_box` et de la colonne) :

```python
        with st.container(border=True, key="meteo_card"):
            ... (contenu météo inchangé, ré-indenté d'un niveau) ...
```

Concrètement : supprimer les lignes 1088-1109 (`col_act, col_meteo = st.columns(2)` + tout le bloc `with col_act:` / `acts_box`) et la ligne `with col_meteo:` ; ré-indenter le contenu de l'ancien `with col_meteo:` pour qu'il soit directement sous `with st.container(border=True, key="meteo_card"):`.

Mettre à jour les prérequis (lignes 1257-1263) — retirer la condition activité :

```python
        missing = []
        if quart["temp_am"] is None and quart["temp_pm"] is None:
            missing.append("une température (AM ou PM)")
        if not quart.get("personnel"):
            missing.append("du personnel")
```

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

Run: `.venv/bin/python -m pytest tests/test_ui.py -q -k "save_and_navigate or save_next or add_quart_creates or day_entry_starts or back_returns"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_ui.py
git commit -m "feat: config sans carte Activités; prérequis = personnel + température"
```

---

### Task 6: Étape Saisie — cartes par ressource (activités TR/TS, équipement)

**Files:**
- Modify: `app.py` (import ligne 16 ; supprimer `_build_hours_df`/`_apply_hours_grid` ~317-361 ; `_clear_quart_widget_state` ~117-127 ; bloc Saisie/AgGrid ~1287-1335 ; ajouter `_render_resource_card`)
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: `_roster`, `_resource_total`, `EQUIP_CODE_VALUES`, `_equip_code_label`, `_to_hours` (Task 1) ; `data_source.get_activities(id_project)`.
- Produces: pour chaque ressource du roster, une carte `st.expander`. Clés de widgets par ressource :
  - activités : `st.multiselect` clé `acts_{jour}_{quart}_{name}`
  - heures : `st.number_input` clés `tr_{jour}_{quart}_{name}_{act}` et `ts_{jour}_{quart}_{name}_{act}`
  - équipement (personnel uniquement) : `st.pills` clé `eqc_{jour}_{quart}_{name}` ; `st.number_input` clé `eqh_{jour}_{quart}_{name}`
  - prime : `st.number_input` clé `p_{jour}_{quart}_{name}` ; commentaire : `st.text_input` clé `c_{jour}_{quart}_{name}`
  L'état écrit : `quart["heures"][name] = {act: {"TR","TS"}}` (entrées à 0 retirées), `quart["equip_codes"][name]`, `quart["equip_hours"][name]`, `quart["prime"][name]`, `quart["commentaire_ligne"][name]`.

- [ ] **Step 1: Écrire les tests (échec attendu)**

Dans `tests/test_ui.py` :

Retirer la section « Logique de la grille AgGrid » (les 4 tests `test_apply_hours_grid_*` / `test_build_hours_df_*`, lignes 650-716) — ces helpers disparaissent.

Retirer les `@pytest.mark.skip(reason=_AGGRID_SKIP)` et leur corps pour les tests devenus obsolètes (`test_day_hours_no_grid_data_editor`, `test_day_total_badge_reflects_entered_hours`, `test_roster_search_filters_resources` dans sa forme actuelle, `test_hours_are_distinct_per_quart`, `test_add_quart_can_copy_team_and_activities`, `test_day_prime_inline_column`, `test_day_comment_inline_column`) **ou** les réécrire selon les clés ci-dessous. On garde et réécrit les plus utiles :

```python
def test_day_hours_entry_updates_model(monkeypatch):
    at = _open_day_for_entry(monkeypatch)   # personnel Alice, activité dispo "C01 - Test"
    _goto_saisie(at)
    # choisir l'activité pour Alice puis saisir TR/TS
    ms = [m for m in at.multiselect if m.key == "acts_Lundi_Jour_Alice"][0]
    ms.set_value(["C01 - Test"]).run()
    [n for n in at.number_input if n.key == "tr_Lundi_Jour_Alice_C01 - Test"][0].set_value(8.0).run()
    [n for n in at.number_input if n.key == "ts_Lundi_Jour_Alice_C01 - Test"][0].set_value(1.5).run()
    q = at.session_state["jours"]["Lundi"]["quarts"]["Jour"]
    assert q["heures"]["Alice"]["C01 - Test"] == {"TR": 8.0, "TS": 1.5}
    assert not at.exception


def test_day_equip_codes_and_hours(monkeypatch):
    at = _open_day_for_entry(monkeypatch)
    _goto_saisie(at)
    [n for n in at.number_input if n.key == "eqh_Lundi_Jour_Alice"][0].set_value(10.0).run()
    q = at.session_state["jours"]["Lundi"]["quarts"]["Jour"]
    assert q["equip_hours"]["Alice"] == 10.0
    # les pills de code d'équipement existent pour l'employé
    assert any((bg.key or "") == "eqc_Lundi_Jour_Alice" for bg in at.button_group)
    assert not at.exception


def test_day_prime_inline(monkeypatch):
    at = _open_day_for_entry(monkeypatch)
    _goto_saisie(at)
    [n for n in at.number_input if n.key == "p_Lundi_Jour_Alice"][0].set_value(2.0).run()
    assert at.session_state["jours"]["Lundi"]["quarts"]["Jour"]["prime"]["Alice"] == 2.0
    assert not at.exception


def test_day_comment_inline(monkeypatch):
    at = _open_day_for_entry(monkeypatch)
    _goto_saisie(at)
    [t for t in at.text_input if t.key == "c_Lundi_Jour_Alice"][0].set_value("RAS").run()
    assert at.session_state["jours"]["Lundi"]["quarts"]["Jour"]["commentaire_ligne"]["Alice"] == "RAS"
    assert not at.exception
```

Réécrire `test_day_entry_no_activity_shows_info` : sans activité disponible (`get_activities → []`), la carte employé affiche un multiselect vide et aucun champ TR/TS :

```python
def test_day_entry_no_activity_shows_info(monkeypatch):
    import data_source
    monkeypatch.setattr(data_source, "get_projects", lambda: [(1, "P-100", "Alpha")])
    monkeypatch.setattr(data_source, "get_activities", lambda pid: [])
    monkeypatch.setattr(data_source, "get_project_staff", lambda pid: [])
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["projet"] = {"no": "P-100", "id_project": 1,
                                  "semaine": datetime.date(2026, 6, 7),
                                  "adresse": "", "lat": None, "lon": None}
    q = _empty_quart_dict()
    q["personnel"] = ["Alice"]
    at.session_state["jours"] = {j: {"date": None, "quarts": {"Jour": _empty_quart_dict()}}
                                  for j in ["Dimanche", "Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]}
    at.session_state["jours"]["Lundi"] = {"date": datetime.date(2026, 6, 8),
                                           "quarts": {"Jour": q}}
    at.session_state["active_day"] = "Lundi"
    at.session_state["view"] = "day_entry"
    at.run()
    _goto_saisie(at)
    # aucune activité disponible -> aucun champ TR pour Alice
    assert not any((n.key or "").startswith("tr_Lundi_Jour_Alice_") for n in at.number_input)
    assert not at.exception
```

Mettre à jour `_empty_quart_dict()` (lignes 39-43) pour inclure les nouveaux champs :

```python
def _empty_quart_dict():
    return {
        "responsable": "", "activites": [], "autres": [], "personnel": [], "equipements": [],
        "temp_am": None, "temp_pm": None, "conditions": [], "heures": {}, "prime": {},
        "commentaire_ligne": {}, "equip_codes": {}, "equip_hours": {}, "description": ""}
```

Idem pour les dicts de quart inlinés dans `_open_day_for_entry` (lignes 55-63) : ajouter `"equip_codes": {}, "equip_hours": {}` aux deux dicts.

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `.venv/bin/python -m pytest tests/test_ui.py -q -k "hours_entry or equip_codes or prime_inline or comment_inline"`
Expected: FAIL (clés de widgets inexistantes / AgGrid encore en place).

- [ ] **Step 3: Implémenter — supprimer AgGrid et écrire les cartes**

(a) Ligne 16 : supprimer l'import devenu inutile.
```python
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode   # <-- SUPPRIMER cette ligne
```

(b) Supprimer les fonctions `_build_hours_df` (317-332) et `_apply_hours_grid` (334-361).

(c) `_clear_quart_widget_state` (117-127) : mettre à jour les préfixes pour les nouvelles clés. Remplacer le tuple `prefixes` par :
```python
    prefixes = (f"tr_{jour}_{quart_name}_", f"ts_{jour}_{quart_name}_",
                f"eqc_{jour}_{quart_name}_", f"eqh_{jour}_{quart_name}_",
                f"p_{jour}_{quart_name}_", f"c_{jour}_{quart_name}_",
                f"acts_{jour}_{quart_name}",
                f"cond_pills_{jour}_{quart_name}",
                f"{jour}_{quart_name}_temp_am", f"{jour}_{quart_name}_temp_pm",
                f"{jour}_{quart_name}_cond", f"roster_search_{jour}_{quart_name}",
                f"personnel_pills_{jour}_{quart_name}", f"note_{jour}_{quart_name}",
                f"show_geoloc_{jour}_{quart_name}", f"geoloc_{jour}_{quart_name}")
```

(d) Ajouter une fonction `_render_resource_card` (la placer près des autres helpers de saisie, p. ex. juste avant `view_day_entry`) :

```python
def _render_resource_card(jour, quart_name, quart, name, typ, all_activities):
    """Carte de saisie d'une ressource : activités (TR/TS), équipement (employé), prime, commentaire."""
    # --- Activités de la ressource (choisies parmi toutes les activités du projet) ---
    ms_key = f"acts_{jour}_{quart_name}_{name}"
    current_acts = list(quart["heures"].get(name, {}).keys())
    if ms_key not in st.session_state:
        st.session_state[ms_key] = current_acts
    options = sorted(set(all_activities) | set(current_acts))
    sel_acts = st.multiselect("Activités", options, key=ms_key,
                              placeholder="🔍 Activités travaillées…", on_change=_mark_dirty)

    new_heures = {}
    for act in (sel_acts or []):
        pair = quart["heures"].get(name, {}).get(act, {})
        ca, cb, _ = st.columns([1, 1, 3])
        tr_key = f"tr_{jour}_{quart_name}_{name}_{act}"
        ts_key = f"ts_{jour}_{quart_name}_{name}_{act}"
        st.session_state.setdefault(tr_key, _to_hours(pair.get("TR")))
        st.session_state.setdefault(ts_key, _to_hours(pair.get("TS")))
        tr = ca.number_input(f"TR — {act.split(' - ')[0]}", key=tr_key, min_value=0.0,
                             step=0.5, format="%.1f", on_change=_mark_dirty)
        ts = cb.number_input(f"TS — {act.split(' - ')[0]}", key=ts_key, min_value=0.0,
                             step=0.5, format="%.1f", on_change=_mark_dirty)
        if tr > 0 or ts > 0:
            new_heures[act] = {"TR": float(tr), "TS": float(ts)}
    if new_heures:
        quart["heures"][name] = new_heures
    elif name in quart["heures"]:
        del quart["heures"][name]

    # --- Équipement rattaché à l'employé (personnel uniquement) ---
    if typ == "P":
        ce1, ce2 = st.columns([3, 1])
        eqc_key = f"eqc_{jour}_{quart_name}_{name}"
        if eqc_key not in st.session_state:
            st.session_state[eqc_key] = list(quart["equip_codes"].get(name, []))
        codes = ce1.pills("Équipement", EQUIP_CODE_VALUES, selection_mode="multi",
                          format_func=_equip_code_label, key=eqc_key, on_change=_mark_dirty)
        if codes:
            quart["equip_codes"][name] = list(codes)
        elif name in quart["equip_codes"]:
            del quart["equip_codes"][name]
        eqh_key = f"eqh_{jour}_{quart_name}_{name}"
        st.session_state.setdefault(eqh_key, _to_hours(quart["equip_hours"].get(name)))
        eqh = ce2.number_input("Hrs Éq.", key=eqh_key, min_value=0.0, step=0.5,
                               format="%.1f", on_change=_mark_dirty)
        if eqh > 0:
            quart["equip_hours"][name] = float(eqh)
        elif name in quart["equip_hours"]:
            del quart["equip_hours"][name]

    # --- Prime + commentaire ---
    cp, cc = st.columns([1, 3])
    p_key = f"p_{jour}_{quart_name}_{name}"
    st.session_state.setdefault(p_key, _to_hours(quart["prime"].get(name)))
    prime = cp.number_input("Prime ($)", key=p_key, min_value=0.0, step=0.5,
                            format="%.2f", on_change=_mark_dirty)
    if prime > 0:
        quart["prime"][name] = float(prime)
    elif name in quart["prime"]:
        del quart["prime"][name]
    c_key = f"c_{jour}_{quart_name}_{name}"
    st.session_state.setdefault(c_key, quart["commentaire_ligne"].get(name, ""))
    com = cc.text_input("Commentaire", key=c_key, on_change=_mark_dirty)
    if com.strip():
        quart["commentaire_ligne"][name] = com.strip()
    elif name in quart["commentaire_ligne"]:
        del quart["commentaire_ligne"][name]
```

(e) Remplacer le bloc Saisie (lignes ~1287-1335, du `cols_labels = _quart_columns(quart)` jusqu'à la fin du `else:` de la grille, avant `st.divider()` ligne 1336) par les cartes :

```python
        full_roster = _roster(quart)
        hd1, hd2 = st.columns([2, 1])
        hd1.markdown("#### 🕐 Saisie des heures")
        query = hd2.text_input("Rechercher une ressource", key=f"roster_search_{jour}_{quart_name}",
                               placeholder="🔍 Rechercher une ressource…",
                               label_visibility="collapsed").strip().lower()
        roster = [(n, t) for n, t in full_roster if query in n.lower()] if query else full_roster
        all_activities = data_source.get_activities(st.session_state.projet.get("id_project"))
        if not full_roster:
            st.info("💡 Commencez par sélectionner le **personnel / équipements** dans la configuration.")
        elif not roster:
            st.info("🔍 Aucune ressource ne correspond à la recherche.")
        else:
            for name, typ in roster:
                icon = "👷" if typ == "P" else "🚜"
                with st.expander(f"{icon} {name} — {_resource_total(quart, name):.1f} h", expanded=True):
                    _render_resource_card(jour, quart_name, quart, name, typ, all_activities)
```

(Conserver le `st.divider()` + « 📝 Note du quart » + barre du bas qui suivent, inchangés.)

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

Run: `.venv/bin/python -m pytest tests/test_ui.py -q`
Expected: PASS (toute la suite UI).

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_ui.py
git commit -m "feat: saisie par cartes (activités TR/TS, équipement par employé); retrait AgGrid"
```

---

### Task 7: Copie de quart / copie de jour adaptées au nouveau modèle

**Files:**
- Modify: `app.py` (`_add_quart` ~975-987 ; copie de jour ~1026-1037)
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: format d'état Task 1 (`heures` nesté, `equip_codes`, `equip_hours`).
- Produces: `_add_quart(copy_from=...)` copie la config (personnel, équipements, responsable) **sans** les heures ; la copie de jour copie `heures` (profond), `equip_codes`, `equip_hours`.

- [ ] **Step 1: Écrire le test (échec attendu)**

Ajouter dans `tests/test_ui.py` :

```python
def test_copy_day_copies_hours_and_equipment(monkeypatch):
    at = _open_day_for_entry(monkeypatch, jour="Mardi", personnel=("Alice",))
    # préparer Lundi (jour précédent) avec heures TR/TS + équipement
    lundi = at.session_state["jours"]["Lundi"]
    lundi["date"] = datetime.date(2026, 6, 8)
    ql = lundi["quarts"]["Jour"]
    ql["personnel"] = ["Alice"]
    ql["heures"] = {"Alice": {"C01 - Test": {"TR": 6.0, "TS": 0.0}}}
    ql["equip_codes"] = {"Alice": ["C"]}
    ql["equip_hours"] = {"Alice": 4.0}
    at.run()
    [b for b in at.button if b.key == "copy_Mardi"][0].click().run()
    qm = at.session_state["jours"]["Mardi"]["quarts"]["Jour"]
    assert qm["heures"] == {"Alice": {"C01 - Test": {"TR": 6.0, "TS": 0.0}}}
    assert qm["equip_codes"] == {"Alice": ["C"]}
    assert qm["equip_hours"] == {"Alice": 4.0}
    assert not at.exception
```

(Le bouton « 📋 Copier de … » a la clé `copy_{jour}` et n'apparaît que pour un jour ayant un jour précédent — d'où `jour="Mardi"`.)

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `.venv/bin/python -m pytest "tests/test_ui.py::test_copy_day_copies_hours_and_equipment" -q`
Expected: FAIL (la copie de jour ne copie pas encore `equip_*`, et copie `activites` obsolète).

- [ ] **Step 3: Implémenter**

`_add_quart` (lignes 978-984) — copier la config sans heures, sans `activites`/`autres` :

```python
    if copy_from and copy_from in day["quarts"]:
        src = day["quarts"][copy_from]
        q["personnel"] = list(src["personnel"])
        q["equipements"] = list(src["equipements"])
        q["responsable"] = src["responsable"]
```

Copie de jour (lignes 1030-1036) — copier `heures` (profond, valeurs nestées), `equip_codes`, `equip_hours` :

```python
            prev_day_obj = st.session_state.jours[prev_day]
            src = prev_day_obj["quarts"][_day_quart_names(prev_day_obj)[0]]
            quart = day["quarts"][current]
            quart["heures"] = {r: {a: dict(p) for a, p in acts.items()}
                               for r, acts in src["heures"].items()}
            quart["equip_codes"] = {r: list(c) for r, c in src["equip_codes"].items()}
            quart["equip_hours"] = dict(src["equip_hours"])
            _clear_quart_widget_state(jour, current)
            _mark_dirty()
            st.rerun()
```

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

Run: `.venv/bin/python -m pytest tests/test_ui.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_ui.py
git commit -m "feat: copie quart/jour adaptées au modèle par employé (heures nestées, équipement)"
```

---

### Task 8: Vérification globale

**Files:** aucun (vérification).

- [ ] **Step 1: Suite complète**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (tous les fichiers : `test_model`, `test_ui`, `test_reports`, `test_data_source`, `test_sync`, `test_smoke`).

- [ ] **Step 2: Lancement de l'app (fumée)**

Démarrer l'app, sélectionner un projet, ouvrir une journée :
- Config : plus de carte « Activités » ; on peut passer à la saisie avec personnel + météo.
- Saisie : une carte par ressource ; choisir des activités, saisir TR/TS, codes équipement + Hrs Éq., prime, commentaire.
- Enregistrer puis recharger : les données reviennent (cf. Task 4 Step 4).

- [ ] **Step 3: Commit éventuel** (si ajustements de fumée) ; sinon, fin.

---

## Self-Review

**Spec coverage:**
- A. Modèle (EQUIP_CODES, heures TR/TS, equip_codes/equip_hours, BD) → Tasks 1, 3, 4. ✓
- B. Config (retrait carte Activités, prérequis) → Task 5. ✓
- C. Saisie (cartes par ressource, activités par employé, TR/TS, équipement employé, équipement autonome sans codes) → Task 6 (`_render_resource_card` : codes/Hrs Éq. seulement si `typ == "P"`). ✓
- D. Persistance (save/load TR/TS + équipement, union activités) → Task 4. ✓
- E. Export (`_legacy_day`), tests, migration → Task 2 (`_legacy_day`), Tasks 1-7 (tests), Task 3 (migration). ✓
- Copie quart/jour (impact du changement de modèle) → Task 7. ✓

**Placeholder scan:** aucun TODO/TBD ; chaque step de code montre le code complet. ✓

**Type consistency:** `heures[emp][act] = {"TR": float, "TS": float}` cohérent entre Tasks 1, 2, 4, 6, 7 ; clés de widgets (`tr_`/`ts_`/`eqc_`/`eqh_`/`p_`/`c_`/`acts_..._{name}`) cohérentes entre `_render_resource_card` (Task 6), `_clear_quart_widget_state` (Task 6) et les tests (Tasks 5-7). `_quart_activities`/`_pair_total`/`_resource_total` définis en Task 1 et consommés en Tasks 2, 6. ✓

**Note de risque :** Tasks 4 (save/load) n'a pas de test automatisé (SQL Postgres non reproductible localement) — couverte par vérification e2e (Task 4 Step 4 + Task 8 Step 2). Le correctif `day_id` (NOT NULL) déjà appliqué dans l'arbre de travail (non lié à ce plan) reste à committer séparément.
