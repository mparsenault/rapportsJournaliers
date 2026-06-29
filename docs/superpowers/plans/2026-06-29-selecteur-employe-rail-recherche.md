# Sélecteur d'employé — rail latéral avec recherche — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer le `st.radio` horizontal de sélection d'employé (étape « Saisie des heures ») par un layout maître-détail : rail de gauche avec recherche + liste verticale défilante (icône, statut, total), fiche de saisie inchangée à droite.

**Architecture:** Modification d'un seul bloc dans `view_day_entry` (`app.py`, branche `else` de l'étape « saisie », ~lignes 1316-1338). On garde la même clé d'état `resource_sel_{jour}_{quart_name}` pour la ressource active ; on remplace le widget radio par des `st.button` listés dans un conteneur défilant, précédés d'un `st.text_input` de recherche qui filtre l'affichage sans toucher la sélection.

**Tech Stack:** Python, Streamlit, tests via `streamlit.testing.v1.AppTest` + pytest.

## Global Constraints

- Les widgets de sélection doivent être pilotables sous `AppTest` — utiliser `st.button` (représentable), jamais `st.pills` (non cliquable sous AppTest). Référence : commentaire existant `app.py:1322-1325`.
- Couleur de surlignage = bouton primaire Streamlit (CSS `ONDEL_GREEN` déjà en place) ; pas de nouvelle règle CSS requise.
- La recherche ne modifie jamais `st.session_state[sel_key]` ; seul un clic de bouton ou le garde « sélection hors roster » le change.
- Ne pas toucher : étape « config », modèle de données, `_render_resource_card`.

---

### Task 1 : Rail latéral avec recherche (remplace le radio)

**Files:**
- Modify: `app.py:1316-1338` (branche `else` « saisie » de `view_day_entry`)
- Test: `tests/test_ui.py`

**Interfaces:**
- Consomme (existants, inchangés) : `_roster(quart) -> list[(name, "P"|"E")]`, `_resource_total(quart, name) -> float`, `_render_resource_card(jour, quart_name, quart, name, typ, all_activities)`.
- Clé d'état : `sel_key = f"resource_sel_{jour}_{quart_name}"` (ressource active, str = nom).
- Produit : un `st.text_input` clé `f"res_search_{jour}_{quart_name}"`, et un `st.button` par ressource de clé `f"pick_{jour}_{quart_name}_{name}"`. Le test existant `test_resource_selector_shows_selected_card` pilote la sélection via `session_state[sel_key]` et reste valide.

- [ ] **Step 1 : Écrire le test de filtrage par recherche**

Ajouter dans `tests/test_ui.py` :

```python
def test_resource_search_filters_rail(monkeypatch):
    """La recherche filtre les boutons du rail sans changer la sélection."""
    at = _open_day_for_entry(monkeypatch, personnel=("Alice", "Bob", "Charlie"))
    _goto_saisie(at)
    # Sans filtre : un bouton pick_ par ressource
    pick_keys = {b.key for b in at.button if b.key and b.key.startswith("pick_Lundi_Jour_")}
    assert pick_keys == {"pick_Lundi_Jour_Alice", "pick_Lundi_Jour_Bob", "pick_Lundi_Jour_Charlie"}
    # Filtre "ali" -> seule Alice reste, la sélection par défaut (Alice) est inchangée
    search = [t for t in at.text_input if t.key == "res_search_Lundi_Jour"][0]
    search.set_value("ali").run()
    pick_keys = {b.key for b in at.button if b.key and b.key.startswith("pick_Lundi_Jour_")}
    assert pick_keys == {"pick_Lundi_Jour_Alice"}
    assert at.session_state["resource_sel_Lundi_Jour"] == "Alice"
    assert not at.exception
```

- [ ] **Step 2 : Écrire le test de sélection par clic + persistance malgré le filtre**

Ajouter dans `tests/test_ui.py` :

```python
def test_resource_pick_button_selects_and_survives_filter(monkeypatch):
    """Cliquer un bouton du rail sélectionne la ressource ; un filtre qui l'exclut
    n'efface pas la fiche affichée."""
    at = _open_day_for_entry(monkeypatch, personnel=("Alice", "Bob"))
    _goto_saisie(at)
    # Cliquer Bob -> sa fiche s'affiche
    [b for b in at.button if b.key == "pick_Lundi_Jour_Bob"][0].click().run()
    assert at.session_state["resource_sel_Lundi_Jour"] == "Bob"
    assert any(m.key == "acts_Lundi_Jour_Bob" for m in at.multiselect)
    # Filtrer sur "ali" (exclut Bob du rail) -> la fiche de Bob reste affichée
    [t for t in at.text_input if t.key == "res_search_Lundi_Jour"][0].set_value("ali").run()
    assert at.session_state["resource_sel_Lundi_Jour"] == "Bob"
    assert any(m.key == "acts_Lundi_Jour_Bob" for m in at.multiselect)
    assert not at.exception
```

