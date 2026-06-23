# Retrait du système de données de référence — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retirer entièrement le système `refdata.json` (fichier, chargement, sauvegarde, page Références) et remplacer les options des multiselects par de la saisie libre (`accept_new_options`), Personnel restant alimenté par les suggestions projet (BD).

**Architecture:** Suppression dans `app.py` de toute la logique `ref` + de `view_reference` + du bouton/route Références ; les multiselects Personnel/Équipements deviennent `accept_new_options` ; le multiselect « Autres » de la saisie est retiré. Suppression du fichier `refdata.json`.

**Tech Stack:** Python, Streamlit 1.50 (`st.multiselect(..., accept_new_options=True)`), pytest + AppTest.

## Global Constraints

- Base = working tree `app.py`. Streamlit 1.50 (`accept_new_options` dispo).
- **Personnel** (vue config) : `options = sorted(set(data_source.get_project_staff(projet.get("id_project"))) | set(config["personnel"]))`, `default=config["personnel"]`, `accept_new_options=True`.
- **Équipements** (vue config) : `options = sorted(config["equipements"])`, `default=config["equipements"]`, `accept_new_options=True`.
- **« Autres »** retiré de `view_day_entry` ; `day["autres"]` reste `[]` (via `_empty_day`) — modèle/export inchangés.
- Supprimer : fichier `refdata.json` ; `REFDATA_PATH`, `_load_refdata_file`, `save_refdata`, l'init `st.session_state.ref`, `view_reference`, le bouton « 📚 Références » + la route `elif … == "reference"`.
- `import json` CONSERVÉ (météo). Ne pas toucher météo / projets / activités / `project_staff` / export.
- Boutons du bas : 2 (Équipe & Équipements · Export Excel), tous deux `disabled=not projet_choisi`.
- Tests : `.venv/bin/python -m pytest -q` ; sortie pristine, 0 failed.

## File Structure

- `app.py` — suppressions (constante, 2 fonctions, init, vue, bouton, route) + 2 multiselects config en `accept_new_options` + retrait « Autres ».
- `refdata.json` — supprimé.
- `tests/test_ui.py` — retrait de 2 tests, réécriture de 1.
- `README.md` — mention refdata mise à jour.

---

### Task 1 : Retirer le système refdata

**Files:**
- Modify: `app.py`
- Delete: `refdata.json`
- Modify: `tests/test_ui.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `data_source.get_project_staff(id_project)` (existant).
- Produces: vue config sans `ref` ; plus de page/route/bouton Références ; saisie sans « Autres ».

- [ ] **Step 1 : Mettre à jour `tests/test_ui.py`**

Dans `tests/test_ui.py` :

**(a)** SUPPRIMER entièrement `test_navigation_to_reference` et `test_reference_has_no_activities_tab` (la page Références disparaît).

**(b)** REMPLACER `test_setting_personnel_updates_config` par (Personnel alimenté par le staff projet ; le module importe déjà `datetime` et `AppTest`) :

```python
def test_setting_personnel_updates_config(monkeypatch):
    import data_source
    monkeypatch.setattr(data_source, "get_project_staff", lambda pid: ["Alice"] if pid == 1 else [])
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["projet"] = {"no": "P-1", "id_project": 1,
                                  "semaine": datetime.date(2026, 6, 7),
                                  "adresse": "", "lat": None, "lon": None}
    at.session_state["view"] = "config"
    at.run()
    pers = [m for m in at.multiselect if m.label == "Personnel"][0]
    assert "Alice" in pers.options
    pers.set_value(["Alice"]).run()
    assert at.session_state["config"]["personnel"] == ["Alice"]
    assert not at.exception
