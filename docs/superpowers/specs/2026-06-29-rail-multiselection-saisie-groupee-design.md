# Rail multisélection — saisie groupée des heures

Date : 2026-06-29

## Problème

La saisie groupée actuelle passe par une section « Appliquer aussi à… » dans la
fiche d'un travailleur : on saisit une fiche, puis on copie ses activités/heures
vers d'autres. En pratique il est plus naturel de **cocher plusieurs ressources
dans le rail de gauche** puis de saisir une seule fois les activités + heures
pour tout le groupe.

Ce design remplace la section « Appliquer aussi à… » par une **multisélection
dans le rail**.

## Décisions de cadrage

- **Rail = bascules de sélection** : cliquer une ressource la coche/décoche ; les
  ressources cochées restent surlignées. La sélection est un ensemble qui
  persiste pendant la recherche.
- **Panneau de droite adaptatif** selon le nombre de cochés :
  - **0** → message d'invite « Sélectionnez une ou plusieurs ressources ».
  - **1** → fiche individuelle complète actuelle, inchangée (activités, heures,
    équipement, prime, commentaire).
  - **2+** → fiche de **groupe vierge** : multiselect d'activités + saisie des
    heures (TR/TS direct ou plages) uniquement, puis bouton « Appliquer à N
    travailleurs ».
- **Fiche de groupe au départ : vierge** (on saisit du neuf pour tout le monde ;
  pas de pré-remplissage).
- **Fusion** : les activités saisies en groupe s'ajoutent/mettent à jour
  par-dessus l'existant de chaque destinataire ; les activités déjà présentes
  chez un destinataire et absentes de la saisie de groupe sont conservées.
- **Champs copiés** : activités + heures uniquement. PAS équipement, prime,
  commentaire (restent individuels).
