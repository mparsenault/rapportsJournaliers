# Design — Nouvelle requête projets + description dans le menu

Date : 2026-06-18
Statut : approuvé pour planification

## Objectif

La requête actuelle des projets (`SOURCE_QUERY` dans `sync_projects.py`) est trop
restrictive (`transfer2Maestro = 1`, `maestroProjNo <> ''`, `ID_Tree <> -1`) :
**des projets manquent**. On la remplace par une requête aux filtres élargis
(`Valid = 1`, `Project_No like '08%'`) et on ajoute la **description du projet**
(`p.Description`) pour l'afficher dans le menu déroulant.

## Portée

Dans la portée :
- Remplacer `SOURCE_QUERY` (filtres + ajout `p.Description`).
- Ajouter une colonne `description` à la table Neon `projects` (+ `alter` pour
  la table existante).
- Adapter `rows_to_payload` (5 colonnes ; projets en 3-uplets).
- Adapter `write_payload` (insert 3 colonnes projets).
- `data_source.get_projects` renvoie `(id_project, project_no, description)`.
- Menu déroulant : afficher `"Project_No — Description"`.
- Mettre à jour les tests touchés par le changement de forme.

Hors portée (inchangé) :
- Les activités (format `"Code - Description"`, table `activities`).
- `project_staff` / suggestion d'équipe.
- La saisie journalière et l'export (l'export utilise `proj["no"]` =
  `project_no`, donc non affecté).

## Requête source (sync)

```sql
select p.ID_Project, p.Project_No, p.Description, a.ActivityCode, a.Description
from Projects.Projects p
left join Projects.Activities a on p.ID_Project = a.ID_Project
where p.ID_Company = 1
  and p.Valid = 1
  and p.Project_No like '08%'
```

5 colonnes positionnelles : `(ID_Project, Project_No, project_description,
ActivityCode, activity_description)`. (Deux colonnes nommées « Description » —
sans importance, pymssql renvoie des tuples positionnels.)

## Schéma Neon (`projects`)

```sql
create table if not exists projects (
    id_project integer primary key,
    project_no text not null,
    description text
);
alter table projects add column if not exists description text;
```

L'`alter ... add column if not exists` migre la table déjà existante (qui n'a
que `id_project, project_no`). Idempotent.

## `rows_to_payload` (sync)

Adapté aux 5 colonnes :
- `projects` → `list[(id_project, project_no, description)]`, dédupliqué par
  `id_project`, trié par `id_project`.
- `activities` → `list[(id_project, activity_code, activity_description)]`
  (lignes à code non vide) — **inchangé**.

```python
def rows_to_payload(rows):
    projects = {}
    activities = []
    for id_project, project_no, proj_desc, code, act_desc in rows:
        projects.setdefault(id_project, (project_no, proj_desc))
        if code is not None and str(code).strip() != "":
            activities.append((id_project, code, act_desc))
    proj_list = [(pid, no, desc) for pid, (no, desc) in sorted(projects.items())]
    return proj_list, activities
```

## `write_payload` (sync)

```python
cur.executemany(
    "insert into projects (id_project, project_no, description) values (%s, %s, %s)",
    projects,
)
```

(Le `staff` et les `activities` restent inchangés ; `main()` n'a pas besoin de
changer.)

## Accès app (`data_source`)

```python
_PROJECTS_SQL = "select id_project, project_no, description from projects order by project_no"

def get_projects():
    # renvoie list[(id_project:int, project_no:str, description:str)]
    ...  # [] si base injoignable (try/except inchangé)
```

`projects_from_df(df)` renvoie `(int(id_project), str(project_no), description or "")`.

## Menu déroulant (`view_dashboard`)

- Libellé affiché = `f"{project_no} — {description}"`, ou `project_no` seul si la
  description est vide.
- On stocke toujours `proj["no"]` = `project_no` (compatibilité export) et
  `proj["id_project"]`.
- La sélection courante est restaurée en retrouvant l'option dont le
  `project_no` == `proj["no"]`.
- Le pré-remplissage d'équipe (`staff_prefilled_for`, basé sur `id_project`)
  reste inchangé.

Séparateur retenu : « — » (tiret cadratin).

## Gestion des erreurs / cas limites

- Description NULL/vide → libellé = `project_no` seul.
- Base injoignable → `get_projects()` renvoie `[]` (comportement inchangé).
- Deux projets de même `project_no` (improbable) → libellés identiques ; on
  garde le mapping par libellé (cas accepté).

## Tests

- `rows_to_payload` (`tests/test_sync.py`) : entrées à 5 colonnes ; projets en
  3-uplets `(id, no, desc)` ; dédup ; activités inchangées.
- `get_projects` / `projects_from_df` (`tests/test_data_source.py`) : 3-uplets,
  colonne `description` (dont cas description vide).
- UI (`tests/test_ui.py`) : le selectbox affiche `"no — desc"` ; sélection →
  `id_project` + `no` corrects ; mise à jour du helper `_run_with_project` et
  des tests `test_project_selectbox_lists_db_projects` /
  `test_selecting_project_sets_id` pour la nouvelle forme et les libellés.

## Migration

Après déploiement : relancer `sync_projects.py`. Le DDL ajoute la colonne
`description` et recharge `projects` (nouveaux filtres + descriptions),
`activities` et `project_staff` en une transaction.

## Critères de succès

- Les projets précédemment manquants (filtrés par les anciens critères Maestro)
  apparaissent dans le menu, limités à `Valid = 1` et `Project_No like '08%'`.
- Le menu affiche `"Project_No — Description"`.
- Aucune régression : activités, équipe suggérée, saisie, export.

## Risques / compromis

- Changement de forme de `get_projects` et `rows_to_payload` → plusieurs tests à
  mettre à jour (couvert dans Tests).
- Élargir les filtres peut faire apparaître plus de projets ; bornés par
  `Valid = 1` et `Project_No like '08%'`.
