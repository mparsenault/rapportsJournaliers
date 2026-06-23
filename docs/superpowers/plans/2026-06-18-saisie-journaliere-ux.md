# Refonte UX saisie journalière (liste par ressource) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer la matrice `st.data_editor` de la saisie d'un jour par une liste **par ressource** (une carte par personne/équipement, un champ nombre par activité du jour), adaptée au doigt sur tablette.

**Architecture:** `view_day_entry` rend, pour chaque ressource du roster, une carte avec un `st.number_input` par colonne (`960` + activités du jour), un total de ligne, et un `st.popover` « ⋯ » pour Prime/Commentaire. Les champs écrivent directement dans `day["heures"]/["prime"]/["commentaire_ligne"]` (structures inchangées → export intact).

**Tech Stack:** Python, Streamlit 1.50 (`st.number_input`, `st.popover`, `st.columns`), pytest + `streamlit.testing.v1.AppTest`.

## Global Constraints

- Base de code = working tree `app.py` (vues `view_dashboard`/`view_day_entry`/`view_reference`).
- Structures de données **inchangées** : `day["heures"][ressource][colonne]`, `day["prime"][ressource]`, `day["commentaire_ligne"][ressource]`. **Ne stocker que les valeurs non nulles** (champ à 0 → colonne non écrite ; ressource sans heure → absente de `heures` ; idem prime nulle / commentaire vide → clé retirée).
- L'export Excel (`_legacy_day`, `build_workbook`) ne doit PAS changer.
- Colonnes du jour = `_day_columns(day)` = `["960"] + day["activites"] + day["autres"]`.
- Libellé d'un champ d'heures = **code seul** : `colonne.split(" - ")[0]` ; description complète en infobulle via `help=colonne`.
- Clés de widgets stables : `f"h_{jour}_{ressource}_{colonne}"`, `f"p_{jour}_{ressource}"`, `f"c_{jour}_{ressource}"`. **Pré-amorcer** `st.session_state[clé]` depuis `day` quand la clé est absente (ne pas passer `value=` avec une clé).
- `number_input` : `min_value=0.0, step=0.5, format="%.1f"`.
- Roster = personnel (type `"P"`) puis équipements (type `"E"`).
- Tests : `.venv/bin/python -m pytest -q` ; sortie pristine, 0 failed.

## File Structure

- `app.py` — ajout de `_roster` / `_resource_total` ; réécriture du bloc heures de `view_day_entry` ; **suppression** de `_day_grid_df` et `_grid_df_to_day`.
- `tests/test_model.py` — suppression de `test_day_grid_df` / `test_grid_df_to_day_roundtrip` ; ajout de `test_roster_order_and_types` / `test_resource_total`.
- `tests/test_ui.py` — ajout de tests AppTest de saisie d'heures.

---

### Task 1 : Helpers `_roster` et `_resource_total`

**Files:**
- Modify: `app.py` (section « Logic Métier & Grille », près de `_day_total`)
- Modify: `tests/test_model.py`

**Interfaces:**
- Consumes: `config` dict (`personnel`, `equipements`), `day` dict (`heures`).
- Produces:
  - `_roster(config) -> list[tuple[str, str]]` — `(nom, "P"|"E")`, personnel puis équipements.
  - `_resource_total(day, name) -> float` — somme des heures de la ressource.

- [ ] **Step 1 : Écrire les tests (échouent : fonctions absentes)**

Dans `tests/test_model.py`, ajouter (les helpers `_sample_config` / `_sample_day` existent déjà dans ce fichier) :

```python
def test_roster_order_and_types():
    assert app._roster(_sample_config()) == [("Mathis", "P"), ("Roy", "P"), ("Camion v1892", "E")]


def test_resource_total():
    day = _sample_day()
    assert app._resource_total(day, "Mathis") == 14.0          # 8 + 4 + 2
    assert app._resource_total(day, "Camion v1892") == 8.0
    assert app._resource_total(day, "Inconnu") == 0.0          # ressource sans heures
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `.venv/bin/python -m pytest tests/test_model.py::test_roster_order_and_types tests/test_model.py::test_resource_total -q 2>&1 | tail -5`
Expected : FAIL (`AttributeError: module 'app' has no attribute '_roster'`).

- [ ] **Step 3 : Implémenter les helpers dans `app.py`**

Juste avant `def _day_columns(day):` (section « Logic Métier & Grille »), insérer :

```python
def _roster(config):
    """Liste ordonnée des ressources : personnel (P) puis équipements (E)."""
    return ([(n, "P") for n in config.get("personnel", [])]
            + [(e, "E") for e in config.get("equipements", [])])

