# Saisie groupée — appliquer activités + heures à plusieurs travailleurs

Date : 2026-06-29

## Problème

Dans la saisie journalière (`view_day_entry`), les heures sont saisies une
ressource à la fois via un maître-détail (rail à gauche, fiche à droite). Quand
plusieurs travailleurs ont fait exactement les mêmes activités aux mêmes heures
ou plages horaires, il faut tout ressaisir manuellement pour chacun. On veut
pouvoir appliquer les activités + heures de la fiche courante à plusieurs autres
travailleurs d'un coup.

## Décisions de cadrage

- **Déclencheur** : multisélection « Appliquer aussi à… » en tête de la fiche
  courante (option 3).
- **Sémantique** : copie ponctuelle. Une fois copiés, chaque travailleur reste
  indépendant et éditable séparément (pas de synchronisation continue).
- **Champs copiés** : uniquement les **activités + heures** (TR/TS direct ou
  plages). PAS l'équipement, PAS la prime, PAS le commentaire de ligne.
- **Conflit** : fusion. Les activités copiées s'ajoutent/mettent à jour
  par-dessus celles du destinataire ; les activités déjà présentes chez le
  destinataire et absentes de la source sont conservées ; les activités communes
  sont écrasées par la valeur source.
- **Déclenchement concret** : bouton explicite « Appliquer à N travailleur(s) ».
  Rien ne change tant qu'il n'est pas cliqué.
- **Destinataires** : personnel (`type == "P"`) uniquement, hors travailleur
  courant.

## Modèle de données (rappel)

```python
quart["heures"][nom_ressource][activité] = {
    "mode": "direct" | "plage",
    "TR": float, "TS": float,
    "ranges": [{"debut": "HH:MM", "fin": "HH:MM", "type": "TR"|"TS"}, ...],
}
```

La source de la copie est `quart["heures"][source_name]` (dict
`{activité: entrée}`).

## Architecture

### 1. Fonction pure de fusion (logique de modèle, testable)

```python
def _apply_hours_to_resources(quart, source_name, dest_names):
    """Copie (fusion) les heures de `source_name` vers chaque destinataire.

    Pour chaque activité de la source, écrit une copie profonde dans
    quart["heures"][dest][activité]. Les activités existantes du destinataire
    absentes de la source sont conservées ; les communes sont écrasées.
    Renvoie la liste des destinataires effectivement modifiés.
    """
```

- Placée près des autres helpers de modèle dans `app.py`.
- N'agit que si la source contient au moins une activité.
- Utilise une copie profonde (`copy.deepcopy` ou reconstruction) pour que les
  `ranges` ne soient pas partagés par référence entre travailleurs.
- Testée dans `tests/test_model.py` sans dépendance à Streamlit.

### 2. Couche UI (dans `view_day_entry`, panneau de droite)

Sous le titre du travailleur courant, dans une section encadrée :

- `multiselect` « Appliquer aussi à… » dont les options sont les noms du
  personnel du roster (`_roster(quart)` filtré sur `type == "P"`), moins le
  travailleur courant.
- Bouton « Appliquer à N travailleur(s) » :
  - désactivé si aucun destinataire coché **ou** si la fiche courante n'a aucune
    heure (`quart["heures"].get(source)` vide) ;
  - dans ce dernier cas, afficher une caption d'aide
    (« Saisissez d'abord des heures pour les copier »).
- Au clic :
  1. appeler `_apply_hours_to_resources(quart, source, dests)` ;
  2. **purger les clés `session_state` des widgets d'heures de chaque
     destinataire** pour forcer leur réamorçage depuis le modèle au prochain
     rerun (sinon l'ancien état d'affichage masque les données copiées). Clés
     concernées, préfixées par `{jour}_{quart_name}_{dest}` :
     `acts_…`, et pour chaque activité `mode_…`, `tr_…`, `ts_…`, et les clés de
     plage `ranges_…`, `rangeseq_…`, `rg_deb_…`, `rg_fin_…`, `rg_knd_…` ;
  3. `_mark_dirty()` ;
  4. message de succès listant les destinataires ;
  5. `st.rerun()`.

#### Purge des clés widget

La purge doit couvrir toutes les clés dont le préfixe correspond au destinataire
pour le jour/quart courant. Approche robuste : balayer `st.session_state` et
supprimer les clés contenant le segment `{jour}_{quart_name}_{dest}` parmi les
familles de préfixes ci-dessus. Cela évite d'avoir à recalculer la liste exacte
des activités/identifiants de plage.

## Cas limites

- Fiche courante vide → bouton désactivé, pas d'action.
- Destinataire identique au courant → exclu de la liste d'options.
- Destinataire sans heures préalables → reçoit simplement la copie.
- Mode plage → les `ranges` sont copiés en profondeur ; les clés de plage du
  destinataire sont purgées pour réamorçage.
- Aucune ressource personnel autre que le courant → multiselect vide, bouton
  désactivé (ou section masquée).

## Tests

`tests/test_model.py` :

- copie vers un destinataire vide : activités + heures identiques (direct).
- copie en mode plage : `ranges` copiés et indépendants (mutation de la source
  après copie ne modifie pas le destinataire).
- fusion : destinataire avec une activité hors source → conservée ; activité
  commune → écrasée par la source.
- source vide → aucun destinataire modifié, renvoie liste vide.

## Hors périmètre

- Synchronisation continue / groupes persistants.
- Copie de l'équipement, de la prime, du commentaire.
- Copie inter-quarts ou inter-jours (la copie « jour précédent » existe déjà).
