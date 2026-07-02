# Prime en codes — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer la prime numérique (`Prime ($)`) par une sélection multiple de codes de prime (I, S, G, T, A, Pa, P, H, R, Pu, Co), en calquant le patron des codes d'équipement.

**Architecture:** Changement traversant saisie → stockage → export. `app.py` : constante `PRIME_CODES` + pastilles multi (miroir de `equip_codes`) ; `reports.py` : colonne `prime_codes text[]` (ancienne colonne `prime numeric` supprimée) ; `excel_report.py` : affichage des codes joints. La clé du quart passe de `prime: {name: float}` à `prime_codes: {name: [codes]}`.

**Tech Stack:** Python 3.9, Streamlit (`st.pills`), openpyxl, Postgres (Neon), pytest.

## Global Constraints

- `app.py` NE DOIT PAS importer `excel_report` au niveau module (invariant).
- Suivre à l'identique le patron `equip_codes` (constante, `_..._label`, pastilles `selection_mode="multi"`, colonne `text[]`).
- Codes de prime : `I` Intempérie, `S` Surtemps, `G` Galvanisé, `T` Poste HT, `A` Peinture, `Pa` Panier, `P` Préavis, `H` Hauteur, `R` Repas, `Pu` Puissance, `Co` Contrôle.
- Ancienne colonne `prime numeric` : supprimée (nettoyage destructif, aucune conversion des anciennes primes).
- Clé du quart : `prime_codes` (plus de clé `prime`).
- Runner de tests (pas de `.venv` dans un worktree) : `/Users/marie-pierarsenault/Documents/GitHub/rapportsJournaliers/.venv/bin/python -m pytest`. Tester par fichier ciblé.
- La persistance SQL réelle est validée end-to-end contre Neon ; `test_reports.py` ne teste que la logique pure et la liste `_DDL_STATEMENTS`.

---

### Task 1 : Constante PRIME_CODES + modèle de données

**Files:**
- Modify: `app.py` (après `EQUIP_CODES`/`_equip_code_label` ~l.56-65 ; `_empty_quart` l.222)
- Test: `tests/test_model.py`

**Interfaces:**
- Produces :
  - `app.PRIME_CODES` (liste de tuples), `app.PRIME_CODE_VALUES` (liste de str), `app._prime_code_label(code) -> str`
  - `app._empty_quart()` renvoie un dict avec `"prime_codes": {}` (et **plus** de clé `"prime"`)

- [ ] **Step 1 : Écrire les tests**

Dans `tests/test_model.py`, remplacer l'assertion prime existante (l.11) et ajouter un test de libellé. Remplacer :

```python
    assert q["heures"] == {} and q["prime"] == {} and q["commentaire_ligne"] == {}
```

par :

```python
    assert q["heures"] == {} and q["prime_codes"] == {} and q["commentaire_ligne"] == {}
    assert "prime" not in q
```

Et ajouter (après ce test) :

```python
def test_prime_code_label():
    import app
    assert app._prime_code_label("H") == "H — Hauteur"
    assert set(app.PRIME_CODE_VALUES) == {"I","S","G","T","A","Pa","P","H","R","Pu","Co"}
```

- [ ] **Step 2 : Lancer, voir échouer**

Run : `/Users/marie-pierarsenault/Documents/GitHub/rapportsJournaliers/.venv/bin/python -m pytest tests/test_model.py -q`
Expected : FAIL (`prime_codes` absent / `PRIME_CODE_VALUES` inexistant).

- [ ] **Step 3 : Ajouter la constante et le libellé**

Dans `app.py`, juste après le bloc `EQUIP_CODES` / `_equip_code_label` (après la l.65), ajouter :

```python
PRIME_CODES = [
    ("I", "Intempérie"), ("S", "Surtemps"), ("G", "Galvanisé"),
    ("T", "Poste HT"), ("A", "Peinture"), ("Pa", "Panier"),
    ("P", "Préavis"), ("H", "Hauteur"), ("R", "Repas"),
    ("Pu", "Puissance"), ("Co", "Contrôle"),
]
PRIME_CODE_VALUES = [c for c, _ in PRIME_CODES]
_PRIME_CODE_LABELS = dict(PRIME_CODES)


def _prime_code_label(code):
    return f"{code} — {_PRIME_CODE_LABELS.get(code, code)}"
```

