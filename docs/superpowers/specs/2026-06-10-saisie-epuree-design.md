# Design — Page de saisie épurée (Rapport Journalier Ondel)

Date : 2026-06-10
Statut : approuvé pour planification

## Objectif

Améliorer la fluidité de la première page (« Saisie hebdomadaire ») de l'app
Streamlit `app.py`. Deux frictions ont été identifiées par l'utilisateur :

- **③** La configuration des colonnes d'activité est cachée dans un expander et
  pilote pourtant les grilles : pas évident de savoir quoi remplir d'abord.
- **⑤** Personnel et Équipement sont deux grosses grilles séparées empilées :
  saisie longue, vision d'ensemble difficile.

Contraintes métier confirmées :
- L'**équipe** (personnel) et les **équipements** sont **stables** sur la
  semaine → se configurent une seule fois.
- Le **responsable** et le **quart** sont aussi stables (config de semaine),
  mais modifiables par jour au besoin.
- Les **activités** peuvent **varier d'un jour à l'autre** → choix par jour.

Direction retenue : **A · Épuré** (parmi 3 approches présentées). Config de
semaine en haut, sélecteur de jour sur place, **une seule grille combinée**.

## Portée

Dans la portée :
- Refonte de la page « Saisie hebdomadaire » (`page_saisie` / `_render_day` /
  `_empty_day` / `grid_editor`).
- Nouveau modèle de données en session (config de semaine + jours).
- Adaptateur de compatibilité vers l'export Excel existant.

Hors portée (inchangé) :
- L'export Excel lui-même (Synthèse, feuilles par jour, logo, totaux,
  suppression des lignes/colonnes vides).
- La météo automatique (géocodage + Open-Meteo) ; ses champs vivent désormais
  dans l'en-tête du jour, mais la logique ne change pas.
- La page « Données de référence » et la page « Export Excel ».
- Le thème, le logo, la couleur d'accent.
- La persistance des données (toujours en mémoire de session).

## Structure de la nouvelle page

1. **Bandeau Ondel** (inchangé).
2. **Ligne projet** : No Projet · Semaine du (+ propagation auto des dates) ·
   Adresse du chantier · bouton « 🌦️ Remplir la météo ». Sur une ligne compacte.
3. **⚙️ Configuration de la semaine** (encadré, repliable une fois rempli) :
   - 👷 Équipe (personnel) — multiselect depuis `ref.personnel`
   - 🚜 Équipements / véhicules — multiselect depuis `ref.vehicules`
   - Responsable (défaut semaine) · Quart de travail (défaut semaine)
4. **📌 Sélecteur de jour** (`st.segmented_control`, rendu sticky en CSS) avec
   le **total du jour** affiché à droite. On change de jour **sur place** ; seul
   le jour sélectionné est rendu.
5. **Zone du jour sélectionné** :
   - **📅 En-tête du jour** (compact) : date (auto), responsable et quart
     (pré-remplis depuis la config, modifiables), temp. AM/PM, conditions,
     description.
   - **🏗️ Activités du jour** : deux multiselects compacts (Activités depuis
     `ref.activites` ; Autres projets depuis `ref.autres_projets`), juste
     au-dessus de la grille. « 960 » est toujours présent. Limite : ≤ 7
     activités + ≤ 4 autres projets (capacité du gabarit de rapport).
   - **🕐 Grille d'heures combinée** (voir ci-dessous).
   - **Ligne de totaux** sous la grille (par colonne + total du jour).
   - **📝 Commentaires & revu par**.

## Modèle de données (session_state)

### Niveau semaine
```
config = {
    "responsable": str,        # défaut de la semaine
    "quart": str,              # défaut de la semaine
    "personnel": [str],        # roster équipe (libellés ref.personnel)
    "equipements": [str],      # roster équipements (libellés ref.vehicules)
}
```
`projet = {"no", "semaine", "adresse"}` (inchangé).

### Niveau jour (`jours[jour]`)
```
{
    "date": date | None,
    "responsable": str,        # défaut = config.responsable, surchargeable
    "quart": str,              # défaut = config.quart, surchargeable
    "temp_am": float | None,
    "temp_pm": float | None,
    "conditions": [str],
    "description": str,
    "activites": [str],        # activités choisies pour CE jour (≤ 7) ; vide par défaut
    "autres": [str],           # autres projets pour CE jour (≤ 4) ; vide par défaut
    "heures": { ressource: { libellé_colonne: float } },  # libellé_colonne ∈ {"960"} ∪ activites ∪ autres
    "prime": { ressource: float },
    "commentaire_ligne": { ressource: str },
    "commentaires": str,       # commentaires du jour
    "revu_par": str,
}
```
- `ressource` = le libellé d'une personne ou d'un équipement présent dans le
  roster. Le **type** (personnel/équipement) est déduit de la config (présence
  dans `config.personnel` vs `config.equipements`).
