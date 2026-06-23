# Design — Retrait de la colonne d'heures fixe « 960 »

Date : 2026-06-18
Statut : approuvé pour planification

## Objectif

La grille d'heures impose toujours une première colonne fixe « 960 »
(`FIXED_COL = "960"`), héritée du classeur Excel manuel d'origine. Comme les
activités viennent désormais de la base (Maestro), cette colonne codée en dur
n'a plus lieu d'être : on la **retire**. Les heures se saisissent uniquement sur
les **activités** (et « autres ») choisies pour le jour.

## Portée

Dans la portée :
- Suppression de `FIXED_COL` et de la colonne « 960 » dans `_day_columns`.
- Adaptation de l'export `_legacy_day` (les activités occupent `h0..h7`).
- Garde-fou dans `view_day_entry` quand aucune colonne d'heures n'existe.
- Mise à jour des tests (fixture + attentes) + nouveau test du cas vide.

Hors portée (inchangé) :
- Projets, activités (BD), `project_staff`, météo, tableau de bord, le reste de
  l'UI et de l'export.

## Modèle

- Supprimer la constante `FIXED_COL = "960"`.
- `_day_columns(day)` → `list(day["activites"]) + list(day["autres"])`
  (plus de « 960 » en tête).
- Conséquence assumée : sans activité ni « autre » sélectionné, **aucune colonne
  d'heures** ; il faut choisir une activité pour saisir des heures. Plus de
  saisie d'heures « génériques ».

## Export (`_legacy_day`)

- Retirer `headers["h0"] = "960"` et l'amorce `label_to_key = {FIXED_COL: "h0"}`.
- Les activités du jour occupent désormais `h0..h7` (jusqu'à 8) au lieu de
  `h1..h7` ; les « autres » restent `a0..a3`. Les cellules `h*`/`a*` non
  utilisées restent vides (`""`), comme avant.
- Le reste de `_legacy_day` (construction de `pers`/`equip` via `label_to_key`)
  est inchangé : il mappe chaque libellé de colonne présent dans
  `day["heures"]` vers sa clé.

## Saisie du jour (`view_day_entry`) — cas limite

`cols_labels = _day_columns(day)` peut maintenant être **vide**. La grille fait
`st.columns(len(cols_labels))` ; `st.columns(0)` lèverait une erreur. Donc :

- Si `cols_labels` est vide : afficher
  `st.info("Sélectionnez au moins une activité pour saisir des heures.")` et **ne
  pas** rendre les cartes par ressource.
- Sinon : rendu par ressource inchangé.
- Le « Total jour » reste affiché (0.00 h quand aucune colonne).

## Tests

- Mettre à jour la fixture `_sample_day` (`tests/test_model.py`) pour que les
  heures portent sur des **activités réelles** (plus sur « 960 »), p. ex.
  `{"Mathis": {"Excavation": 4.0, "P-77": 2.0}, "Camion v1892": {"Excavation": 8.0}}`.
- Mettre à jour les attentes :
  - `test_day_columns` → `["Excavation", "P-77"]` (sans 960).
  - `test_day_total` → recalculé (p. ex. 14.0).
  - `test_resource_total` → recalculé.
  - `test_legacy_day_maps_labels_to_keys` → `headers["h0"]` = 1re activité
    (« Excavation »), `a0` = « P-77 », mapping `h0`/`a0` cohérent.
- Ajouter un test AppTest : ouverture d'un jour **sans activité** →
  message d'info présent, `not at.exception`, aucune carte de ressource.

## Critères de succès

- Plus de colonne « 960 » dans la grille ni dans `_day_columns`.
- Saisir des heures uniquement sur les activités/autres choisis.
- Aucun plantage quand aucune activité n'est sélectionnée.
- Export cohérent (activités sur `h0..h7`), sans régression sur la structure
  `pers`/`equip`.

## Risques / compromis

- Changement de mise en page de l'export (les activités glissent de `h1..h7`
  vers `h0..h7`) — assumé, c'est la conséquence directe du retrait.
- Les anciennes données éventuelles avec une clé « 960 » dans `day["heures"]`
  ne seraient plus comptées (colonne absente) ; non pertinent (données en
  mémoire de session uniquement).
