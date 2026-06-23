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
