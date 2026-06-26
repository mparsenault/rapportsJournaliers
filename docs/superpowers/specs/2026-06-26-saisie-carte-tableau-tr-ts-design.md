# Saisie par employé — carte raffinée (tableau TR/TS aligné, cartes repliées)

Date : 2026-06-26
Fichier touché : `app.py` (fonction `_render_resource_card` et l'expander de la
boucle Saisie dans `view_day_entry`).

## Contexte

La saisie par employé (livrée dans
`2026-06-26-saisie-par-employe-equipement-tr-ts`) affiche une carte `st.expander`
par ressource. Retour d'usage : la saisie n'est pas intuitive. Trois frictions
identifiées :

1. **TR/TS verbeux** : chaque activité affiche deux `number_input` avec une
   étiquette répétée (« TR — 0125 », « TS — 0125 », « TR — 0016 »…), empilés.
2. **Trop de défilement** : chaque carte est ouverte (`expanded=True`), donc une
   équipe nombreuse produit une page très longue, sans vue d'ensemble.
3. **Libellés d'activité tronqués** : les puces du multiselect coupent le libellé
   (« 0125 - Fournitur… »), on ne sait plus de quelle activité il s'agit.

La friction « perte de la vue d'ensemble » n'a PAS été retenue : le modèle
carte-par-employé convient, il faut juste le resserrer.

## Objectif

Rendre la carte plus lisible sans toucher au modèle, à la persistance, ni aux
clés de widgets :

- Cartes **repliées par défaut**.
- Heures en **tableau aligné** : en-tête unique `Activité | TR | TS`, une ligne
  par activité avec le **libellé complet** et les champs TR/TS sans étiquette
  répétée.

## Modifications (`app.py`)

### 1. Expander replié

Dans la boucle Saisie de `view_day_entry`, l'expander de chaque ressource passe de
`expanded=True` à `expanded=False`. Le titre existant (« icône Nom — total h »)
reste la ligne scannable.

### 2. Tableau TR/TS dans `_render_resource_card`

Après le `st.multiselect` des activités, lorsque `sel_acts` est non vide :

- Une **ligne d'en-tête** rendue une seule fois via `st.columns(_HOURS_COLS)` où
  `_HOURS_COLS = [3, 1, 1]` : trois libellés discrets `Activité`, `TR`, `TS`
  (markdown/caption).
- **Pour chaque activité sélectionnée**, une ligne via `st.columns(_HOURS_COLS)`
  (mêmes poids → colonnes alignées) :
  - colonne 1 : le **libellé complet** de l'activité (`st.markdown`), non tronqué ;
  - colonne 2 : `st.number_input` TR, clé `tr_{jour}_{quart_name}_{name}_{act}`,
    `label="TR"`, `label_visibility="collapsed"` ;
  - colonne 3 : `st.number_input` TS, clé `ts_{jour}_{quart_name}_{name}_{act}`,
    `label="TS"`, `label_visibility="collapsed"`.

Les clés, le seed via `st.session_state.setdefault(...)`, la normalisation
`_norm_pair`, la reconstruction de `new_heures` et la suppression des paires nulles
restent **identiques** à l'implémentation actuelle — seule la présentation change
(en-tête unique + libellé complet en colonne au lieu d'étiquettes répétées par
champ ; colonnes `[3,1,1]` au lieu de `[1,1,3]`).

### 3. Reste de la carte

Équipement (pills + Hrs Éq.), Prime, Commentaire : inchangés.

## Hors périmètre (YAGNI)

- Pas de `st.data_editor` / grille tableur (écarté : tactile et test moins
  pratiques).
- Pas de changement au modèle, à la BD, ni à `save_report`/`load_report`.
- La troncature des puces du multiselect lui-même n'est pas corrigée (limitation
  native de Streamlit) ; le libellé complet apparaît désormais dans la colonne
  « Activité » du tableau, ce qui lève l'ambiguïté.

## Tests

- Les tests de carte existants (`test_day_hours_entry_updates_model`,
  `test_day_equip_codes_and_hours`, `test_day_prime_inline`,
  `test_day_comment_inline`, etc.) ciblent les widgets par **clé** (inchangées) et
  doivent passer sans modification. Note : sous AppTest, le contenu d'un
  `st.expander` reste dans l'arbre des éléments même replié (`expanded=False`
  n'affecte que l'affichage), donc l'accès par clé reste valable.
- Ajouter un test léger : après sélection d'une activité à l'étape Saisie, une
  en-tête de tableau « Activité » / « TR » / « TS » est présente dans le rendu
  (ex. recherche du texte d'en-tête dans `at.markdown`), et aucune étiquette
  « TR — » répétée ne subsiste.

## Critères de réussite

- Les cartes de ressources s'ouvrent **repliées**.
- Une activité sélectionnée affiche une ligne `Activité | TR | TS` alignée avec
  le libellé complet et deux champs sans étiquette « TR — code » répétée.
- Les heures saisies sont toujours écrites dans `heures[nom][activité] =
  {"TR", "TS"}` (clés et logique inchangées).
- La suite de tests passe (tests de carte existants + le nouveau test d'en-tête).