- **Après « Appliquer »** : on **vide la sélection** (retour à l'état 0) et on
  réinitialise la fiche de groupe.
- La section « Appliquer aussi à… » et son helper UI sont **retirés**.

## Modèle de données (rappel)

```python
quart["heures"][nom][activité] = {
    "mode": "direct" | "plage",
    "TR": float, "TS": float,
    "ranges": [{"debut": "HH:MM", "fin": "HH:MM", "type": "TR"|"TS"}, ...],
}
```

## Architecture

### 1. Fusion par dictionnaire (logique de modèle, testable)

Remplace la fonction nom-à-nom par une fusion à partir d'un dict d'heures :

```python
def _apply_hours_dict_to_resources(quart, hours, dest_names):
    """Fusionne le dict `hours` ({activité: entrée}) dans chaque destinataire.

    Pour chaque activité de `hours`, écrit une copie indépendante dans
    quart["heures"][dest][activité]. Les activités préexistantes du destinataire
    absentes de `hours` sont conservées ; les communes sont écrasées.
    N'agit pas si `hours` est vide. Renvoie la liste des destinataires
    effectivement modifiés (sans doublon).
    """
```

- `_copy_entry(raw)` (déjà existant) reste la brique de copie profonde.
- L'ancienne `_apply_hours_to_resources(quart, source_name, dest_names)` est
  **retirée** (plus aucun appelant après le retrait de la section « Appliquer
  aussi à… »).

### 2. Rail multisélection (UI, dans `view_day_entry`)

- Clé de sélection : `sel_set_{jour}_{quart_name}` → ensemble (stocké en liste
  ordonnée) de noms de ressources cochées. Initialisé vide.
- Chaque entrée du rail reste un `st.button` (testable sous AppTest). Le bouton
  est `type="primary"` si la ressource est cochée. Au clic : bascule la présence
  dans l'ensemble, puis `st.rerun()`.
- La recherche filtre l'affichage ; elle ne modifie jamais l'ensemble de
  sélection. Les compteurs « X résultat(s) · N sur M saisies » restent.

### 3. Panneau de droite adaptatif

```
sel = [n for n in labels if n in selection_set]   # ordre du rail
if len(sel) == 0:   st.info("Sélectionnez une ou plusieurs ressources…")
elif len(sel) == 1: <fiche individuelle existante via _render_resource_card>
else:               <fiche de groupe>
```

#### Fiche de groupe (2+ sélectionnés)

- En-tête listant les noms sélectionnés (ex. « 3 travailleurs : Alice, Bob, … »).
- `multiselect` « Activités » (clé `grp_acts_{jour}_{quart_name}`), options =
  `all_activities`. Démarre vide.
- Pour chaque activité choisie, éditeur d'heures via `_render_activity_hours`
  avec un nom synthétique de groupe (`__groupe__`) → base de clés distincte
  `{jour}_{quart_name}___groupe___{act}`, donc aucune collision avec les fiches
  individuelles. Entrée initiale vide (`{}`).
- On agrège les entrées non vides en `grp_heures = {act: entry}`.
- Bouton « Appliquer à N travailleur(s) » : désactivé si `grp_heures` est vide.
- Au clic :
  1. `changed = _apply_hours_dict_to_resources(quart, grp_heures, sel)` ;
  2. `_purge_resource_hour_keys(jour, quart_name, changed)` (réamorçage des
     fiches individuelles des destinataires) ;
  3. poser les drapeaux différés de réinitialisation : vidage de la sélection
     (`sel_set_…` → ensemble vide) et purge des clés de la fiche de groupe ;
  4. `_mark_dirty()` ; message de succès ; `st.rerun()`.

#### Réinitialisation de la fiche de groupe (clés widget)

Comme pour le multiselect précédent et le champ d'ajout manuel, on ne peut pas
modifier une clé de widget après instanciation dans le même run. On utilise donc
le **pattern différé** :

- Au clic « Appliquer », poser `st.session_state["clear_grp_{jour}_{quart_name}"]
  = True` (et vider l'ensemble de sélection, qui n'est pas une clé de widget).
- **Avant** d'instancier les widgets de la fiche de groupe au run suivant,
  consommer ce drapeau et supprimer : `grp_acts_{jour}_{quart_name}` et toutes
  les clés de la famille de plages/heures du nom synthétique `__groupe__`
  (préfixes `acts_/mode_/tr_/ts_/ranges_/rangeseq_/rg_*` contenant le segment
  `{jour}_{quart_name}___groupe__`). Réutiliser `_purge_resource_hour_keys(jour,
  quart_name, ["__groupe__"])` couvre la famille d'heures ; supprimer en plus
  `grp_acts_…` explicitement.

## Cas limites

- Sélection vide → invite, pas de fiche.
- Exactement 1 sélectionné → fiche individuelle inchangée.
- Fiche de groupe sans aucune heure saisie → bouton désactivé.
- Destinataire sans heures préalables → reçoit la copie.
- Destinataire avec activité hors saisie de groupe → conservée ; activité
  commune → écrasée.
- Mode plage en groupe → `ranges` copiés en profondeur et indépendants par
  destinataire.
- Noms de ressources où l'un est préfixe de l'autre → la purge ancrée existante
  (`k == p+seg or k.startswith(p+seg+"_")`) évite la collision.

## Tests

`tests/test_model.py` (adapter les tests de l'ancienne fonction) :
- `_apply_hours_dict_to_resources` : dict → destinataire vide (direct) ;
  indépendance des plages ; fusion sans effacement ; dict vide → no-op ;
  dédoublonnage des destinataires.

`tests/test_ui.py` :
- Cocher 2 ressources dans le rail → la fiche de groupe apparaît (multiselect
  « Activités » présent).
- Saisir une activité + heures en groupe, cliquer « Appliquer » → les heures
  sont écrites sur les 2 ressources ; aucune exception ; la sélection est vidée
  (retour à l'invite) ; le multiselect d'activités de groupe est vidé.
- Cocher 1 ressource → fiche individuelle (présence des champs équipement/prime).
- L'ancienne section « Appliquer aussi à… » n'est plus rendue.

## Hors périmètre

- Synchronisation continue / groupes persistants.
- Copie de l'équipement, prime, commentaire en groupe.
- Édition simultanée de valeurs différentes par personne dans la fiche de groupe
  (la fiche de groupe écrit la même chose à tous).