- Les heures sont stockées par ressource/colonne, indépendamment des colonnes
  affichées un jour donné. Retirer une ressource du roster masque ses heures
  (conservées en mémoire ; réapparaissent si on la remet).

## La grille d'heures combinée

- Une seule `st.data_editor`, **lignes fixes** (`num_rows="fixed"`) = roster
  (personnel d'abord, puis équipements).
- Colonnes :
  - **Ressource** (texte, `disabled`)
  - **Type** (👷 / 🚜, `disabled`)
  - **960** puis une colonne par activité du jour puis par autre projet du jour
    (`NumberColumn`, min 0, pas 0,5, format `%.2f`)
  - **Prime** (`NumberColumn`)
  - **Total** (ligne, `disabled`) — recalculé au rafraîchissement (pas à la
    frappe), cohérent avec le comportement actuel des totaux
  - **Commentaire** (`TextColumn`)
- À chaque interaction : on relit le `data_editor`, on réécrit `heures`,
  `prime`, `commentaire_ligne` du jour.
- Une **ligne de totaux** (somme par colonne + total du jour) est affichée
  dessous, recalculée à chaque rafraîchissement.

## Sélecteur de jour

- `st.segmented_control(JOURS, ...)` mémorisé en `session_state`, rendu sticky
  en haut via CSS (comme le bandeau).
- Le jour actif détermine la zone rendue. **Un seul jour rendu** par exécution
  → plus léger que les 7 onglets actuels (`st.tabs` rend les 7 simultanément).
- Le total du jour s'affiche à droite du sélecteur.

## Compatibilité avec l'export Excel

L'export (`build_workbook` et fonctions associées) reste **inchangé**. Un
**adaptateur** reconstruit, juste avant l'export, les structures historiques
attendues, pour chaque jour :

- `headers` : `{"h0": "960", "h1": activites[0], …, "a0": autres[0], …}`
  (activités du jour mappées sur les emplacements `h1..h7`, autres sur
  `a0..a3`).
- `pers` : DataFrame `["Nom"] + HOUR_KEYS + ["Prime","Commentaire"]`, une ligne
  par personne du roster, heures puisées dans `heures[ressource]` (960 → `h0`).
- `equip` : idem avec `["Véhicule"] + …` pour les équipements.
- Champs scalaires du jour (date, responsable, quart, temp, conditions,
  description, commentaires, revu_par) passés tels quels.

Ainsi la logique existante (feuille Synthèse, feuilles par jour, logo,
suppression des lignes/colonnes vides, totaux) fonctionne sans modification. La
limite ≤ 7 activités + ≤ 4 autres par jour découle de cette capacité.

## Impacts sur le code

- **Réécriture** : `_empty_day`, `init_state` (ajout de `config`), `page_saisie`,
  `_render_day`, `grid_editor` (devient une grille combinée pilotée par le
  roster), `_apply_week_dates` (inchangé sur le fond).
- **Ajout** : section « Configuration de la semaine » ; sélecteur de jour ;
  construction de la grille combinée ; adaptateur d'export
  (`_day_to_legacy(jour)` → `headers/pers/equip`).
- **Inchangé** : tout le bloc export Excel, la météo, les pages référence/export,
  le thème/CSS (ajout d'un style sticky pour le sélecteur).

## Critères de succès

- Configurer l'équipe/équipements une seule fois ; les 7 jours héritent des
  lignes.
- Choisir les activités par jour en quelques clics, sans expander caché.
- Saisir les heures d'un jour dans **une seule grille**, avec totaux visibles.
- Changer de jour sans remonter en haut de page.
- L'export Excel produit le **même résultat** qu'aujourd'hui pour des données
  équivalentes.

## Risques / compromis

- Total par ligne non « live » (mise à jour au rafraîchissement) — accepté.
- Refonte notable de la page de saisie, mais circonscrite (export et autres
  pages intacts).
- Capacité ≤ 7 activités + ≤ 4 autres par jour (héritée du gabarit).
