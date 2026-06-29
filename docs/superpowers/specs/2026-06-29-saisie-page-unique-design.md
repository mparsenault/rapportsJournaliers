# Saisie journalière sur une page unique (fusion config + saisie)

**Date :** 2026-06-29
**Fichier principal :** `app.py` — `view_day_entry` (~lignes 1104-1352) et `_add_quart` (~940)
**Tests :** `tests/test_ui.py`
**Branche :** suite de `feat/selecteur-employe-rail-recherche` (réutilise le rail latéral + recherche déjà construit).

## Problème

La saisie d'un quart se fait en deux étapes pilotées par `st.session_state.day_entry_step` :

1. **« config »** — météo, personnel présent, équipements sur place, puis bouton
   « 💾 Enregistrer et saisir les heures → » (bloqué tant que météo + personnel
   manquent).
2. **« saisie »** — sélection de la ressource (rail latéral) + saisie des heures,
   avec un bouton « ← Retour à la configuration ».

L'aller-retour entre les deux étapes est lourd : on sélectionne le personnel, puis
on change d'écran pour saisir les heures, sans vue d'ensemble.

## Solution retenue

**Tout sur une seule page, par quart.** Suppression de la machine d'états
`day_entry_step` et des transitions. `view_day_entry` rend une seule colonne :

1. **Sélecteur de quart** — `_render_quart_selector`, désormais toujours rendu
   (aujourd'hui réservé à l'étape config, `app.py:1135-1136`).
2. **🌤️ Météo** — carte actuelle, inchangée (temp AM/PM, conditions, GPS).
3. **👷 Personnel & saisie des heures** — fusion :
   - **Contrôles d'ajout** (repris tels quels de la config) : pills « Employés du
     projet », selectbox « autre projet », ajout manuel.
   - **Rail + fiche** (le composant déjà construit) : à gauche, recherche + liste
     défilante des employés présents (statut 🟢/⚪, total) ; à droite, la fiche de
     saisie (`_render_resource_card`) de l'employé sélectionné. Ajouter un employé
     le fait apparaître immédiatement dans le rail.
4. **📝 Note du quart** — inchangée.
5. **💾 Enregistrer** — un seul bouton.

**Suppressions :**
- La section « 🚜 Équipements sur place » (`app.py:1250-1283`) et tout l'équipement
  autonome.
- La machine `day_entry_step`, les boutons `save_next_*` et `back_config_*`.
- Le gate dur de validation entre étapes.

## Détails

### Équipement autonome retiré
- On retire l'UI « Équipements sur place ». Le champ `quart["equipements"]` reste
  dans le modèle de données mais demeure une liste vide : l'export Excel continue de
  fonctionner, le tableau « Véhicule » est simplement vide (`app.py:401`).
- L'**équipement par employé** (codes + heures dans `_render_resource_card`,
  `equip_codes`/`equip_hours`) est **conservé** tel quel.
- `_roster` (`app.py:314-316`) est laissé inchangé : `equipements` étant toujours
  vide, le rail ne liste que du personnel (icône 👷). Aucune modification de code
  nécessaire côté roster.

### Validation
- Plus de bouton bloquant. À la place, un message d'information doux si la
  température (AM et PM) ou le personnel manquent — affiché juste au-dessus du bouton
  « 💾 Enregistrer », à l'emplacement du bandeau d'état actuel — mais
  **l'enregistrement reste possible**.
- Le bandeau d'état « modifications non enregistrées / enregistré » existant est
  conservé.

### Quart, ajout de quart
- `_add_quart` (`app.py:~940`) ne doit plus forcer `day_entry_step = "config"`
  (ligne à retirer) — il n'y a plus d'étape.
- Le sélecteur de quart est rendu une seule fois, en haut, avant la résolution du
  quart courant (le commentaire `app.py:1130-1134` reste valable : il consomme la
  sélection en attente d'`_add_quart`).

### Enregistrement
- Le bouton « 💾 Enregistrer » appelle `save_report_from_state()` (inchangé) et
  affiche succès/erreur. Plus de changement d'étape après sauvegarde.

## Impact sur les tests

`day_entry_step`, `_goto_saisie`, `_goto_config`, `save_next_Lundi`,
`back_config_Lundi` sont très présents dans `tests/test_ui.py`. Plan d'adaptation :

- **Helpers** : `_goto_saisie` / `_goto_config` deviennent de simples passe-plats
  (`return at.run()`) — tout est sur une page, aucun changement d'étape. Les nombreux
  tests qui les appellent continuent de fonctionner sans autre édition.
- **À supprimer** (testent la machine d'états disparue) :
  - `test_day_entry_starts_on_config_step`
  - `test_save_and_navigate_advances_to_saisie`
  - `test_back_returns_to_config`
- **À réécrire** (le gate dur disparaît) :
  - `test_save_next_disabled_until_requirements_met` et
    `test_save_next_requires_temperature` → un seul test vérifiant que le message
    d'info s'affiche quand température/personnel manquent et disparaît une fois
    remplis, sans bloquer un bouton (il n'y a plus de `save_next`).
- **À conserver / vérifier** : `test_resource_selector_shows_selected_card`,
  `test_resource_search_filters_rail`,
  `test_resource_pick_button_selects_and_survives_filter`, et tous les tests de la
  fiche de saisie (`acts_*`, `tr_*`, etc.) — ils trouvent désormais les widgets
  directement sur la page unique.
- **À ajouter** : un test « ajouter un employé via les pills du projet le fait
  apparaître comme bouton `pick_*` dans le rail ».

## Hors périmètre

- Pas de changement au modèle de données (`equipements` reste, vide).
- Pas de refonte de l'export Excel (le tableau Véhicule vide est accepté).
- Pas de changement à `_render_resource_card`, `save_report_from_state`, ni à la
  carte Météo.
