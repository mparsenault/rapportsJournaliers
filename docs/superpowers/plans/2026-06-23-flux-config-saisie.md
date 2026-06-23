# Flux séquentiel Configuration → Saisie des heures — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer les onglets « Configuration / Saisie des heures » de la saisie journalière par un flux séquentiel en deux étapes, où le bouton de la Configuration enregistre puis bascule vers la grille des heures.

**Architecture:** Un état `st.session_state.day_entry_step` (`"config"` | `"saisie"`) pilote l'aiguillage dans `view_day_entry`. Les corps des deux anciens onglets deviennent les deux branches `if step == "config":` / `else:` (même indentation, corps inchangés). Le sélecteur de quart et les barres de bas de page sont répartis par étape.

**Tech Stack:** Python, Streamlit, `streamlit.testing.v1.AppTest` (pytest).

## Global Constraints

- Cible unique : `app.py` (fonction `view_day_entry`, env. lignes 982-1228) et `tests/test_ui.py`.
- Aucun changement au modèle de données ni à la persistance (`save_report_from_state` réutilisé tel quel).
- Libellé exact du bouton de l'étape Configuration : `💾 Enregistrer et saisir les heures →`.
- Libellé exact du bouton retour : `← Retour à la configuration`.
- Clés de widgets : `save_next_{jour}` (config), `back_config_{jour}` (retour), `save_{jour}` (enregistrer final, inchangé).
- Le bouton 💾 Enregistrer final n'apparaît qu'à l'étape Saisie.

---

## File Structure

- `app.py`
  - `view_dashboard` (bouton `go_{jour}`) : réinitialise `day_entry_step` à `"config"` à l'entrée d'une journée.
  - `view_day_entry` : aiguillage par étape, sélecteur de quart sur config seulement, deux barres de bas de page.
  - bloc CSS des onglets : supprimé.
- `tests/test_ui.py`
  - 3 nouveaux tests de navigation.
  - helpers `_goto_saisie` / `_goto_config`.
  - 8 tests existants ajustés pour traverser l'étape Saisie.

---

## Task 1 : Flux en deux étapes dans `view_day_entry`

**Files:**
- Modify: `app.py` (`view_dashboard` ~897-903 ; `view_day_entry` ~1005-1228 ; CSS ~819-822)
- Test: `tests/test_ui.py`

**Interfaces:**
- Consomme : `save_report_from_state() -> (bool, str)` (existant, `app.py:174`), `_render_quart_selector(jour, day, prev_day)`, `_current_quart_name(jour)`.
- Produit : état `st.session_state["day_entry_step"] ∈ {"config","saisie"}` ; boutons de clés `save_next_{jour}`, `back_config_{jour}`, `save_{jour}`.

- [ ] **Step 1 : Écrire les tests de navigation (échouent)**

Ajouter dans `tests/test_ui.py`, après la fonction `_open_day_for_entry` (vers la ligne 63), les helpers et les 3 tests suivants :

```python
def _goto_saisie(at):
    """Passe à l'étape Saisie des heures (le flux n'a plus d'onglets)."""
    at.session_state["day_entry_step"] = "saisie"
    return at.run()


def _goto_config(at):
    """Revient à l'étape Configuration."""
    at.session_state["day_entry_step"] = "config"
    return at.run()


def test_day_entry_starts_on_config_step(monkeypatch):
    """À l'ouverture d'une journée, on est sur la Configuration (pas de grille d'heures)."""
    at = _open_day_for_entry(monkeypatch)
    assert at.session_state["day_entry_step"] == "config"
    assert any(b.key == "save_next_Lundi" for b in at.button)
    assert not any(b.key == "back_config_Lundi" for b in at.button)
    assert not any(b.key == "save_Lundi" for b in at.button)
    assert not any((t.key or "") == "roster_search_Lundi_Jour" for t in at.text_input)
    assert not at.exception


def test_save_and_navigate_advances_to_saisie(monkeypatch):
    """Le bouton « Enregistrer et saisir les heures → » enregistre puis ouvre la Saisie."""
    import reports
    monkeypatch.setattr(reports, "save_report", lambda *a, **k: None)
    at = _open_day_for_entry(monkeypatch)
    [b for b in at.button if b.key == "save_next_Lundi"][0].click().run()
    assert at.session_state["day_entry_step"] == "saisie"
    assert at.session_state["dirty"] is False
    assert any(b.key == "back_config_Lundi" for b in at.button)
    assert any(b.key == "save_Lundi" for b in at.button)
    assert not at.exception


def test_back_returns_to_config(monkeypatch):
    """« ← Retour à la configuration » ramène à l'étape 1 sans perdre l'état."""
    at = _open_day_for_entry(monkeypatch)
    _goto_saisie(at)
    assert at.session_state["day_entry_step"] == "saisie"
    [b for b in at.button if b.key == "back_config_Lundi"][0].click().run()
    assert at.session_state["day_entry_step"] == "config"
    assert any(b.key == "save_next_Lundi" for b in at.button)
    assert not at.exception
```

