# Authentification Microsoft (Entra ID) — Rapports Journaliers Ondel

Date : 2026-06-29
Statut : spec approuvée (design)

## Objectif

Ajouter une authentification Microsoft à l'application Streamlit afin de :

1. **Sécuriser l'accès** — réserver l'app aux comptes du tenant ELEM.
2. **Identifier l'utilisateur** — utiliser l'identité connectée dans l'app :
   verrouiller le « Responsable » sur la personne connectée, afficher
   l'utilisateur dans l'en-tête avec un bouton de déconnexion, et tracer
   l'auteur (email) de chaque sauvegarde.

## Approche retenue

Authentification **OIDC native de Streamlit** (`st.login` / `st.user` /
`st.logout`, disponible depuis Streamlit 1.42 ; l'app tourne en 1.50)
branchée sur **Microsoft Entra ID**. Aucune librairie d'auth maison.

Seule dépendance ajoutée : `Authlib>=1.3.2` (requise par l'auth native).

**Mono-tenant** : en pointant `server_metadata_url` sur l'autorité Entra
spécifique au tenant ELEM (avec le `tenant_id`), **seuls les comptes ELEM
peuvent se connecter**. Cela satisfait « réservé aux employés » sans gérer
de liste d'autorisation.

Hébergement cible : **Streamlit Community Cloud** (`*.streamlit.app`).

## Prérequis Azure (hors code — réalisés par un admin Entra)

Enregistrer une application dans Entra ID (« App registrations ») :

- **Redirect URIs** (plateforme *Web*) :
  - `http://localhost:8501/oauth2callback` (développement)
  - `https://<ton-app>.streamlit.app/oauth2callback` (production)
- Récupérer : `client_id`, `tenant_id`, et un `client_secret` (avec sa date
  d'expiration notée pour rotation).

Ces valeurs alimentent les secrets (ci-dessous). La création de l'app
Entra n'est pas automatisable depuis ce dépôt.

## Configuration (secrets)

Nouvelle section `[auth]` dans `.streamlit/secrets.toml` (déjà gitignored).
`secrets.toml.example` est mis à jour avec les clés **sans valeurs**.

```toml
[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "<chaîne aléatoire forte>"
client_id = "<client_id>"
client_secret = "<client_secret>"
server_metadata_url = "https://login.microsoftonline.com/<tenant_id>/v2.0/.well-known/openid-configuration"
```

En production : les mêmes clés sont saisies dans **Settings → Secrets** de
l'app sur Streamlit Community Cloud, avec `redirect_uri` pointant vers
l'URL `.streamlit.app`.

## Changements applicatifs

### 1. Portail d'accès (`app.py`, dans `main()`)

Avant tout rendu de contenu, exiger la connexion :

```python
if not st.user.is_logged_in:
    # écran de connexion : logo Ondel + bouton "Se connecter avec Microsoft"
    # qui appelle st.login()
    st.stop()
```

L'écran de connexion reprend l'identité visuelle Ondel (logo, titre).

### 2. En-tête

Dans l'en-tête existant (colonne droite, à côté du logo), afficher
`st.user.name` (+ email) et un bouton **« Se déconnecter »** appelant
`st.logout()`.

### 3. Responsable verrouillé

Le `responsable` de chaque quart est fixé à `st.user.name`
(non modifiable) et affiché en lecture seule dans l'en-tête de la vue de
saisie.

Comportement sur un rapport déjà enregistré : la valeur `responsable`
stockée en BD est conservée pour l'affichage à la relecture, mais la
prochaine sauvegarde l'écrase avec l'utilisateur courant.

### 4. Traçage de l'auteur

- Nouvelle colonne `saved_by text` sur la table `reports`, ajoutée par une
  migration idempotente (`alter table reports add column if not exists
  saved_by text`) dans `_DDL_STATEMENTS`, suivant le motif existant.
- `save_report(...)` reçoit un paramètre `saved_by` (l'email de `st.user`)
  et l'enregistre dans l'upsert de l'en-tête (`insert ... on conflict ...
  do update set saved_by = excluded.saved_by`).
- À l'export Excel, le nom de l'exportateur est estampillé dans le fichier
  généré (cellule de pied de page de la feuille « Synthèse »).

### Résolution de l'utilisateur courant

Fonction pure `current_user()` qui renvoie `{nom, email}` à partir de
`st.user`, isolant l'accès à `st.user` pour faciliter les tests et l'usage
côté `save_report` / export.

## Tests

- `save_report` persiste correctement `saved_by` (test sur BD / via le
  paramètre).
- `current_user()` renvoie nom/email attendus (en mockant `st.user`).
- Le portail (`st.login` / `st.stop`) relève de l'intégration : non couvert
  par les tests unitaires, vérifié manuellement.

## Hors scope (YAGNI)

- Pas de restriction par groupe Entra ni liste d'utilisateurs explicite
  (le mono-tenant suffit pour « réservé aux employés ELEM »).
- Pas de rôles / permissions ni de page d'administration.
- Pas de persistance de l'historique des exports (seul le dernier
  `saved_by` est conservé sur `reports`).

Ces éléments pourront être ajoutés ultérieurement si le besoin émerge.