- [ ] **Step 4 : Modifier `_empty_quart`**

Dans `app.py` l.222, remplacer :

```python
        "heures": {}, "prime": {}, "commentaire_ligne": {},
```

par :

```python
        "heures": {}, "prime_codes": {}, "commentaire_ligne": {},
```

- [ ] **Step 5 : Lancer, voir passer**

Run : `/Users/marie-pierarsenault/Documents/GitHub/rapportsJournaliers/.venv/bin/python -m pytest tests/test_model.py -q`
Expected : PASS.

- [ ] **Step 6 : Commit**

```bash
git add app.py tests/test_model.py
git commit -m "feat(prime): constante PRIME_CODES + prime_codes dans _empty_quart"
```

---

### Task 2 : Saisie en pastilles + _legacy_day

**Files:**
- Modify: `app.py` (carte de ressource l.1322-1331 ; `_legacy_day` l.493)
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes : `app.PRIME_CODE_VALUES`, `app._prime_code_label` (Task 1) ; `quart["prime_codes"]`.
- Produces : la carte de ressource écrit `quart["prime_codes"][name] = [codes]` ; l'aperçu `_legacy_day` expose `rec["Prime"]` = codes joints.

- [ ] **Step 1 : Mettre à jour les fixtures et réécrire le test prime**

Dans `tests/test_ui.py`, remplacer **toutes** les occurrences `"prime": {}` (l.29, 47, 52) par `"prime_codes": {}`, et l'assertion l.571 `assert qs["prime"] == {}` par `assert qs["prime_codes"] == {}`.

Puis réécrire `test_day_prime_inline` (l.301-306) :

```python
def test_day_prime_inline(monkeypatch):
    at = _open_day_for_entry(monkeypatch)
    _goto_saisie(at)
    [bg for bg in at.button_group if bg.key == "p_Lundi_Jour_Alice"][0].set_value(["H"]).run()
    assert at.session_state["jours"]["Lundi"]["quarts"]["Jour"]["prime_codes"]["Alice"] == ["H"]
    assert not at.exception
```

- [ ] **Step 2 : Lancer, voir échouer**

Run : `/Users/marie-pierarsenault/Documents/GitHub/rapportsJournaliers/.venv/bin/python -m pytest tests/test_ui.py::test_day_prime_inline -q`
Expected : FAIL (le widget `p_...` est encore un `number_input`, pas un `button_group` ; et `prime_codes` absent du quart).

- [ ] **Step 3 : Remplacer le number_input par des pastilles**

Dans `app.py`, remplacer le bloc prime (l.1324-1331) :

```python
    p_key = f"p_{jour}_{quart_name}_{name}"
    st.session_state.setdefault(p_key, _to_hours(quart["prime"].get(name)))
    prime = cp.number_input("Prime ($)", key=p_key, min_value=0.0, step=0.5,
                            format="%.2f", on_change=_mark_dirty)
    if prime > 0:
        quart["prime"][name] = float(prime)
    elif name in quart["prime"]:
        del quart["prime"][name]
```

par (miroir du bloc équipement l.1304-1312) :

```python
    p_key = f"p_{jour}_{quart_name}_{name}"
    if p_key not in st.session_state:
        st.session_state[p_key] = list(quart["prime_codes"].get(name, []))
    codes = cp.pills("Prime", PRIME_CODE_VALUES, selection_mode="multi",
                     format_func=_prime_code_label, key=p_key, on_change=_mark_dirty)
    if codes:
        quart["prime_codes"][name] = list(codes)
    elif name in quart["prime_codes"]:
        del quart["prime_codes"][name]
```

- [ ] **Step 4 : Mettre à jour `_legacy_day`**

Dans `app.py` l.493, remplacer :

```python
            rec["Prime"] = quart["prime"].get(name)
```

par :

```python
            rec["Prime"] = ", ".join(quart["prime_codes"].get(name) or [])
```

- [ ] **Step 5 : Lancer les tests UI**

