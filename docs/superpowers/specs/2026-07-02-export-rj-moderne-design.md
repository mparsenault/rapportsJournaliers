# Export RJ modernisé — design

**Date :** 2026-07-02
**Périmètre :** refonte visuelle de l'export Excel des rapports journaliers
([excel_report.py](../../../excel_report.py)), pour qu'il soit une version
moderne du formulaire officiel de l'employeur, tout en conservant le
regroupement par employé propre à l'app.

## Objectif

Les fichiers `RJ …xlsx` fournis (formulaire officiel de l'employeur) servent de
référence. L'export doit reprendre **la mise en page et l'esprit** de ce
formulaire (en-tête projet, bloc température/conditions, tableau des heures,
zone commentaires, blocs de signature), mais :

- avec un style visuel moderne et épuré (accent teal Ondel, hairlines légères) ;
- en **ne montrant que les données réellement saisies par l'app** — aucune
  colonne officielle non alimentée ;
- en conservant la **structure groupée par employé** de l'app
  (nom → activités → plages horaires → ligne Total).

## Décisions arrêtées

| Sujet | Décision |
|---|---|
| Intention | Reprendre le formulaire officiel, modernisé |
| Champs officiels non saisis (Code Empl., No Contrat/ligne, Réf. Interne, Code Activité, Pu/Co, Mat. O/N, Surv. Client) | **Retirés** de l'export |
| Blocs de signature « Revu par / Approuvé par » | **Conservés**, vides (remplis à la main) |
| Style d'en-tête | Bandeau teal (logo + « Rapport journalier ») |
| Activité unique sans plages (saisie directe TR/TS) | **Structure groupée conservée** (nom / activité / Total) — pas de fusion |
| Portée | Export journée **et** hebdomadaire, même style |

## Périmètre des données

Champs disponibles et utilisés (issus du modèle de [reports.py](../../../reports.py)) :

- **Projet / jour** : No projet, adresse, date (jour + date longue FR).
- **Par quart** (`Jour`/`Soir`/`Nuit`) : responsable (≈ contremaître),
  température AM/PM, conditions atmosphériques, note du quart, personnel,
  équipements.
- **Par employé × activité** : heures TR/TS, plages horaires (début–fin, type),
  prime (numérique), commentaire (≈ « Travaux effectués »), heures
  d'équipement, codes d'équipement.

Hors périmètre : tous les champs officiels que l'app ne saisit pas (voir tableau).

## Mise en page d'une feuille (une journée)

Ordre vertical, largeur = tableau du personnel (colonne la plus large) :

1. **Bandeau titre** (fond teal `#0999AA`, texte blanc) : logo Ondel, titre
   « Rapport journalier », et à droite `Projet <no>` + pagination.
2. **Bloc méta jour** (fond blanc) : Date, Adresse. Ces champs sont au niveau
   jour/projet.
3. **Par quart rempli** (`_quart_total > 0`), dans l'ordre Jour → Soir → Nuit :
   - **Bandeau de quart** (fond teal foncé, texte blanc) : « Quart <nom> »,
     « Resp. : <responsable ou exportateur> », et le bloc
     **Température AM/PM + Conditions** (les conditions comme libellés séparés).
     Pour le cas courant à un seul quart, l'ensemble en-tête + bandeau donne
     l'allure de la maquette validée.
   - **Note** du quart si présente.
   - **Tableau du personnel** groupé par employé (voir ci-dessous).
   - **Tableau des équipements** si présents (mêmes règles, sans colonnes
     Hrs éq./Code éq.).
4. **Total de la journée** : ligne en gras, totaux TR / TS (et Hrs éq.),
   séparée par un filet teal.
5. **Légende des codes d'équipement** (conservée : BT, C, D, É, G, N…), car
   l'app saisit ces codes.
6. **Commentaires / plaintes / suggestions** : libellé + zone vide (cadre).
7. **Blocs de signature** : « Revu par » et « Approuvé par » côte à côte, lignes
   vides.
8. **Estampille** : « Exporté par <nom> · <date longue> » en pied, discret.

### Tableau du personnel (structure groupée conservée)

Colonnes : `Employé / activité | Plage | T.R. | T.S. | Hrs éq. | Code éq. |
Prime | Travaux effectués`.

- Ligne d'en-tête (fond teal foncé).
- Pour chaque employé :
  - **Ligne du nom** (fond teal clair, fusionnée sur toute la largeur).
  - Pour chaque activité :
    - **Sous-ligne activité** (indentée), puis
    - une **ligne par plage** (début–fin, type TR/TS, heures dérivées) ; OU,
      en saisie directe, une ligne « directe » unique avec TR/TS.
  - **Ligne Total** de l'employé (gras, fond teal clair) : totaux TR/TS,
    Hrs éq., Codes éq. (joints), Prime, Commentaire/Travaux effectués.

Le tableau des équipements reprend la même structure avec les colonnes
`Véhicule / activité | Plage | T.R. | T.S. | Prime | Commentaire`.

## Palette et typographie

- Teal : `#0999AA` (bandeau titre), `#077A88` (bandeaux/en-têtes de tableau et
  libellés), bande claire `#EEF8F9` / `#F5FBFC`.
- Filets : gris clair `#D9E2E4` (hairline), filet teal pour le total du jour.
- Police : famille sans-serif (Calibri, cohérent avec l'existant openpyxl).
- Format des heures : `0.00`.

## Architecture (code)

Le module [excel_report.py](../../../excel_report.py) reste le seul responsable
de la présentation. **L'API publique est inchangée** :

- `build_day_workbook(projet, jour_name, day, exported_by)`
- `build_week_workbook(projet, jours, jours_order, exported_by)`
- `build_day_email(projet, jour_name, day, exported_by)`

Les fonctions internes évoluent :

- `_build_day_sheet` : nouvel ordre (bandeau titre → méta jour → quarts →
  total jour → légende → commentaires → signatures → estampille).
- Nouveaux helpers : `_title_band` (bandeau teal + logo + pagination),
  `_meta_block` (Date/Adresse), `_quart_header` (bandeau quart +
  température/conditions), `_day_total_row`, `_equip_legend`,
  `_comments_block`, `_signature_block`.
- `_write_resource_table` : conservé, en-têtes renommés (« Travaux effectués »),
  styles ajustés.
- `_quart_info` : réutilisé pour la ligne responsable ; température/conditions
  déplacées dans `_quart_header`.

`app.py` n'importe toujours pas `excel_report` au niveau module (import
paresseux dans les vues) — invariant conservé.

## Tests

[tests/test_excel_report.py](../../../tests/test_excel_report.py) recharge le
`.xlsx` et vérifie le contenu. À mettre à jour / ajouter :

- Le titre attendu passe de `RAPPORT JOURNALIER — ONDEL` à `Rapport journalier`
  (adapter `test_build_day_workbook_une_feuille_et_entete` et
  `test_build_day_workbook_jour_vide_sans_personnel`).
- Conserver les garanties existantes : une feuille par jour, No projet présent,
  regroupement nom/activité/Total, plages horaires, TR/TS/prime, responsable
  replié sur l'exportateur, largeurs de colonnes.
- **Nouveaux tests** : présence du bloc température/conditions, ligne
  « Total de la journée », légende des codes d'équipement, libellés
  « Commentaires / plaintes / suggestions », « Revu par » et « Approuvé par ».

## Hors périmètre

- Aucune modification du modèle de données ni de la saisie (app.py, reports.py).
- Pas d'ajout des champs officiels non saisis.
- Pas de changement de l'envoi courriel ni du nom de fichier.
