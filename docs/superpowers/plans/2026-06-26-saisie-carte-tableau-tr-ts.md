# Saisie carte raffinée (tableau TR/TS aligné, cartes repliées) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre la carte de saisie par employé plus lisible : cartes repliées par défaut et heures en tableau aligné `Activité | TR | TS` (libellé complet, sans étiquette répétée).

**Architecture:** Modification de présentation seulement dans `app.py` — l'expander de la boucle Saisie passe à `expanded=False`, et le bloc activités de `_render_resource_card` rend une ligne d'en-tête unique puis une ligne par activité avec `st.columns` de poids fixes. Clés de widgets, seed, normalisation `_norm_pair`, reconstruction de `heures` et suppression des paires nulles : inchangés.

**Tech Stack:** Python, Streamlit (`st.expander`, `st.columns`, `st.markdown`, `st.number_input`), pytest + `streamlit.testing.v1.AppTest`.

## Global Constraints

- Aucun changement au modèle, à la BD, ni à `save_report`/`load_report`.
- Les clés de widgets restent EXACTEMENT : `tr_{jour}_{quart_name}_{name}_{act}` et `ts_{jour}_{quart_name}_{name}_{act}` (et `eqc_`/`eqh_`/`p_`/`c_` inchangées).
- Convention de seed : `st.session_state.setdefault(key, valeur)` puis lecture de la valeur de retour ; jamais de `value=`/`default=` calculé sur un widget muni de `key=`.
- `heures[name][act]` reste de forme `{"TR": float, "TS": float}` ; une paire TR==0 et TS==0 est retirée.
- Les `number_input` TR/TS utilisent `label_visibility="collapsed"` (pas d'étiquette « TR — code »).

---

### Task 1: Carte repliée + tableau TR/TS aligné

**Files:**
- Modify: `app.py` — constante `_HOURS_COLS` (nouvelle, juste avant `_render_resource_card`, ~ligne 1023) ; bloc activités de `_render_resource_card` (lignes 1035-1052) ; l'expander de la boucle Saisie (ligne 1321, `expanded=True` → `expanded=False`)
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: `_norm_pair(pair) -> {"TR": float, "TS": float}`, `_to_hours`, `_mark_dirty`, `_resource_total` (tous déjà présents).
- Produces: aucune nouvelle signature publique. Comportement : l'étape Saisie rend, par activité sélectionnée, une ligne `st.columns(_HOURS_COLS)` alignée sous une ligne d'en-tête `Activité | TR | TS` ; les number_input gardent leurs clés.

- [ ] **Step 1: Écrire le test (échec attendu)**

Ajouter dans `tests/test_ui.py` :

```python
def test_saisie_card_table_header_and_no_repeated_labels(monkeypatch):
    """Étape Saisie : une activité sélectionnée affiche l'en-tête de tableau
    Activité/TR/TS, sans étiquette répétée « TR — … », et la saisie écrit
    toujours dans la forme {"TR","TS"}."""
    at = _open_day_for_entry(monkeypatch)   # personnel Alice, activité "C01 - Test"
    _goto_saisie(at)
    ms = [m for m in at.multiselect if m.key == "acts_Lundi_Jour_Alice"][0]
    ms.set_value(["C01 - Test"]).run()
    md = " ".join((m.value or "") for m in at.markdown)
    assert "Activité" in md and "TR" in md and "TS" in md   # ligne d'en-tête présente
    labels = [(n.label or "") for n in at.number_input]
    assert not any(l.startswith("TR —") or l.startswith("TS —") for l in labels)
    tr = [n for n in at.number_input if n.key == "tr_Lundi_Jour_Alice_C01 - Test"][0]
    tr.set_value(8.0).run()
    q = at.session_state["jours"]["Lundi"]["quarts"]["Jour"]
    assert q["heures"]["Alice"]["C01 - Test"] == {"TR": 8.0, "TS": 0.0}
    assert not at.exception
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `.venv/bin/python -m pytest "tests/test_ui.py::test_saisie_card_table_header_and_no_repeated_labels" -q`
Expected: FAIL — l'en-tête « Activité » n'existe pas encore et les number_input portent encore le label « TR — C01 » (donc `labels` contient une entrée commençant par « TR — »).

- [ ] **Step 3: Ajouter la constante `_HOURS_COLS`**

Dans `app.py`, juste avant `def _render_resource_card(` (ligne ~1024) :

```python
# Poids des colonnes du tableau d'heures par activité (Activité | TR | TS).
_HOURS_COLS = [4, 2, 2]
```

- [ ] **Step 4: Réécrire le bloc activités de `_render_resource_card`**

Remplacer les lignes 1035-1052 (de `new_heures = {}` jusqu'au `del quart["heures"][name]` inclus, c.-à-d. tout le bloc qui construit la grille TR/TS) par :

```python
    if sel_acts:
        hc1, hc2, hc3 = st.columns(_HOURS_COLS)
        hc1.markdown("**Activité**")
        hc2.markdown("**TR**")
        hc3.markdown("**TS**")
    new_heures = {}
    for act in (sel_acts or []):
        pair = _norm_pair(quart["heures"].get(name, {}).get(act, {}))
        ca, cb, cc_ = st.columns(_HOURS_COLS, vertical_alignment="center")
        ca.markdown(act)
        tr_key = f"tr_{jour}_{quart_name}_{name}_{act}"
        ts_key = f"ts_{jour}_{quart_name}_{name}_{act}"
        st.session_state.setdefault(tr_key, pair["TR"])
        st.session_state.setdefault(ts_key, pair["TS"])
        tr = cb.number_input("TR", key=tr_key, min_value=0.0, step=0.5,
                             format="%.1f", label_visibility="collapsed", on_change=_mark_dirty)
        ts = cc_.number_input("TS", key=ts_key, min_value=0.0, step=0.5,
                              format="%.1f", label_visibility="collapsed", on_change=_mark_dirty)
        if tr > 0 or ts > 0:
            new_heures[act] = {"TR": float(tr), "TS": float(ts)}
    if new_heures:
        quart["heures"][name] = new_heures
    elif name in quart["heures"]:
        del quart["heures"][name]
```

(Le `st.multiselect` des activités au-dessus, et tout ce qui suit le bloc — équipement, prime, commentaire — restent inchangés.)

- [ ] **Step 5: Replier l'expander par défaut**

À la ligne 1321, remplacer :

```python
                with st.expander(f"{icon} {name} — {_resource_total(quart, name):.1f} h", expanded=True):
```
par :
```python
                with st.expander(f"{icon} {name} — {_resource_total(quart, name):.1f} h", expanded=False):
```

- [ ] **Step 6: Lancer le test ciblé puis la suite complète**

Run: `.venv/bin/python -m pytest "tests/test_ui.py::test_saisie_card_table_header_and_no_repeated_labels" -q`
Expected: PASS.

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — toute la suite (les tests de carte existants ciblent les clés `tr_`/`ts_`/`eqc_`/`eqh_`/`p_`/`c_`, inchangées ; le contenu d'un `st.expander` reste dans l'arbre AppTest même replié).

- [ ] **Step 7: Commit**

```bash
git add app.py tests/test_ui.py
git commit -m "feat: saisie carte raffinée (tableau TR/TS aligné, cartes repliées)"
```

---

## Self-Review

**Spec coverage:**
- « Cartes repliées par défaut » → Step 5 (`expanded=False`). ✓
- « Tableau aligné : en-tête unique Activité/TR/TS » → Step 4 (ligne d'en-tête + `st.columns(_HOURS_COLS)`). ✓
- « Libellé complet en colonne 1 » → Step 4 (`ca.markdown(act)`). ✓
- « number_input sans étiquette répétée » → Step 4 (`label_visibility="collapsed"`). ✓
- « Clés / seed / `_norm_pair` / drop des 0 inchangés » → Step 4 conserve la logique. ✓
- « Pas de changement modèle/BD/save/load » → seules présentation + un test. ✓
- Test d'en-tête → Step 1. ✓

**Placeholder scan:** aucun TODO/TBD ; tout le code est explicite. ✓

**Type consistency:** clés `tr_`/`ts_` identiques entre Step 4 et le test (Step 1) ; `_HOURS_COLS` défini (Step 3) avant usage (Step 4) ; `_norm_pair` renvoie bien `{"TR","TS"}` consommé tel quel. ✓
