# Quart de travail par jour (Jour / Soir / Nuit) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un sélecteur de quart de travail par jour (Jour / Soir / Nuit) dans l'onglet « Saisie des heures », saisi en pills et persisté avec le rapport.

**Architecture:** L'UI écrit le choix dans `day["quart"]` (champ déjà présent dans `_empty_day()`). La persistance ajoute une colonne `quart` à `report_days` ; `save_report`/`load_report` l'écrivent/relisent ; `load_report_into_state` ré-hydrate le state et `_clear_grid_widget_state` purge le widget après un chargement BD.

**Tech Stack:** Python, Streamlit (`st.pills`), SQLAlchemy + Postgres (Neon), pytest + `streamlit.testing.v1.AppTest`.

## Global Constraints

- Textes d'interface en **français**.
- Cibles tactiles tablette : boutons ≥ 42px (cohérent avec les pills existantes).
- **Source unique** pour la liste des quarts : dériver de la constante `QUARTS = ["", "Jour", "Soir", "Nuit"]` (app.py:46) ; ne pas redéfinir la liste.
- Quart **par jour** (pas au niveau semaine). Le quart semaine existant (`config["quart"]`, `reports.quart`) reste **intact** — aucune suppression de colonne.
- Migration de schéma **non destructive** et idempotente.

## File Structure

- `app.py` — UI du sélecteur (`view_day_entry`, onglet `tab_saisie`), CSS des pills (`get_css`), hydratation (`load_report_into_state`) et purge widget (`_clear_grid_widget_state`).
- `reports.py` — schéma (`_DDL_STATEMENTS`), écriture (`save_report`), lecture (`load_report`).
- `tests/test_ui.py` — test AppTest du sélecteur.

## Task Ordering

- **Task 1** livre le sélecteur fonctionnel en session (testable via AppTest).
- **Task 2** ajoute la persistance par jour (non testable en unitaire — convention `test_reports.py`, validée e2e/manuellement).

---

### Task 1: Sélecteur de quart (UI) + écriture dans le state

**Files:**
- Modify: `app.py` — `view_day_entry`, onglet `tab_saisie` (insertion après la ligne titre/recherche, vers app.py:1051) ; `get_css` (ajout de règles pills, vers app.py:679).
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes : constante `QUARTS` (app.py:46) ; champ `day["quart"]` (défaut `""`, app.py:188) ; helper de test `_open_day_for_entry` (tests/test_ui.py:206) ; `_mark_dirty` (app.py:130).
- Produces : widget `st.pills` clé `f"quart_{jour}"` (mono-sélection) ; écrit `day["quart"]` (`""` si rien). Conteneur CSS `st-key-quart_box`. Task 2 s'appuie sur `day["quart"]`.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter dans `tests/test_ui.py` (après `test_day_comment_inline_column`) :

```python
def test_day_quart_pills_select_updates_model(monkeypatch):
    """Onglet Saisie des heures : 3 pills de quart (Jour/Soir/Nuit) ;
    en sélectionner un met à jour day['quart']."""
    at = _open_day_for_entry(monkeypatch)
    # les pills de quart exposent les trois options
    opts = [getattr(o, "content", o)
            for bg in at.button_group for o in getattr(bg, "options", [])]
    assert "Jour" in opts and "Soir" in opts and "Nuit" in opts
    # sélectionner « Soir » via la clé du widget -> day['quart'] = 'Soir'
    at.session_state["quart_Lundi"] = "Soir"
    at.run()
    assert at.session_state["jours"]["Lundi"]["quart"] == "Soir"
    assert not at.exception
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `python -m pytest tests/test_ui.py::test_day_quart_pills_select_updates_model -v`
Expected: FAIL — `at.button_group` ne contient aucune pill de quart, donc `assert "Jour" in opts` échoue (`opts` vide).

- [ ] **Step 3: Implémenter le sélecteur de quart**

Dans `app.py`, onglet `tab_saisie`, juste après le bloc titre/recherche (la ligne `query = hd2.text_input(...).strip().lower()`, app.py:1048-1051) et **avant** `full_roster = _roster(config)` (app.py:1053), insérer :

```python
        # Quart de travail (Jour / Soir / Nuit) — par jour, mono-sélection
        with st.container(key="quart_box"):
            st.caption("Quart de travail")
            _quart_options = [q for q in QUARTS if q]
            st.session_state.setdefault(f"quart_{jour}", day["quart"] or None)
            _selected_quart = st.pills(
                "Quart de travail", _quart_options,
                selection_mode="single", key=f"quart_{jour}",
                label_visibility="collapsed", on_change=_mark_dirty)
            day["quart"] = _selected_quart or ""
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `python -m pytest tests/test_ui.py::test_day_quart_pills_select_updates_model -v`
Expected: PASS

