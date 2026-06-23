# Design — Sélection de projets et d'activités depuis la base de données

Date : 2026-06-18
Statut : approuvé pour planification

## Objectif

Aujourd'hui, dans `app.py` :
- le **numéro de projet** est un champ texte libre (`projet["no"]`) ;
- les **activités** proviennent d'une liste statique globale dans
  `refdata.json` (clé `activites`, ~90 entrées au format `Code - Description`),
  proposée par jour via `st.multiselect`.

L'utilisateur veut que projets **et** activités proviennent des données
réelles de Maestro/Qualifab, issues de cette requête (SQL Server) :

```sql
select p.ID_Project, p.Project_No, a.ActivityCode, a.Description
from Projects.Projects p
left join Projects.Activities a
  on p.ID_Project = a.ID_Project
where p.ID_Company = 1            -- Qualifab
  and p.transfer2Maestro = 1
  and p.maestroProjNo <> ''
  and p.ID_Tree <> -1
```

La requête renvoie une ligne par couple **projet → activité** (`LEFT JOIN` :
un projet peut n'avoir aucune activité). On passe donc d'une saisie libre à la
**sélection d'un projet réel**, puis au choix d'**activités filtrées par ce
projet**.

## Architecture cible

L'app sera hébergée dans le cloud ; SQL Server reste on-prem. On ne connecte
**pas** l'app directement à SQL Server. À la place, les données sont **poussées
périodiquement** vers une **base Postgres cloud** (Supabase / Azure), que l'app
lit.

```
[SQL Server on-prem] ──(la requête)──┐
                                     ▼
                          sync_projects.py        ← planifié par l'utilisateur (cron /
                          (lit SQL Server,           Azure Function / Tâche planifiée),
                           écrit Postgres)           p. ex. chaque nuit. Tourne LÀ où
                                     │               SQL Server est joignable.
                                     ▼
                           [Postgres cloud]  (Supabase / Azure)
                                     │
                                     ▼
                          data_source.py  (lecture + cache st.cache_data, ttl)
                                     │
                                     ▼
                              app.py (UX projet → activités)
```

Deux livrables **indépendants**, ne partageant que le schéma Postgres :
1. **Script de sync** — tourne près de SQL Server.
2. **App** — hébergée cloud, lit Postgres.

## Base de code (working tree)

La fonctionnalité est bâtie sur la version **non commitée** d'`app.py` présente
dans le répertoire de travail (réécriture « UX Dashboard tablette » :
`view_dashboard` / `view_day_entry` / `view_reference`, `_legacy_day`,
`build_workbook()` lisant `session_state`). Cette réécriture a rendu obsolètes
les 15 tests hérités du HEAD ; le plan les remet au vert (voir Tests).
L'export y est un **stub** (feuille « Synthèse » simplifiée, pas de feuilles par
jour) — laissé tel quel.

## Portée

Dans la portée :
- Schéma Postgres (deux tables normalisées).
- Script de sync autonome `sync_projects.py` (SQL Server → Postgres).
- Couche d'accès `data_source.py` (lecture projets/activités + cache).
- Changement d'UX dans `app.py` : numéro de projet → `selectbox` alimenté par
  la base ; activités du jour filtrées par le projet choisi.
- Retrait de l'onglet « Activités » de la page Références (les activités
  viennent désormais de Postgres).
- Re-baseline complet des tests existants (`tests/test_model.py`,
  `tests/test_ui.py`) vers l'API du working tree (la réécriture « UX Dashboard
  tablette » les avait rendus obsolètes), + nouveaux tests BD.
- Dépendances et configuration des secrets.

Hors portée (inchangé) :
- L'export Excel (dans le working tree : feuille « Synthèse » simplifiée) reste
  inchangé ; on conserve le format des libellés d'activité (`Code - Description`).
  Les tests d'export se limitent à un smoke (la génération ne plante pas).
- La météo / géolocalisation.
- Le personnel, les véhicules et les « autres projets » : **restent** dans
  `refdata.json` (la requête ne les couvre pas).
