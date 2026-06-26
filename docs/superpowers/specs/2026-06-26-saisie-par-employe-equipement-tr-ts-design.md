# Saisie par employé : activités TR/TS et équipement par employé

Date : 2026-06-26
Fichiers touchés : `app.py` (étape Configuration et Saisie de `view_day_entry`,
modèle `_empty_quart`, prépa export `_legacy_day`), `reports.py` (schéma,
`save_report`, `load_report`), tests.

## Contexte

Aujourd'hui la saisie d'un quart se fait en deux étapes (`view_day_entry`) :

- **Configuration** : on choisit les **activités du quart** (liste globale,
  `quart["activites"]`), la météo, le **personnel**, les **équipements
  autonomes**.
- **Saisie des heures** : une grille AgGrid en **matrice** ressources × activités.
  Chaque ressource (personnel + équipement) a une ligne ; chaque activité du quart
  est une colonne **commune à tous**. Une seule valeur d'heures par cellule.
  `quart["heures"] = {ressource: {activité: heures}}`. Prime et commentaire par
  ressource.

Deux limites motivent ce changement :

1. **Activités communes** : tous les employés héritent de toutes les activités du
   quart, alors que chacun ne travaille pas sur toutes → grande matrice avec
   beaucoup de cases vides.
2. **Équipement détaché** : l'équipement est une ressource autonome (sa propre
   ligne), alors que le formulaire papier l'associe à l'employé (colonnes « Hrs Éq. »
   et « Code Éq. » sur la ligne du travailleur).
3. **Pas de TR/TS** : le formulaire papier distingue les heures **T.R.** (temps
   régulier) et **T.S.** (temps supplémentaire) ; l'app ne stocke qu'une valeur.

## Objectif

Passer à un modèle **entièrement par employé** à l'étape Saisie :

- Chaque employé choisit **ses** activités (parmi toutes les activités du projet) et
  saisit, pour chacune, **TR** et **TS**.
- Chaque employé porte des **codes d'équipement** (liste fixe, plusieurs possibles)
  et un **total d'heures équipement** (« Hrs Éq. »).
- On **conserve** les équipements autonomes (décision « garder les deux »).

La grille matricielle AgGrid est remplacée par **une carte par ressource**.

## A. Modèle de données

### Constante (dans `app.py`)

```python
EQUIP_CODES = [
    ("C", "Camion"), ("N", "Nacelle"), ("É", "Éch. Hyd."),
    ("D", "Détecteur"), ("G", "Grue"), ("BT", "Chariot élév."),
]
```

### État du quart (`_empty_quart`)

`heures` passe d'une valeur unique à un couple TR/TS par activité, et on ajoute
l'équipement par employé :

```python
"heures": {},        # {employé: {activité: {"TR": 8.0, "TS": 2.0}}}
"equip_codes": {},   # {employé: ["C", "N"]}
"equip_hours": {},   # {employé: 10.0}
```

`prime` et `commentaire_ligne` restent par ressource. `quart["activites"]`
(liste globale) **n'est plus une entrée de configuration** : elle est dérivée de
l'union des activités présentes dans `heures` quand on en a besoin (export).
`quart["autres"]` reste réservé/vide (aucune UI active aujourd'hui).

Les activités sélectionnées par un employé sont l'ensemble des clés de
`heures[employé]`. La sélection en cours d'édition vit dans l'état du widget
multiselect ; à l'enregistrement, une activité dont TR et TS valent 0 est retirée
(même logique « on drop le zéro » qu'aujourd'hui).

### Base de données (`reports.py`)

Migrations idempotentes ajoutées à `_DDL_STATEMENTS` (jouées par `ensure_schema()`
au démarrage) :

```sql
-- report_hours : ajouter le temps supplémentaire ; la colonne hours existante
-- devient le temps régulier (TR). Rétro-compatible : les données existantes
-- comptent comme du TR, hours_ts = 0.
alter table report_hours add column if not exists hours_ts numeric not null default 0;

-- report_lines : équipement rattaché à l'employé
alter table report_lines add column if not exists equip_hours numeric;
alter table report_lines add column if not exists equip_codes text[] not null default '{}';
```

`report_hours` reste `(quart_id, resource_name, activity_label, hours, hours_ts)` où
**`hours` = TR** et **`hours_ts` = TS**. Le grain (1 ligne par employé × activité)
supporte déjà la sélection éparse par employé — aucun autre changement de structure.

## B. Étape Configuration (ce qui change)

- ❌ **Retirer** la carte « 🏗️ Activités du quart » (`acts_box`, env. lignes
  1090-1109) : les activités ne se choisissent plus en configuration.
- ✅ **Conserver** : météo, « 👷 Personnel présent », « 🚜 Équipements sur place »
  (équipements autonomes).
- **Prérequis** pour passer à la saisie (env. lignes 1257-1263) : retirer la
  condition « une activité » ; ne garder que **personnel + température (AM ou PM)**.
- Mettre à jour les libellés résiduels mentionnant les activités en config.

## C. Étape Saisie — remplace la grille AgGrid

La matrice ressources × activités (AgGrid, env. lignes 1287-1340+) est remplacée par
**une carte par ressource**, dans l'ordre du roster (`_roster` : personnel puis
équipements autonomes). Chaque carte est idéalement un `st.expander` dont le titre
affiche le nom de la ressource et son total d'heures. Le champ de **recherche de
ressource** existant est conservé pour filtrer les cartes affichées.

