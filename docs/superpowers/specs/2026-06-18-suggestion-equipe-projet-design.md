# Design — Suggestion d'équipe par projet (employés de la semaine précédente)

Date : 2026-06-18
Statut : approuvé pour planification

## Objectif

Faciliter l'assignation du personnel à un projet. Aujourd'hui le personnel
vient d'une liste statique (`refdata.json`) sélectionnée à la main. On veut, à
partir des **feuilles de temps** de SQL Server, **pré-remplir l'équipe** d'un
projet avec les employés qui y ont travaillé la **semaine précédente**.

Décisions confirmées :
- **Suggestion par projet uniquement** — on ne remplace pas l'annuaire ;
  `refdata.json` reste la liste de personnel de base, en plus des suggérés.
- **Pré-remplir** l'équipe (modifiable) quand un projet est sélectionné.
- Semaine de référence = **dernière semaine complète** (max `WeekLastDay` avant
  aujourd'hui), calculée côté SQL Server.

## Portée

Dans la portée :
- 2ᵉ requête source dans `sync_projects.py` + table Neon `project_staff`.
- `data_source.get_project_staff(id_project)`.
- Pré-remplissage de `config["personnel"]` au changement de projet (dashboard).
- Options du multiselect Personnel = union (refdata + suggérés + sélection).
- Tests (helpers purs + AppTest).

Hors portée (inchangé) :
- Les équipements (les feuilles de temps ne couvrent que les employés).
- `refdata.json` (conservé tel quel).
- L'export Excel et le reste de l'UI.

## Source SQL (sync)

Requête dérivée de celle fournie, avec `ID_Project` (pour la jointure côté app)
et la semaine précédente calculée en SQL :

```sql
select distinct tsis.ID_Project, eu.FirstName, eu.LastName, o.Name as Occupation
from FDT.TimeSheetItemsStore tsis
left join HumanResources.Employees_U eu on eu.ID_Employee = tsis.ID_Employee
left join Reference.Occupation o on eu.ID_Occupation = o.ID_Occupation
where tsis.ID_Company = 1
  and tsis.ID_Project <> ''
  and tsis.WeekLastDay = (select max(WeekLastDay) from FDT.TimeSheetItemsStore
                          where ID_Company = 1 and WeekLastDay < cast(getdate() as date))
```

`Project_No` / `Description` ne sont pas resélectionnés (ils viennent déjà de la
table `projects`).

## Schéma Neon

```sql
create table if not exists project_staff (
    id_project integer not null,
    employee   text not null,
    primary key (id_project, employee)
);
create index if not exists idx_project_staff_project on project_staff(id_project);
```

- **Pas de clé étrangère** vers `projects` : un projet présent dans les feuilles
  de temps n'est pas forcément dans la table `projects` (filtres plus stricts :
  `transfer2Maestro=1`, etc.). Les lignes de staff pour des projets non
  synchronisés ne sont jamais requêtées par l'app (qui interroge par
  `id_project` d'un projet valide).
- `employee` = libellé `"Prénom Nom (Métier)"`, ou `"Prénom Nom"` si métier
  vide/NULL — même format que le personnel existant (ex. `"J-Paul Jobin (élec)"`).

## Sync (`sync_projects.py`)

- `STAFF_QUERY` (ci-dessus).
- `fetch_staff_rows()` — exécute `STAFF_QUERY` sur SQL Server (mêmes connexion /
  imports internes que `fetch_source_rows`).
- `staff_rows_to_payload(rows) -> list[(id_project, employee)]` — **pure** :
  construit le libellé (`f"{first} {last} ({occupation})"`, ou `f"{first} {last}"`
  si occupation vide), déduplique, ignore les lignes sans `id_project`.
- `write_payload(pg_url, projects, activities, staff)` — étendu : crée la table
  `project_staff` (DDL), puis dans la **même transaction** que projects/activities :
  `delete from project_staff;` + insertion en masse. Rafraîchissement complet.
- `main()` — appelle aussi `fetch_staff_rows()` / `staff_rows_to_payload`, passe
  `staff` à `write_payload`, et journalise le nombre de lignes de staff.

## Accès app (`data_source.py`)

- `get_project_staff(id_project) -> list[str]` : libellés d'employés du projet,
  triés ; `[]` si `id_project` est `None`, aucun résultat, ou base injoignable
  (même schéma try/except que `get_activities`).
  SQL : `select employee from project_staff where id_project = :pid order by employee`.

## Pré-remplissage (`view_dashboard`)

Après la sélection du projet (`proj["id_project"]` connu) :

```
pid = proj["id_project"]
if pid is not None and st.session_state.get("staff_prefilled_for") != pid:
    suggested = data_source.get_project_staff(pid)
    if suggested:
        config["personnel"] = suggested      # pré-remplit l'équipe (remplace)
    st.session_state["staff_prefilled_for"] = pid
```

- Le marqueur `staff_prefilled_for` garantit que le pré-remplissage ne se fait
  **qu'une fois par changement de projet** — les ajouts/retraits manuels ne sont
  pas écrasés aux reruns suivants.
- Au **changement** de projet, l'équipe est **remplacée** par la nouvelle
  suggestion (nouveau projet = nouvelle équipe).
- Les **équipements** ne sont jamais touchés.

## Options du multiselect Personnel (vue « Équipe & Équipements »)

```
options = sorted(set(ref["personnel"])
                 | set(data_source.get_project_staff(proj["id_project"]))
                 | set(config["personnel"]))
config["personnel"] = st.multiselect("Personnel", options, default=config["personnel"])
```

- Inclure les suggérés rend les noms pré-remplis **sélectionnables** ; inclure
  `config["personnel"]` garantit que `default` ⊆ `options` (pas de plantage
  Streamlit). `refdata.json` reste la base, non modifié.

## Gestion des erreurs / cas limites

- Base injoignable / projet sans staff → `get_project_staff` renvoie `[]` →
  aucun pré-remplissage, aucune erreur.
- Projet non actif la semaine précédente → aucune suggestion pour lui (accepté).
- Métier NULL → libellé sans parenthèses.
- Deux employés homonymes → libellés identiques fusionnés (cas rare accepté).

## Tests

- `staff_rows_to_payload` : tests purs (format du libellé, occupation NULL/vide,
  dédup, ligne sans id_project ignorée).
- `get_project_staff` : `_connection` monkeypatché (résultat + cas injoignable → `[]`).
- AppTest : sélection d'un projet (monkeypatch `get_projects` + `get_project_staff`)
  → `config["personnel"]` pré-rempli ; changement de projet → re-rempli ; les
  options du multiselect Personnel incluent les suggérés.
- L'export reste couvert par la suite existante.

## Critères de succès

- Choisir un projet pré-remplit l'équipe avec les employés de la semaine
  précédente, modifiable ensuite.
- Les employés suggérés sont sélectionnables (options valides) en plus de la
  liste `refdata`.
- Un sync rafraîchit `project_staff` sans interruption (transaction).
- Aucune régression de l'export ni du reste de l'UI.

## Risques / compromis

- Identité employé par libellé (pas d'ID) → homonymes fusionnés ; jugé
  acceptable vu l'usage.
- Le pré-remplissage **remplace** l'équipe au changement de projet ; si
  l'utilisateur avait composé une équipe manuellement puis change de projet,
  elle est remplacée (cohérent : un projet = une équipe).
- Dépend d'un sync à jour ; sinon les suggestions datent du dernier snapshot.