def _resource_total(day, name):
    """Somme des heures d'une ressource sur toutes ses colonnes."""
    return float(sum(float(v or 0) for v in day["heures"].get(name, {}).values()))
```

- [ ] **Step 4 : Lancer, vérifier le vert**

Run : `.venv/bin/python -m pytest tests/test_model.py -q 2>&1 | tail -3`
Expected : tous les tests de `test_model.py` passent (les deux nouveaux inclus).

- [ ] **Step 5 : Commit**

```bash
git add app.py tests/test_model.py
git commit -m "feat: helpers _roster et _resource_total pour la saisie par ressource"
```

---

### Task 2 : Réécrire la saisie en liste par ressource + retirer la grille

**Files:**
- Modify: `app.py` (`view_day_entry` ; suppression de `_day_grid_df` et `_grid_df_to_day`)
- Modify: `tests/test_model.py` (retrait des tests de grille)
- Modify: `tests/test_ui.py` (nouveaux tests de saisie)

**Interfaces:**
- Consumes: `_roster(config)`, `_resource_total(day, name)` (Task 1), `_day_columns(day)`, `_day_total(config, day)`, `data_source.get_activities`, `data_source.filter_known`.
- Produces: `view_day_entry()` rend la liste par ressource ; écrit `day["heures"]/["prime"]/["commentaire_ligne"]`.

- [ ] **Step 1 : Vérifier qu'aucun autre code n'utilise les helpers de grille**

Run : `grep -n "_day_grid_df\|_grid_df_to_day" app.py`
Expected : occurrences **uniquement** dans `view_day_entry` et les définitions des deux fonctions. (Sinon, escalader — un autre appelant existe.)

- [ ] **Step 2 : Écrire les tests AppTest de saisie (échouent contre l'ancienne grille)**

Dans `tests/test_ui.py` (le module importe déjà `datetime` et `AppTest`), ajouter :

```python
def _open_day_for_entry(monkeypatch, jour="Lundi", personnel=("Alice",)):
    import data_source
    monkeypatch.setattr(data_source, "get_projects", lambda: [(1, "P-100")])
    monkeypatch.setattr(data_source, "get_activities", lambda pid: ["C01 - Test"])
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["projet"] = {"no": "P-100", "id_project": 1,
                                  "semaine": datetime.date(2026, 6, 7),
                                  "adresse": "", "lat": None, "lon": None}
    at.session_state["config"] = {"responsable": "", "quart": "",
                                  "personnel": list(personnel), "equipements": []}
    at.session_state["active_day"] = jour
    at.session_state["view"] = "day_entry"
    at.run()
    return at


def test_day_hours_entry_updates_model(monkeypatch):
    at = _open_day_for_entry(monkeypatch)
    # sélectionner l'activité du jour -> colonnes = 960 + "C01 - Test"
    acts = [m for m in at.multiselect if m.label == "Activités"][0]
    acts.set_value(["C01 - Test"]).run()
    # saisir 8 h sur 960 pour Alice (champ ciblé par clé)
    champ = [n for n in at.number_input if n.key == "h_Lundi_Alice_960"][0]
    champ.set_value(8.0).run()
    day = at.session_state["jours"]["Lundi"]
    assert day["heures"]["Alice"]["960"] == 8.0
    assert not at.exception


def test_day_hours_no_grid_data_editor(monkeypatch):
    at = _open_day_for_entry(monkeypatch)
    # la matrice data_editor a disparu, et les champs d'heures par clé existent
    assert any(n.key == "h_Lundi_Alice_960" for n in at.number_input)
    assert not at.exception


def test_day_prime_via_popover(monkeypatch):
    at = _open_day_for_entry(monkeypatch)
    prime = [n for n in at.number_input if n.key == "p_Lundi_Alice"][0]
    prime.set_value(2.0).run()
    assert at.session_state["jours"]["Lundi"]["prime"]["Alice"] == 2.0
