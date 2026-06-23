# Refonte du sélecteur de quarts

Date : 2026-06-23

## Problème

Le sélecteur de quarts actuel (`_render_quart_selector`, app.py) cumule trop d'éléments
(légende « Quart actif », bouton 🗑️ de suppression, `radio` horizontal, popover ＋ avec
selectbox de type + radio de source de copie + bouton confirmer). Reproches de l'utilisatrice :

- **Trop d'étapes pour ajouter** un quart (type + source + confirmer = 4 actions).
- **Encombré / peu esthétique**.
- **Mécanique de bascule** (radio) peu agréable.

## Contrainte clé

Il n'existe que **3 quarts possibles, fixes et ordonnés** : Jour · Soir · Nuit
(`QUART_NAMES`). Inutile de demander « quel type ajouter » : chaque quart a sa place fixe.

## Design retenu — rangée de 3 pastilles

Une seule rangée de 3 boutons pleine largeur, un par quart, toujours dans l'ordre Jour/Soir/Nuit :

- **Quart actif** : bouton `primary` (rempli, mis en avant).
- **Quart existant mais non actif** : bouton `secondary` → un clic bascule dessus.
- **Quart non créé (ghost)** : `st.popover` libellé « ＋ Nuit », style grisé/pointillé.
  À l'ouverture, deux boutons :
  - **« Copier depuis _[quart actif]_ »** (primaire, défaut) — copie essentielle conservée.
  - **« Vide »**.

  Source de copie = quart actif courant. Pour copier d'un autre quart, on bascule dessus d'abord.

→ Ajout en **2 clics max** (ouvrir le popover, choisir), vs 4 aujourd'hui. Bascule en **1 clic**.

## Suppression

**Aucune suppression dans l'UI** (décision utilisatrice). On retire le bouton 🗑️ et la
fonction `_remove_quart` (introduite dans le WIP non commité, non utilisée par ailleurs).

## Touch / CSS

Le conteneur `st.container(key="quart_box")` porte le CSS tactile. On remplace les règles
ciblant `div[role="radiogroup"]` par des règles sur les boutons (`stButton`/popover) du bloc :
hauteur min ≥ 44px, et style « ghost » (bordure pointillée, texte atténué) pour les popovers
d'ajout afin de distinguer visuellement les quarts non créés.

## Impact

- Modifié : `_render_quart_selector` (réécrit), CSS du bloc `.st-key-quart_box`.
- Supprimé : `_remove_quart`, usage de `del_quart_btn` / radio `active_quart` (la clé
  `active_quart_{jour}` reste utilisée comme état de session, pilotée par les boutons).
- Conservé : `_add_quart`, mécanique de `_pending_active_quart_{jour}`.