- [ ] **Step 5: Ajouter le style des pills (cohérence tactile teal)**

Dans `app.py`, fonction `get_css`, ajouter ce bloc à la fin des règles (avant `</style>`, vers app.py:731). Il réutilise les variables de l'f-string (`{ONDEL_GREEN}`, `{ONDEL_ACCENT}`) déjà en scope :

```python
    /* Pills Quart de travail — même apparence que les pills d'équipe */
    .st-key-quart_box [data-testid="stButtonGroup"] button {{
        min-height: 42px !important;
        font-size: 0.95rem !important;
        border-radius: 21px !important;
        margin: 3px 4px 3px 0 !important;
    }}
    .st-key-quart_box button[data-testid="stBaseButton-pills"] {{
        border: 1.5px solid #CBD5E1 !important;
        background: #FFFFFF !important;
        color: {ONDEL_ACCENT} !important;
    }}
    .st-key-quart_box button[data-testid="stBaseButton-pillsActive"] {{
        background: {ONDEL_GREEN} !important;
        border: 1.5px solid {ONDEL_GREEN} !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
    }}
    .st-key-quart_box button[data-testid="stBaseButton-pillsActive"] p {{
        color: #FFFFFF !important;
    }}
```

- [ ] **Step 6: Relancer toute la suite UI (pas de régression)**

Run: `python -m pytest tests/test_ui.py -v`
Expected: PASS (y compris le nouveau test ; aucun test existant cassé).

- [ ] **Step 7: Commit**

```bash
git add app.py tests/test_ui.py
git commit -m "feat: sélecteur de quart par jour (Jour/Soir/Nuit) dans la saisie des heures

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Persistance par jour + hydratation du state

**Files:**
- Modify: `reports.py` — `_DDL_STATEMENTS` (reports.py:50-63 + ajout d'un `alter`), `save_report` (insert `report_days`, reports.py:175-196), `load_report` (select + dict `days_by_date`, reports.py:271-307).
- Modify: `app.py` — `load_report_into_state` (`day.update`, app.py:160-166), `_clear_grid_widget_state` (app.py:120-124).

**Interfaces:**
- Consumes : `day["quart"]` (produit par Task 1) ; structure `data["days_by_date"][...]` de `load_report`.
- Produces : colonne `report_days.quart` ; clé `"quart"` dans chaque entrée `days_by_date` de `load_report` ; ré-hydratation de `day["quart"]` au chargement BD.

> **Note testing :** la persistance BD n'est **pas** couverte en unitaire (convention `test_reports.py` : types Postgres `text[]`/`serial` non reproductibles en SQLite ; validation e2e contre Neon). Les étapes de vérification ci-dessous sont (a) la suite de tests existante pour garantir l'absence de régression de chargement, et (b) une vérification manuelle BD.

- [ ] **Step 1: Ajouter la colonne `quart` au schéma `report_days`**

Dans `reports.py`, `_DDL_STATEMENTS`, modifier le `create table if not exists report_days` (reports.py:50-63) pour ajouter `quart text` après `note text,` :

```python
    """
    create table if not exists report_days (
        id         serial primary key,
        report_id  integer not null references reports(id) on delete cascade,
        day_date   date not null,
        note       text,
        quart      text,
        temp_am    numeric,
        temp_pm    numeric,
        conditions text[] not null default '{}',
        activites  text[] not null default '{}',
        autres     text[] not null default '{}',
        unique (report_id, day_date)
    )
    """,
```

Puis ajouter, dans la même liste `_DDL_STATEMENTS` (après le dernier index, reports.py:84), une migration idempotente pour les bases déjà créées :

```python
    "alter table report_days add column if not exists quart text",
```

- [ ] **Step 2: Écrire `quart` dans `save_report`**

Dans `reports.py`, `save_report`, l'`insert into report_days` (reports.py:175-196) : ajouter `quart` aux colonnes et `:quart` aux valeurs, puis le paramètre.

Remplacer le bloc SQL et le dict de params par :

```python
            day_id = s.execute(
                text(
                    """
                    insert into report_days
                        (report_id, day_date, note, quart, temp_am, temp_pm,
                         conditions, activites, autres)
                    values
                        (:r, :d, :note, :quart, :tam, :tpm, :cond, :acts, :autres)
                    returning id
                    """
                ),
                {
                    "r": report_id,
                    "d": d_date,
                    "note": day.get("description") or None,
                    "quart": day.get("quart") or None,
                    "tam": day.get("temp_am"),
                    "tpm": day.get("temp_pm"),
                    "cond": list(day.get("conditions") or []),
                    "acts": list(day.get("activites") or []),
                    "autres": list(day.get("autres") or []),
                },
            ).scalar()
