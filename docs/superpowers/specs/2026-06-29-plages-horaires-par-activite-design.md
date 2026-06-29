# Plages horaires par activité

**Date :** 2026-06-29
**Fichiers :** `app.py` (`_render_resource_card`, `_norm_pair`, helpers de calcul), `reports.py` (schéma, `save_report`, `load_report`), `tests/`
**Branche :** suite de `feat/selecteur-employe-rail-recherche`.

## Problème

Aujourd'hui, pour un employé et une activité, on ne saisit qu'un total d'heures
réparti en TR (temps régulier) et TS (temps supplémentaire) — deux `number_input`
(`app.py:1052-1055`). On ne peut pas exprimer « X a travaillé de 10h à 12h sur
l'activité Y ». L'objectif : permettre une saisie par **plages horaires** (début →
fin), avec durée calculée, tout en gardant la saisie directe TR/TS.

## Solution retenue

**Choix du mode par activité**, défaut = saisie directe TR/TS (les plages sont
opt-in). En mode plage, l'utilisateur ajoute une ou plusieurs plages début→fin ;
chaque plage porte une bascule TR/TS ; les durées s'additionnent et alimentent les
totaux TR/TS qui restent la source de vérité pour l'export.

### Modèle de données

`quart["heures"][resource][activité]` passe de `{"TR", "TS"}` à :

```python
{
  "mode": "direct" | "plage",
  "ranges": [{"debut": "10:00", "fin": "12:00", "type": "TR"}, ...],  # vide en mode direct
  "TR": float,   # mode direct : saisi ; mode plage : dérivé (Σ durées TR)
  "TS": float,   # idem
}
```

- En **mode plage**, `TR`/`TS` sont recalculés à chaque édition à partir des
  `ranges` (toujours cohérents).
- En **mode direct**, `ranges == []` et `TR`/`TS` sont saisis à la main.
- **Rétrocompatibilité** : `_norm_pair` (`app.py:325-334`) est étendu pour accepter
  l'ancien format (`{"TR","TS"}` ou scalaire hérité) → `mode="direct"`, `ranges=[]`,
  et pour normaliser le nouveau format (clés/typage). Toujours renvoyer au minimum
  `{"TR","TS"}` pour ne pas casser les lecteurs existants (`_pair_total`,
  `_resource_total`, export, save_report).

### Fonctions de calcul (pures, testables)

- `_range_hours(debut: str, fin: str) -> float` : durée en heures décimales,
  `0.0` si `fin <= debut` ou format invalide. Pas de 15 min ⇒ multiples de 0.25.
- `_ranges_to_pair(ranges: list) -> dict` : `{"TR": Σ durées type TR, "TS": Σ durées type TS}`.

### UI — `_render_resource_card`

Le tableau compact actuel (Activité | TR | TS, `app.py:1039-1062`) est remplacé par
un **bloc par activité**. On extrait un helper `_render_activity_hours(jour,
quart_name, name, act, entry) -> dict` qui rend l'éditeur d'une activité et renvoie
l'entrée mise à jour (`mode`, `ranges`, `TR`, `TS`).

Par activité :
- Une **bascule de mode** via `st.radio` horizontal (représentable sous `AppTest`,
  contrairement à `st.pills`/`segmented_control`), clé
  `mode_{jour}_{quart_name}_{name}_{act}`, options « TR/TS direct » / « ⏱ Plage »,
  défaut « TR/TS direct ».
- **Mode plage** : pour chaque plage, une ligne `[st.time_input début] →
  [st.time_input fin] [bascule TR/TS] [durée affichée] [bouton ✕ retirer]`.
  `st.time_input` avec `step=timedelta(minutes=15)`. Un bouton « ＋ Ajouter une
  plage » (clé `addrange_{…}_{act}`) ajoute une plage par défaut (ex. 08:00→08:00,
  type TR) et `st.rerun()`. Sous-total affiché : `TR Σ · TS Σ`.
- **Mode direct** : les deux `number_input` actuels (pas 0.25, format `%.2f`).

L'écriture dans `quart["heures"][name][act]` suit la logique actuelle : on retire
l'entrée si total nul (`_pair_total == 0` et pas de plages), sinon on stocke
`{"mode","ranges","TR","TS"}`.

### Persistance — `reports.py`

- `report_hours` **inchangée** : continue de stocker les totaux TR/TS par
  (quart, resource, activité). Export et autres lecteurs non touchés.
- **Nouvelle table** `report_hour_ranges` créée dans `_DDL_STATEMENTS` (donc via
  `ensure_schema`) :
  ```sql
  create table if not exists report_hour_ranges (
      quart_id       integer references report_quarts(id) on delete cascade,
      resource_name  text not null,
      activity_label text not null,
      seq            integer not null,
      start_min      integer not null,   -- minutes depuis minuit
      end_min        integer not null,
      kind           text not null       -- 'TR' | 'TS'
  )
  ```
- `save_report` (`reports.py:279-289`) : après l'insertion dans `report_hours`,
  insérer chaque plage de `entry["ranges"]` dans `report_hour_ranges`
  (`start_min`/`end_min` = conversion `"HH:MM"`→minutes ; `seq` = index).
- `load_report` (`reports.py:350-357`) : après avoir construit `heures` depuis
  `report_hours`, lire `report_hour_ranges` pour le quart, regrouper par
  (resource, activité), reconstruire `ranges` (`minutes`→`"HH:MM"`) triées par
  `seq`, et fixer `mode = "plage"` si l'activité a des plages, sinon `"direct"`.

### Export Excel

Aucun changement : `_legacy_day`/`build_df` lisent `_pair_total` / les totaux TR/TS.
Les plages ne sont pas exportées (hors périmètre).

### Validation

- Par plage : `fin > début`, sinon durée 0 et avertissement discret (`st.caption`
  ou icône) sur la ligne. N'empêche pas l'enregistrement.
- **Hors périmètre** : détection de chevauchement entre plages, plages à cheval sur
  minuit (travail de jour).

## Tests

- **Unitaires** : `_range_hours` (cas normal, fin<=début→0, format invalide→0,
  quart d'heure) ; `_ranges_to_pair` (somme par type) ; `_norm_pair` rétrocompat
  (ancien `{"TR","TS"}`, scalaire hérité, nouveau format).
- **UI** (`AppTest`) : en mode plage, présence des `st.time_input` (`at.time_input`)
  et du bouton « ＋ Ajouter une plage » ; un clic ajoute une plage ; la bascule de
  mode fait apparaître/disparaître les `time_input` vs `number_input` ; le total
  TR/TS de l'activité reflète les plages.
- **Persistance** : test d'aller-retour `save_report` → `load_report` (BD SQLite de
  test si dispo dans la suite, sinon test ciblé) conservant les plages et le mode.

## Hors périmètre

- Pas de changement à l'export Excel.
- Pas de chevauchement / minuit / fuseaux.
- Pas de migration des données historiques (anciens rapports restent en mode direct).
