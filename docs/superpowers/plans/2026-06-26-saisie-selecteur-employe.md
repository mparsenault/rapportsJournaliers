# Saisie sélecteur d'employé Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer l'accordéon de la saisie par un sélecteur d'employé (`st.pills`) : on choisit un membre de l'équipe et sa seule fiche s'affiche, dépliée.

**Architecture:** Dans la boucle Saisie de `view_day_entry` (`app.py`), remplacer le champ de recherche + le `for … st.expander` par un `st.pills` de sélection simple (libellés stables) qui détermine l'unique ressource dont `_render_resource_card` est rendue (sans expander). Le corps de `_render_resource_card`, le modèle et la persistance ne changent pas.

**Tech Stack:** Python, Streamlit (`st.pills` selection_mode="single", `st.markdown`), pytest + `streamlit.testing.v1.AppTest`.

## Global Constraints

- Aucun changement au modèle, à la BD, à `save_report`/`load_report`, ni au corps de `_render_resource_card`.
- Clés de widgets de la fiche inchangées : `acts_`, `tr_`, `ts_`, `eqc_`, `eqh_`, `p_`, `c_` (toutes suffixées `{jour}_{quart_name}_{name}` / `…_{act}`).
- Clé du sélecteur : `resource_sel_{jour}_{quart_name}`.
- Libellés des pastilles **stables** : `f"{'👷' if typ=='P' else '🚜'} {name}"` — sans total d'heures (sinon la sélection sauterait quand le total change).
- Convention de seed : seeder `st.session_state[sel_key]` une fois (si l'état courant n'est pas dans les libellés), pas de `default=` sur le widget muni de `key=`.
- `pytest` doit passer : `.venv/bin/python -m pytest -q`.

---

### Task 1: Sélecteur d'employé remplace l'accordéon

