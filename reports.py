"""Persistance des rapports journaliers saisis -> Postgres (Neon).

L'app LIT les projets/activités/personnel via data_source (snapshot rafraîchi
par sync_projects.py). Ce module ÉCRIT et RELIT les rapports saisis par
l'utilisateur (en-tête, jours, quarts, heures, primes, commentaires).

Schéma normalisé, clé métier = (id_project, week_start) :
    reports               : en-tête de semaine (GPS…)
    report_resources      : (legacy) personnel + équipements de la semaine
    report_days           : un jour de la semaine
    report_quarts         : un quart d'un jour (Jour / Soir / Nuit)
    report_quart_resources: personnel ('P') + équipements ('E') du quart
    report_hours          : 1 ligne par ressource × activité × quart (grain fin)
    report_lines          : prime + commentaire par ressource × quart

IMPORTANT : aucune FK vers `projects`. sync_projects.py fait `delete from
projects` à chaque sync ; une FK ON DELETE CASCADE effacerait les rapports.
On stocke id_project + project_no en dur.
"""
from datetime import date

import streamlit as st
from sqlalchemy import text

# --------------------------------------------------------------------------
# Schéma
# --------------------------------------------------------------------------
_DDL_STATEMENTS = [
    """
    create table if not exists reports (
        id          serial primary key,
        id_project  integer not null,
        project_no  text not null,
        week_start  date not null,
        responsable text,
        quart       text,
        adresse     text,
        lat         double precision,
        lon         double precision,
        updated_at  timestamptz not null default now(),
        unique (id_project, week_start)
    )
    """,
    """
    create table if not exists report_resources (
        report_id integer not null references reports(id) on delete cascade,
        name      text not null,
        kind      char(1) not null check (kind in ('P', 'E')),
        primary key (report_id, name)
    )
    """,
    """
    create table if not exists report_days (
        id         serial primary key,
        report_id  integer not null references reports(id) on delete cascade,
        day_date   date not null,
        note       text,
        quart      text,
        temp_am    numeric,
        temp_pm    numeric,
        conditions text[] not null default '{}',
        activites  text[] not null default '{}',
        autres     text[] not null default '{}',
        unique (report_id, day_date)
    )
    """,
    """
    create table if not exists report_hours (
        day_id         integer references report_days(id) on delete cascade,
        resource_name  text not null,
        activity_label text not null,
        hours          numeric not null
    )
    """,
    """
    create table if not exists report_lines (
        day_id        integer references report_days(id) on delete cascade,
        resource_name text not null,
        prime         numeric,
        commentaire   text
    )
    """,
    "create index if not exists idx_report_days_report on report_days(report_id)",
    "create index if not exists idx_report_hours_day on report_hours(day_id)",
    "create index if not exists idx_report_hours_resource on report_hours(resource_name)",
    # Migration pour les bases déjà créées
    "alter table report_days add column if not exists quart text",
    # Nouveau grain : quarts
    """
    create table if not exists report_quarts (
        id         serial primary key,
        day_id     integer not null references report_days(id) on delete cascade,
        quart      text not null,
        ordinal    integer not null default 0,
        responsable text,
        note       text,
        temp_am    numeric,
        temp_pm    numeric,
        conditions text[] not null default '{}',
        activites  text[] not null default '{}',
        autres     text[] not null default '{}',
        unique (day_id, quart)
    )
    """,
    """
    create table if not exists report_quart_resources (
        quart_id  integer not null references report_quarts(id) on delete cascade,
        name      text not null,
        kind      char(1) not null check (kind in ('P', 'E')),
        primary key (quart_id, name)
    )
    """,
    "create index if not exists idx_report_quarts_day on report_quarts(day_id)",
    # Migration : 1 quart « Jour » par jour existant (no-op si déjà fait)
    """
    insert into report_quarts (day_id, quart, ordinal, note, temp_am, temp_pm,
                               conditions, activites, autres)
    select d.id, 'Jour', 0, d.note, d.temp_am, d.temp_pm,
           d.conditions, d.activites, d.autres
    from report_days d
    where not exists (select 1 from report_quarts q where q.day_id = d.id)
    """,
    # report_hours : ajouter quart_id et le backfiller depuis day_id
    "alter table report_hours add column if not exists quart_id integer references report_quarts(id) on delete cascade",
    """
    update report_hours h set quart_id = q.id
    from report_quarts q
    where q.day_id = h.day_id and q.quart = 'Jour' and h.quart_id is null
    """,
    # report_lines : idem
    "alter table report_lines add column if not exists quart_id integer references report_quarts(id) on delete cascade",
    """
    update report_lines l set quart_id = q.id
    from report_quarts q
    where q.day_id = l.day_id and q.quart = 'Jour' and l.quart_id is null
    """,
    # Les anciennes bases ont une PK sur (day_id, ...) qui exige day_id NOT NULL et
    # bloquerait les nouveaux inserts par quart_id (day_id NULL). On retire ces PK
    # (non destructif : aucune donnée perdue, seulement la contrainte). Le grain est
    # garanti par la stratégie delete-all-then-insert de save_report.
    "alter table report_hours drop constraint if exists report_hours_pkey",
    "alter table report_lines drop constraint if exists report_lines_pkey",
    # Heures : séparer temps régulier (hours, existant) et temps supplémentaire.
    # Rétro-compatible : les données existantes comptent comme du TR, hours_ts = 0.
    "alter table report_hours add column if not exists hours_ts numeric not null default 0",
    # Équipement rattaché à l'employé : total d'heures + liste de codes (C/N/É/D/G/BT).
    "alter table report_lines add column if not exists equip_hours numeric",
    "alter table report_lines add column if not exists equip_codes text[] not null default '{}'",
    # Postgres ne retire PAS le NOT NULL implicite des colonnes quand on drop la
    # PK ci-dessus : day_id reste NOT NULL et bloque les inserts par quart_id
    # (day_id NULL) avec NotNullViolation. On le retire explicitement.
    "alter table report_hours alter column day_id drop not null",
    "alter table report_lines alter column day_id drop not null",
    # report_quart_resources : backfill depuis report_resources (équipe semaine -> quart Jour de chaque jour)
    """
    insert into report_quart_resources (quart_id, name, kind)
    select q.id, r.name, r.kind
    from report_quarts q
    join report_days d on d.id = q.day_id
    join report_resources r on r.report_id = d.report_id
    where q.quart = 'Jour'
      and not exists (select 1 from report_quart_resources x where x.quart_id = q.id and x.name = r.name)
    """,
]


