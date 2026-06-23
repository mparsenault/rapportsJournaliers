# Design — Saisie par quart (chaque quart = un mini-rapport dans la journée)

Date : 2026-06-22
Statut : approuvé pour planification

> Remplace le design `2026-06-22-quart-travail-par-jour-design.md` (sélecteur de
> quart **unique** par jour). Ce besoin-là était insuffisant : il faut pouvoir
> saisir des **heures distinctes pour chaque quart de chaque jour**, et plus
> largement gérer chaque quart comme un mini-rapport autonome.

## Objectif

Permettre, dans une journée, de gérer 1 à 3 **quarts** (Jour < Soir < Nuit),
chacun avec ses propres équipe, équipements, activités, météo, heures, primes,
commentaires, note et responsable. Une journée démarre avec le seul quart
« Jour » ; l'utilisateur ajoute Soir/Nuit au besoin.

## Portée

Dans la portée :
- Modèle d'état : un jour contient des quarts ; les champs aujourd'hui au niveau
  jour/semaine passent **par quart**.
- UI `view_day_entry` : sélecteur de quart + ajout/retrait ; les onglets
  Configuration / Saisie sont branchés sur le quart courant.
- Persistance : nouveau grain (jour → quarts → heures/lignes/ressources) +
  migration non destructive des données déjà enregistrées.
- Tableau de bord : total agrégé sur les quarts + indicateur des quarts présents.
- Export Excel : un bloc par quart.
- Tests UI (AppTest) ; persistance e2e/manuelle.

Hors portée (inchangé) :
- Projets / activités / personnel (snapshot `data_source`, lecture seule).
- Géolocalisation / récupération météo (réutilisée telle quelle, mais par quart).

Remplacé / retiré :
- Le sélecteur de quart **unique** par jour (radio `st.radio`, `day["quart"]`).
- La colonne `report_days.quart` et les champs semaine `reports.quart` /
  `reports.responsable`.
- Le `config` au niveau semaine (personnel/équipements/responsable/quart).

## Modèle conceptuel

- **Jour** : conteneur, identifié par sa date. Contient 1..3 quarts.
- **Quart** : un parmi `["Jour", "Soir", "Nuit"]`, ordonné (Jour < Soir < Nuit),
  unique dans le jour. C'est un mini-rapport autonome.
- Un jour a **toujours au moins un quart** (par défaut « Jour »). On ne peut pas
  retirer le dernier quart.

## État (`st.session_state`)

```
jours[nom_jour] = {
    "date": date,
    "quarts": { "Jour": <quart>, "Soir": <quart>, ... },   # sous-ensemble ordonné
}

<quart> = {
    "responsable": "", "activites": [], "autres": [],
    "personnel": [], "equipements": [],
    "temp_am": None, "temp_pm": None, "conditions": [],
    "heures": {}, "prime": {}, "commentaire_ligne": {},
    "description": "",
}
```

- Le quart actif dans l'UI est stocké en `st.session_state` par jour
  (ex. `active_quart_{jour}`), pas dans le modèle de données.
- Le `config` semaine disparaît. La suggestion de personnel projet
  (`data_source.get_project_staff`) sert d'**amorce** à la création d'un quart,
  pas de stockage semaine.

## UI — `view_day_entry`

Sous la carte de date (navigation jour précédent/suivant inchangée) :

- **Rangée de quarts** : un bouton par quart actif du jour (`Jour`, `Soir`, …)
  + un contrôle **« ➕ Ajouter un quart »**. Le quart sélectionné est mis en
  évidence. Sélection unique → définit le quart courant.