**Files:**
- Modify: `app.py` — boucle Saisie de `view_day_entry` (le bloc `full_roster = _roster(quart)` … jusqu'à la fin du `for … _render_resource_card`, env. lignes 1316-1331) ; `_clear_quart_widget_state` (lignes 128-137)
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: `_roster(quart) -> list[(name, typ)]`, `_resource_total(quart, name) -> float`, `_render_resource_card(jour, quart_name, quart, name, typ, all_activities)`, `data_source.get_activities(id_project)`.
- Produces: à l'étape Saisie, un `st.pills` de clé `resource_sel_{jour}_{quart_name}` ; la fiche de la ressource sélectionnée est rendue sans `st.expander`. Plus de champ `roster_search_{jour}_{quart_name}`.

- [ ] **Step 1: Mettre à jour les tests (échec attendu)**

Dans `tests/test_ui.py`, **remplacer** `test_roster_search_filters_resources` (env. lignes 423-…) par :

```python
def test_resource_selector_shows_selected_card(monkeypatch):
    """Le sélecteur d'employé affiche la fiche du membre choisi (et masque les autres).
    On pilote la sélection via session_state (st.pills non cliquable sous AppTest)."""
    at = _open_day_for_entry(monkeypatch, personnel=("Alice", "Bob"))
    _goto_saisie(at)
    # Alice (premier du roster) est sélectionnée par défaut -> sa fiche est rendue
    assert any(m.key == "acts_Lundi_Jour_Alice" for m in at.multiselect)
    assert not any(m.key == "acts_Lundi_Jour_Bob" for m in at.multiselect)
    # Sélectionner Bob -> sa fiche s'affiche, celle d'Alice disparaît
    at.session_state["resource_sel_Lundi_Jour"] = "👷 Bob"
    at.run()
    assert any(m.key == "acts_Lundi_Jour_Bob" for m in at.multiselect)
    assert not any(m.key == "acts_Lundi_Jour_Alice" for m in at.multiselect)
    assert not at.exception
```

Aucun autre test ne change : `_open_day_for_entry` n'a qu'« Alice » au roster, donc Alice est sélectionnée par défaut et sa fiche reste rendue pour les tests de carte existants. (Le test `test_day_entry_starts_on_config_step` vérifie déjà l'absence de `roster_search_Lundi_Jour` à l'étape Config — toujours vrai après retrait.)

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `.venv/bin/python -m pytest "tests/test_ui.py::test_resource_selector_shows_selected_card" -q`
Expected: FAIL — la clé `resource_sel_Lundi_Jour` n'existe pas et les deux fiches (Alice ET Bob) sont rendues par l'accordéon, donc `acts_Lundi_Jour_Bob` est présent dès le départ → la 2ᵉ assertion (`not any … Bob`) échoue.

- [ ] **Step 3: Remplacer le bloc Saisie par le sélecteur**

Dans `view_day_entry`, remplacer ce bloc actuel :

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
                with st.expander(f"{icon} {name} — {_resource_total(quart, name):.1f} h", expanded=False):
                    _render_resource_card(jour, quart_name, quart, name, typ, all_activities)
```

par :

```python
        full_roster = _roster(quart)
        st.markdown("#### 🕐 Saisie des heures")
        all_activities = data_source.get_activities(st.session_state.projet.get("id_project"))
        if not full_roster:
            st.info("💡 Commencez par sélectionner le **personnel / équipements** dans la configuration.")
        else:
            def _res_label(name, typ):
                return f"{'👷' if typ == 'P' else '🚜'} {name}"
            labels = [_res_label(n, t) for n, t in full_roster]
            by_label = {_res_label(n, t): (n, t) for n, t in full_roster}
            sel_key = f"resource_sel_{jour}_{quart_name}"
            if st.session_state.get(sel_key) not in labels:
                st.session_state[sel_key] = labels[0]
            sel_label = st.pills("Employé / équipement", labels, selection_mode="single",
                                 key=sel_key, label_visibility="collapsed")
            if sel_label not in by_label:
                sel_label = labels[0]
            name, typ = by_label[sel_label]
            st.markdown(f"##### {sel_label} — {_resource_total(quart, name):.1f} h")
            _render_resource_card(jour, quart_name, quart, name, typ, all_activities)
```

(Le `st.divider()` + « 📝 Note du quart » + barre dirty + bouton 💾 Enregistrer qui suivent restent inchangés.)

- [ ] **Step 4: Mettre à jour `_clear_quart_widget_state`**

Dans le tuple `prefixes` (lignes 129-137), remplacer `f"roster_search_{jour}_{quart_name}"` par `f"resource_sel_{jour}_{quart_name}"`. Résultat :

```python
    prefixes = (f"tr_{jour}_{quart_name}_", f"ts_{jour}_{quart_name}_",
                f"eqc_{jour}_{quart_name}_", f"eqh_{jour}_{quart_name}_",
                f"p_{jour}_{quart_name}_", f"c_{jour}_{quart_name}_",
                f"acts_{jour}_{quart_name}",
                f"cond_pills_{jour}_{quart_name}",
                f"{jour}_{quart_name}_temp_am", f"{jour}_{quart_name}_temp_pm",
                f"{jour}_{quart_name}_cond", f"resource_sel_{jour}_{quart_name}",
                f"personnel_pills_{jour}_{quart_name}", f"note_{jour}_{quart_name}",
                f"show_geoloc_{jour}_{quart_name}", f"geoloc_{jour}_{quart_name}")
```

- [ ] **Step 5: Lancer le test ciblé puis la suite complète**

Run: `.venv/bin/python -m pytest "tests/test_ui.py::test_resource_selector_shows_selected_card" -q`
Expected: PASS.

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — toute la suite. Les tests de carte ciblent les clés inchangées et « Alice » (seul au roster) est sélectionnée par défaut.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_ui.py
git commit -m "feat: saisie via sélecteur d'employé (remplace l'accordéon)"
```

---

## Self-Review

**Spec coverage:**
- Sélecteur `st.pills` + fiche unique sans expander → Step 3. ✓
- Libellés stables sans total → Step 3 (`_res_label`). ✓
- Seed sans `default=` + repli si invalide/nul → Step 3. ✓
- En-tête `##### {libellé} — {total} h` → Step 3. ✓
- Roster vide → info (conservé) → Step 3. ✓
- Retrait recherche + maj `_clear_quart_widget_state` → Steps 3 & 4. ✓
- Remplacement du test de recherche par un test de sélecteur → Step 1. ✓

**Placeholder scan:** aucun TODO/TBD ; code complet à chaque étape. ✓

**Type consistency:** clé `resource_sel_{jour}_{quart_name}` identique entre Step 3, Step 4 et le test (Step 1) ; libellé `"👷 Bob"` du test correspond à `_res_label("Bob","P")` ; `_render_resource_card` appelée avec la signature existante. ✓