def _connection():
    # pool_pre_ping : teste la connexion (SELECT 1) avant de la prêter et se
    # reconnecte si elle est morte. Neon suspend le compute après quelques
    # minutes d'inactivité, ce qui ferme la connexion SSL côté serveur ; sans
    # cela, le premier INSERT échoue avec « SSL connection has been closed
    # unexpectedly ». pool_recycle force le renouvellement avant ce délai.
    return st.connection("postgres", type="sql", pool_pre_ping=True, pool_recycle=300)


def ensure_schema():
    """Crée les tables de rapports si absentes. Idempotent."""
    conn = _connection()
    with conn.session as s:
        for stmt in _DDL_STATEMENTS:
            s.execute(text(stmt))
        s.commit()


# --------------------------------------------------------------------------
# Écriture
# --------------------------------------------------------------------------
def save_report(projet, config, jours, jours_order):
    """Persiste tout le rapport de la semaine (upsert par projet+semaine).

    Stratégie : upsert de l'en-tête, puis suppression/réinsertion complète des
    enfants (days → quarts → resources/hours/lines) dans une transaction unique.
    Simple et garantit la cohérence avec l'état courant à l'écran.

    Renvoie l'id du rapport (reports.id).
    """
    id_project = projet.get("id_project")
    if id_project is None:
        raise ValueError("Aucun projet sélectionné : impossible d'enregistrer.")
    week_start = projet.get("semaine")
    if not isinstance(week_start, date):
        raise ValueError("Semaine invalide : impossible d'enregistrer.")

    conn = _connection()
    with conn.session as s:
        report_id = s.execute(
            text(
                """
                insert into reports
                    (id_project, project_no, week_start, responsable, quart,
                     adresse, lat, lon, updated_at)
                values
                    (:idp, :no, :wk, :resp, :quart, :addr, :lat, :lon, now())
                on conflict (id_project, week_start) do update set
                    project_no  = excluded.project_no,
                    responsable = excluded.responsable,
                    quart       = excluded.quart,
                    adresse     = excluded.adresse,
                    lat         = excluded.lat,
                    lon         = excluded.lon,
                    updated_at  = now()
                returning id
                """
            ),
            {
                "idp": int(id_project),
                "no": str(projet.get("no") or ""),
                "wk": week_start,
                "resp": None,
                "quart": None,
                "addr": projet.get("adresse") or None,
                "lat": projet.get("lat"),
                "lon": projet.get("lon"),
            },
        ).scalar()

        # Réinitialise les enfants (cascade pour days -> quarts -> resources/hours/lines)
        s.execute(text("delete from report_days where report_id = :r"), {"r": report_id})

        # Jours + quarts + grille
        for jour in jours_order:
            day = jours.get(jour) or {}
            d_date = day.get("date")
            if not isinstance(d_date, date):
                continue
            day_id = s.execute(
                text("insert into report_days (report_id, day_date) values (:r, :d) returning id"),
                {"r": report_id, "d": d_date},
            ).scalar()
            for ordinal, qname in enumerate(
                    [q for q in ("Jour", "Soir", "Nuit") if q in day.get("quarts", {})]):
                quart = day["quarts"][qname]
                quart_id = s.execute(
                    text(
                        """
                        insert into report_quarts
                            (day_id, quart, ordinal, responsable, note,
                             temp_am, temp_pm, conditions, activites, autres)
                        values (:d, :q, :o, :resp, :note, :tam, :tpm, :cond, :acts, :autres)
                        returning id
                        """
                    ),
                    {"d": day_id, "q": qname, "o": ordinal,
                     "resp": quart.get("responsable") or None,
                     "note": quart.get("description") or None,
                     "tam": quart.get("temp_am"), "tpm": quart.get("temp_pm"),
                     "cond": list(quart.get("conditions") or []),
                     "acts": list(quart.get("activites") or []),
                     "autres": list(quart.get("autres") or [])},
                ).scalar()
                for name in quart.get("personnel", []):
                    s.execute(text("insert into report_quart_resources (quart_id, name, kind) "
                                   "values (:q, :n, 'P') on conflict do nothing"),
                              {"q": quart_id, "n": name})
                for name in quart.get("equipements", []):
                    s.execute(text("insert into report_quart_resources (quart_id, name, kind) "
                                   "values (:q, :n, 'E') on conflict do nothing"),
                              {"q": quart_id, "n": name})
                for resource_name, acts in (quart.get("heures") or {}).items():
                    for activity_label, hrs in (acts or {}).items():
                        if hrs is None:
                            continue
                        s.execute(text("insert into report_hours (quart_id, resource_name, activity_label, hours) "
                                       "values (:q, :rn, :al, :h)"),
                                  {"q": quart_id, "rn": resource_name, "al": activity_label, "h": float(hrs)})
                prime = quart.get("prime") or {}
                commentaire = quart.get("commentaire_ligne") or {}
                for resource_name in set(prime) | set(commentaire):
                    s.execute(text("insert into report_lines (quart_id, resource_name, prime, commentaire) "
                                   "values (:q, :rn, :p, :c)"),
                              {"q": quart_id, "rn": resource_name,
                               "p": float(prime[resource_name]) if resource_name in prime else None,
                               "c": commentaire.get(resource_name) or None})

        s.commit()
    return report_id