Run : `/Users/marie-pierarsenault/Documents/GitHub/rapportsJournaliers/.venv/bin/python -m pytest tests/test_ui.py -q`
Expected : PASS (dont `test_day_prime_inline`, et pas d'exception AppTest ailleurs).

- [ ] **Step 6 : Commit**

```bash
git add app.py tests/test_ui.py
git commit -m "feat(prime): saisie en pastilles multi (codes) au lieu du montant \$"
```

---

### Task 3 : Persistance (reports.py)

**Files:**
- Modify: `reports.py` (`_DDL_STATEMENTS` ~l.159 ; `save_report` l.339-351 ; `load_report` l.420-443)
- Test: `tests/test_reports.py`

**Interfaces:**
- Consumes : quart avec `prime_codes: {name: [codes]}`.
- Produces : colonne SQL `report_lines.prime_codes text[]` ; `load_report` renvoie le quart avec `"prime_codes": {name: [codes]}` (plus de clé `"prime"`).

- [ ] **Step 1 : Écrire le test DDL**

Dans `tests/test_reports.py`, ajouter :

```python
def test_ddl_has_prime_codes_migration():
    ddl = " ".join(reports._DDL_STATEMENTS)
    assert "report_lines add column if not exists prime_codes text[]" in ddl
    assert "report_lines drop column if exists prime" in ddl
```

- [ ] **Step 2 : Lancer, voir échouer**

Run : `/Users/marie-pierarsenault/Documents/GitHub/rapportsJournaliers/.venv/bin/python -m pytest tests/test_reports.py::test_ddl_has_prime_codes_migration -q`
Expected : FAIL (migrations absentes).

- [ ] **Step 3 : Ajouter les migrations DDL**

Dans `reports.py`, dans la liste `_DDL_STATEMENTS`, juste après la ligne `equip_codes` (l.159), ajouter :

```python
    # Prime rattachée à l'employé : liste de codes (I/S/G/T/A/Pa/P/H/R/Pu/Co)
    # au lieu d'un montant. On ajoute la colonne tableau et on retire l'ancienne
    # colonne numérique (les anciennes primes numériques sont abandonnées).
    "alter table report_lines add column if not exists prime_codes text[] not null default '{}'",
    "alter table report_lines drop column if exists prime",
```

- [ ] **Step 4 : Mettre à jour `save_report`**

Dans `reports.py` (l.339-351), remplacer :

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

par :

```python
                prime_codes = quart.get("prime_codes") or {}
                commentaire = quart.get("commentaire_ligne") or {}
                equip_hours = quart.get("equip_hours") or {}
                equip_codes = quart.get("equip_codes") or {}
                for resource_name in set(prime_codes) | set(commentaire) | set(equip_hours) | set(equip_codes):
                    s.execute(text("insert into report_lines "
                                   "(quart_id, resource_name, prime_codes, commentaire, equip_hours, equip_codes) "
                                   "values (:q, :rn, :pc, :c, :eh, :ec)"),
                              {"q": quart_id, "rn": resource_name,
                               "pc": list(prime_codes.get(resource_name) or []),
                               "c": commentaire.get(resource_name) or None,
                               "eh": float(equip_hours[resource_name]) if resource_name in equip_hours else None,
                               "ec": list(equip_codes.get(resource_name) or [])})
```

- [ ] **Step 5 : Mettre à jour `load_report`**

Dans `reports.py`, remplacer la sélection (l.420-422) :

```python
                lines = s.execute(
                    text("select resource_name, prime, commentaire, equip_hours, equip_codes "
                         "from report_lines where quart_id = :q"),
                    {"q": q["id"]}).mappings().all()
                prime = {l["resource_name"]: float(l["prime"]) for l in lines if l["prime"] is not None}
```

par :

```python
                lines = s.execute(
                    text("select resource_name, prime_codes, commentaire, equip_hours, equip_codes "
                         "from report_lines where quart_id = :q"),
                    {"q": q["id"]}).mappings().all()
                prime_codes = {l["resource_name"]: list(l["prime_codes"])
                               for l in lines if l["prime_codes"]}
```

Puis, dans le dict du quart (l.442), remplacer :

```python
                    "heures": heures, "prime": prime, "commentaire_ligne": commentaire,
```

par :

```python
                    "heures": heures, "prime_codes": prime_codes, "commentaire_ligne": commentaire,
```

- [ ] **Step 6 : Lancer les tests reports**

Run : `/Users/marie-pierarsenault/Documents/GitHub/rapportsJournaliers/.venv/bin/python -m pytest tests/test_reports.py -q`
Expected : PASS.

- [ ] **Step 7 : Commit**

```bash
git add reports.py tests/test_reports.py
git commit -m "feat(prime): persistance prime_codes text[] (suppression colonne prime numeric)"
```

---

### Task 4 : Export (excel_report.py)

**Files:**
- Modify: `excel_report.py` (`_write_resource_table` l.381, 429, 431)
- Test: `tests/test_excel_report.py`

**Interfaces:**
- Consumes : quart avec `prime_codes: {name: [codes]}`.
- Produces : colonne « Prime » de la ligne Total = codes joints (`"I, H"`).

- [ ] **Step 1 : Mettre à jour la fixture et le test**

Dans `tests/test_excel_report.py`, `_day_rempli` (l.22), remplacer :

```python
    q["prime"] = {"Mathis Lajeunesse": 25.0}
```

par :

```python
    q["prime_codes"] = {"Mathis Lajeunesse": ["S"]}
```

Et `test_build_day_workbook_heures_et_prime_presentes` (l.128-133), remplacer l'assertion prime `assert 25.0 in vals` par une vérification de la cellule Prime (col 7) de la ligne Total (évite un faux positif : l'en-tête « TS » contient aussi « S ») :

