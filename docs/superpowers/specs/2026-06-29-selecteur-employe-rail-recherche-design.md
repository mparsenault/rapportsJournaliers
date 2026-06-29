# Sélecteur d'employé : rail latéral avec recherche

**Date :** 2026-06-29
**Fichier touché :** `app.py` (étape « Saisie des heures » de `view_day_entry`, ~lignes 1316-1338)

## Problème

À l'étape « Saisie des heures », la ressource active se choisit via un `st.radio`
horizontal (`app.py:1331`). Deux irritants :

1. **Visuellement brut** — les boutons radio en ligne détonnent avec le style carte
   de l'app.
2. **Scale mal** — avec 8-15 employés + équipements, la ligne déborde et s'enroule,
   devient illisible.

## Solution retenue

Remplacer le radio horizontal par un layout **maître-détail** :

- **Rail latéral gauche** : champ de recherche + liste verticale et défilante des
  ressources. Chaque ligne montre l'icône (👷 personnel / 🚜 équipement), le nom, un
  point de statut (vert = des heures saisies, gris = aucune) et le total d'heures.
  La ressource sélectionnée est surlignée en sarcelle (`ONDEL_GREEN`).
- **Fiche à droite** : la carte de saisie existante (`_render_resource_card`),
  inchangée, pour la ressource sélectionnée.

Sur écran étroit (tablette), les colonnes Streamlit empilent naturellement le rail
au-dessus de la fiche.

## Comportement

### Recherche
- Un `st.text_input` au-dessus de la liste filtre les noms en direct (sous-chaîne,
  insensible à la casse/accents au minimum sur la casse — on garde simple : `casefold`).
- Un compteur sous le champ indique « N résultat(s) · X sur Y saisies » (Y = total
  ressources, X = nombre avec total > 0).
- Si la recherche ne correspond à rien : message discret « Aucune ressource ne
  correspond. » dans la zone de liste.

### Sélection
- La ressource active est mémorisée dans `st.session_state[sel_key]`
  (`sel_key = f"resource_sel_{jour}_{quart_name}"`), comme aujourd'hui.
- Chaque ligne du rail est un `st.button` (clé unique par ressource). Un clic règle
  `sel_key` sur ce nom et `st.rerun()`.
- **La recherche n'affecte pas la sélection** : si la personne sélectionnée est
  filtrée hors de la liste, sa fiche reste affichée à droite (validé avec
  l'utilisateur). On ne réinitialise la sélection que si elle ne fait plus partie
  du roster (ressource retirée à la config) — même garde qu'aujourd'hui
  (`app.py:1329-1330`).

### Liste défilante
- La liste est rendue dans un `st.container(height=...)` à hauteur fixe pour activer
  le défilement vertical quand il y a beaucoup de monde (au lieu de pousser la fiche
  vers le bas). Hauteur indicative : ~300 px.

## Implémentation (esquisse)

Dans la branche `else` (étape « saisie ») de `view_day_entry`, remplacer le bloc
`st.radio` (1326-1338) par :

```python
labels = [n for n, _t in full_roster]
by_label = {n: (n, t) for n, t in full_roster}
sel_key = f"resource_sel_{jour}_{quart_name}"
if st.session_state.get(sel_key) not in labels:
    st.session_state[sel_key] = labels[0]

col_rail, col_pane = st.columns([1, 2], gap="medium")

with col_rail:
    q = st.text_input("Rechercher", key=f"res_search_{jour}_{quart_name}",
                      placeholder="🔍 Rechercher une ressource…",
                      label_visibility="collapsed")
    done = sum(1 for n in labels if _resource_total(quart, n) > 0)
    filt = [n for n in labels if q.casefold() in n.casefold()] if q else labels
    st.caption(f"{len(filt)} résultat(s) · {done} sur {len(labels)} saisies")
    with st.container(height=300):
        if not filt:
            st.caption("Aucune ressource ne correspond.")
        for n in filt:
            _n, t = by_label[n]
            tot = _resource_total(quart, n)
            icon = "👷" if t == "P" else "🚜"
            status = "🟢" if tot > 0 else "⚪"
            label = f"{icon} {n} · {status} {tot:.1f} h"
            is_sel = (n == st.session_state[sel_key])
            if st.button(label, key=f"pick_{jour}_{quart_name}_{n}",
                         use_container_width=True,
                         type="primary" if is_sel else "secondary"):
                st.session_state[sel_key] = n
                st.rerun()

with col_pane:
    name, typ = by_label[st.session_state[sel_key]]
    icon = "👷" if typ == "P" else "🚜"
    st.markdown(f"##### {icon} {name} — {_resource_total(quart, name):.1f} h")
    _render_resource_card(jour, quart_name, quart, name, typ, all_activities)
```

Le surlignage de la ligne sélectionnée passe par `type="primary"` du bouton (sarcelle
via le CSS bouton primaire déjà en place). Le statut utilise des émojis 🟢/⚪ pour rester
simple sous Streamlit (pas de CSS de point dédié requis) ; à ajuster si on préfère un
rendu plus discret via CSS plus tard.

## Tests

Les tests existants utilisent `AppTest` et naviguent l'étape « saisie ». Points clés :

- Les `st.button` du rail sont représentables sous `AppTest` (`at.button(key=...)`),
  contrairement à `st.pills` — le commentaire existant (`app.py:1322-1325`) justifiait
  le choix du radio par cette contrainte ; les boutons la respectent aussi.
- **Adapter** tout test qui sélectionnait la ressource via `at.radio(key=sel_key)` :
  désormais c'est un clic de bouton `at.button(key=f"pick_{jour}_{quart_name}_{n}")`.
- Ajouter un test : taper une recherche filtre la liste (moins de boutons `pick_…`
  rendus) sans changer `sel_key`.
- Vérifier qu'aucune régression : la fiche de la ressource sélectionnée s'affiche
  toujours, l'enregistrement fonctionne.

## Hors périmètre

- Pas de changement à l'étape « config » (ajout du personnel/équipement).
- Pas de changement au modèle de données ni à `_render_resource_card`.
- Pas de tri/regroupement avancé (personnel vs équipement) — la liste garde l'ordre
  du roster. À envisager plus tard si souhaité.
