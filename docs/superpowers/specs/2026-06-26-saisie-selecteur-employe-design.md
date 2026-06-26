# Saisie par employé — sélecteur d'employé (remplace l'accordéon)

Date : 2026-06-26
Fichier touché : `app.py` (boucle Saisie de `view_day_entry` ;
`_clear_quart_widget_state`).

## Contexte

La saisie affiche aujourd'hui une carte `st.expander` par ressource du roster
(personnel + équipements autonomes), repliée par défaut. Retour d'usage :
**l'accordéon ne convient pas**. La contrainte connexe reste : éviter une page
très longue (tout déplié) tout en gardant une vue d'ensemble.

## Objectif

Remplacer l'accordéon par un **sélecteur d'employé** : une rangée de pastilles
liste l'équipe ; on choisit une personne et **sa seule fiche** s'affiche en
dessous, dépliée. Une ressource à la fois, pas d'accordéon, pas de long
défilement.

## Modifications (`app.py`)

### 1. Sélecteur + fiche unique (boucle Saisie de `view_day_entry`)

Remplacer le bloc actuel (titre + champ de recherche + `roster`/filtre +
`for … st.expander`) par :

- Titre `#### 🕐 Saisie des heures`.
- Si `full_roster` est vide → message d'info existant (« Commencez par
  sélectionner le **personnel / équipements**… »).
- Sinon :
  - Construire des **libellés stables** `f"{'👷' if typ=='P' else '🚜'} {name}"`
    pour chaque `(name, typ)` du roster, et une table `libellé → (name, typ)`.
    Les libellés **ne contiennent pas** le total d'heures (sinon le libellé
    changerait à chaque saisie et ferait sauter la sélection).
  - Un `st.pills` **sélection simple** (clé `resource_sel_{jour}_{quart_name}`,
    `label_visibility="collapsed"`), initialisé sur le premier libellé si
    l'état courant n'est pas dans la liste (seed via `st.session_state[...]`,
    pas de `default=`).
  - Résoudre le libellé sélectionné en `(name, typ)` ; si la sélection est nulle
    ou invalide, repli sur le premier libellé.
  - Afficher un en-tête `##### {libellé} — {_resource_total(quart, name):.1f} h`
    puis appeler `_render_resource_card(jour, quart_name, quart, name, typ,
    all_activities)` **sans `st.expander`**.

Le corps de `_render_resource_card` (tableau TR/TS aligné, équipement, prime,
commentaire) ne change pas. La note de quart, la barre dirty et le bouton
Enregistrer qui suivent restent inchangés.

### 2. Retrait de la recherche de ressource

Le champ « 🔍 Rechercher une ressource » (clé `roster_search_{jour}_{quart_name}`)
et le filtrage `roster` associé sont supprimés (le sélecteur le remplace).

Dans `_clear_quart_widget_state`, retirer le préfixe `roster_search_{jour}_{quart_name}`
et ajouter `resource_sel_{jour}_{quart_name}`.

## Cas limites

- Roster vide → info (inchangé).
- Sélection nulle (déselection d'une pastille) ou devenue invalide (roster
  modifié) → repli sur le premier libellé.

## Hors périmètre (YAGNI)

- Aucun changement au modèle, à la BD, à `save_report`/`load_report`, ni au corps
  de `_render_resource_card`.
- Pas de total d'heures dans les libellés des pastilles (le total reste dans
  l'en-tête de la fiche sélectionnée).
- Pas de recherche/filtre dans le sélecteur (YAGNI ; à ajouter seulement si une
  équipe devient ingérable en pastilles).

## Tests

- Les tests de carte existants (`test_day_hours_entry_updates_model`,
  `test_day_equip_codes_and_hours`, `test_day_prime_inline`,
  `test_day_comment_inline`, `test_saisie_card_table_header_…`,
  `test_day_entry_no_activity_shows_info`) utilisent `_open_day_for_entry` avec un
  seul employé (« Alice ») : Alice est le premier du roster, donc **sélectionnée
  par défaut** et sa fiche est rendue — ces tests passent sans modification.
- Remplacer `test_roster_search_filters_resources` par un test de **sélecteur** :
  avec deux employés (Alice, Bob), Alice est rendue par défaut ; après avoir posé
  `at.session_state["resource_sel_Lundi_Jour"] = "👷 Bob"` puis `at.run()`, la
  fiche de Bob est rendue (clé `acts_Lundi_Jour_Bob` présente) et celle d'Alice ne
  l'est plus. (On pilote la sélection via `session_state` car `st.pills` n'est pas
  cliquable de façon fiable sous AppTest — même approche que `_goto_saisie`.)

## Critères de réussite

- Plus aucun `st.expander` dans la boucle Saisie ; à la place, un `st.pills` de
  l'équipe + une seule fiche.
- Choisir une personne dans le sélecteur affiche sa fiche (et masque les autres).
- Les clés de widgets de la fiche (`acts_`, `tr_`, `ts_`, `eqc_`, `eqh_`, `p_`,
  `c_`) et la logique d'écriture sont inchangées.
- La suite de tests passe (tests de carte existants + nouveau test de sélecteur ;
  l'ancien test de recherche est retiré).
