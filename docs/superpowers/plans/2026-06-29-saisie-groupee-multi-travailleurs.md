# Saisie groupée multi-travailleurs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre de copier (fusion) les activités + heures de la fiche du travailleur courant vers plusieurs autres membres du personnel, en un clic.

**Architecture :** Une fonction pure de modèle `_apply_hours_to_resources(quart, source_name, dest_names)` effectue la fusion sur `quart["heures"]` (testable sans Streamlit). La couche UI, dans `view_day_entry`, ajoute un `multiselect` « Appliquer aussi à… » + un bouton « Appliquer à N travailleur(s) » qui appelle la fonction pure, purge les clés `session_state` des widgets d'heures des destinataires pour forcer leur réamorçage, marque l'état modifié et relance le rendu.

**Tech Stack :** Python 3.9, Streamlit, pytest, `streamlit.testing.v1.AppTest`.

## Global Constraints

- Cible Python 3.9 (pas de syntaxe 3.10+ : pas de `match`, pas de `X | Y` en annotations runtime).
- Les tests de modèle vivent dans `tests/test_model.py` et importent `app` directement.
- Les tests UI utilisent `AppTest.from_file("app.py")` (cf. `tests/test_ui.py`).
- Le modèle d'heures est `quart["heures"][nom][activité] = {"mode","TR","TS","ranges"}` ; normaliser via `app._norm_entry` avant copie.
- Champs copiés : **activités + heures uniquement**. Ne JAMAIS copier équipement, prime, commentaire.
- Destinataires : personnel (`type == "P"`) uniquement, hors travailleur courant.
- Sémantique fusion : activités de la source écrasent les activités homonymes du destinataire ; les autres activités du destinataire sont conservées.

---

### Task 1: Fonction pure de fusion `_apply_hours_to_resources`