- [ ] **Step 3 : Lancer les deux tests pour vérifier qu'ils échouent**

Run: `.venv/bin/python -m pytest tests/test_ui.py::test_resource_search_filters_rail tests/test_ui.py::test_resource_pick_button_selects_and_survives_filter -v`
Expected: FAIL — `res_search_…` / `pick_…` introuvables (le radio est encore en place).

- [ ] **Step 4 : Remplacer le bloc radio par le rail maître-détail**

Dans `app.py`, remplacer le bloc actuel (de `labels = [n for n, _t in full_roster]` jusqu'à l'appel `_render_resource_card(...)`, ~lignes 1326-1338) par :

```python
            # Sélecteur maître-détail : rail de gauche (recherche + liste défilante
            # de boutons) + fiche de saisie à droite. st.button est représentable
            # sous AppTest (contrairement à st.pills), donc testable.
            labels = [n for n, _t in full_roster]
            by_label = {n: (n, t) for n, t in full_roster}
            sel_key = f"resource_sel_{jour}_{quart_name}"
            if st.session_state.get(sel_key) not in labels:
                st.session_state[sel_key] = labels[0]

            col_rail, col_pane = st.columns([1, 2], gap="medium")
            with col_rail:
                q = st.text_input("Rechercher une ressource", key=f"res_search_{jour}_{quart_name}",
                                  placeholder="🔍 Rechercher une ressource…",
                                  label_visibility="collapsed")
                done = sum(1 for n in labels if _resource_total(quart, n) > 0)
                filt = [n for n in labels if q.casefold() in n.casefold()] if q else labels
                st.caption(f"{len(filt)} résultat(s) · {done} sur {len(labels)} saisies")
                with st.container(height=300):
                    if not filt:
                        st.caption("Aucune ressource ne correspond.")
                    for n in filt:
                        _n, t = by_label[n]
                        tot = _resource_total(quart, n)
                        ic = "👷" if t == "P" else "🚜"
                        status = "🟢" if tot > 0 else "⚪"
                        is_sel = (n == st.session_state[sel_key])
                        if st.button(f"{ic} {n} · {status} {tot:.1f} h",
                                     key=f"pick_{jour}_{quart_name}_{n}",
                                     use_container_width=True,
                                     type="primary" if is_sel else "secondary"):
                            st.session_state[sel_key] = n
                            st.rerun()

            with col_pane:
                name, typ = by_label[st.session_state[sel_key]]
                icon = "👷" if typ == "P" else "🚜"
                st.markdown(f"##### {icon} {name} — {_resource_total(quart, name):.1f} h")
                _render_resource_card(jour, quart_name, quart, name, typ, all_activities)
```

- [ ] **Step 5 : Lancer les deux nouveaux tests pour vérifier qu'ils passent**

Run: `.venv/bin/python -m pytest tests/test_ui.py::test_resource_search_filters_rail tests/test_ui.py::test_resource_pick_button_selects_and_survives_filter -v`
Expected: PASS (2 passed).

- [ ] **Step 6 : Lancer toute la suite UI pour vérifier l'absence de régression**

Run: `.venv/bin/python -m pytest tests/test_ui.py -v`
Expected: tous PASS (dont `test_resource_selector_shows_selected_card`, qui pilote la sélection via `session_state` — inchangé).

- [ ] **Step 7 : Commit**

```bash
git add app.py tests/test_ui.py
git commit -m "feat: sélecteur d'employé en rail latéral avec recherche

Remplace le radio horizontal par un layout maître-détail : rail gauche
(recherche + liste défilante avec statut et total par ressource) et fiche
de saisie à droite.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Couverture de la spec :**
- Layout maître-détail (rail + fiche) → Step 4. ✓
- Recherche filtre en direct → Step 4 (`filt`), testé Step 1. ✓
- Compteur « N résultats · X sur Y saisies » → Step 4 (`st.caption`). ✓
- Aucune correspondance → message discret → Step 4 (`if not filt`). ✓
- Filtre n'efface pas la sélection → Step 4 (logique) + test Step 2. ✓
- Liste défilante hauteur fixe → Step 4 (`st.container(height=300)`). ✓
- Surlignage sélection via bouton primaire → Step 4 (`type="primary"`). ✓
- Statut 🟢/⚪ + total + icône par ligne → Step 4. ✓
- Boutons testables sous AppTest → tests Steps 1-2. ✓
- Garde « sélection hors roster » conservé → Step 4 (`if … not in labels`). ✓

**2. Placeholders :** aucun — tout le code et les commandes sont complets.

**3. Cohérence des types :** `sel_key`, `labels`, `by_label`, `pick_{…}_{name}`, `res_search_{…}` cohérents entre Step 4 et les tests Steps 1-2. `_resource_total`/`_render_resource_card` appelés avec les signatures existantes.

Note : la commande pytest utilise `.venv/bin/python -m pytest` (venv présent dans le repo). Si l'exécutant préfère, `pytest` direct fonctionne aussi tant que le venv est activé.
