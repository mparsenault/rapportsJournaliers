# Envoi du rapport Excel par courriel (un fichier par journée)

Date : 2026-06-29

## Objectif

Permettre, depuis la saisie journalière, d'envoyer par courriel le rapport Excel
de la journée affichée. Un clic = une journée = un fichier `.xlsx` = un courriel.

Aujourd'hui l'export Excel (`build_workbook` → `_build_synthese`) ne produit qu'un
titre + un logo + une estampille : **aucune donnée de journée n'est écrite** dans
le classeur. Ce projet construit donc d'abord la vraie mise en page d'une journée,
puis l'envoi par courriel via Microsoft Graph.

## Décisions

- **Déclencheur** : bouton manuel, dans `view_day_entry`, à côté de « 💾 Enregistrer ».
- **Portée d'un envoi** : la **journée affichée** uniquement.
- **Destinataire** : valeur par défaut configurable (`graph.default_recipients`) +
  champ modifiable avant envoi.
- **Contenu** : un fichier Excel de la journée, mise en page **propre** (équivalente,
  pas une copie au pixel près) inspirée de `template.xlsm`.
- **Livraison** : un courriel par journée (donc par clic).
- **Transport** : Microsoft Graph API, envoi serveur (client credentials) depuis une
  boîte d'envoi dédiée.
- **Source des données de l'attachement** : l'**état courant à l'écran**
  (`st.session_state.jours[jour]`). L'envoi ne force pas d'enregistrement préalable,
  comme le téléchargement actuel.
- L'écran Export **ne contient pas** d'envoi courriel : il conserve uniquement son
  bouton de téléchargement (désormais rempli).

## Prérequis hors code (IT / Azure)

- Une boîte d'envoi (ex. `rapports@elem.global`).
- La permission **application `Mail.Send`** consentie par un administrateur, sur
  l'app Entra existante ou une nouvelle app dédiée.
- Les valeurs `tenant_id`, `client_id`, `client_secret`, `sender`,
  `default_recipients` renseignées dans `secrets.toml`.

Sans ces prérequis, l'app reste fonctionnelle : l'envoi signale une erreur claire
(secrets manquants), sans planter.

## Architecture & modules

Pour ne pas alourdir `app.py` (~1550 lignes), on extrait deux modules.

| Module | Rôle |
|---|---|
| `excel_report.py` (nouveau) | Génération Excel. Reçoit `_legacy_day`, `_add_logo`, les styles Excel et `build_workbook`. Ajoute la vraie mise en page d'une journée. |
| `mailer.py` (nouveau) | Envoi via Microsoft Graph. Obtention + cache du jeton, appel `sendMail`. |
| `app.py` (modifié) | `view_day_entry` : popover « Envoyer par courriel » à côté d'Enregistrer. `view_export` : utilise la nouvelle génération pour le téléchargement. |

### Interfaces publiques

`excel_report.py`
- `build_day_workbook(projet: dict, jour_name: str, day: dict, exported_by: str = "") -> BytesIO`
  — classeur 1 feuille pour la journée donnée.
- `build_week_workbook(projet: dict, jours: dict, jours_order: list[str], exported_by: str = "") -> BytesIO`
  — classeur, 1 feuille par jour **rempli** (`_day_total(day) > 0`) ; remplace l'actuel `build_workbook`.

`mailer.py`
- `send_mail(to: list[str] | str, subject: str, html_body: str, attachment_name: str, attachment_bytes: bytes) -> tuple[bool, str]`
  — ne lève jamais ; toute erreur (config, jeton, réseau, Graph) est capturée et
  renvoyée dans le message.

## Composant A — Mise en page Excel d'une journée (`excel_report.py`)

Fonction interne `_build_day_sheet(ws, projet, jour_name, day, exported_by)` qui
écrit dans une feuille, en réutilisant les styles Ondel existants et les données
déjà calculées par `_legacy_day(quart)` :

- **Bloc en-tête** : titre « RAPPORT JOURNALIER — ONDEL » + logo (`_add_logo`),
  No Projet, Date (`jour_name` + `day["date"]`), Adresse (`projet["adresse"]`),
  Responsable, Température (AM/PM), Conditions atmosphériques.
- **Pour chaque quart rempli du jour** (ordre `QUART_NAMES` = Jour / Soir / Nuit) :
  - libellé du quart ;
  - **tableau Personnel** : `Nom` + colonnes d'activités (`headers` issus de
    `_legacy_day`) + Autres Projets + `TR` + `TS` + `Hrs Éq.` + `Code Éq.` +
    `Prime` + `Commentaire` ;
  - **tableau Équipement-Véhicule** : mêmes colonnes pertinentes (sans équipement
    rattaché).
