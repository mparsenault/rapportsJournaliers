"""Accès aux données projets/activités, lues depuis Postgres (cloud).

Les projets et activités proviennent d'un snapshot Postgres alimenté
périodiquement par sync_projects.py (source : SQL Server / Maestro). Le
personnel, les véhicules et les « autres projets » restent dans refdata.json.
"""
import streamlit as st

_PROJECTS_SQL = "select id_project, project_no, description from projects order by project_no"
_ACTIVITIES_SQL = (
    "select activity_code, description from activities "
    "where id_project = :pid order by activity_code"
)
_STAFF_SQL = "select employee from project_staff where id_project = :pid order by employee"
_ALL_STAFF_SQL = "select distinct employee from project_staff order by employee"


def activity_label(code, desc):
    """Libellé d'activité : 'CODE - Description' (ou 'CODE' si description vide)."""
    code = (code or "").strip()
    desc = (desc or "").strip()
    return f"{code} - {desc}" if desc else code


def filter_known(selected, options):
    """Retire de `selected` les valeurs absentes de `options` (ordre préservé)."""
    allowed = set(options)
    return [s for s in selected if s in allowed]


def projects_from_df(df):
    """DataFrame(id_project, project_no, description) -> list[(int, str, str)]."""
    out = []
    for r in df.itertuples(index=False):
        desc = r.description if isinstance(r.description, str) else ""
        out.append((int(r.id_project), str(r.project_no), desc))
    return out


def activity_labels_from_df(df):
    """DataFrame(activity_code, description) -> list[str] de libellés."""
    return [activity_label(r.activity_code, r.description)
            for r in df.itertuples(index=False)]


def _connection():
    return st.connection("postgres", type="sql")


def get_projects():
    """Liste de 3-uplets (id_project, project_no, description) triée. [] si la base est injoignable."""
    try:
        df = _connection().query(_PROJECTS_SQL, ttl=600)
        return projects_from_df(df)
    except Exception:
        return []


def get_activities(id_project):
    """Libellés d'activités du projet, triés. [] si aucun / base injoignable."""
    if id_project is None:
        return []
    try:
        df = _connection().query(_ACTIVITIES_SQL, params={"pid": int(id_project)}, ttl=600)
        return activity_labels_from_df(df)
    except Exception:
        return []


def get_project_staff(id_project):
    """Libellés d'employés ayant travaillé sur le projet (semaine précédente).

    [] si id_project None, aucun résultat, ou base injoignable.
    """
    if id_project is None:
        return []
    try:
        df = _connection().query(_STAFF_SQL, params={"pid": int(id_project)}, ttl=600)
        return [str(r.employee) for r in df.itertuples(index=False)]
    except Exception:
        return []


def get_all_staff():
    """Liste de tous les employés connus (tous projets confondus), triée.

    [] si base injoignable.
    """
    try:
        df = _connection().query(_ALL_STAFF_SQL, ttl=600)
        return [str(r.employee) for r in df.itertuples(index=False)]
    except Exception:
        return []
