# Flux séquentiel Configuration → Saisie des heures

Date : 2026-06-23
Fichier touché : `app.py` (fonction `view_day_entry`, env. lignes 982-1228)

## Contexte

La saisie journalière (`view_day_entry`) présente actuellement deux onglets
Streamlit : `st.tabs(["⚙️ Configuration", "🕐 Saisie des heures"])`. L'utilisateur
bascule librement entre les deux. Le bouton **💾 Enregistrer** (écriture en base
via `save_report_from_state()`) est global, sous les deux onglets.

## Objectif

Remplacer les onglets par un **flux séquentiel en deux étapes** : on configure le
quart, on clique pour enregistrer et passer à la saisie des heures, puis on saisit.
Plus de notion d'onglets.

## Modèle de navigation

État d'étape stocké dans `st.session_state` :

```python
step = st.session_state.setdefault("day_entry_step", "config")  # "config" | "saisie"
```

Un seul écran est rendu à la fois (pas de tabs). L'état est **réinitialisé à
`"config"`** au moment où l'on entre dans une journée depuis le tableau de bord
(bouton `go_{jour}`, `view_dashboard`, env. ligne 897-899) :

```python
if st.button(label, key=f"go_{jour}", ...):
    st.session_state.view = "day_entry"
    st.session_state.day_entry_step = "config"
    ...
```

Le sélecteur de quart (`_render_quart_selector`) et la résolution du quart courant
(`_current_quart_name`, `day["quarts"][quart_name]`) restent en tête de
`view_day_entry`, exécutés avant l'aiguillage d'étape. Le sélecteur de quart est
**affiché uniquement à l'étape Configuration**.

## Étape 1 — Configuration

Rendu lorsque `step == "config"` :

- Sélecteur de quart (`_render_quart_selector`).
- Contenu actuel de `tab_config` : titre « Configuration du quart », colonnes
  Activités / Météo, puis bloc Personnel présent / Équipements.
- **Barre du bas** (remplace l'usage global du bouton Enregistrer pour cette étape) :
  - colonne gauche : indicateur d'état
    - si `st.session_state.get("dirty")` → `st.warning("⚠️ Modifications non enregistrées…")`
    - sinon → `st.caption("✓ Toutes les modifications sont enregistrées.")`
  - colonne droite : bouton primaire **« 💾 Enregistrer et saisir les heures → »**.
    Au clic :
    ```python
    ok, msg = save_report_from_state()
    if ok:
        st.session_state.day_entry_step = "saisie"
        st.rerun()
    else:
        st.error(msg)
    ```
    En cas d'échec, on reste sur la Configuration et l'erreur est affichée.

## Étape 2 — Saisie des heures

Rendu lorsque `step == "saisie"` :

- **Barre du haut** :
  - bouton **« ← Retour à la configuration »** → `st.session_state.day_entry_step =
    "config"; st.rerun()`. Pas d'écriture en base : les données vivent déjà dans
    `session_state`.
  - libellé du quart courant affiché en contexte (ex. nom du quart).
- Contenu actuel de `tab_saisie` : entête « 🕐 Saisie des heures » + recherche de
  ressource, grille des heures (par ressource : heures par activité, prime,
  commentaire, total), `st.divider()`, « 📝 Note du quart ».
- **Barre du bas inchangée** : indicateur dirty (gauche) + bouton **💾 Enregistrer**
  (droite) qui appelle `save_report_from_state()` et affiche le résultat.

## Nettoyage

- Supprimer le bloc CSS des onglets (commentaire « Onglets Configuration / Saisie :
  surlignage teal… », env. ligne 819).
- Mettre à jour les messages d'info de l'étape Saisie qui référencent « l'onglet
  Configuration » → « la configuration » :
  - « 💡 Commencez par sélectionner le **personnel / équipements** dans la
    configuration. » (env. ligne 1167)
  - « 💡 Sélectionnez une ou plusieurs **Activités** dans la configuration. »
    (env. ligne 1169)

## Hors périmètre (YAGNI)

- Pas de barre de progression / fil d'Ariane visuel multi-étapes.
- Pas de validation bloquante avant de passer à la saisie (on peut enregistrer une
  config partielle ; les messages d'info de l'étape Saisie guident déjà
  l'utilisateur si activités ou ressources manquent).
- Pas de changement au modèle de données ni à la persistance.

## Critères de réussite

- Aucun `st.tabs` dans `view_day_entry`.
- Entrer dans une journée affiche la Configuration ; le bouton « 💾 Enregistrer et
  saisir les heures → » enregistre puis bascule vers la grille des heures.
- « ← Retour à la configuration » ramène à l'étape 1 sans perdre les saisies en cours.
- Le bouton 💾 Enregistrer final n'apparaît qu'à l'étape Saisie.
- Les tests existants (`tests/test_ui.py`) passent (mis à jour si nécessaire pour
  refléter l'absence d'onglets).
