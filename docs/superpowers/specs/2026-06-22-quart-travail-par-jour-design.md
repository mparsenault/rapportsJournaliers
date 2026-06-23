# Design — Quart de travail par jour (Jour / Soir / Nuit)

Date : 2026-06-22
Statut : approuvé pour planification

## Objectif

Dans l'entrée journalière, permettre de choisir le **quart de travail** parmi
trois options : **Jour**, **Soir**, **Nuit**. Le choix se fait par jour, en haut
de l'onglet « Saisie des heures », et il est persisté avec le rapport.

Aujourd'hui la constante `QUARTS = ["", "Jour", "Soir", "Nuit"]` existe déjà et
`_empty_day()` contient un champ `"quart": ""`, mais **aucun widget** ne permet
de le saisir et il n'est **pas persisté** par jour. Il existe par ailleurs un
quart au niveau de la semaine (`config["quart"]`, colonne `reports.quart`),
jamais affiché dans l'UI actuelle.

## Portée

Dans la portée :
- Sélecteur de quart par jour (pills mono-sélection) dans l'onglet « Saisie des
  heures » de `view_day_entry`.
- Persistance par jour : colonne `quart` sur `report_days` (+ migration
  idempotente), écriture dans `save_report`, lecture dans `load_report`.
- Hydratation du state (`load_report_into_state`) et purge du widget
  (`_clear_grid_widget_state`).
- Test UI (`tests/test_ui.py`).

Hors portée (inchangé) :
- Le quart au niveau semaine (`config["quart"]`, `reports.quart`) : conservé tel
  quel, jamais supprimé (migration destructive évitée).
- Export Excel : aucun changement de code requis (voir « Export »).
- Tableau de bord, météo, personnel/équipements, projets/activités.

## UI — `app.py`, `view_day_entry`, onglet `tab_saisie`

Sous le titre `#### 🕐 Saisie des heures`, ajouter une ligne « Quart de travail » :

- `st.pills` mono-sélection, options dérivées de la constante existante :
  `[q for q in QUARTS if q]` → `["Jour", "Soir", "Nuit"]` (source unique de
  vérité, pas de liste dupliquée).
- Paramètres : `selection_mode="single"`, `key=f"quart_{jour}"`,
  `label_visibility="collapsed"`, `default=day["quart"] or None`,
  `on_change=_mark_dirty`. Un `st.caption("Quart de travail")` précède les pills.
- **Optionnel** : aucun quart par défaut. La sortie du widget (`None` si rien)
  est écrite dans `day["quart"]` (chaîne vide si `None`), cohérent avec le défaut
  `""` de `_empty_day()`.
- Apparence : réutiliser le style des pills déjà présent (pills personnel,
  `data-testid="stBaseButton-pills"` / `pillsActive`). Étendre la règle CSS au
  conteneur du quart pour garder l'apparence teal/tactile (touch target ≥ 42px).

## Persistance — `reports.py`

- **Schéma** : ajouter une colonne `quart text` à `report_days`. Comme
  `create table if not exists` ne migre pas une table déjà créée, ajouter une
  instruction idempotente à `_DDL_STATEMENTS` :
  `alter table report_days add column if not exists quart text`.
- **`save_report`** : inclure `quart` dans l'`insert into report_days`
  (paramètre `:quart`, valeur `day.get("quart") or None`).
- **`load_report`** : ajouter `quart` au `select ... from report_days`, et
  `"quart": d["quart"] or ""` à chaque entrée de `days_by_date`.

## Hydratation du state — `app.py`

- `load_report_into_state` : ajouter `"quart": saved["quart"]` au
  `day.update({...})`.
- `_clear_grid_widget_state` : ajouter le préfixe `quart_` à la liste des clés
  purgées, pour que les pills se ré-hydratent depuis le nouveau `day["quart"]`
  après un chargement BD (même logique que `temp_am_`, `cond_`, etc.).

## Export (`_legacy_day`) — aucun changement

`_legacy_day` lit déjà `day.get("quart") or config.get("quart", "")`. Le quart
par jour remonte donc automatiquement à l'export, avec repli sur le quart semaine
si le jour n'en a pas. Aucune ligne à modifier.

## Tests

- `tests/test_ui.py` (AppTest) : nouveau test.
  - Ouvrir un jour (`view = "day_entry"`), aller dans l'onglet « Saisie des
    heures ».
  - Vérifier que les pills de quart exposent `Jour`, `Soir`, `Nuit` (via
    `at.button_group`, comme les tests des pills personnel).
  - Définir une valeur (p. ex. `Soir`) et vérifier que
    `at.session_state["jours"][jour]["quart"] == "Soir"`.
  - `assert not at.exception`.
- Persistance BD : non couverte en unitaire (convention de `test_reports.py` —
  types Postgres `text[]`/`serial` non reproductibles en SQLite ; validée e2e
  contre Neon). À vérifier manuellement : enregistrer un jour avec quart, puis
  recharger le rapport (changer de semaine et revenir) → le quart est restauré.

## Critères de succès

- Dans l'onglet « Saisie des heures », trois pills Jour / Soir / Nuit en
  mono-sélection, sous le titre.
- Sélectionner un quart met à jour `day["quart"]` et marque le rapport « dirty ».
- Après enregistrement et rechargement, le quart du jour est restauré.
- L'export reflète le quart du jour (repli sur le quart semaine si absent).
- Aucune régression : tests existants verts.

## Risques / compromis

- **Quart semaine orphelin conservé** : `config["quart"]` / `reports.quart`
  restent en base sans UI. Inoffensif (l'export les utilise en repli). Une
  suppression propre serait une migration destructive, hors périmètre.
- **Migration de colonne** : `alter table ... add column if not exists` est
  idempotent et sûr sur Postgres ; ne touche pas les données existantes (les
  jours déjà enregistrés auront `quart = NULL`, lu comme `""`).
- **Pills + `default` + `key`** : sur un rerun normal, Streamlit privilégie la
  valeur en `session_state` (le `default` est ignoré tant que la clé existe) —
  comportement voulu ; le `default` ne sert qu'au premier rendu et après purge.
