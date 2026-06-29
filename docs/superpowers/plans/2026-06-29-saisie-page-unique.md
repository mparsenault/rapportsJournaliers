# Saisie journalière sur une page unique — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fusionner les deux étapes (config / saisie) de `view_day_entry` en une seule page : météo, ajout du personnel et saisie des heures sur un même écran, sans machine d'états ni section « Équipements sur place ».

**Architecture:** On supprime `st.session_state.day_entry_step` et les deux branches `if step == "config"` / `else` de `view_day_entry`. La fonction rend désormais une seule colonne verticale : sélecteur de quart (toujours), carte Météo (inchangée), carte Personnel & heures (contrôles d'ajout existants + rail/fiche déjà construit), note du quart, puis un unique bouton Enregistrer avec validation douce (message informatif, pas de blocage).

**Tech Stack:** Python, Streamlit, tests via `streamlit.testing.v1.AppTest` + pytest.

## Global Constraints

- Widgets de sélection pilotables sous `AppTest` : `st.button` (jamais `st.pills` pour la sélection de ressource).
- `quart["equipements"]` reste dans le modèle (liste vide) ; ne pas toucher l'export Excel.
- Ne pas modifier `_render_resource_card`, `save_report_from_state`, ni le corps de la carte Météo.
- L'enregistrement n'est jamais bloqué : la validation est seulement informative.
- Commande de test : `.venv/bin/python -m pytest`.

---

### Task 1 : Fusionner config + saisie en une page unique

**Files:**
- Modify: `app.py` — `view_day_entry` (1127-1352), et `view_dashboard` (retrait de la ligne 940)
- Test: `tests/test_ui.py`

**Interfaces:**
- Consomme (inchangés) : `_render_quart_selector(jour, day, prev_day)`, `_current_quart_name(jour)`, `_roster(quart)`, `_resource_total(quart, name)`, `_render_resource_card(jour, quart_name, quart, name, typ, all_activities)`, `save_report_from_state()`, `data_source.get_activities(pid)`.
- Produit : page unique sans `day_entry_step`. Widgets stables : bouton `save_{jour}` (Enregistrer), recherche `res_search_{jour}_{quart_name}`, boutons `pick_{jour}_{quart_name}_{name}`. Disparaissent : `save_next_{jour}`, `back_config_{jour}`, et la section équipement `equip_box` / `add_equipment_*`.

- [ ] **Step 1 : Adapter les helpers de test en passe-plats**

Dans `tests/test_ui.py`, remplacer les helpers `_goto_saisie` / `_goto_config`
(lignes 61-70) par des passe-plats — tout est sur une page, plus d'étape :

```python
def _goto_saisie(at):
    """Compat : la saisie est désormais sur la page unique (plus d'étape)."""
    return at.run()


def _goto_config(at):
    """Compat : la config est désormais sur la page unique (plus d'étape)."""
    return at.run()
```

- [ ] **Step 2 : Supprimer les 3 tests de la machine d'états**

Dans `tests/test_ui.py`, supprimer entièrement ces trois fonctions :
`test_day_entry_starts_on_config_step` (73-81),
`test_save_and_navigate_advances_to_saisie` (84-96),
`test_back_returns_to_config` (99-107).

- [ ] **Step 3 : Remplacer les 2 tests de gate dur par un test de validation douce**

Dans `tests/test_ui.py`, remplacer `test_save_next_disabled_until_requirements_met`
(110-119) et `test_save_next_requires_temperature` (122-129) par :

```python
def test_missing_requirements_shows_soft_warning_but_save_present(monkeypatch):
    """Sans personnel ni température : message informatif affiché, mais le bouton
    Enregistrer existe quand même (plus de gate dur, plus de save_next)."""
    at = _open_day_for_entry(monkeypatch, personnel=())
    assert not any(b.key == "save_next_Lundi" for b in at.button)
    save = [b for b in at.button if b.key == "save_Lundi"]
    assert save and not save[0].disabled
    infos = " ".join(i.value for i in at.info)
    assert "température" in infos and "personnel" in infos
    assert not at.exception


def test_requirements_met_clears_warning(monkeypatch):
    """Personnel + température remplis : plus de message « Pour continuer »."""
    at = _open_day_for_entry(monkeypatch, personnel=("Alice",))
    [n for n in at.number_input if n.key == "Lundi_Jour_temp_am"][0].set_value(0.0).run()
    infos = " ".join(i.value for i in at.info)
    assert "Pour continuer" not in infos
    assert not at.exception
```

- [ ] **Step 4 : Ajouter le test « ajout via pills → apparaît dans le rail »**

Ajouter dans `tests/test_ui.py` (après les tests du rail existants) :

```python
def test_add_employee_via_manual_appears_in_rail(monkeypatch):
    """Ajouter un employé (ajout manuel) le fait apparaître comme bouton du rail
    sur la même page, sans changement d'étape."""
    at = _open_day_for_entry(monkeypatch, personnel=("Alice",))
    assert any(b.key == "pick_Lundi_Jour_Alice" for b in at.button)
    [t for t in at.text_input if t.key == "new_employee_Lundi_Jour"][0].set_value("Bob").run()
    [b for b in at.button if b.key == "add_manual_Lundi_Jour"][0].click().run()
    assert any(b.key == "pick_Lundi_Jour_Bob" for b in at.button)
    assert not at.exception


def test_single_page_has_meteo_and_hours_together(monkeypatch):
    """La page unique montre la météo ET la saisie des heures en même temps,
    sans bouton d'étape."""
    at = _open_day_for_entry(monkeypatch, personnel=("Alice",))
    assert any(n.key == "Lundi_Jour_temp_am" for n in at.number_input)   # météo
    assert any(m.key == "acts_Lundi_Jour_Alice" for m in at.multiselect)  # fiche heures
    assert not any(b.key == "back_config_Lundi" for b in at.button)
    assert not any((t.key or "").startswith("new_equipment_") for t in at.text_input)  # équip. retiré
    assert not at.exception
```

- [ ] **Step 5 : Lancer les tests nouveaux/réécrits pour vérifier qu'ils échouent**

Run: `.venv/bin/python -m pytest tests/test_ui.py -k "missing_requirements or requirements_met or appears_in_rail or single_page_has_meteo" -v`
Expected: FAIL (la page est encore en deux étapes : `back_config_Lundi`/`save_next_Lundi` présents, équipement présent, fiche d'heures absente à l'ouverture).

- [ ] **Step 6 : Retirer le passage à l'étape config dans le dashboard**

Dans `app.py`, dans le bouton `go_{jour}` de `view_dashboard`, supprimer la ligne 940 :

```python
                st.session_state.day_entry_step = "config"
```

(Garder les lignes voisines `st.session_state.active_day = jour`, `view = "day_entry"`, le pré-remplissage météo et `st.rerun()`.)

- [ ] **Step 7 : Restructurer `view_day_entry` en page unique**

Dans `app.py`, remplacer tout le bloc depuis la ligne 1127 (commentaire
« # Flux en deux étapes… ») jusqu'à la fin de la fonction (ligne 1352) par le code
ci-dessous. La carte Météo et les contrôles d'ajout de personnel sont **repris à
l'identique** de l'actuel ; seuls disparaissent la machine `step`, la section
équipement, les boutons d'étape, et la note + le bouton Enregistrer sont placés en
bas.

```python
    # Page unique : météo, personnel et saisie des heures sur un seul écran.
    # Le sélecteur de quart est rendu AVANT la résolution du quart courant pour
    # consommer la sélection en attente posée par _add_quart (sinon le quart
    # fraîchement ajouté s'afficherait un cycle en retard).
    _render_quart_selector(jour, day, prev_day)
    quart_name = _current_quart_name(jour)
    quart = day["quarts"][quart_name]

    # --- Météo (corps inchangé) ---
    with st.container(border=True, key="meteo_card"):
        # [REPRENDRE VERBATIM le corps actuel de la carte météo : app.py:1144-1191,
        #  de `header_cols = st.columns(...)` jusqu'à `quart["conditions"] = list(_sel_cond or [])`]

    # --- Personnel présent + saisie des heures ---
    with st.container(border=True, key="equipe_box"):
        # [REPRENDRE VERBATIM les contrôles d'ajout de personnel : app.py:1195-1247,
        #  de `ph = st.columns(...)` jusqu'au bloc d'ajout manuel `st.rerun()` inclus]

        full_roster = _roster(quart)
        all_activities = data_source.get_activities(st.session_state.projet.get("id_project"))
        st.divider()
        st.markdown("#### 🕐 Saisie des heures")
        if not full_roster:
            st.info("💡 Ajoutez du personnel ci-dessus pour saisir les heures.")
        else:
            # Sélecteur maître-détail : rail (recherche + liste de boutons) + fiche.
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

    # --- Note du quart ---
    quart["description"] = st.text_input("📝 Note du quart", quart["description"],
                                         placeholder="Commentaire sur le quart...",
                                         key=f"note_{jour}_{quart_name}", on_change=_mark_dirty)

    # --- Validation douce + enregistrement unique ---
    st.divider()
    missing = []
    if quart["temp_am"] is None and quart["temp_pm"] is None:
        missing.append("une température (AM ou PM)")
    if not quart.get("personnel"):
        missing.append("du personnel")
    sb1, sb2 = st.columns([3, 1], vertical_alignment="center")
    if missing:
        sb1.info("Pour continuer, pensez à ajouter : " + ", ".join(missing) + ".")
    elif st.session_state.get("dirty"):
        sb1.warning("⚠️ Modifications non enregistrées — pensez à enregistrer avant de quitter.")
    else:
        sb1.caption("✓ Toutes les modifications sont enregistrées.")
    if sb2.button("💾 Enregistrer", use_container_width=True, type="primary", key=f"save_{jour}"):
        ok, msg = save_report_from_state()
        (st.success if ok else st.error)(msg)
```

Note d'implémentation : les deux commentaires `# [REPRENDRE VERBATIM …]` désignent
des blocs existants à copier sans modification (juste réindentés à leur nouvelle
place). Ne rien changer à leur logique. La section « 🚜 Équipements sur place »
(ancien `equip_box`, app.py:1250-1283) n'est **pas** reprise — elle disparaît.

- [ ] **Step 8 : Lancer les tests ciblés pour vérifier qu'ils passent**

Run: `.venv/bin/python -m pytest tests/test_ui.py -k "missing_requirements or requirements_met or appears_in_rail or single_page_has_meteo or resource_" -v`
Expected: PASS.

- [ ] **Step 9 : Lancer toute la suite pour vérifier l'absence de régression**

Run: `.venv/bin/python -m pytest -q`
Expected: tous PASS (sauf le `@pytest.mark.skip` préexistant). Si un test résiduel
référence `day_entry_step`, `save_next_*` ou `back_config_*`, l'adapter (la sélection
de ressource passe par `session_state["resource_sel_…"]` ou un clic `pick_…`).

- [ ] **Step 10 : Commit**

```bash
git add app.py tests/test_ui.py
git commit -m "feat: saisie journalière sur une page unique (fusion config + saisie)

Supprime la machine d'états day_entry_step et la section Équipements sur
place. Météo, ajout du personnel et saisie des heures sur un seul écran,
avec validation douce et un unique bouton Enregistrer.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Couverture de la spec :**
- Page unique (quart selector + météo + personnel/heures + note + 1 save) → Step 7. ✓
- Suppression `day_entry_step` + boutons d'étape → Steps 6, 7. ✓
- Sélecteur de quart toujours rendu → Step 7 (`_render_quart_selector` hors condition). ✓
- Contrôles d'ajout + rail fusionnés, ajout → apparition immédiate dans le rail → Step 7 + test Step 4. ✓
- Section « Équipements sur place » retirée → Step 7 (non reprise) + test Step 4 (`new_equipment_` absent). ✓
- `equipements` conservé vide / export intact → aucun changement au modèle ni à l'export (hors périmètre respecté). ✓
- Équipement par employé conservé → `_render_resource_card` inchangé. ✓
- Validation douce au-dessus d'Enregistrer, sans blocage → Step 7 + tests Step 3. ✓
- Impact tests (supprimer 3, réécrire 2, helpers passe-plats, ajouter tests) → Steps 1-4. ✓
- `_add_quart` ne force plus l'étape → c'est `view_dashboard` ligne 940 qui posait l'étape ; retirée Step 6. (`_add_quart` ne touche pas `day_entry_step`, donc rien à y changer — corrige une imprécision de la spec.) ✓

**2. Placeholders :** les deux `# [REPRENDRE VERBATIM …]` ne sont pas des placeholders de logique à inventer : ils pointent des blocs existants précis (plages de lignes) à copier sans changement. Tout code nouveau/modifié est fourni en entier.

**3. Cohérence des types :** clés stables cohérentes entre Step 7 et les tests : `save_{jour}` (= `save_Lundi`), `res_search_{jour}_{quart_name}`, `pick_{jour}_{quart_name}_{name}`, `Lundi_Jour_temp_am`, `acts_Lundi_Jour_Alice`, `new_employee_Lundi_Jour`, `add_manual_Lundi_Jour`. Absences vérifiées : `save_next_Lundi`, `back_config_Lundi`, `new_equipment_*`.
