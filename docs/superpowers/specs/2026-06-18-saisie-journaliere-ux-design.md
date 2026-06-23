# Design — Refonte UX de la saisie journalière (liste par ressource)

Date : 2026-06-18
Statut : approuvé pour planification

## Objectif

La saisie d'un jour (`view_day_entry`) repose sur une **matrice `st.data_editor`**
(Ressource × colonnes d'activités). Sur **tablette**, cette grille est trop large
(défilement horizontal), avec des cellules petites difficiles à remplir au doigt.
C'est la friction n°1 identifiée par l'utilisateur.

Contexte d'usage confirmé :
- Heures **ventilées par personne** (différentes personnes sur différentes activités).
- **2 à 4 activités** par jour, plus la colonne fixe `960`.
- **6 à 12 ressources** (personnel + équipements) par jour.

Direction retenue (parmi 3 maquettes présentées) : **A · Liste par ressource** —
une carte par ressource avec un champ nombre par activité du jour, plus gros qu'une
cellule de grille, sans défilement horizontal.

## Portée

Dans la portée :
- Remplacement du bloc grille de `view_day_entry` par un rendu **par ressource**.
- Nouveaux helpers purs : `_roster(config)`, `_resource_total(day, nom)`.
- Retrait de `_day_grid_df` et `_grid_df_to_day` (spécifiques à la grille, devenus inutiles).
- Remplacement des tests de ces helpers ; nouveaux tests (helpers + AppTest de saisie).

Hors portée (inchangé) :
- En-tête météo/description (expander actuel).
- Les multiselects **Activités** / **Autres** (définissent les colonnes d'heures).
- L'export Excel (`_legacy_day`, `build_workbook`).
- Le tableau de bord, les pages config/références/export.

## Mise en page de la saisie

1. **⬅️ Retour** + titre **Saisie : {jour}**.
2. **🌤️ Météo & Description** — expander inchangé.
3. **Activités du jour** : multiselects **Activités** (depuis `data_source.get_activities`)
   et **Autres** (depuis `ref["autres_projets"]`), inchangés. Ils déterminent les
   colonnes d'heures du jour : `["960"] + activités + autres` (via `_day_columns`).
4. **Heures par ressource** (nouveau) — pour chaque ressource du roster
   (personnel d'abord, puis équipements), une **carte** (`st.container(border=True)`) :
   - En-tête : `👷`/`🚜` + **nom** (gauche) ; **total de la ligne** + **⋯** (droite).
   - Sous l'en-tête : un `st.number_input` **par colonne** (`960` puis chaque activité du
     jour), disposés en colonnes Streamlit. Libellé = **code seul** (`c.split(" - ")[0]`),
     description complète en infobulle (`help=`). `min_value=0.0`, `step=0.5`, `format="%.1f"`.
   - **⋯** : `st.popover` contenant **Prime** (`number_input`) et **Commentaire**
     (`text_input`) de la ressource.
5. **Total jour** sous la liste (`_day_total`).

## Modèle de données (inchangé)

Les champs écrivent directement dans les structures existantes du jour :
- `day["heures"][ressource][colonne] = float` — **seules les valeurs non nulles** sont
  stockées (un champ à 0 → la colonne n'est pas écrite ; une ressource sans heure →
  absente de `heures`).
- `day["prime"][ressource] = float` (non nul uniquement).
- `day["commentaire_ligne"][ressource] = str` (non vide uniquement).

Ainsi `_legacy_day` et l'export Excel fonctionnent **sans modification**.

## Helpers

- `_roster(config) -> list[(nom, "P"|"E")]` : personnel puis équipements, dans l'ordre.
- `_resource_total(day, nom) -> float` : somme des heures d'une ressource (toutes colonnes).
- `_day_columns(day)` et `_day_total(config, day)` : **conservés** tels quels.

## État des widgets

Chaque champ porte une **clé stable** incluant le jour et la colonne :
`h_{jour}_{ressource}_{colonne}` (heures), `p_{jour}_{ressource}` (prime),
`c_{jour}_{ressource}` (commentaire). Les clés contiennent `{jour}` → valeurs
distinctes par jour. On **pré-amorce** `st.session_state[clé]` depuis `day` quand la
clé est absente (au lieu de passer `value=`), pour éviter tout conflit valeur/clé et
tout avertissement Streamlit.

## Gestion des erreurs / cas limites

- Aucune activité sélectionnée → seule la colonne `960` est présente.
- Ressource retirée du roster (config) → ses heures restent en mémoire mais ne sont
  plus affichées (comportement actuel conservé).
- Changement de jour → clés distinctes, aucune fuite de valeurs entre jours.

## Tests

- `_roster`, `_resource_total` : tests purs (ordre, types, somme).
- AppTest : ouvrir un jour avec projet + équipe + activités ; saisir des heures via les
  champs **ciblés par clé** ; vérifier la mise à jour de `day["heures"]` et du total ;
  vérifier Prime/Commentaire via le popover.
- Retrait des tests `test_day_grid_df` / `test_grid_df_to_day_roundtrip`.
- L'export reste couvert par les tests existants (régression conservée).

## Critères de succès

- Saisir les heures d'une journée (6-12 ressources, 2-4 activités) **sans défilement
  horizontal**, avec des champs confortables au doigt sur tablette.
- Vue centrée sur la personne : on voit chaque ressource et ses heures par activité.
- L'export Excel produit le **même résultat** qu'avant pour des données équivalentes.

## Risques / compromis

- Plus de widgets individuels que la grille (≈ 6-12 ressources × 3-6 champs) → reruns
  un peu plus lourds, jugé acceptable à cette échelle.
- Prime/Commentaire derrière un popover : un clic de plus quand on les utilise
  (rare), au bénéfice d'un flux principal épuré.