```

(`test_config_roster_multiselects_present` reste tel quel — il vérifie seulement la présence des libellés « Personnel » et « Équipements », qui existent toujours.)

- [ ] **Step 2 : Lancer, vérifier l'état**

Run : `.venv/bin/python -m pytest tests/test_ui.py -q 2>&1 | tail -8`
Expected : `test_setting_personnel_updates_config` passe peut-être déjà (le staff est ajouté aux options actuelles) ; l'important est qu'aucune erreur de collecte n'apparaisse après suppression des 2 tests. (RED réel survient à l'étape de retrait du code si un test référence du code supprimé — sinon, la validation est la suite verte finale + l'absence de référence résiduelle au Step 7.)

- [ ] **Step 3 : Retirer les constantes/fonctions refdata dans `app.py`**

- Supprimer la ligne `REFDATA_PATH = os.path.join(BASE_DIR, "refdata.json")`.
- Supprimer la fonction `_load_refdata_file` (le `@st.cache_data` au-dessus inclus) et la fonction `save_refdata`.
- Dans `init_state`, supprimer les deux lignes :
  ```python
      if "ref" not in st.session_state:
          st.session_state.ref = _load_refdata_file()
  ```

- [ ] **Step 4 : Retirer la vue Références, le bouton et la route**

- Supprimer entièrement la fonction `view_reference`.
- Dans `view_dashboard`, remplacer le bloc des boutons du bas :
  ```python
      st.divider()
      c1, c2, c3 = st.columns(3)
      if c1.button("⚙️ Équipe & Équipements", use_container_width=True, disabled=not projet_choisi): st.session_state.view = "config"; st.rerun()
      if c2.button("📚 Références", use_container_width=True, disabled=not projet_choisi): st.session_state.view = "reference"; st.rerun()
      if c3.button("📥 EXPORT EXCEL", type="primary", use_container_width=True, disabled=not projet_choisi): st.session_state.view = "export"; st.rerun()
  ```
  par :
  ```python
      st.divider()
      c1, c2 = st.columns(2)
      if c1.button("⚙️ Équipe & Équipements", use_container_width=True, disabled=not projet_choisi): st.session_state.view = "config"; st.rerun()
      if c2.button("📥 EXPORT EXCEL", type="primary", use_container_width=True, disabled=not projet_choisi): st.session_state.view = "export"; st.rerun()
  ```
- Dans `main`, supprimer la ligne `elif st.session_state.view == "reference": view_reference()`.

- [ ] **Step 5 : Retirer « Autres » et adapter les multiselects config**

- Dans `view_day_entry`, supprimer la ligne :
  ```python
          day["autres"] = st.multiselect("Autres", st.session_state.ref["autres_projets"], default=day["autres"])
  ```
- Dans `main`, bloc `elif st.session_state.view == "config":`, remplacer :
  ```python
          _pers_options = sorted(set(st.session_state.ref["personnel"])
                                 | set(data_source.get_project_staff(st.session_state.projet.get("id_project")))
                                 | set(st.session_state.config["personnel"]))
          st.session_state.config["personnel"] = st.multiselect("Personnel", _pers_options, default=st.session_state.config["personnel"])
          st.session_state.config["equipements"] = st.multiselect("Équipements", st.session_state.ref["vehicules"], default=st.session_state.config["equipements"])
  ```
  par :
  ```python
          _pers_options = sorted(set(data_source.get_project_staff(st.session_state.projet.get("id_project")))
                                 | set(st.session_state.config["personnel"]))
          st.session_state.config["personnel"] = st.multiselect(
              "Personnel", _pers_options, default=st.session_state.config["personnel"],
              accept_new_options=True)
          st.session_state.config["equipements"] = st.multiselect(
              "Équipements", sorted(st.session_state.config["equipements"]),
              default=st.session_state.config["equipements"], accept_new_options=True)
  ```

- [ ] **Step 6 : Supprimer le fichier et mettre à jour le README**

```bash
git rm refdata.json
```

Dans `README.md`, retirer la ligne décrivant `refdata.json` comme source des listes et la remplacer par une mention : personnel = employés suggérés du projet (BD) + saisie libre ; équipements = saisie libre ; plus de page « Données de référence ».

- [ ] **Step 7 : Vérifier l'absence de référence résiduelle**

Run : `grep -nE "refdata|_load_refdata_file|save_refdata|view_reference|session_state.ref\b|REFDATA_PATH|\"reference\"|autres_projets" app.py tests/`
Expected : aucune correspondance (hormis, éventuellement, des mentions dans `docs/`). Si une correspondance subsiste dans `app.py`/`tests/`, la corriger.

- [ ] **Step 8 : Lancer toute la suite**

Run : `.venv/bin/python -m pytest -q 2>&1 | tail -3`
Expected : 0 failed.

- [ ] **Step 9 : Commit**

```bash
git add app.py tests/test_ui.py README.md
git commit -m "refactor: retrait du système de données de référence (refdata)"
```

(`git rm refdata.json` du Step 6 est déjà indexé ; il est inclus dans ce commit.)

---

## Self-Review (auteur du plan)

**Couverture du spec :**
- Suppression refdata (fichier + REFDATA_PATH + _load_refdata_file + save_refdata + init ref) → Steps 3, 6. ✓
- Suppression page/bouton/route Références → Step 4. ✓
- Personnel = staff projet ∪ sélection + `accept_new_options` → Step 5. ✓
- Équipements = saisie libre `accept_new_options` → Step 5. ✓
- « Autres » retiré (input), `day["autres"]` reste `[]` → Step 5. ✓
- Boutons du bas en 2 colonnes → Step 4. ✓
- `import json` conservé (non touché). ✓
- Tests (retrait de 2, réécriture de 1) → Step 1. ✓
- README → Step 6. ✓
- Vérification anti-référence-résiduelle → Step 7. ✓

**Placeholders :** aucun (code complet ; les suppressions citent le code exact à retirer).

**Cohérence des types :** `get_project_staff(id) -> [str]`, options Personnel/Équipements = `list[str]`, `default ⊆ options` garanti (sélection courante incluse).