**Files:**
- Modify: `app.py` (ajouter la fonction près des helpers de modèle d'heures, après `_norm_entry`/`_norm_pair`, ~ligne 403)
- Test: `tests/test_model.py`

**Interfaces:**
- Consumes : `app._norm_entry(raw) -> {"mode","ranges","TR","TS"}` (déjà existant).
- Produces : `app._apply_hours_to_resources(quart: dict, source_name: str, dest_names: list[str]) -> list[str]`
  - Copie (fusion) les entrées d'heures de `quart["heures"].get(source_name, {})` vers chaque nom de `dest_names`.
  - Pour chaque activité de la source : `quart["heures"].setdefault(dest, {})[act] = <copie normalisée indépendante>`.
  - Les activités préexistantes du destinataire absentes de la source sont conservées.
  - N'agit pas si la source est vide ou si un dest == source_name (ignoré).
  - Renvoie la liste des destinataires effectivement modifiés (ordre de `dest_names`, sans doublon ni source).

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à la fin de `tests/test_model.py` :

```python
def test_apply_hours_copies_to_empty_dest():
    q = app._empty_quart()
    q["personnel"] = ["Alice", "Bob"]
    q["heures"] = {"Alice": {"Excavation": {"mode": "direct", "ranges": [],
                                            "TR": 4.0, "TS": 1.0}}}
    changed = app._apply_hours_to_resources(q, "Alice", ["Bob"])
    assert changed == ["Bob"]
    assert q["heures"]["Bob"]["Excavation"]["TR"] == 4.0
    assert q["heures"]["Bob"]["Excavation"]["TS"] == 1.0
    # source intacte
    assert q["heures"]["Alice"]["Excavation"]["TR"] == 4.0


def test_apply_hours_ranges_are_independent():
    q = app._empty_quart()
    q["heures"] = {"Alice": {"Excavation": {
        "mode": "plage",
        "ranges": [{"debut": "08:00", "fin": "12:00", "type": "TR"}],
        "TR": 4.0, "TS": 0.0}}}
    app._apply_hours_to_resources(q, "Alice", ["Bob"])
    # muter la source ne doit pas toucher le destinataire
    q["heures"]["Alice"]["Excavation"]["ranges"][0]["fin"] = "16:00"
    assert q["heures"]["Bob"]["Excavation"]["ranges"][0]["fin"] == "12:00"


def test_apply_hours_merges_without_erasing():
    q = app._empty_quart()
    q["heures"] = {
        "Alice": {"Excavation": {"mode": "direct", "ranges": [], "TR": 4.0, "TS": 0.0}},
        "Bob": {"Coffrage": {"mode": "direct", "ranges": [], "TR": 2.0, "TS": 0.0},
                "Excavation": {"mode": "direct", "ranges": [], "TR": 1.0, "TS": 0.0}},
    }
    app._apply_hours_to_resources(q, "Alice", ["Bob"])
    # activité propre à Bob conservée
    assert q["heures"]["Bob"]["Coffrage"]["TR"] == 2.0
    # activité commune écrasée par la source
    assert q["heures"]["Bob"]["Excavation"]["TR"] == 4.0


def test_apply_hours_empty_source_noop():
    q = app._empty_quart()
    q["heures"] = {"Bob": {"Coffrage": {"mode": "direct", "ranges": [], "TR": 2.0, "TS": 0.0}}}
    changed = app._apply_hours_to_resources(q, "Alice", ["Bob"])
    assert changed == []
    assert q["heures"]["Bob"]["Coffrage"]["TR"] == 2.0


def test_apply_hours_ignores_source_in_dests():
    q = app._empty_quart()
    q["heures"] = {"Alice": {"Excavation": {"mode": "direct", "ranges": [], "TR": 4.0, "TS": 0.0}}}
    changed = app._apply_hours_to_resources(q, "Alice", ["Alice", "Bob"])
    assert changed == ["Bob"]
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `pytest tests/test_model.py -k apply_hours -v`
Expected: FAIL — `AttributeError: module 'app' has no attribute '_apply_hours_to_resources'`

- [ ] **Step 3: Implémenter la fonction minimale**

Dans `app.py`, juste après la définition de `_norm_entry` (~ligne 403), ajouter :

```python
def _copy_entry(raw):
    """Copie normalisée et indépendante d'une entrée d'heures."""
    e = _norm_entry(raw)
    return {
        "mode": e["mode"],
        "ranges": [dict(r) for r in e["ranges"]],
        "TR": e["TR"],
        "TS": e["TS"],
    }


def _apply_hours_to_resources(quart, source_name, dest_names):
    """Copie (fusion) les heures de `source_name` vers chaque destinataire.

    Pour chaque activité de la source, écrit une copie indépendante dans
    quart["heures"][dest][activité]. Les activités préexistantes du
    destinataire absentes de la source sont conservées ; les activités
    communes sont écrasées par la valeur source. Renvoie la liste des
    destinataires effectivement modifiés.
    """
    source = quart["heures"].get(source_name) or {}
    if not source:
        return []
    changed = []
    seen = set()
    for dest in dest_names:
        if dest == source_name or dest in seen:
            continue
        seen.add(dest)
        target = quart["heures"].setdefault(dest, {})
        for act, raw in source.items():
            target[act] = _copy_entry(raw)
        changed.append(dest)
    return changed
```

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

Run: `pytest tests/test_model.py -k apply_hours -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_model.py
git commit -m "feat(saisie): fonction pure de copie/fusion des heures entre travailleurs"
```

---

### Task 2: UI « Appliquer aussi à… » dans la fiche de saisie

**Files:**
- Modify: `app.py` — dans `view_day_entry`, panneau de droite (`with col_pane:`), après l'appel à `_render_resource_card` (~ligne 1432)
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes : `app._apply_hours_to_resources(quart, source_name, dest_names)` (Task 1) ; `app._roster(quart)` qui renvoie une liste de `(nom, type)` ; `app._mark_dirty()`.
- Produces : aucun symbole nouveau consommé ailleurs (couche UI terminale).

- [ ] **Step 1: Écrire le test UI qui échoue**

Dans `tests/test_ui.py`, ajouter un test. Il s'appuie sur les helpers existants `_run_with_project` (sélectionne un projet) ; on injecte du personnel et des heures directement dans `session_state`, puis on déclenche l'application via le bouton.

```python
def test_appliquer_heures_a_autre_travailleur(monkeypatch):
    import app
    at = _run_with_project(monkeypatch)
    jour = at.session_state["active_day"]
    quart_name = app._current_quart_name(jour)
    quart = at.session_state["jours"][jour]["quarts"][quart_name]
    quart["personnel"] = ["Alice", "Bob"]
    quart["heures"] = {"Alice": {"Excavation": {"mode": "direct", "ranges": [],
                                               "TR": 4.0, "TS": 0.0}}}
    at.session_state[f"resource_sel_{jour}_{quart_name}"] = "Alice"
    at.run()
    # cocher Bob comme destinataire
    ms = [m for m in at.multiselect if m.label == "Appliquer aussi à…"][0]
    ms.set_value(["Bob"]).run()
    # cliquer le bouton d'application
    btn = [b for b in at.button if "Appliquer à" in b.label][0]
    btn.click().run()
    quart = at.session_state["jours"][jour]["quarts"][quart_name]
    assert quart["heures"]["Bob"]["Excavation"]["TR"] == 4.0
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `pytest tests/test_ui.py -k appliquer_heures -v`
Expected: FAIL — aucun `multiselect` avec le label « Appliquer aussi à… » (IndexError sur la liste).

- [ ] **Step 3: Implémenter la section UI**

Dans `app.py`, `view_day_entry`, dans le bloc `with col_pane:`, juste après la ligne `_render_resource_card(jour, quart_name, quart, name, typ, all_activities)` (~ligne 1432), insérer :

```python
                # --- Appliquer les activités/heures de cette fiche à d'autres ---
                source_heures = quart["heures"].get(name) or {}
                dest_options = [n for n, t in full_roster if t == "P" and n != name]
                if dest_options:
                    with st.container(border=True):
                        st.caption("👥 Copier les activités et heures de cette fiche vers d'autres travailleurs")
                        bulk_key = f"bulk_apply_{jour}_{quart_name}_{name}"
                        dests = st.multiselect("Appliquer aussi à…", dest_options,
                                               key=bulk_key,
                                               placeholder="🔍 Travailleurs destinataires…")
                        disabled = (not dests) or (not source_heures)
                        if not source_heures:
                            st.caption("Saisissez d'abord des heures pour les copier.")
                        if st.button(f"Appliquer à {len(dests)} travailleur(s)",
                                     key=f"bulk_btn_{jour}_{quart_name}_{name}",
                                     disabled=disabled, use_container_width=True):
                            changed = _apply_hours_to_resources(quart, name, dests)
                            _purge_resource_hour_keys(jour, quart_name, changed)
                            st.session_state[bulk_key] = []
                            _mark_dirty()
                            st.success("Copié vers : " + ", ".join(changed))
                            st.rerun()
```

Puis ajouter le helper de purge des clés widget, près des autres helpers d'app (par ex. juste avant `_render_resource_card`, ~ligne 1187) :

```python
def _purge_resource_hour_keys(jour, quart_name, names):
    """Supprime de session_state les clés des widgets d'heures des ressources
    `names` (pour le jour/quart courant) afin qu'elles se réamorcent depuis le
    modèle au prochain rendu. Couvre activités, modes, TR/TS et plages."""
    prefixes = ("acts_", "mode_", "tr_", "ts_", "ranges_", "rangeseq_",
                "rg_deb_", "rg_fin_", "rg_knd_", "rg_del_", "rg_add_")
    for nm in names:
        seg = f"{jour}_{quart_name}_{nm}"
        for k in list(st.session_state.keys()):
            if seg in k and any(k.startswith(p) for p in prefixes):
                del st.session_state[k]
```

- [ ] **Step 4: Lancer le test pour vérifier le succès**

Run: `pytest tests/test_ui.py -k appliquer_heures -v`
Expected: PASS

- [ ] **Step 5: Lancer toute la suite (non-régression)**

Run: `pytest -q`
Expected: PASS (aucune régression)

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_ui.py
git commit -m "feat(saisie): appliquer activités/heures de la fiche à plusieurs travailleurs"
```

---

## Self-Review

**Couverture du spec :**
- Multiselect « Appliquer aussi à… » + bouton explicite → Task 2. ✓
- Copie ponctuelle + fusion → Task 1 (`_apply_hours_to_resources`) + tests. ✓
- Copie activités + heures uniquement (pas équipement/prime/commentaire) → la fonction n'agit que sur `quart["heures"]`. ✓
- Conflit = fusion (conserve les activités propres, écrase les communes) → `test_apply_hours_merges_without_erasing`. ✓
- Destinataires personnel uniquement, hors courant → `dest_options` filtre `t == "P" and n != name`. ✓
- Bouton désactivé si pas de destinataire ou fiche vide → `disabled` + caption d'aide. ✓
- Purge des clés widget des destinataires → `_purge_resource_hour_keys`. ✓
- Mode plage : ranges copiés en profondeur et indépendants → `test_apply_hours_ranges_are_independent`. ✓
- `_mark_dirty` + message + `st.rerun` → Task 2 Step 3. ✓

**Placeholders :** aucun — tout le code est fourni.

**Cohérence des types :** `_apply_hours_to_resources(quart, source_name, dest_names) -> list` utilisé tel quel en Task 2. `_purge_resource_hour_keys(jour, quart_name, names)` défini et appelé avec les mêmes paramètres. `_copy_entry` interne. Noms de clés (`acts_`, `mode_`, `tr_`, `ts_`, `ranges_`, `rg_*`) alignés sur ceux de `_render_activity_hours`/`_render_ranges_editor`/`_render_resource_card`.