# --------------------------------------------------------------------------
# Lecture
# --------------------------------------------------------------------------
def load_report(id_project, week_start):
    """Relit un rapport (projet+semaine) -> dict prêt à hydrater le state.

    Renvoie None si aucun rapport enregistré. Sinon :
        {
          "meta": {"responsable", "quart", "adresse", "lat", "lon", "updated_at"},
          "days_by_date": { date(...): {"date": ..., "quarts": {nom: <quart>}}, ... },
        }
    """
    if id_project is None or not isinstance(week_start, date):
        return None
    conn = _connection()
    with conn.session as s:
        rep = s.execute(
            text(
                "select id, responsable, quart, adresse, lat, lon, updated_at "
                "from reports where id_project = :idp and week_start = :wk"
            ),
            {"idp": int(id_project), "wk": week_start},
        ).mappings().first()
        if not rep:
            return None
        report_id = rep["id"]

        days = s.execute(
            text("select id, day_date from report_days where report_id = :r"),
            {"r": report_id},
        ).mappings().all()

        days_by_date = {}
        for d in days:
            quarts = s.execute(
                text("select id, quart, responsable, note, temp_am, temp_pm, "
                     "conditions, activites, autres from report_quarts "
                     "where day_id = :d order by ordinal"),
                {"d": d["id"]},
            ).mappings().all()
            quarts_dict = {}
            for q in quarts:
                hrs = s.execute(
                    text("select resource_name, activity_label, hours from report_hours where quart_id = :q"),
                    {"q": q["id"]}).mappings().all()
                heures = {}
                for h in hrs:
                    heures.setdefault(h["resource_name"], {})[h["activity_label"]] = float(h["hours"])
                lines = s.execute(
                    text("select resource_name, prime, commentaire from report_lines where quart_id = :q"),
                    {"q": q["id"]}).mappings().all()
                prime = {l["resource_name"]: float(l["prime"]) for l in lines if l["prime"] is not None}
                commentaire = {l["resource_name"]: l["commentaire"] for l in lines if l["commentaire"]}
                res = s.execute(
                    text("select name, kind from report_quart_resources where quart_id = :q order by name"),
                    {"q": q["id"]}).mappings().all()
                quarts_dict[q["quart"]] = {
                    "responsable": q["responsable"] or "",
                    "description": q["note"] or "",
                    "temp_am": float(q["temp_am"]) if q["temp_am"] is not None else None,
                    "temp_pm": float(q["temp_pm"]) if q["temp_pm"] is not None else None,
                    "conditions": list(q["conditions"] or []),
                    "activites": list(q["activites"] or []),
                    "autres": list(q["autres"] or []),
                    "personnel": [r["name"] for r in res if r["kind"] == "P"],
                    "equipements": [r["name"] for r in res if r["kind"] == "E"],
                    "heures": heures, "prime": prime, "commentaire_ligne": commentaire,
                }
            if not quarts_dict:
                quarts_dict = {"Jour": None}  # jour sans quart enregistré -> sera vide
            days_by_date[d["day_date"]] = {"date": d["day_date"], "quarts": quarts_dict}

        return {
            "meta": dict(rep),
            "days_by_date": days_by_date,
        }
