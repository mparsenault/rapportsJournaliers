# Design — Retrait du système de données de référence

Date : 2026-06-18
Statut : approuvé pour planification

## Objectif

Les « données de référence » (`refdata.json` → `st.session_state.ref`) maintenaient
manuellement les listes **personnel**, **véhicules** et **autres projets**, éditées
via la page « 📚 Références ». Depuis l'arrivée des données BD (employés suggérés par
projet), ce système est obsolète. On le **retire entièrement** et on remplace les
options par de la **saisie libre** (multiselects `accept_new_options`).

Décisions confirmées :
- Retirer **tout** le système refdata (fichier + chargement + sauvegarde + page).
- **Personnel** : employés suggérés du projet (BD) **+ ajout libre**.
- **Équipements** : **saisie libre**.
- **« Autres »** (saisie du jour) : **retiré**.

## Portée

Dans la portée :
- Suppression de `refdata.json` et de toute la logique refdata dans `app.py`.
- Suppression de la page Références (`view_reference`), du bouton du tableau de
  bord et de la route.
- Remplacement des multiselects Personnel / Équipements par des multiselects
  `accept_new_options=True`.
- Retrait du multiselect « Autres » de la saisie du jour.
- Mise à jour des tests + README.

Hors portée (inchangé) :
- Météo, projets/activités/`project_staff` (BD), export Excel.
- Le pré-remplissage d'équipe par projet (`staff_prefilled_for`).
- Le modèle `day["autres"]` reste présent (toujours `[]`) — l'export et
  `_day_columns` gèrent déjà le cas vide ; aucune modification de l'export.

## Suppressions (`app.py` + fichier)

- Fichier `refdata.json` : supprimé du dépôt.
- `REFDATA_PATH`, `_load_refdata_file`, `save_refdata`.
- L'init `st.session_state.ref = _load_refdata_file()` dans `init_state`.
- La fonction `view_reference`.
- Le bouton « 📚 Références » du tableau de bord et la route
  `elif st.session_state.view == "reference": view_reference()`.
- `import json` est **conservé** (utilisé par la météo `_fetch_day_weather`).

## Saisie du roster

Vue config (« ⚙️ Équipe & Équipements ») :

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

- **Personnel** : options = employés suggérés du projet ∪ sélection courante ;
  `accept_new_options` permet d'ajouter quelqu'un en tapant. `default ⊆ options`
  toujours respecté (la sélection courante est incluse dans les options).
- **Équipements** : pas de source externe ; options = sélection courante ;
  saisie libre via `accept_new_options`.

## Saisie du jour (`view_day_entry`)

- Retirer la ligne `day["autres"] = st.multiselect("Autres", ...)`. `day["autres"]`
  conserve sa valeur initiale `[]` (via `_empty_day`). `_day_columns` =
  `["960"] + activites + autres` continue de fonctionner (autres vide).

## Tableau de bord

- Retirer le bouton « 📚 Références ». Les boutons du bas passent de 3 à 2
  colonnes : **⚙️ Équipe & Équipements** et **📥 EXPORT EXCEL** (tous deux
  `disabled=not projet_choisi`, inchangé).

## Gestion des erreurs / cas limites

- Aucun projet sélectionné → `get_project_staff(None)` = `[]` → options Personnel
  vides, mais `accept_new_options` permet quand même d'ajouter.
- `default` du multiselect Personnel toujours inclus dans `options` (pas de
  plantage Streamlit).

## Tests

- **Supprimer** `test_navigation_to_reference` et `test_reference_has_no_activities_tab`
  (la page Références n'existe plus).
- **Adapter** `test_config_roster_multiselects_present` (les multiselects
  Personnel/Équipements existent toujours dans la vue config) et
  `test_setting_personnel_updates_config` (Personnel sans projet a des options
  vides ; tester via un projet avec staff suggéré monkeypatché, ou via l'ajout
  d'une valeur).
- Vérifier qu'aucun test ne référence plus `ref`, `save_refdata`,
  `view_reference`, ni le multiselect « Autres ».
- Les tests de saisie d'heures (`test_day_hours_*`) ne référencent pas « Autres »
  → inchangés.

## Documentation

- `README.md` : retirer la mention de `refdata.json` comme source des listes ;
  indiquer que personnel vient des suggestions projet (BD) + saisie libre, et
  équipements en saisie libre.

## Critères de succès

- Plus de page Références ni de fichier `refdata.json`.
- Personnel : suggéré depuis le projet + ajout libre ; Équipements : saisie
  libre ; « Autres » absent de la saisie.
- Aucune régression : saisie d'heures, export, projets/activités/staff.

## Risques / compromis

- Saisie libre = pas de validation/normalisation des noms (fautes de frappe
  possibles) — accepté, contrepartie de l'absence de liste à maintenir.
- `day["autres"]` reste dans le modèle (toujours vide) plutôt que d'être retiré
  partout — choix volontaire pour ne pas toucher à l'export.