```python
    ws = wb["Lundi"]
    total = next(r for r in range(1, ws.max_row + 1)
                 if ws.cell(r, 1).value == "Total")
    assert ws.cell(total, 7).value == "S"   # code de prime dans la colonne Prime
```

- [ ] **Step 2 : Lancer, voir échouer**

Run : `/Users/marie-pierarsenault/Documents/GitHub/rapportsJournaliers/.venv/bin/python -m pytest tests/test_excel_report.py -q`
Expected : FAIL (`_write_resource_table` lit encore `quart.get("prime")`, la fixture n'a plus `prime`).

- [ ] **Step 3 : Lire prime_codes dans le tableau**

Dans `excel_report.py`, dans `_write_resource_table`, remplacer (l.381) :

```python
    prime = quart.get("prime") or {}
```

par :

```python
    prime = quart.get("prime_codes") or {}
```

Puis, dans la construction de la ligne Total (l.423-431), remplacer les deux occurrences `prime.get(name)` par les codes joints. La branche `with_equip` (l.425-426) :

```python
        if with_equip:
            codes = ", ".join(eqc.get(name) or []) or None
            total = ["Total", None, tr_tot, ts_tot, codes, eqh.get(name),
                     ", ".join(prime.get(name) or []) or None, comm.get(name)]
```

et la branche équipement (l.431) :

```python
            total = ["Total", None, tr_tot, ts_tot, ", ".join(prime.get(name) or []) or None, comm.get(name)]
```

- [ ] **Step 4 : Lancer les tests export**

Run : `/Users/marie-pierarsenault/Documents/GitHub/rapportsJournaliers/.venv/bin/python -m pytest tests/test_excel_report.py -q`
Expected : PASS.

- [ ] **Step 5 : Suite complète (garde-fou)**

Run : `/Users/marie-pierarsenault/Documents/GitHub/rapportsJournaliers/.venv/bin/python -m pytest -q`
Expected : PASS (aucune référence résiduelle à l'ancienne clé `prime`).

- [ ] **Step 6 : Commit**

```bash
git add excel_report.py tests/test_excel_report.py
git commit -m "feat(prime): export des codes de prime (au lieu du montant)"
```

---

## Self-review (couverture spec)

- Constante `PRIME_CODES` + `_prime_code_label` → Task 1.
- `_empty_quart` `prime_codes` → Task 1.
- Saisie pastilles multi → Task 2.
- `_legacy_day` codes joints → Task 2.
- Schéma `prime_codes text[]` + drop `prime` → Task 3.
- `save_report` / `load_report` → Task 3.
- Export codes joints → Task 4.
- Légende « Code de prime » : déjà présente (`_PRIME_LEGEND`), aucune action.
- Tests mis à jour : test_model (T1), test_ui (T2), test_reports (T3), test_excel_report (T4).
- Cohérence des noms : clé `prime_codes`, colonne `prime_codes`, widget key `p_...` (inchangé) — cohérent d'un bout à l'autre.
