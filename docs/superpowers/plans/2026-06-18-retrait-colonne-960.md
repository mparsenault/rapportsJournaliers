# Retrait de la colonne d'heures fixe « 960 » — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retirer la colonne fixe « 960 » de la grille d'heures : les heures se saisissent uniquement sur les activités/autres choisis ; aucun plantage quand aucune activité n'est sélectionnée.

**Architecture:** Suppression de `FIXED_COL` et de « 960 » dans `_day_columns` ; remap des activités sur `h0..h7` dans l'export `_legacy_day` ; garde-fou dans `view_day_entry` quand il n'y a aucune colonne ; mise à jour des tests.

**Tech Stack:** Python, Streamlit 1.50, pytest + AppTest, openpyxl (export inchangé hors mapping).

## Global Constraints

- Base = working tree `app.py`.
- Supprimer la constante `FIXED_COL = "960"` (plus aucun usage après les changements).
- `_day_columns(day)` → `list(day["activites"]) + list(day["autres"])` (plus de « 960 »).
- `_legacy_day` : retirer `headers["h0"] = "960"` et l'amorce `label_to_key`; les activités occupent `h0..h7` (jusqu'à 8), les « autres » `a0..a3`. Cellules inutilisées = `""`.
- `view_day_entry` : si `_day_columns(day)` est vide → `st.info("Sélectionnez au moins une activité pour saisir des heures.")` et ne PAS rendre les cartes (évite `st.columns(0)`). Garder le garde-fou roster vide. « Total jour » toujours affiché.
- Activités/projets (BD), staff, météo, dashboard : inchangés.
- Tests : `.venv/bin/python -m pytest -q` ; sortie pristine, 0 failed.

## File Structure

- `app.py` — `FIXED_COL` (suppr.), `_day_columns`, `_legacy_day`, `view_day_entry`.
- `tests/test_model.py` — fixture `_sample_day` + attentes (`test_day_columns`, `test_day_total`, `test_resource_total`, `test_legacy_day_maps_labels_to_keys`).
- `tests/test_ui.py` — nouveau test du cas « aucune activité ».

---

### Task 1 : Retirer la colonne fixe « 960 »

**Files:**
- Modify: `app.py`
- Modify: `tests/test_model.py`
- Modify: `tests/test_ui.py`

**Interfaces:**
- Produces: `_day_columns(day) -> list[str]` = activités + autres (sans « 960 »).

- [ ] **Step 1 : Mettre à jour la fixture et les tests modèle (échouent : 960 encore présent)**

Dans `tests/test_model.py` :

**(a)** Remplacer la fixture `_sample_day` par (heures sur activités réelles, plus « 960 ») :

```python
def _sample_day():
    d = app._empty_day()
    d["activites"] = ["Excavation"]
    d["autres"] = ["P-77"]
    d["heures"] = {"Mathis": {"Excavation": 4.0, "P-77": 2.0},
                   "Camion v1892": {"Excavation": 8.0}}
    d["prime"] = {"Mathis": 2.0}
    d["commentaire_ligne"] = {"Mathis": "test"}
    return d
```

**(b)** Remplacer les assertions :

```python
def test_day_total():
    assert app._day_total(_sample_config(), _sample_day()) == 14.0  # (4+2) + 8


def test_day_columns():
    d = _sample_day()
    assert app._day_columns(d) == ["Excavation", "P-77"]   # plus de 960


def test_resource_total():
    day = _sample_day()
    assert app._resource_total(day, "Mathis") == 6.0          # 4 + 2
    assert app._resource_total(day, "Camion v1892") == 8.0
    assert app._resource_total(day, "Inconnu") == 0.0


def test_legacy_day_maps_labels_to_keys():
    leg = app._legacy_day(_sample_config(), _sample_day())
    assert leg["headers"]["h0"] == "Excavation"   # 1re activité en h0 (plus de 960)
    assert leg["headers"]["a0"] == "P-77"
    pers, equip = leg["pers"], leg["equip"]
    for k in app.HOUR_KEYS:
        assert k in pers.columns and k in equip.columns
    assert list(pers["Nom"]) == ["Mathis", "Roy"]
    mathis = pers[pers["Nom"] == "Mathis"].iloc[0]
    assert mathis["h0"] == 4.0 and mathis["a0"] == 2.0   # Excavation->h0, P-77->a0
    assert mathis["Prime"] == 2.0 and mathis["Commentaire"] == "test"
    assert list(equip["Véhicule"]) == ["Camion v1892"]
    camion = equip[equip["Véhicule"] == "Camion v1892"].iloc[0]
    assert camion["h0"] == 8.0
```

(`test_empty_day_shape` et les autres tests restent inchangés.)

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv/bin/python -m pytest tests/test_model.py -q 2>&1 | tail -8`
Expected : FAIL (`_day_columns` renvoie encore `["960", …]`, `_legacy_day` met `h0 == "960"`).

- [ ] **Step 3 : Retirer `FIXED_COL` et l'utiliser nulle part**

- Supprimer la ligne `FIXED_COL = "960"` (constantes en tête de `app.py`).
- Remplacer le corps de `_day_columns` par :
  ```python
  def _day_columns(day):
      return list(day["activites"]) + list(day["autres"])
  ```

- [ ] **Step 4 : Adapter `_legacy_day` (activités sur h0..h7)**

Dans `_legacy_day`, remplacer le bloc :

```python
    acts = list(day["activites"])[:7]
    autres = list(day["autres"])[:4]
    headers = {f"h{i}": "" for i in range(8)}
    headers.update({f"a{i}": "" for i in range(4)})
    headers["h0"] = "960"
    label_to_key = {FIXED_COL: "h0"}
    for i, lbl in enumerate(acts):
        headers[f"h{i+1}"] = lbl
        label_to_key[lbl] = f"h{i+1}"
    for i, lbl in enumerate(autres):
        headers[f"a{i}"] = lbl
        label_to_key[lbl] = f"a{i}"