### Carte d'un employé (👷)

- **Activités** : `st.multiselect` cherchant dans **toutes les activités du projet**
  (`data_source.get_activities(id_project)`, recherche type-to-filter), pré-amorcé
  avec les activités déjà saisies (clés de `heures[employé]`).
- Pour **chaque activité sélectionnée** : deux champs numériques côte à côte
  **TR** et **TS** (heures).
- **Équipement** : `st.pills` en mode multi sur les codes fixes `EQUIP_CODES`
  (affichage « C — Camion », valeur = le code) + un champ numérique **« Hrs Éq. »**
  (total unique).
- **Prime ($)** : champ numérique.
- **Commentaire** : champ texte.
- **Total** affiché : Σ (TR + TS) sur les activités de l'employé.

### Carte d'un équipement autonome (🚜)

- Mêmes **activités + TR/TS**, **prime** et **commentaire**.
- **Pas** de codes d'équipement ni de « Hrs Éq. » (réservés aux employés).

### Réécriture de l'état

Chaque modification de widget réécrit l'état du quart (`heures`, `equip_codes`,
`equip_hours`, `prime`, `commentaire_ligne`) pour la ressource concernée et marque
« non enregistré » (`_mark_dirty`), comme le fait aujourd'hui `_apply_hours_grid`.
À l'écriture, on retire les activités dont TR = TS = 0, les primes ≤ 0, les
commentaires vides, les `equip_hours` nuls et les `equip_codes` vides.

### Fonctions utilitaires impactées

- `_quart_columns` (colonnes globales de la grille) et `_build_hours_df` /
  `_apply_hours_grid` (AgGrid) : supprimés ou remplacés par les helpers par carte.
- `_resource_total` / `_quart_total` / `_day_total` : recalculés sur la base
  `{activité: {"TR","TS"}}` (somme TR + TS).

## D. Persistance (`reports.py`)

### `save_report`

- `report_hours` : pour chaque employé × activité ayant TR ou TS > 0, insérer
  `(quart_id, resource_name, activity_label, hours=TR, hours_ts=TS)`.
- `report_lines` : insérer une ligne dès qu'une ressource a une **prime**, un
  **commentaire**, des **equip_hours** ou des **equip_codes** ; écrire `equip_hours`
  et `equip_codes` (les équipements autonomes n'en ont pas → valeurs nulles/vide).
  Étendre l'ensemble itéré : `set(prime) | set(commentaire) | set(equip_hours) |
  set(equip_codes)`.
- `report_quarts.activites` : écrire l'**union** des activités de tous les employés
  (pour information / export) ; non utilisé pour réhydrater.

### `load_report`

- `report_hours` → `heures[resource][activity] = {"TR": hours, "TS": hours_ts}`.
- `report_lines` → `prime`, `commentaire_ligne`, plus
  `equip_hours[resource]` et `equip_codes[resource]` (liste).
- La sélection d'activités par employé se réamorce depuis les clés de `heures`.

## E. Export, tests, migration

- `_legacy_day` : dériver l'ensemble des activités depuis l'**union des `heures`**
  (au lieu de `quart["activites"]`) ; mapper TR/TS vers les colonnes T.R./T.S. et
  ajouter codes / Hrs Éq. par employé aux enregistrements `pers`. L'export reste un
  stub (`build_workbook`/`_build_synthese` n'écrivent qu'un titre) — on prépare les
  données, on ne câble pas le mapping complet.
- Migration `report_hours`/`report_lines` jouée par `ensure_schema()` au démarrage,
  idempotente.
- Tests :
  - `tests/test_reports.py` (logique pure) : inchangé pour les gardes ; pas de test
    BD (validé e2e contre Neon).
  - `tests/test_ui.py` / `tests/test_model.py` : adapter au nouveau modèle (TR/TS,
    `equip_codes`/`equip_hours`, absence de la carte Activités en config). Ajouter la
    couverture des helpers de réécriture/total par carte.

## Hors périmètre (YAGNI)

- Pas de mapping Excel complet (l'export reste un stub).
- Pas de « copier les activités d'un autre employé » / « appliquer à tous » (peut
  être ajouté plus tard si la saisie répétitive devient pénible).
- Pas de pool d'activités au niveau du quart : chaque employé choisit directement
  dans toutes les activités du projet (décision validée).
- Pas de prime/commentaire par activité (restent par ressource, comme le formulaire).

## Critères de réussite

- L'étape Configuration n'a plus de carte « Activités du quart » ; on peut passer à
  la saisie avec personnel + météo seulement.
- L'étape Saisie n'utilise plus AgGrid : une carte par ressource, activités choisies
  par employé, TR et TS par activité, codes + Hrs Éq. par employé.
- Un employé peut avoir des activités différentes d'un autre.
- Enregistrer puis recharger un rapport restitue fidèlement TR/TS, codes et Hrs Éq.
- La migration tourne sans erreur sur une base existante (données existantes vues
  comme du TR, `hours_ts = 0`).
- Les tests passent (mis à jour pour le nouveau modèle).
