# Prime en codes (au lieu d'un montant $) — design

**Date :** 2026-07-02
**Périmètre :** remplacer la prime numérique (`Prime ($)`) par une sélection de
**codes de prime** (I, S, G, T, A, Pa, P, H, R, Pu, Co), en calquant exactement
le patron existant des **codes d'équipement** (`equip_codes`).

## Objectif

Dans le domaine métier, la prime d'un employé est un (ou plusieurs) **code(s)**,
pas un montant. L'app saisit aujourd'hui un montant via
`number_input("Prime ($)")` et le stocke en numérique. On remplace cela par une
sélection multiple de codes, stockée en tableau de texte, affichée telle quelle
dans l'export.

## Décisions arrêtées

| Sujet | Décision |
|---|---|
| Plusieurs codes par employé | **Oui** — sélection multiple (pastilles), comme l'équipement |
| Ancienne colonne `prime numeric` | **Supprimée** (nettoyage destructif ; anciennes primes numériques abandonnées) |
| Nom de la clé / colonne | `prime_codes` (parallèle à `equip_codes`) |

## Codes de prime

Nouvelle constante dans `app.py`, sur le modèle de `EQUIP_CODES` :

```python
PRIME_CODES = [
    ("I", "Intempérie"), ("S", "Surtemps"), ("G", "Galvanisé"),
    ("T", "Poste HT"), ("A", "Peinture"), ("Pa", "Panier"),
    ("P", "Préavis"), ("H", "Hauteur"), ("R", "Repas"),
    ("Pu", "Puissance"), ("Co", "Contrôle"),
]
PRIME_CODE_VALUES = [c for c, _ in PRIME_CODES]
_PRIME_CODE_LABELS = dict(PRIME_CODES)

def _prime_code_label(code):
    return f"{code} — {_PRIME_CODE_LABELS.get(code, code)}"
```

## Modèle de données

Le quart porte désormais `prime_codes: {name: [codes]}` (au lieu de
`prime: {name: float}`), exactement comme `equip_codes`.

- `app._empty_quart()` : remplacer `"prime": {}` par `"prime_codes": {}`.

## Saisie (app.py, carte de ressource ~1322-1331)

Remplacer le bloc `number_input("Prime ($)")` par des pastilles multi, calquées
sur « Équipement » (~1307) :

```python
pc_key = f"p_{jour}_{quart_name}_{name}"
if pc_key not in st.session_state:
    st.session_state[pc_key] = list(quart["prime_codes"].get(name, []))
codes = cp.pills("Prime", PRIME_CODE_VALUES, selection_mode="multi",
                 format_func=_prime_code_label, key=pc_key, on_change=_mark_dirty)
if codes:
    quart["prime_codes"][name] = list(codes)
elif name in quart["prime_codes"]:
    del quart["prime_codes"][name]
```

La colonne du commentaire (`cc`) et la mise en page en deux colonnes
(`cp, cc = st.columns([1, 3])`) restent. La clé widget reste préfixée `p_`
(déjà gérée par la purge de `_clear_quart_widget_state`).

## Persistance (reports.py)

**Schéma** — ajouter la colonne tableau et retirer la colonne numérique
(migrations idempotentes ajoutées à `_DDL_STATEMENTS`, après celles
d'`equip_codes`) :

```sql
alter table report_lines add column if not exists prime_codes text[] not null default '{}';
alter table report_lines drop column if exists prime;
```

**Écriture** (`save_report`, ~339-351) : lire `quart.get("prime_codes")`, écrire
la colonne `prime_codes` (tableau), sur le modèle d'`equip_codes`. La condition
de la boucle `for resource_name in set(...)` utilise `set(prime_codes)` au lieu
de `set(prime)`.

**Lecture** (`load_report`, ~420-442) : sélectionner `prime_codes` (au lieu de
`prime`), reconstruire `prime_codes = {name: list(codes)}`, et exposer
`"prime_codes": prime_codes` dans le quart (retirer `"prime": prime`).

## Export (excel_report.py)

- `_write_resource_table` (~381, 429, 431) : lire `quart.get("prime_codes")` ;
  la colonne « Prime » de la ligne Total affiche les codes joints
  (`", ".join(prime_codes.get(name) or []) or None`) au lieu du nombre.
- La légende « Code de prime » (déjà présente, `_PRIME_LEGEND`) est conservée.
- `_legacy_day` (app.py ~493) : `rec["Prime"] = ", ".join(quart["prime_codes"].get(name) or [])`.

## Tests à mettre à jour / ajouter

- `tests/test_model.py:11` : `q["prime"] == {}` → `q["prime_codes"] == {}`.
- `tests/test_model.py:26` : `q["prime"] = {"Mathis": 2.0}` → `q["prime_codes"] = {"Mathis": ["H"]}` (adapter l'assertion associée).
- `tests/test_ui.py` : occurrences `"prime": {}` dans les quarts factices → `"prime_codes": {}` ; `test_day_prime_inline` (301-305) réécrit pour les pastilles (sélection d'un code → `prime_codes["Alice"] == ["<code>"]`) ; `qs["prime"] == {}` (571) → `qs["prime_codes"] == {}`.
- `tests/test_excel_report.py` : `_day_rempli` (22) `q["prime"] = {...: 25.0}` → `q["prime_codes"] = {...: ["S"]}` ; `test_build_day_workbook_heures_et_prime_presentes` (128-133) vérifie la présence du code (ex. `"S"`) au lieu de `25.0`.
- **Nouveau** : test de persistance (`test_reports.py` si présent) pour l'aller-retour `prime_codes` (sinon couvert par test_model/test_ui).

## Hors périmètre

- Pas de conversion des anciennes primes numériques en codes (abandonnées).
- Pas de changement de la mise en page de l'export (déjà alignée sur le modèle cible).
- Pas de total/somme de primes (ce sont des codes, pas des montants).

## Invariants conservés

- `app.py` n'importe pas `excel_report` au niveau module.
- API publique d'`excel_report` inchangée.
- Patron `equip_codes` suivi à l'identique (cohérence de saisie et de code).
