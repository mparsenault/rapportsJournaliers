# Rapport Journalier Ondel — application Streamlit

Reproduction du classeur `Rapport_Journalier_Ondel - version manuel.xlsm` :
saisie hebdomadaire des heures par activité (personnel et équipement),
avec export dans le gabarit Excel d'origine.

## Installation

```bash
pip install -r requirements.txt
```

## Lancement

```bash
streamlit run app.py
```

L'application s'ouvre dans le navigateur (http://localhost:8501).

## Contenu du dossier

- `app.py` — l'application Streamlit
- `template.xlsm` — le gabarit Excel d'origine (utilisé pour l'export)
- `data_source.py` — lecture des **projets** et **activités** depuis Postgres
  (cloud), alimenté par `sync_projects.py`.
- `sync_projects.py` — sync périodique SQL Server (Maestro/Qualifab) → Postgres.
  À planifier là où SQL Server est joignable. Voir `db/schema.sql`.
- Les listes **personnel** et **équipements** sont saisies librement dans la vue
  « Équipe & Équipements » : le personnel est pré-suggéré depuis la base de données
  (employés du projet) et complété par saisie libre ; les équipements sont en saisie
  libre uniquement. Il n'y a plus de page « Données de référence » ni de fichier
  `refdata.json`.

## Fonctionnement

**Saisie hebdomadaire** — un onglet par jour (Dimanche → Samedi) :
en-tête (No projet, date, responsable, quart, température, conditions),
configuration des colonnes d'activité (1re fixée à « 960 », puis
activités et « Autres Projets » au choix), grilles Personnel et
Équipement de type tableur avec totaux automatiques.

**Équipe & Équipements** — le personnel est pré-suggéré depuis la base de données
(employés du projet) et complété par saisie libre (`accept_new_options`) ;
les équipements sont en saisie libre. Les activités sont chargées depuis la base Postgres.

**Export Excel** — génère un `.xlsm` identique au gabarit avec les
données des 7 jours ; les formules de totaux (`O8`, `B46`, `O46`, …)
sont conservées et recalculées par Excel à l'ouverture.

> Les données saisies vivent en mémoire pendant la session. Exportez
> en `.xlsm` pour les conserver.

## Base de données (projets / activités)

1. Provisionner une base Postgres (Supabase / Azure) et appliquer `db/schema.sql`.
2. Configurer l'accès de l'app : copier `.streamlit/secrets.toml.example` vers
   `.streamlit/secrets.toml` et renseigner l'URL de connexion.
3. Planifier `sync_projects.py` (cron / Azure Function / Tâche planifiée) avec
   les variables d'env `SQLSERVER_*` et `POSTGRES_URL` ; dépendances dans
   `requirements-sync.txt`.

## Authentification Microsoft

L'accès est réservé aux comptes du tenant Microsoft ELEM via l'authentification
OIDC native de Streamlit branchée sur Microsoft Entra ID (mono-tenant).

### Enregistrer l'application dans Entra ID (admin)

1. Portail Azure → **Microsoft Entra ID → App registrations → New registration**.
2. **Redirect URI** (plateforme *Web*) :
   - `http://localhost:8501/oauth2callback` (développement)
   - `https://<ton-app>.streamlit.app/oauth2callback` (production)
3. Noter le **Application (client) ID** et le **Directory (tenant) ID**.
4. **Certificates & secrets → New client secret** : créer un secret, copier sa
   valeur (noter la date d'expiration pour la rotation).

### Configurer les secrets

- En local : copier les valeurs dans la section `[auth]` de
  `.streamlit/secrets.toml` (voir `secrets.toml.example`). Générer le
  `cookie_secret` avec `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- En production (Streamlit Community Cloud) : saisir les mêmes clés dans
  **Settings → Secrets**, avec `redirect_uri` pointant sur l'URL `.streamlit.app`.
