# Rail multisélection — saisie groupée Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer la section « Appliquer aussi à… » par une multisélection dans le rail : cocher 2+ ressources affiche une fiche de groupe vierge dont les activités+heures sont fusionnées dans tous les sélectionnés.

**Architecture :** Une fonction pure `_apply_hours_dict_to_resources(quart, hours, dest_names)` fusionne un dict d'heures dans chaque destinataire (l'ancienne `_apply_hours_to_resources` délègue à elle en Task 1, puis est retirée en Task 2). L'UI de `view_day_entry` passe d'une sélection unique (`resource_sel_…`) à un ensemble (`sel_set_…`) ; le panneau de droite affiche une invite (0), la fiche individuelle (1) ou une fiche de groupe (2+) via `_render_group_card`.

**Tech Stack :** Python 3.9, Streamlit, pytest, `streamlit.testing.v1.AppTest`.

## Global Constraints

- Cible Python 3.9 — pas de syntaxe 3.10+ (`match`, `X | Y` runtime).
- Tests modèle dans `tests/test_model.py` (importent `app`) ; tests UI dans `tests/test_ui.py` via `AppTest.from_file("app.py")` avec le helper `_run_with_project(monkeypatch)`.
- Runner : `.venv/bin/python -m pytest`. Tester par FICHIER ciblé (la suite complète a un flake d'inter-pollution connu).
- Modèle d'heures : `quart["heures"][nom][activité] = {"mode","TR","TS","ranges"}` ; copie via `_copy_entry`.
- Fusion : activités saisies écrasent les homonymes du destinataire ; les autres activités du destinataire sont conservées.
- Champs touchés en groupe : activités + heures UNIQUEMENT (jamais équipement/prime/commentaire).
- On ne peut pas modifier/supprimer la clé d'un widget après son instanciation dans le run → utiliser le pattern de vidage différé (drapeau `clear_*` consommé AVANT instanciation), comme pour l'ajout manuel d'employé.
- Le rail reste en `st.button` (testable sous AppTest, contrairement à `st.pills`).

---

### Task 1: Fusion par dictionnaire `_apply_hours_dict_to_resources`

**Files:**
- Modify: `app.py` — ajouter la fonction près de `_apply_hours_to_resources` (~ligne 417) ; refactorer `_apply_hours_to_resources` pour déléguer.
- Test: `tests/test_model.py`

**Interfaces:**
- Consumes : `app._copy_entry(raw)` (existant).
- Produces : `app._apply_hours_dict_to_resources(quart, hours, dest_names) -> list`
  - Fusionne le dict `hours` (`{activité: entrée}`) dans chaque destinataire de `dest_names`.
  - N'agit pas si `hours` est vide (renvoie `[]`). Dédoublonne `dest_names`. Renvoie la liste des destinataires modifiés.
  - `app._apply_hours_to_resources(quart, source_name, dest_names)` continue d'exister (délègue) jusqu'à son retrait en Task 2.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à la fin de `tests/test_model.py` :

```python
def test_apply_dict_copies_to_empty_dest():
    q = app._empty_quart()
    q["personnel"] = ["Alice", "Bob"]
    hours = {"Excavation": {"mode": "direct", "ranges": [], "TR": 4.0, "TS": 1.0}}
    changed = app._apply_hours_dict_to_resources(q, hours, ["Bob"])
    assert changed == ["Bob"]
    assert q["heures"]["Bob"]["Excavation"]["TR"] == 4.0
    assert q["heures"]["Bob"]["Excavation"]["TS"] == 1.0


def test_apply_dict_ranges_are_independent():
    q = app._empty_quart()
    hours = {"Excavation": {"mode": "plage",
                            "ranges": [{"debut": "08:00", "fin": "12:00", "type": "TR"}],
                            "TR": 4.0, "TS": 0.0}}
    app._apply_hours_dict_to_resources(q, hours, ["Alice", "Bob"])
    # muter la source ne doit pas toucher les destinataires
    hours["Excavation"]["ranges"][0]["fin"] = "16:00"
    assert q["heures"]["Alice"]["Excavation"]["ranges"][0]["fin"] == "12:00"
    assert q["heures"]["Bob"]["Excavation"]["ranges"][0]["fin"] == "12:00"
    # les deux destinataires sont indépendants l'un de l'autre
    q["heures"]["Alice"]["Excavation"]["ranges"][0]["fin"] = "10:00"
    assert q["heures"]["Bob"]["Excavation"]["ranges"][0]["fin"] == "12:00"


def test_apply_dict_merges_without_erasing():
    q = app._empty_quart()
    q["heures"] = {"Bob": {"Coffrage": {"mode": "direct", "ranges": [], "TR": 2.0, "TS": 0.0},
                           "Excavation": {"mode": "direct", "ranges": [], "TR": 1.0, "TS": 0.0}}}
    hours = {"Excavation": {"mode": "direct", "ranges": [], "TR": 4.0, "TS": 0.0}}
    app._apply_hours_dict_to_resources(q, hours, ["Bob"])
    assert q["heures"]["Bob"]["Coffrage"]["TR"] == 2.0   # propre à Bob conservée
    assert q["heures"]["Bob"]["Excavation"]["TR"] == 4.0  # commune écrasée


def test_apply_dict_empty_hours_noop():
    q = app._empty_quart()
    q["heures"] = {"Bob": {"Coffrage": {"mode": "direct", "ranges": [], "TR": 2.0, "TS": 0.0}}}
    changed = app._apply_hours_dict_to_resources(q, {}, ["Bob"])
    assert changed == []
    assert q["heures"]["Bob"]["Coffrage"]["TR"] == 2.0


def test_apply_dict_dedupes_dests():
    q = app._empty_quart()
    hours = {"Excavation": {"mode": "direct", "ranges": [], "TR": 4.0, "TS": 0.0}}
    changed = app._apply_hours_dict_to_resources(q, hours, ["Bob", "Bob", "Alice"])
    assert changed == ["Bob", "Alice"]
```

- [ ] **Step 2: Lancer pour vérifier l'échec**

Run: `.venv/bin/python -m pytest tests/test_model.py -k apply_dict -v`
Expected: FAIL — `AttributeError: module 'app' has no attribute '_apply_hours_dict_to_resources'`

- [ ] **Step 3: Implémenter + refactorer**

Dans `app.py`, juste après `_copy_entry` (~ligne 415) et avant `_apply_hours_to_resources`, ajouter :

```python
def _apply_hours_dict_to_resources(quart, hours, dest_names):
    """Fusionne le dict `hours` ({activité: entrée}) dans chaque destinataire.

    Pour chaque activité de `hours`, écrit une copie indépendante dans
    quart["heures"][dest][activité]. Les activités préexistantes du destinataire
    absentes de `hours` sont conservées ; les communes sont écrasées. N'agit pas
    si `hours` est vide. Renvoie la liste des destinataires effectivement
    modifiés (sans doublon, dans l'ordre de `dest_names`).
    """
    if not hours:
        return []
    changed = []
    seen = set()
    for dest in dest_names:
        if dest in seen:
            continue
        seen.add(dest)
        target = quart["heures"].setdefault(dest, {})
        for act, raw in hours.items():
            target[act] = _copy_entry(raw)
        changed.append(dest)
    return changed
```

Puis remplacer le CORPS de `_apply_hours_to_resources` (garder sa signature et son docstring) par une délégation :

```python
def _apply_hours_to_resources(quart, source_name, dest_names):
    """Copie (fusion) les heures de `source_name` vers chaque destinataire.

    (Conservée pour compatibilité ; délègue à _apply_hours_dict_to_resources.)
    """
    source = quart["heures"].get(source_name) or {}
    dests = [d for d in dest_names if d != source_name]
    return _apply_hours_dict_to_resources(quart, source, dests)
```

- [ ] **Step 4: Lancer pour vérifier le succès**

Run: `.venv/bin/python -m pytest tests/test_model.py -q`
Expected: PASS (anciens tests `apply_hours` + nouveaux `apply_dict`, 0 régression)

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_model.py
git commit -m "refactor(saisie): fusion des heures par dictionnaire (_apply_hours_dict_to_resources)"
```

---

### Task 2: Rail multisélection + fiche de groupe

**Files:**
- Modify: `app.py` — `_clear_quart_widget_state` (~ligne 120-132) ; ajouter `_render_group_card` (près de `_render_resource_card`, ~ligne 1237) ; réécrire le bloc rail/pane de `view_day_entry` (~lignes 1444-1509) ; retirer `_apply_hours_to_resources` (~ligne 417) devenu mort.
- Test: `tests/test_ui.py`, `tests/test_model.py` (retrait des tests de l'ancienne fonction)

**Interfaces:**
- Consumes : `app._apply_hours_dict_to_resources(quart, hours, dest_names)` (Task 1) ; `app._roster(quart)` → liste `(nom, type)` ; `app._render_resource_card(jour, quart_name, quart, name, typ, all_activities)` ; `app._render_activity_hours(jour, quart_name, name, act, raw)` → entrée normalisée ; `app._purge_resource_hour_keys(jour, quart_name, names)` ; `app._mark_dirty()` ; `app._resource_total(quart, name)`.
- Produces : `app._render_group_card(jour, quart_name, quart, selection, all_activities, sel_set_key)` (UI, pas de valeur de retour utilisée).

- [ ] **Step 1: Écrire les tests UI qui échouent**

Dans `tests/test_ui.py`, ajouter ces tests. Ils naviguent vers la saisie comme le test existant (clic carte « Lundi »), injectent du personnel, puis pilotent le rail.

```python
def _enter_day_with_staff(monkeypatch, staff, activities=("Excavation",)):
    import data_source
    monkeypatch.setattr(data_source, "get_activities", lambda pid: list(activities))
    at = _run_with_project(monkeypatch)
    [b for b in at.button if "Lundi" in (b.label or "")][0].click().run()
    jour = at.session_state["active_day"]
    _aq = f"active_quart_{jour}"
    quart_name = (at.session_state[_aq] if _aq in at.session_state
                  else list(at.session_state["jours"][jour]["quarts"].keys())[0])
    quart = at.session_state["jours"][jour]["quarts"][quart_name]
    quart["personnel"] = list(staff)
    at.run()
    return at, jour, quart_name


def _rail_click(at, jour, quart_name, name):
    btn = [b for b in at.button if b.key == f"pick_{jour}_{quart_name}_{name}"][0]
    btn.click().run()


def test_groupe_apparait_quand_2_selectionnes(monkeypatch):
    at, jour, qn = _enter_day_with_staff(monkeypatch, ["Alice", "Bob"])
    _rail_click(at, jour, qn, "Alice")
    _rail_click(at, jour, qn, "Bob")
    # La fiche de groupe expose un multiselect "Activités" et le bouton d'application.
    assert [m for m in at.multiselect if m.label == "Activités"]
    assert [b for b in at.button if "Appliquer à" in (b.label or "")]


def test_un_seul_selectionne_montre_fiche_individuelle(monkeypatch):
    at, jour, qn = _enter_day_with_staff(monkeypatch, ["Alice", "Bob"])
    _rail_click(at, jour, qn, "Alice")
    # Fiche individuelle : pas de bouton "Appliquer à", présence des pills Équipement.
    assert not [b for b in at.button if "Appliquer à" in (b.label or "")]
    assert [m for m in at.multiselect if m.label == "Activités"]


def test_ancienne_section_appliquer_aussi_absente(monkeypatch):
    at, jour, qn = _enter_day_with_staff(monkeypatch, ["Alice", "Bob"])
    _rail_click(at, jour, qn, "Alice")
    assert not [m for m in at.multiselect if m.label == "Appliquer aussi à…"]


def test_groupe_applique_heures_et_vide_selection(monkeypatch):
    at, jour, qn = _enter_day_with_staff(monkeypatch, ["Alice", "Bob"])
    _rail_click(at, jour, qn, "Alice")
    _rail_click(at, jour, qn, "Bob")
    # choisir une activité de groupe
    ms = [m for m in at.multiselect if m.label == "Activités"][0]
    ms.set_value(["Excavation"]).run()
    # saisir des heures TR
    tr = [n for n in at.number_input if n.label == "TR"][0]
    tr.set_value(8.0).run()
    # appliquer
    btn = [b for b in at.button if "Appliquer à" in (b.label or "")][0]
    btn.click().run()
    assert not at.exception
    quart = at.session_state["jours"][jour]["quarts"][qn]
    assert quart["heures"]["Alice"]["Excavation"]["TR"] == 8.0
    assert quart["heures"]["Bob"]["Excavation"]["TR"] == 8.0
    # la sélection est vidée -> retour à l'invite (plus de bouton "Appliquer à")
    assert at.session_state[f"sel_set_{jour}_{qn}"] == []
    assert not [b for b in at.button if "Appliquer à" in (b.label or "")]
```

- [ ] **Step 2: Lancer pour vérifier l'échec**

Run: `.venv/bin/python -m pytest tests/test_ui.py -k "groupe or appliquer_aussi or individuelle" -v`
Expected: FAIL (le rail est encore en sélection unique ; pas de `_render_group_card`, pas de clé `sel_set_…`, pas de bouton clé `pick_…` en multi).

- [ ] **Step 3: Mettre à jour `_clear_quart_widget_state`**

Dans `app.py` (~ligne 125), remplacer l'entrée `f"resource_sel_{jour}_{quart_name}"` par les clés de la nouvelle sélection et de la fiche de groupe :

```python
                f"{jour}_{quart_name}_cond", f"sel_set_{jour}_{quart_name}",
                f"grp_acts_{jour}_{quart_name}", f"clear_grp_{jour}_{quart_name}",
```

(c.-à-d. supprimer `resource_sel_{jour}_{quart_name}` de la liste et ajouter ces trois clés ; les clés d'heures du nom synthétique `__groupe__` sont déjà couvertes par les préfixes `tr_/ts_/mode_/ranges_/rangeseq_/rg_*` + `acts_` qui contiennent `{jour}_{quart_name}_`).

- [ ] **Step 4: Ajouter `_render_group_card`**

Dans `app.py`, juste avant `def _render_resource_card` (~ligne 1237), ajouter :

```python
def _render_group_card(jour, quart_name, quart, selection, all_activities, sel_set_key):
    """Fiche de groupe : saisie d'activités + heures appliquée à tous les
    travailleurs sélectionnés (fusion). Activités/heures uniquement."""
    st.markdown(f"##### 👥 {len(selection)} travailleurs : " + ", ".join(selection))
    grp_acts_key = f"grp_acts_{jour}_{quart_name}"
    grp_clear_key = f"clear_grp_{jour}_{quart_name}"
    # Réinitialisation différée : on purge AVANT d'instancier les widgets de groupe.
    if st.session_state.pop(grp_clear_key, False):
        _purge_resource_hour_keys(jour, quart_name, ["__groupe__"])
        st.session_state.pop(grp_acts_key, None)
    sel_acts = st.multiselect("Activités", sorted(all_activities), key=grp_acts_key,
                              placeholder="🔍 Activités travaillées…", on_change=_mark_dirty)
    grp_heures = {}
    for act in (sel_acts or []):
        entry = _render_activity_hours(jour, quart_name, "__groupe__", act, {})
        if entry["TR"] > 0 or entry["TS"] > 0 or entry["ranges"]:
            grp_heures[act] = entry
    if not grp_heures:
        st.caption("Saisissez des activités et des heures à appliquer.")
    if st.button(f"Appliquer à {len(selection)} travailleur(s)",
                 key=f"grp_btn_{jour}_{quart_name}", disabled=not grp_heures,
                 use_container_width=True):
        changed = _apply_hours_dict_to_resources(quart, grp_heures, selection)
        _purge_resource_hour_keys(jour, quart_name, changed)
        st.session_state[sel_set_key] = []
        st.session_state[grp_clear_key] = True
        _mark_dirty()
        st.success("Appliqué à : " + ", ".join(changed))
        st.rerun()
```

- [ ] **Step 5: Réécrire le bloc rail/pane de `view_day_entry`**

Dans `app.py`, remplacer tout le bloc `else:` qui commence par le commentaire « Sélecteur maître-détail » (~ligne 1444) jusqu'à la fin du `with col_pane:` incluant l'ancienne section « Appliquer aussi à… » (~ligne 1509) par :

```python
            # Rail multisélection : boutons-bascules (st.button testable sous
            # AppTest, contrairement à st.pills) ; le panneau de droite s'adapte
            # au nombre de ressources cochées (0 = invite, 1 = fiche, 2+ = groupe).
            labels = [n for n, _t in full_roster]
            by_label = {n: (n, t) for n, t in full_roster}
            sel_set_key = f"sel_set_{jour}_{quart_name}"
            selection = [n for n in st.session_state.get(sel_set_key, []) if n in labels]
            col_rail, col_pane = st.columns([1, 2], gap="medium")
            with col_rail:
                q = st.text_input("Rechercher une ressource", key=f"res_search_{jour}_{quart_name}",
                                  placeholder="🔍 Rechercher une ressource…",
                                  label_visibility="collapsed")
                done = sum(1 for n in labels if _resource_total(quart, n) > 0)
                filt = [n for n in labels if q.casefold() in n.casefold()] if q else labels
                st.caption(f"{len(filt)} résultat(s) · {done} sur {len(labels)} saisies · "
                           f"{len(selection)} sélectionné(s)")
                with st.container(height=300):
                    if not filt:
                        st.caption("Aucune ressource ne correspond.")
                    for n in filt:
                        _n, t = by_label[n]
                        tot = _resource_total(quart, n)
                        ic = "👷" if t == "P" else "🚜"
                        status = "🟢" if tot > 0 else "⚪"
                        is_sel = n in selection
                        check = "☑️" if is_sel else "⬜"
                        if st.button(f"{check} {ic} {n} · {status} {tot:.1f} h",
                                     key=f"pick_{jour}_{quart_name}_{n}",
                                     use_container_width=True,
                                     type="primary" if is_sel else "secondary"):
                            cur = [x for x in st.session_state.get(sel_set_key, []) if x in labels]
                            if n in cur:
                                cur.remove(n)
                            else:
                                cur.append(n)
                            st.session_state[sel_set_key] = cur
                            st.rerun()
            with col_pane:
                selection = [n for n in st.session_state.get(sel_set_key, []) if n in labels]
                if len(selection) == 0:
                    st.info("Sélectionnez une ou plusieurs ressources dans la liste pour saisir les heures.")
                elif len(selection) == 1:
                    name, typ = by_label[selection[0]]
                    icon = "👷" if typ == "P" else "🚜"
                    st.markdown(f"##### {icon} {name} — {_resource_total(quart, name):.1f} h")
                    _render_resource_card(jour, quart_name, quart, name, typ, all_activities)
                else:
                    _render_group_card(jour, quart_name, quart, selection, all_activities, sel_set_key)
```

- [ ] **Step 6: Retirer la fonction morte `_apply_hours_to_resources`**

Vérifier qu'il n'y a plus aucun appelant :

Run: `grep -n "_apply_hours_to_resources" app.py`
Expected: aucune ligne (sinon, supprimer l'appel résiduel d'abord).

Puis supprimer entièrement la définition de `def _apply_hours_to_resources(...)` (le bloc ajouté en Task 1 qui délègue), dans `app.py` (~ligne 417). Conserver `_copy_entry` et `_apply_hours_dict_to_resources`.

Dans `tests/test_model.py`, supprimer les 5 tests de l'ancienne fonction : `test_apply_hours_copies_to_empty_dest`, `test_apply_hours_ranges_are_independent`, `test_apply_hours_merges_without_erasing`, `test_apply_hours_empty_source_noop`, `test_apply_hours_ignores_source_in_dests`. (Garder les nouveaux `test_apply_dict_*`.)

- [ ] **Step 7: Lancer les tests ciblés**

Run: `.venv/bin/python -m pytest tests/test_ui.py -k "groupe or appliquer_aussi or individuelle" -v`
Expected: PASS (4 tests)

Run: `.venv/bin/python -m pytest tests/test_model.py -q`
Expected: PASS (plus aucune référence à l'ancienne fonction)

- [ ] **Step 8: Non-régression par fichier**

Run: `.venv/bin/python -m pytest tests/test_ui.py tests/test_model.py -q`
Expected: PASS (anciens tests de saisie individuelle toujours verts ; l'ancien `test_appliquer_heures_a_autre_travailleur` n'existe plus — voir ci-dessous)

Note : l'ancien test `test_appliquer_heures_a_autre_travailleur` (dans `tests/test_ui.py`) cible la section retirée. Le supprimer dans le Step 6 (avec les autres retraits) puisqu'il référence le multiselect « Appliquer aussi à… » et la clé `bulk_apply_…` qui n'existent plus.

- [ ] **Step 9: Commit**

```bash
git add app.py tests/test_ui.py tests/test_model.py
git commit -m "feat(saisie): rail multisélection + fiche de groupe (retrait de 'Appliquer aussi à…')"
```

---

## Self-Review

**Couverture du spec :**
- Rail = bascules de sélection, ensemble persistant → Step 5 (`sel_set_key`, toggle). ✓
- Panneau adaptatif 0/1/2+ → Step 5 (`with col_pane`). ✓
- Fiche de groupe vierge (activités + heures seulement) → Step 4 (`_render_group_card`, entrée `{}`, pas d'équipement/prime/commentaire). ✓
- Fusion → Task 1 (`_apply_hours_dict_to_resources`) + `test_apply_dict_merges_without_erasing`. ✓
- Après application : vider sélection + réinitialiser groupe → Step 4 (`sel_set_key=[]`, `clear_grp` différé) + `test_groupe_applique_heures_et_vide_selection`. ✓
- Retrait de « Appliquer aussi à… » + fonction morte → Steps 5-6 + `test_ancienne_section_appliquer_aussi_absente`. ✓
- Pas de modif de clé widget après instanciation → pattern différé `clear_grp_*` (Step 4) ; toggle écrit `sel_set_` qui n'est pas une clé de widget (Step 5). ✓
- Purge ancrée réutilisée pour `__groupe__` et destinataires → Step 4 (`_purge_resource_hour_keys`). ✓
- `_clear_quart_widget_state` suit la nouvelle clé `sel_set_` → Step 3. ✓
- Mode plage en groupe indépendant → `test_apply_dict_ranges_are_independent`. ✓

**Placeholders :** aucun — code complet à chaque étape.

**Cohérence des types :** `_apply_hours_dict_to_resources(quart, hours, dest_names) -> list` défini en Task 1 et appelé en Step 4. `_render_group_card(jour, quart_name, quart, selection, all_activities, sel_set_key)` défini Step 4, appelé Step 5. Clés cohérentes : `sel_set_{jour}_{quart_name}`, `grp_acts_{jour}_{quart_name}`, `clear_grp_{jour}_{quart_name}`, `pick_{jour}_{quart_name}_{n}`, `grp_btn_{jour}_{quart_name}`. Nom synthétique de groupe `"__groupe__"` cohérent entre `_render_activity_hours` et `_purge_resource_hour_keys`.