- [ ] **Step 2 : Lancer les 3 tests pour vérifier l'échec**

Run: `python3 -m pytest tests/test_ui.py -k "starts_on_config or save_and_navigate or back_returns" -v`
Expected: FAIL (les boutons `save_next_*` / `back_config_*` n'existent pas, `day_entry_step` absent).

- [ ] **Step 3 : Réinitialiser l'étape à l'entrée d'une journée (`view_dashboard`)**

Dans `app.py`, le bouton `go_{jour}` (~897-903). Remplacer :

```python
            if st.button(label, key=f"go_{jour}", use_container_width=True, disabled=not projet_choisi):
                st.session_state.active_day = jour
                st.session_state.view = "day_entry"
```

par :

```python
            if st.button(label, key=f"go_{jour}", use_container_width=True, disabled=not projet_choisi):
                st.session_state.active_day = jour
                st.session_state.view = "day_entry"
                st.session_state.day_entry_step = "config"
```

- [ ] **Step 4 : Remplacer l'entête (sélecteur + résolution + tabs) dans `view_day_entry`**

Dans `app.py`, remplacer le bloc actuel (~1005-1012) :

```python
    # Sélecteur de quart : rendu AVANT la résolution du quart courant, pour consommer
    # la sélection en attente posée par _add_quart (sinon les onglets afficheraient le
    # quart fraîchement ajouté un cycle en retard).
    _render_quart_selector(jour, day, prev_day)
    quart_name = _current_quart_name(jour)
    quart = day["quarts"][quart_name]

    tab_config, tab_saisie = st.tabs(["⚙️ Configuration", "🕐 Saisie des heures"])
```

par :

```python
    # Flux en deux étapes (plus d'onglets) : on configure, on enregistre, puis on saisit.
    step = st.session_state.setdefault("day_entry_step", "config")

    # Sélecteur de quart : rendu AVANT la résolution du quart courant, pour consommer
    # la sélection en attente posée par _add_quart (sinon la vue afficherait le quart
    # fraîchement ajouté un cycle en retard). Affiché à l'étape Configuration seulement ;
    # à l'étape Saisie aucun _add_quart n'a lieu, donc aucune sélection en attente à
    # consommer.
    if step == "config":
        _render_quart_selector(jour, day, prev_day)
    quart_name = _current_quart_name(jour)
    quart = day["quarts"][quart_name]
```

- [ ] **Step 5 : Transformer le bloc Configuration en branche `if step`**

Dans `app.py`, remplacer la ligne (~1014) :

```python
    with tab_config:
```

par :

```python
    if step == "config":
```

(Le corps — « Configuration du quart », colonnes Activités/Météo, bloc Personnel/Équipements — reste **inchangé**, même indentation.)

- [ ] **Step 6 : Ajouter la barre du bas de la Configuration**

Dans `app.py`, la branche Configuration se termine par le bouton « Ajouter » de l'équipement (~1151-1153) :

```python
                if new_equipment.strip() and new_equipment.strip() not in quart["equipements"]:
                    quart["equipements"].append(new_equipment.strip())
                    st.rerun()

    with tab_saisie:
```

Remplacer ce fragment par (insertion de la barre du bas dans la branche config, puis bascule de `with tab_saisie:` vers `else:` avec la barre de retour) :

```python
                if new_equipment.strip() and new_equipment.strip() not in quart["equipements"]:
                    quart["equipements"].append(new_equipment.strip())
                    st.rerun()

        st.divider()
        cb1, cb2 = st.columns([3, 1], vertical_alignment="center")
        if st.session_state.get("dirty"):
            cb1.warning("⚠️ Modifications non enregistrées — pensez à enregistrer avant de quitter.")
        else:
            cb1.caption("✓ Toutes les modifications sont enregistrées.")
        if cb2.button("💾 Enregistrer et saisir les heures →", use_container_width=True,
                      type="primary", key=f"save_next_{jour}"):
            ok, msg = save_report_from_state()
            if ok:
                st.session_state.day_entry_step = "saisie"
                st.rerun()
            else:
                st.error(msg)

    else:
        sb_top1, sb_top2 = st.columns([2, 3], vertical_alignment="center")
        if sb_top1.button("← Retour à la configuration", key=f"back_config_{jour}",
                          use_container_width=True):
            st.session_state.day_entry_step = "config"
            st.rerun()
        sb_top2.markdown(f"**Quart : {quart_name}**")
```

(Le corps de l'ancien `with tab_saisie:` — recherche de ressource, grille des heures, note du quart — reste **inchangé**, même indentation, juste sous le `else:`.)

- [ ] **Step 7 : Réindenter la barre Enregistrer finale dans la branche Saisie**

Dans `app.py`, le bloc final (~1220-1228) est aujourd'hui au niveau de la fonction (4 espaces) :

```python
    st.divider()
    sb1, sb2 = st.columns([3, 1], vertical_alignment="center")
    if st.session_state.get("dirty"):
        sb1.warning("⚠️ Modifications non enregistrées — pensez à enregistrer avant de quitter.")
    else:
        sb1.caption("✓ Toutes les modifications sont enregistrées.")
    if sb2.button("💾 Enregistrer", use_container_width=True, type="primary", key=f"save_{jour}"):
        ok, msg = save_report_from_state()
        (st.success if ok else st.error)(msg)
```

Le réindenter à 8 espaces pour qu'il appartienne à la branche `else:` (Saisie) :

```python
        st.divider()
        sb1, sb2 = st.columns([3, 1], vertical_alignment="center")
        if st.session_state.get("dirty"):
            sb1.warning("⚠️ Modifications non enregistrées — pensez à enregistrer avant de quitter.")
        else:
            sb1.caption("✓ Toutes les modifications sont enregistrées.")
        if sb2.button("💾 Enregistrer", use_container_width=True, type="primary", key=f"save_{jour}"):
            ok, msg = save_report_from_state()
            (st.success if ok else st.error)(msg)
```

- [ ] **Step 8 : Mettre à jour les messages d'info de l'étape Saisie**

Dans `app.py` (~1167-1169), remplacer :

```python
            st.info("💡 Commencez par sélectionner le **personnel / équipements** dans l'onglet Configuration.")
        elif not cols_labels:
            st.info("💡 Sélectionnez une ou plusieurs **Activités** dans l'onglet Configuration.")
```

par :

```python
            st.info("💡 Commencez par sélectionner le **personnel / équipements** dans la configuration.")
        elif not cols_labels:
            st.info("💡 Sélectionnez une ou plusieurs **Activités** dans la configuration.")
```

- [ ] **Step 9 : Supprimer le CSS des onglets**

Dans `app.py` (~819-822), supprimer le bloc :

```python
    /* Onglets Configuration / Saisie : surlignage teal, libellé actif teal */
    .stTabs [data-baseweb="tab-highlight"] {{ background: {ONDEL_GREEN} !important; }}
    .stTabs [data-baseweb="tab"] {{ font-size: 1rem !important; font-weight: 600 !important; }}
    .stTabs [aria-selected="true"] {{ color: {ONDEL_GREEN_DARK} !important; }}
```

(Laisser la ligne `</style>` qui suit.)

- [ ] **Step 10 : Lancer les nouveaux tests de navigation**

Run: `python3 -m pytest tests/test_ui.py -k "starts_on_config or save_and_navigate or back_returns" -v`
Expected: PASS (3 tests).

- [ ] **Step 11 : Adapter les tests existants qui saisissent des heures**

Dans `tests/test_ui.py`, insérer une bascule vers l'étape Saisie après la sélection des activités, dans chacun de ces tests.

`test_day_hours_entry_updates_model`, `test_day_hours_no_grid_data_editor`,
`test_day_prime_inline_column`, `test_day_comment_inline_column`,
`test_roster_search_filters_resources` — après la ligne
`acts.set_value(["C01 - Test"]).run()`, ajouter :

```python
    _goto_saisie(at)
```

`test_day_entry_no_activity_shows_info` — l'info « Activités » est désormais sur
l'étape Saisie. Après le `at.run()` de mise en place (~ligne 450), ajouter :

```python
    _goto_saisie(at)
```

`test_hours_are_distinct_per_quart` — remplacer :

```python
    acts = _acts_pills(at, "Lundi")
    acts.set_value(["C01 - Test"]).run()
    [n for n in at.number_input if n.key == "h_Lundi_Jour_Alice_C01 - Test"][0].set_value(8.0).run()
    # ajouter Soir (vide) via le popover ＋ ; la vue bascule dessus
    [b for b in at.button if b.key == "empty_quart_Lundi_Soir"][0].click().run()
```

par :

```python
    acts = _acts_pills(at, "Lundi")
    acts.set_value(["C01 - Test"]).run()
    _goto_saisie(at)
    [n for n in at.number_input if n.key == "h_Lundi_Jour_Alice_C01 - Test"][0].set_value(8.0).run()
    # le sélecteur de quart est sur l'étape Configuration : y revenir pour ajouter Soir
    _goto_config(at)
    # ajouter Soir (vide) via le popover ＋ ; la vue bascule dessus
    [b for b in at.button if b.key == "empty_quart_Lundi_Soir"][0].click().run()
```

`test_add_quart_can_copy_team_and_activities` — remplacer :

```python
    acts = _acts_pills(at, "Lundi")
    acts.set_value(["C01 - Test"]).run()
    # saisir des heures sur Jour -> elles ne doivent PAS être copiées
    [n for n in at.number_input if n.key == "h_Lundi_Jour_Alice_C01 - Test"][0].set_value(5.0).run()
    # ajouter Soir en copiant depuis Jour via le popover ＋ « Copier depuis Jour »
    [b for b in at.button if b.key == "copy_quart_Lundi_Soir"][0].click().run()
```

par :

```python
    acts = _acts_pills(at, "Lundi")
    acts.set_value(["C01 - Test"]).run()
    # saisir des heures sur Jour -> elles ne doivent PAS être copiées
    _goto_saisie(at)
    [n for n in at.number_input if n.key == "h_Lundi_Jour_Alice_C01 - Test"][0].set_value(5.0).run()
    # le popover de copie est sur l'étape Configuration : y revenir
    _goto_config(at)
    # ajouter Soir en copiant depuis Jour via le popover ＋ « Copier depuis Jour »
    [b for b in at.button if b.key == "copy_quart_Lundi_Soir"][0].click().run()
```

- [ ] **Step 12 : Mettre à jour les docstrings/commentaires mentionnant les onglets**

Dans `tests/test_ui.py` :
- ligne ~89, docstring de `test_day_config_shows_project_personnel` : remplacer
  `"""L'onglet Configuration du jour propose les employés du projet (pills)."""` par
  `"""La configuration du jour propose les employés du projet (pills)."""`.
- ligne ~465, commentaire de `test_add_quart_creates_second_quart` : remplacer
  `# les onglets se rendent contre « Soir », d'où la clé acts_pills_Lundi_Soir.` par
  `# la vue se rend contre « Soir », d'où la clé acts_Lundi_Soir.`

- [ ] **Step 13 : Lancer toute la suite**

Run: `python3 -m pytest tests/test_ui.py -v`
Expected: PASS (tous les tests, y compris les 3 nouveaux ; `test_day_total_badge_reflects_entered_hours` reste `skip`).

- [ ] **Step 14 : Commit**

```bash
git add app.py tests/test_ui.py
git commit -m "feat: flux config→saisie en deux étapes (retrait des onglets)"
```

---

## Self-Review

**Spec coverage :**
- Modèle de navigation (`day_entry_step`, reset à l'entrée) → Steps 3-4. ✓
- Étape Configuration (sélecteur de quart, contenu, bouton enregistrer+naviguer) → Steps 4-6. ✓
- Étape Saisie (barre retour + libellé quart, contenu, barre Enregistrer finale) → Steps 6-7. ✓
- Nettoyage (CSS onglets, messages d'info) → Steps 8-9. ✓
- Critères de réussite (plus de `st.tabs`, navigation, retour sans perte, bouton final sur Saisie seulement) → tests Steps 1, 10, 13. ✓

**Placeholder scan :** aucun TBD/TODO ; tout le code est explicite. ✓

**Type consistency :** clés `save_next_{jour}`, `back_config_{jour}`, `save_{jour}` cohérentes entre app et tests ; `save_report_from_state()` renvoie `(ok, msg)` utilisé partout pareil ; helpers `_goto_saisie`/`_goto_config` définis avant usage. ✓