```

- [ ] **Step 3: Relire `quart` dans `load_report`**

Dans `reports.py`, `load_report` :

(a) ajouter `quart` au `select` des jours (reports.py:272-275) :

```python
        days = s.execute(
            text(
                "select id, day_date, note, quart, temp_am, temp_pm, conditions, activites, autres "
                "from report_days where report_id = :r"
            ),
            {"r": report_id},
        ).mappings().all()
```

(b) ajouter `"quart"` à chaque entrée `days_by_date` (reports.py:296-307), après la ligne `"description": d["note"] or "",` :

```python
            days_by_date[d["day_date"]] = {
                "date": d["day_date"],
                "description": d["note"] or "",
                "quart": d["quart"] or "",
                "temp_am": float(d["temp_am"]) if d["temp_am"] is not None else None,
                "temp_pm": float(d["temp_pm"]) if d["temp_pm"] is not None else None,
                "conditions": list(d["conditions"] or []),
                "activites": list(d["activites"] or []),
                "autres": list(d["autres"] or []),
                "heures": heures,
                "prime": prime,
                "commentaire_ligne": commentaire,
            }
```

- [ ] **Step 4: Ré-hydrater `day["quart"]` dans `load_report_into_state`**

Dans `app.py`, `load_report_into_state`, le `day.update({...})` (app.py:160-166) : ajouter la clé `quart`, après `"description": saved["description"],` :

```python
                day.update({
                    "description": saved["description"],
                    "quart": saved["quart"],
                    "temp_am": saved["temp_am"], "temp_pm": saved["temp_pm"],
                    "conditions": saved["conditions"], "activites": saved["activites"],
                    "autres": saved["autres"], "heures": saved["heures"],
                    "prime": saved["prime"], "commentaire_ligne": saved["commentaire_ligne"],
                })
```

- [ ] **Step 5: Purger la clé widget du quart après un chargement BD**

Dans `app.py`, `_clear_grid_widget_state`, la condition de purge (app.py:121-124) : ajouter `k.startswith("quart_")` :

```python
    for k in list(st.session_state.keys()):
        if (k.startswith("h_") or k.startswith("p_") or k.startswith("c_")
                or k.startswith("acts_") or k.startswith("temp_am_")
                or k.startswith("temp_pm_") or k.startswith("cond_")
                or k.startswith("quart_")):
            del st.session_state[k]
```

- [ ] **Step 6: Vérifier l'absence de régression (suite complète)**

Run: `python -m pytest -v`
Expected: PASS — toute la suite verte (les tests `test_reports.py` de logique pure et les tests UI restent verts ; le chargement BD est inerte en test car la base est injoignable → repli sans exception).

- [ ] **Step 7: Vérification manuelle BD (Neon)**

Lancer l'app (`streamlit run app.py`), choisir un projet + une semaine, ouvrir un jour, sélectionner un quart (p. ex. « Soir »), **Enregistrer**. Puis changer de semaine et revenir : le quart « Soir » doit être restauré sur ce jour. Vérifier aussi qu'un jour sans quart se recharge vide (pas d'erreur).

- [ ] **Step 8: Commit**

```bash
git add app.py reports.py
git commit -m "feat: persistance du quart par jour (colonne report_days.quart)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage :**
- UI pills mono-sélection sous le titre Saisie des heures → Task 1, steps 3/5. ✓
- Options dérivées de `QUARTS` (source unique) → Task 1, step 3 (`[q for q in QUARTS if q]`). ✓
- Optionnel, écrit `day["quart"]` (`""` si rien) → Task 1, step 3. ✓
- `on_change=_mark_dirty` → Task 1, step 3. ✓
- Style tactile teal → Task 1, step 5. ✓
- Schéma : colonne `quart` + migration idempotente → Task 2, step 1. ✓
- `save_report` / `load_report` → Task 2, steps 2/3. ✓
- Hydratation `load_report_into_state` → Task 2, step 4. ✓
- Purge `_clear_grid_widget_state` (préfixe `quart_`) → Task 2, step 5. ✓
- Export : aucun changement (repli `day → semaine` déjà présent) → hors tâches, conforme spec. ✓
- Quart semaine conservé intact → aucune tâche ne le touche. ✓
- Test UI → Task 1, step 1. ✓
- Persistance e2e/manuelle → Task 2, step 7. ✓

**Placeholder scan :** aucun TBD/TODO ; chaque step de code montre le code complet.

**Type consistency :** clé widget `quart_{jour}` cohérente (UI + purge) ; clé dict `"quart"` cohérente (`save_report` param `:quart`, `load_report` select + `days_by_date`, `load_report_into_state` `saved["quart"]`). ✓