- Le provisionnement de la base Postgres et la planification du job de sync
  (réalisés par l'utilisateur dans son environnement).

## Schéma Postgres

```sql
create table if not exists projects (
    id_project integer primary key,
    project_no text not null
);

create table if not exists activities (
    id_project    integer not null references projects(id_project) on delete cascade,
    activity_code text not null,
    description   text,
    primary key (id_project, activity_code)
);

create index if not exists idx_activities_project on activities(id_project);
```

- Un projet sans activité (`LEFT JOIN` → `ActivityCode` NULL) existe avec
  **zéro ligne** dans `activities` — géré naturellement.
- La clé primaire `(id_project, activity_code)` suppose un code d'activité
  unique par projet (cohérent avec la source). Les lignes où `ActivityCode`
  est NULL ne sont pas insérées dans `activities`.

## Script de sync (`sync_projects.py`)

- Lit SQL Server avec la requête **exacte** ci-dessus, via `pymssql` (évite
  l'installation d'un pilote ODBC système).
- Écrit dans Postgres **dans une transaction unique**, en **rafraîchissement
  complet** :
  1. `delete from activities;`
  2. `delete from projects;`
  3. insertion en masse des projets (déduplication des `ID_Project` puisque la
     requête répète le projet par activité), puis des activités (lignes à
     `ActivityCode` non NULL).
  4. `commit`.
  - Le rafraîchissement complet reflète les **suppressions** côté source.
  - La transaction garantit que l'app ne voit **jamais** un état vide pendant
    le sync : elle lit l'ancien snapshot jusqu'au `commit`. En cas d'erreur,
    `rollback` → Postgres conserve le dernier bon snapshot.
- Séparation **transformation / I/O** : une fonction pure
  `rows_to_payload(rows) -> (projects, activities)` (déduplication, gestion des
  NULL) testable sans base.
- Configuration par variables d'environnement
  (`SQLSERVER_HOST/DB/USER/PASSWORD`, `POSTGRES_URL`). Idempotent, journalise
  les compteurs (projets / activités écrits), sort en code ≠ 0 sur erreur pour
  que le planificateur puisse alerter.

## Couche d'accès de l'app (`data_source.py`)

- `get_projects() -> list[tuple[int, str]]` : `(id_project, project_no)` triés
  par `project_no`.
- `get_activities(id_project) -> list[str]` : libellés
  `"ActivityCode - Description"` triés par `activity_code`.
- `activity_label(code, desc) -> str` : fonction **pure** produisant le libellé
  (même format que `refdata.json` aujourd'hui → l'export et les en-têtes Excel
  restent inchangés).
- `filter_known(selected, options) -> list` : fonction **pure** qui retire d'une
  sélection les valeurs absentes des options (garde-fou changement de projet).
- Lecture via `st.connection("postgres", type="sql")` (SQLAlchemy), connexion
  définie dans `.streamlit/secrets.toml`. Résultats mis en cache avec
  `st.cache_data(ttl=600)`.
- En cas d'erreur (base injoignable) : `get_projects` / `get_activities`
  attrapent l'exception, renvoient une liste vide et laissent l'appelant
  afficher un message ; le cache (ttl) amortit les coupures brèves.

## Changements dans `app.py`

- `init_state` : ajout de `projet["id_project"] = None`.
- **Tableau de bord** (`view_dashboard`) : le `text_input("Numéro de Projet")`
  devient un `selectbox` alimenté par `get_projects()`. On stocke à la fois
  `projet["id_project"]` et `projet["no"]` (= `project_no`, garde l'export
  fonctionnel). Si la base est injoignable, afficher
  `st.error("Impossible de charger les projets…")` et présenter un placeholder.
- **Saisie d'un jour** (`view_day_entry`) : le multiselect Activités liste
  uniquement `get_activities(projet["id_project"])`. Garde-fou : la valeur
  `default` est filtrée via `filter_known(day["activites"], options)` pour ne
  pas planter Streamlit si le projet a changé. Le multiselect « Autres » reste
  alimenté par `ref["autres_projets"]`.
- **Références** (`view_reference`) : retrait de l'onglet « Activités » (et de
  l'usage de `ref["activites"]`). Personnel / Véhicules / Autres restent
  éditables.

## Gestion des erreurs

- Postgres injoignable ou vide → liste vide + `st.error(...)`, `selectbox`/
  multiselect avec placeholder ; pas de plantage.
- Projet sans activité → multiselect Activités vide (normal).
- Changement de projet → `filter_known` évite l'erreur « default not in
  options ».
- Sync → transaction + `rollback` sur erreur ; dernier bon snapshot préservé ;
  code de sortie ≠ 0.

## Tests

- `activity_label`, `filter_known`, `rows_to_payload` : tests **purs**
  (dont le cas « projet sans activité » et la déduplication des projets).
- `get_projects` / `get_activities` : `st.connection` monkeypatché renvoyant
  des DataFrames bidon ; on vérifie la forme et le format des libellés.
- Re-baseline de `tests/test_model.py` et `tests/test_ui.py` vers l'API du
  working tree (`_legacy_day`, `_grid_df_to_day(edited, day)`, `build_workbook()`,
  vues `view_dashboard` / `view_day_entry` / `view_reference`). Les tests UI
  utilisent AppTest et monkeypatchent `data_source.get_projects` /
  `get_activities`.
- L'export Excel doit continuer à produire le même résultat pour des données
  équivalentes (régression existante conservée).

## Dépendances & secrets

- `requirements.txt` (app) : ajout de `SQLAlchemy` et `psycopg2-binary`.
- `requirements-sync.txt` (job de sync) : `pymssql`, `psycopg2-binary`.
- `.streamlit/secrets.toml` (gitignored) :
  ```toml
  [connections.postgres]
  url = "postgresql+psycopg2://user:pass@host:5432/dbname"
  ```
- `.gitignore` : ajouter `.streamlit/secrets.toml` et `.env`.

## Critères de succès

- Le numéro de projet se choisit dans un menu déroulant alimenté par la base.
- Lors de la saisie d'un jour, seules les activités du projet choisi sont
  proposées.
- Un sync planifié rafraîchit projets/activités sans interruption visible côté
  app.
- L'export Excel produit le même résultat qu'aujourd'hui pour des données
  équivalentes.
- L'app reste utilisable (message clair, pas de plantage) si Postgres est
  momentanément injoignable.

## Risques / compromis

- Dépendance à un job de sync externe : si le sync est en panne, les données
  affichées datent du dernier bon snapshot (acceptable).
- Latence Postgres masquée par `st.cache_data(ttl)` ; fraîcheur ≈ ttl + cadence
  de sync.
- Le provisionnement Postgres et la planification du sync relèvent de
  l'utilisateur ; ce design fournit le code et la configuration, pas
  l'infrastructure.