```

par :

```python
    acts = list(day["activites"])[:8]
    autres = list(day["autres"])[:4]
    headers = {f"h{i}": "" for i in range(8)}
    headers.update({f"a{i}": "" for i in range(4)})
    label_to_key = {}
    for i, lbl in enumerate(acts):
        headers[f"h{i}"] = lbl
        label_to_key[lbl] = f"h{i}"
    for i, lbl in enumerate(autres):
        headers[f"a{i}"] = lbl
        label_to_key[lbl] = f"a{i}"
```

(le reste de `_legacy_day` — `build_df`, le `return` — est inchangé)

- [ ] **Step 5 : Garde-fou « aucune colonne » dans `view_day_entry`**

Remplacer le bloc à partir de `cols_labels = _day_columns(day)` jusqu'à la fin de la boucle `for name, typ in roster:` par (on enveloppe le rendu par ressource dans un `else:`, on ajoute le cas `not cols_labels`) :

```python
    cols_labels = _day_columns(day)
    st.markdown("#### 🕐 Heures par ressource")
    roster = _roster(config)
    if not cols_labels:
        st.info("Sélectionnez au moins une activité pour saisir des heures.")
    elif not roster:
        st.info("Ajoutez du personnel / équipement dans « Équipe & Équipements ».")
    else:
        for name, typ in roster:
            h = day["heures"].get(name, {})
            with st.container(border=True):
                top = st.columns([5, 2, 1])
                top[0].markdown(f"{'👷' if typ == 'P' else '🚜'} **{name}**")
                ncols = st.columns(len(cols_labels))
                new_h = {}
                for i, c in enumerate(cols_labels):
                    k = f"h_{jour}_{name}_{c}"
                    if k not in st.session_state:
                        st.session_state[k] = float(h.get(c) or 0.0)
                    v = ncols[i].number_input(c.split(" - ")[0], min_value=0.0, step=0.5,
                                              format="%.1f", key=k, help=c)
                    if v:
                        new_h[c] = float(v)
                top[1].markdown(f"**{sum(new_h.values()):.1f} h**")
                with top[2].popover("⋯"):
                    pk = f"p_{jour}_{name}"
                    if pk not in st.session_state:
                        st.session_state[pk] = float(day["prime"].get(name) or 0.0)
                    prime = st.number_input("Prime", min_value=0.0, step=0.5, format="%.1f", key=pk)
                    ck = f"c_{jour}_{name}"
                    if ck not in st.session_state:
                        st.session_state[ck] = day["commentaire_ligne"].get(name, "")
                    comment = st.text_input("Commentaire", key=ck)
                if new_h: day["heures"][name] = new_h
                else: day["heures"].pop(name, None)
                if prime: day["prime"][name] = float(prime)
                else: day["prime"].pop(name, None)
                if comment.strip(): day["commentaire_ligne"][name] = comment
                else: day["commentaire_ligne"].pop(name, None)
    st.markdown(f"### Total jour : {_day_total(config, day):.2f} h")
```

- [ ] **Step 6 : Ajouter le test du cas « aucune activité » (`tests/test_ui.py`)**

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
    at.session_state["config"] = {"responsable": "", "quart": "",
                                  "personnel": ["Alice"], "equipements": []}
    at.session_state["active_day"] = "Lundi"
    at.session_state["view"] = "day_entry"
    at.run()
    infos = " ".join((m.value or "") for m in at.info)
    assert "activité" in infos.lower()
    assert not any((n.key or "").startswith("h_Lundi_Alice_") for n in at.number_input)
    assert not at.exception
```

(Si `at.info` n'expose pas les messages dans cette version d'AppTest, vérifier l'absence de cartes via les `number_input` clés `h_Lundi_Alice_*` et `not at.exception`, et chercher le texte « activité » dans `at.markdown`/`at.main` — l'essentiel : message présent + aucune carte + pas d'exception.)

- [ ] **Step 7 : Vérifier qu'aucun usage résiduel de FIXED_COL/960 ne subsiste**

Run : `grep -nE "FIXED_COL|\"960\"" app.py`
Expected : aucune correspondance.

- [ ] **Step 8 : Lancer toute la suite**

Run : `.venv/bin/python -m pytest -q 2>&1 | tail -3`
Expected : 0 failed.

- [ ] **Step 9 : Commit**

```bash
git add app.py tests/test_model.py tests/test_ui.py
git commit -m "feat: retrait de la colonne d'heures fixe 960 (heures sur activités uniquement)"
```

---

## Self-Review (auteur du plan)

**Couverture du spec :**
- Suppression `FIXED_COL` + `_day_columns` sans 960 → Step 3. ✓
- `_legacy_day` activités sur h0..h7 → Step 4. ✓
- Garde-fou `view_day_entry` (cols vides → info, pas de `st.columns(0)`) → Step 5. ✓
- Tests : fixture + 4 attentes + nouveau test cas vide → Steps 1, 6. ✓
- Anti-résidu FIXED_COL/960 → Step 7. ✓
- Export/structure pers/equip sinon inchangés → Step 4 ne touche que le mapping. ✓

**Placeholders :** aucun (code complet).

**Cohérence des types :** `_day_columns -> list[str]` ; `_legacy_day` mappe activités→h0.., autres→a0.. ; fixture/attentes alignées (Excavation→h0, P-77→a0, totaux 14/6/8).