```

- [ ] **Step 3 : Lancer, vérifier l'échec**

Run : `.venv/bin/python -m pytest tests/test_ui.py::test_day_hours_entry_updates_model -q 2>&1 | tail -6`
Expected : FAIL (aucun `number_input` de clé `h_Lundi_Alice_960` — c'est encore la grille `data_editor`).

- [ ] **Step 4 : Réécrire `view_day_entry` dans `app.py`**

Remplacer **toute** la fonction `view_day_entry` par :

```python
def view_day_entry():
    jour = st.session_state.active_day
    day = st.session_state.jours[jour]
    config = st.session_state.config
    if st.button("⬅️ Retour"): st.session_state.view = "dashboard"; st.rerun()
    st.subheader(f"Saisie : {jour}")
    with st.expander("🌤️ Météo & Description"):
        m1, m2, m3 = st.columns(3)
        day["temp_am"] = m1.number_input("Temp AM", value=float(day["temp_am"] or 0))
        day["temp_pm"] = m2.number_input("Temp PM", value=float(day["temp_pm"] or 0))
        day["conditions"] = m3.multiselect("Conditions", CONDITIONS, default=day["conditions"])
        day["description"] = st.text_input("Description", day["description"])
    with st.container(border=True):
        acts = data_source.get_activities(st.session_state.projet.get("id_project"))
        day["activites"] = st.multiselect(
            "Activités", acts,
            default=data_source.filter_known(day["activites"], acts))
        day["autres"] = st.multiselect("Autres", st.session_state.ref["autres_projets"], default=day["autres"])

    cols_labels = _day_columns(day)              # ["960"] + activités + autres
    st.markdown("#### 🕐 Heures par ressource")
    roster = _roster(config)
    if not roster:
        st.info("Ajoutez du personnel / équipement dans « Équipe & Équipements ».")
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

- [ ] **Step 5 : Supprimer les helpers de grille devenus inutiles**

Dans `app.py`, **supprimer entièrement** les deux fonctions `def _day_grid_df(config, day):` et `def _grid_df_to_day(edited, day):` (avec leurs corps). Conserver `_day_columns` et `_day_total`.

- [ ] **Step 6 : Retirer les tests de grille obsolètes**

Dans `tests/test_model.py`, **supprimer** `test_day_grid_df` et `test_grid_df_to_day_roundtrip` (ces fonctions n'existent plus). Conserver `test_day_total`, `test_day_columns`, `test_empty_day_shape`, `test_legacy_day_maps_labels_to_keys`, et tous les autres.

- [ ] **Step 7 : Lancer les tests ciblés, vérifier le vert**

Run : `.venv/bin/python -m pytest tests/test_ui.py::test_day_hours_entry_updates_model tests/test_ui.py::test_day_hours_no_grid_data_editor tests/test_ui.py::test_day_prime_via_popover -q 2>&1 | tail -6`
Expected : 3 passed.
*(Si `test_day_prime_via_popover` échoue parce qu'AppTest n'expose pas les widgets internes d'un `st.popover` : vérifier ce point ; si la limitation est confirmée, remplacer ce test par une vérification du commentaire/prime via la même clé hors-popover n'est PAS possible — signaler à la place que Prime/Commentaire sont vérifiés manuellement et retirer ce test. Documenter le choix dans le rapport.)*

- [ ] **Step 8 : Lancer toute la suite**

Run : `.venv/bin/python -m pytest -q 2>&1 | tail -3`
Expected : 0 failed.

- [ ] **Step 9 : Commit**

```bash
git add app.py tests/test_model.py tests/test_ui.py
git commit -m "feat: saisie journalière en liste par ressource (remplace la matrice data_editor)"
```

---

## Self-Review (auteur du plan)

**Couverture du spec :**
- Liste par ressource, champ par colonne, total ligne, popover Prime/Commentaire → Task 2 Step 4. ✓
- Libellé = code seul + help = label complet → Step 4 (`c.split(" - ")[0]`, `help=c`). ✓
- Clés stables + pré-amorçage session_state → Step 4. ✓
- Non-nul uniquement (heures/prime/commentaire) → Step 4 (`if new_h / else pop`, etc.). ✓
- Helpers `_roster` / `_resource_total` → Task 1. ✓
- Retrait `_day_grid_df` / `_grid_df_to_day` + tests → Task 2 Steps 5-6. ✓
- Export inchangé → aucune modification de `_legacy_day`/`build_workbook` ; vérifié par la suite existante (Step 8). ✓
- Tests helpers + AppTest saisie → Tasks 1 & 2. ✓

**Placeholders :** aucun (code complet). Le seul point conditionnel (Step 7) concerne une limite éventuelle d'AppTest sur les popovers, avec consigne explicite.

**Cohérence des types :** `_roster -> [(str,str)]`, `_resource_total -> float`, clés `h_/p_/c_{jour}_{name}[_col]` cohérentes entre Step 4 et les tests.
