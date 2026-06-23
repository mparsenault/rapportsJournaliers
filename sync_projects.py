"""Sync projets/activités : SQL Server (Maestro/Qualifab) -> Postgres (cloud).

Rafraîchissement complet dans une transaction unique. À planifier (cron /
Azure Function / Tâche planifiée) LÀ où SQL Server est joignable.

Configuration (variables d'environnement, ou un fichier .env à côté du script) :
  SQLSERVER_HOST, SQLSERVER_DB, SQLSERVER_USER, SQLSERVER_PASSWORD
  POSTGRES_URL   (forme libpq : postgresql://user:pass@host:5432/dbname)

Le script charge automatiquement un fichier .env présent dans le dossier
courant (les vraies variables d'environnement ont priorité sur le .env).
"""
import os
import sys

SOURCE_QUERY = """
select p.ID_Project, p.Project_No, p.Description, a.ActivityCode, a.Description
from Projects.Projects p
left join Projects.Activities a
  on p.ID_Project = a.ID_Project
where p.ID_Company = 1
  and p.Valid = 1
  and p.Project_No like '08%'
"""

SCHEMA_DDL = """
create table if not exists projects (
    id_project integer primary key,
    project_no text not null,
    description text
);
alter table projects add column if not exists description text;
create table if not exists activities (
    id_project    integer not null references projects(id_project) on delete cascade,
    activity_code text not null,
    description   text,
    primary key (id_project, activity_code)
);
create index if not exists idx_activities_project on activities(id_project);
create table if not exists project_staff (
    id_project integer not null,
    employee   text not null,
    primary key (id_project, employee)
);
create index if not exists idx_project_staff_project on project_staff(id_project);
"""

STAFF_QUERY = """
select distinct tsis.ID_Project, eu.FirstName, eu.LastName, o.Name as Occupation
from FDT.TimeSheetItemsStore tsis
left join HumanResources.Employees_U eu on eu.ID_Employee = tsis.ID_Employee
left join Reference.Occupation o on eu.ID_Occupation = o.ID_Occupation
where tsis.ID_Company = 1
  and tsis.ID_Project <> ''
  and tsis.WeekLastDay = (select max(WeekLastDay) from FDT.TimeSheetItemsStore
                          where ID_Company = 1 and WeekLastDay < cast(getdate() as date))
"""


def rows_to_payload(rows):
    """rows: (id_project, project_no, project_description, activity_code, activity_description).

    Renvoie (projects, activities) :
      projects   : list[(id_project, project_no, description)] dédup, trié par id_project
      activities : list[(id_project, activity_code, activity_description)] (code non vide)
    """
    projects = {}
    activities = []
    for id_project, project_no, proj_desc, code, act_desc in rows:
        projects.setdefault(id_project, (project_no, proj_desc))
        if code is not None and str(code).strip() != "":
            activities.append((id_project, code, act_desc))
    proj_list = [(pid, no, desc) for pid, (no, desc) in sorted(projects.items())]
    return proj_list, activities


def staff_rows_to_payload(rows):
    """rows: itérable de (id_project, first_name, last_name, occupation).

    Renvoie list[(id_project, employee)] dédupliquée et triée. Libellé employé :
    "Prénom Nom (Métier)", ou "Prénom Nom" si le métier est vide/NULL. Les lignes
    sans id_project (ou sans nom) sont ignorées.
    """
    seen = set()
    out = []
    for id_project, first, last, occupation in rows:
        if id_project is None:
            continue
        name = f"{(first or '').strip()} {(last or '').strip()}".strip()
        if not name:
            continue
        occ = (occupation or "").strip()
        label = f"{name} ({occ})" if occ else name
        key = (id_project, label)
        if key not in seen:
            seen.add(key)
            out.append((id_project, label))
    return sorted(out)


def fetch_source_rows():
    import pymssql
    conn = pymssql.connect(
        server=os.environ["SQLSERVER_HOST"],
        user=os.environ["SQLSERVER_USER"],
        password=os.environ["SQLSERVER_PASSWORD"],
        database=os.environ["SQLSERVER_DB"],
    )
    try:
        cur = conn.cursor()
        cur.execute(SOURCE_QUERY)
        return cur.fetchall()
    finally:
        conn.close()


def fetch_staff_rows():
    import pymssql
    conn = pymssql.connect(
        server=os.environ["SQLSERVER_HOST"],
        user=os.environ["SQLSERVER_USER"],
        password=os.environ["SQLSERVER_PASSWORD"],
        database=os.environ["SQLSERVER_DB"],
    )
    try:
        cur = conn.cursor()
        cur.execute(STAFF_QUERY)
        return cur.fetchall()
    finally:
        conn.close()


def write_payload(pg_url, projects, activities, staff):
    import psycopg2
    conn = psycopg2.connect(pg_url)
    try:
        cur = conn.cursor()
        cur.execute(SCHEMA_DDL)
        cur.execute("delete from activities;")
        cur.execute("delete from project_staff;")
        cur.execute("delete from projects;")
        if projects:
            cur.executemany(
                "insert into projects (id_project, project_no, description) values (%s, %s, %s)",
                projects,
            )
        if activities:
            cur.executemany(
                "insert into activities (id_project, activity_code, description) "
                "values (%s, %s, %s)",
                activities,
            )
        if staff:
            cur.executemany(
                "insert into project_staff (id_project, employee) values (%s, %s)",
                staff,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _parse_dotenv(text):
    """Parse le contenu d'un .env -> dict {clé: valeur}.

    Ignore les lignes vides et les commentaires (#) ; coupe sur le premier '='
    (les valeurs peuvent donc contenir des '=' et '&', utile pour POSTGRES_URL) ;
    retire d'éventuels guillemets entourant la valeur.
    """
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def _load_dotenv(path=".env"):
    """Charge un fichier .env dans os.environ (sans écraser les variables déjà définies)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for key, val in _parse_dotenv(f.read()).items():
            os.environ.setdefault(key, val)


def main():
    _load_dotenv()
    projects, activities = rows_to_payload(fetch_source_rows())
    staff = staff_rows_to_payload(fetch_staff_rows())
    write_payload(os.environ["POSTGRES_URL"], projects, activities, staff)
    print(f"Sync OK : {len(projects)} projets, {len(activities)} activités, "
          f"{len(staff)} affectations")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"Sync FAILED : {exc}", file=sys.stderr)
        sys.exit(1)