- **Estampille** « Exporté par {exported_by} » en pied (police 8, italique, gris).

`build_day_workbook` : un classeur, une feuille (`_build_day_sheet`), titrée du jour.
`build_week_workbook` : un classeur, une feuille par jour rempli ; sert au
téléchargement de `view_export`.

Le titre de feuille est nettoyé (≤ 31 caractères, sans caractères interdits Excel).

## Composant B — Envoi Microsoft Graph (`mailer.py`)

- **Jeton** : `POST https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token`
  (`grant_type=client_credentials`, `scope=https://graph.microsoft.com/.default`),
  via `httpx`. Le jeton est mis en cache en mémoire (module-level) jusqu'à
  ~60 s avant son `expires_in`, pour éviter de le redemander à chaque envoi.
- **Envoi** : `POST https://graph.microsoft.com/v1.0/users/{sender}/sendMail`
  avec `message` = { `subject`, `body` (HTML), `toRecipients`, `attachments`
  [`#microsoft.graph.fileAttachment`, `contentBytes` base64,
  `contentType` = `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`] }.
- **Config** — nouvelle section `[graph]` dans `secrets.toml` :
  `tenant_id`, `client_id`, `client_secret`, `sender`, `default_recipients`.
  Mise à jour de `secrets.toml.example`.
- **Dépendance** : `httpx` ajouté **inconditionnellement** dans `requirements.txt`
  (aujourd'hui présent seulement pour Python ≥ 3.10 ; on le rend disponible aussi
  en local 3.9 pour le mailer).
- `send_mail` retourne `(True, "Courriel envoyé ✓")` ou `(False, "<raison>")`.

## Composant C — Bouton Envoi dans la saisie journalière (`view_day_entry`)

Dans la barre d'actions en bas d'un jour ([app.py:1482](../../../app.py)) — actuellement
`sb1`/`sb2` avec « 💾 Enregistrer » — on ajoute à côté un `st.popover("📧 Envoyer par courriel")` :

- **Champ destinataire(s)** (`st.text_input`) pré-rempli depuis
  `st.secrets["graph"]["default_recipients"]`, modifiable, séparés par `;`.
- Bouton **« Envoyer »** :
  1. lit la journée courante depuis `st.session_state.jours[jour]` ;
  2. `build_day_workbook(projet, jour, day, exported_by=current_user()["name"])` ;
  3. `send_mail(to, subject, html_body, f"Rapport_{no}_{AAAA-MM-JJ}.xlsx", bytes)`
     avec sujet `Rapport journalier — {no} — {date} ({jour})` et corps court
     mentionnant « Exporté par {current_user} » ;
  4. affiche `st.success` / `st.error` selon `(ok, message)`.
- **Désactivé** si la journée n'est pas remplie (`_day_total(day) == 0`) → message
  « journée vide, rien à envoyer ».

## Gestion d'erreurs

- Champ destinataire vide → message, pas d'envoi.
- Section `[graph]` ou clé manquante dans les secrets → message clair via `send_mail`.
- Échec d'obtention du jeton / d'appel `sendMail` (réseau, 4xx/5xx Graph) → capturé,
  message renvoyé ; l'app ne plante pas.

## Tests (pytest, `tests/`)

- `excel_report` :
  - `build_day_workbook` sur une journée remplie → recharger le `.xlsx` avec openpyxl
    et vérifier : titre, No Projet, date/jour, lignes de personnel, heures TR/TS, prime.
  - journée vide → feuille en-tête sans lignes de personnel.
  - `build_week_workbook` → une feuille par jour rempli, jours vides exclus.
- `mailer` (`httpx` mocké, **aucun réseau**) :
  - obtention du jeton : bonne URL, `grant_type`, `scope` ; mise en cache (2 envois →
    1 seule requête de jeton).
  - `sendMail` : URL avec le bon `sender`, payload avec `toRecipients`, `subject`,
    pièce jointe en base64 et bon `contentType`.
  - secrets manquants → `(False, ...)` sans exception.

## Hors périmètre (YAGNI)

- Pas d'envoi automatique à l'enregistrement ni de tâche planifiée.
- Pas de table de destinataires en base (config secrets suffit).
- Pas de copie au pixel près de `template.xlsm` ni d'usage du fichier `.xlsm`.
- Pas d'historique/journal des envois.