- **➕ Ajouter** : propose les quarts restants (parmi Jour/Soir/Nuit non encore
  présents, dans l'ordre). À la création, option **« copier l'équipe + activités
  depuis [quart existant] »** (défaut : le 1ᵉʳ quart du jour) pour éviter la
  re-saisie. Les heures/primes/commentaires ne sont **pas** copiés (distincts par
  quart).
- **Retirer un quart** : action par quart ; si le quart contient des heures,
  demander confirmation. Interdit de retirer le dernier quart restant.
- **Onglets Configuration / Saisie des heures** : structure interne inchangée,
  mais lit/écrit le **quart courant** (`jours[jour]["quarts"][quart_courant]`) au
  lieu du jour. Les clés de widgets incluent le quart
  (ex. `h_{jour}_{quart}_{name}_{activite}`, `acts_{jour}_{quart}`,
  `{jour}_{quart}_temp_am`, etc.) pour isoler les quarts.

## Persistance (`reports.py`) — nouveau grain

```
report_days   (id, report_id, day_date,
               unique(report_id, day_date))                 -- conteneur jour

report_quarts (id, day_id references report_days on delete cascade,
               quart text, ordinal int, responsable text, note text,
               temp_am numeric, temp_pm numeric,
               conditions text[], activites text[], autres text[],
               unique(day_id, quart))                        -- un mini-rapport

report_quart_resources (quart_id references report_quarts on delete cascade,
               name text, kind char(1) check (kind in ('P','E')),
               primary key(quart_id, name))                  -- équipe par quart

report_hours  (quart_id references report_quarts on delete cascade,
               resource_name text, activity_label text, hours numeric,
               primary key(quart_id, resource_name, activity_label))

report_lines  (quart_id references report_quarts on delete cascade,
               resource_name text, prime numeric, commentaire text,
               primary key(quart_id, resource_name))
```

- `report_hours` / `report_lines` sont **repointés** de `day_id` vers `quart_id`.
- `report_resources` (équipe au niveau semaine) est remplacé par
  `report_quart_resources`.
- On retire `report_days.quart`, `reports.quart`, `reports.responsable`.
- `save_report` : upsert en-tête, puis suppression/réinsertion complète des
  enfants (jours → quarts → resources/hours/lines), dans une transaction unique
  (même stratégie qu'aujourd'hui, un niveau plus profond).
- `load_report` : reconstruit `jours[...]["quarts"][...]`.

### Migration non destructive

Les types Postgres et le repointage de FK ne sont pas couverts par
`create table if not exists`. La migration (idempotente, exécutée dans
`ensure_schema`) :
1. crée `report_quarts` et `report_quart_resources` si absentes ;
2. si d'anciennes données existent (présence de `report_days.quart` ou de
   `report_hours.day_id`), replie chaque `report_days` existant dans un
   `report_quarts` « Jour » (ordinal 0), y rattache les `report_hours` /
   `report_lines` / `report_resources` correspondants, puis bascule les FK ;
3. supprime les colonnes/tables obsolètes une fois la bascule faite.

Le détail SQL exact (ordre des `alter`/backfill) est défini dans le plan
d'implémentation. Principe : aucune heure saisie n'est perdue.

## Tableau de bord (`view_dashboard`)

- Total de la carte de jour = **somme des heures sur tous les quarts** du jour.
- Petit indicateur des quarts présents ayant des heures (ex. « Jour · Soir »).
- Le surlignage « jour rempli » se base sur le total agrégé.

## Export Excel

Chaque quart d'un jour produit **son propre bloc** (équipe, activités, météo,
heures, primes, commentaires), titré par jour + quart. `_legacy_day` et
`build_workbook` itèrent désormais sur (jour, quart). Structure de bloc
inchangée par rapport à aujourd'hui ; c'est l'itération qui descend d'un niveau.

## Tests

- `tests/test_ui.py` (AppTest) :
  - un jour démarre avec un seul quart « Jour » ;
  - « ➕ Ajouter » crée un 2ᵉ quart (Soir) ; bascule entre quarts ;
  - saisir des heures dans Jour puis dans Soir → les deux jeux sont **distincts**
    dans l'état (`jours[j]["quarts"]["Jour"]["heures"]` ≠ celles de Soir) ;
  - « copier l'équipe + activités » à la création pré-remplit l'équipe/activités
    mais pas les heures ;
  - retrait d'un quart ; interdiction de retirer le dernier.
- Persistance BD : round-trip non testé en unitaire (convention `test_reports.py`
  — types Postgres non reproductibles hors ligne) ; vérifié e2e/manuellement,
  y compris la migration des anciennes données.

## Critères de succès

- On peut, pour un même jour, saisir des heures **différentes** par quart, et
  elles sont persistées et rechargées sans collision.
- Un jour à un seul quart reste aussi simple à utiliser qu'avant.
- Ajouter/retirer un quart fonctionne ; le dernier quart ne peut être retiré.
- Le tableau de bord agrège correctement ; l'export sort un bloc par quart.
- Les rapports déjà enregistrés sont migrés (données en quart « Jour »), rien
  n'est perdu.
- Suite de tests verte.

## Risques / compromis

- **Ampleur** : touche état, UI, persistance (nouveau grain + migration), tableau
  de bord et export. Découpage en tâches indépendantes dans le plan.
- **Migration de schéma** : repointage de FK `day_id → quart_id` ; risque sur
  données existantes. Mitigation : backfill dans un quart « Jour » avant bascule,
  le tout idempotent, validé manuellement contre Neon avant usage réel.
- **Saisie plus lourde** quand plusieurs quarts : atténuée par « copier l'équipe
  + activités » à la création d'un quart.
- **Remplace du travail récent** (sélecteur de quart unique) : assumé — ce design
  le supersède entièrement.
