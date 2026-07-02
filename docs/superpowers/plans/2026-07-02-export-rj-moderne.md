# Export RJ modernisé — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refondre la présentation de l'export Excel des rapports journaliers pour qu'il soit une version moderne du formulaire officiel, en conservant le regroupement par employé de l'app.

**Architecture:** Toute la refonte tient dans [excel_report.py](../../../excel_report.py) : on ajoute une palette/typographie modernes et des helpers de section (bandeau titre, méta, bandeau de quart, total du jour, légende, commentaires, signatures), et on recâble `_build_day_sheet` pour les enchaîner de haut en bas. L'API publique (`build_day_workbook`, `build_week_workbook`, `build_day_email`) et `build_week_workbook` (qui réutilise `_build_day_sheet`) restent inchangées.

**Tech Stack:** Python 3.9, openpyxl, pytest. Les tests rechargent le `.xlsx` produit et vérifient le contenu (style existant de [tests/test_excel_report.py](../../../tests/test_excel_report.py)).

## Global Constraints

- `app.py` NE DOIT PAS importer `excel_report` au niveau module ; `excel_report` importe `app` (invariant existant, à conserver).
- L'API publique ne change pas : `build_day_workbook(projet, jour_name, day, exported_by="")`, `build_week_workbook(projet, jours, jours_order, exported_by="")`, `build_day_email(projet, jour_name, day, exported_by="")`.
- Ne montrer que les données saisies par l'app ; aucune colonne officielle non alimentée.
- Conserver la structure groupée (nom → activité → plages → Total), même pour une activité unique.
- Format des heures : `0.00`. Police : Calibri. Accent teal : `#0999AA` (titre), `#077A88` (en-têtes), bande claire `#EEF8F9` / `#F5FBFC`.
- Un onglet Excel par jour rempli pour l'export hebdomadaire.
- Lancer les tests avec `.venv/bin/pytest`.

---

### Task 1 : Palette moderne + bandeau titre + bloc méta

**Files:**
- Modify: `excel_report.py` (constantes de style ; nouveaux helpers `_title_band`, `_meta_block`, `_stamp` ; refonte du haut de `_build_day_sheet`)
- Test: `tests/test_excel_report.py`

**Interfaces:**
- Consumes : `app.LOGO_PATH`, `app.fr_date_long`, `app._day_quart_names`, `app._quart_total`, helpers existants `_add_logo`, `_safe_title`, `_apply_widths`, `_banner`, `_quart_info`, `_write_resource_table`.
- Produces :
  - `_title_band(ws, projet) -> int` (renvoie la prochaine ligne libre)
  - `_meta_block(ws, row, projet, jour_name, day) -> int`
  - `_stamp(ws, exported_by) -> None`

- [ ] **Step 1 : Mettre à jour les tests dépendant de l'ancien titre**

Dans `tests/test_excel_report.py`, remplacer les deux assertions sur l'ancien titre :

```python
def test_build_day_workbook_une_feuille_et_entete():
    buf = excel_report.build_day_workbook(_projet(), "Lundi", _day_rempli(), "Test User")
    wb = openpyxl.load_workbook(buf)
    assert wb.sheetnames == ["Lundi"]
    txt = _all_text(wb["Lundi"])
    assert "Rapport journalier" in txt
    assert "12345" in txt                      # No Projet (bandeau titre)
    assert "123 rue Principale" in txt         # adresse (bloc méta)
    assert "Mathis Lajeunesse" in txt          # ligne de personnel
    assert "Exporté par Test User" in txt      # estampille


def test_build_day_workbook_jour_vide_sans_personnel():
    buf = excel_report.build_day_workbook(_projet(), "Lundi", _day_vide(), "")
    wb = openpyxl.load_workbook(buf)
    txt = _all_text(wb["Lundi"])
    assert "Rapport journalier" in txt
    assert "Mathis" not in txt
```

- [ ] **Step 2 : Lancer ces tests pour les voir échouer**

Run : `.venv/bin/pytest tests/test_excel_report.py::test_build_day_workbook_une_feuille_et_entete -v`
Expected : FAIL (l'ancien titre `RAPPORT JOURNALIER — ONDEL` est produit ; `Rapport journalier` absent ; adresse absente du bloc méta).

- [ ] **Step 3 : Ajouter la palette/typographie modernes**

Dans `excel_report.py`, après le bloc de styles existant (juste après `_HOURS_FMT = "0.00"`), ajouter :

```python
_BAND_LT = "F5FBFC"          # bande claire secondaire
_SIGN_LINE = "9FB0B2"        # ligne de signature
_F_SUB = Font(name="Calibri", size=9, color="FFFFFF")
_F_SIGN = Font(name="Calibri", size=9, color="5F6E70")
_F_LEGEND = Font(name="Calibri", size=8, color="5F6E70")
_RIGHT = Alignment(horizontal="right", vertical="center")
```

Et porter le titre à 18 pt (remplacer la ligne `_F_TITLE = ...`) :

```python
_F_TITLE = Font(name="Calibri", size=18, bold=True, color="FFFFFF")
```

- [ ] **Step 4 : Écrire `_title_band`, `_meta_block`, `_stamp`**

Ajouter dans `excel_report.py` (avant `_build_day_sheet`) :

```python
def _title_band(ws, projet):
    """Bandeau titre teal (lignes 1-2) : logo, 'Rapport journalier' + sous-titre,
    et à droite 'Projet <no>' + pagination. Renvoie la prochaine ligne libre."""
    for r in (1, 2):
        for c in range(1, _NCOL + 1):
            ws.cell(row=r, column=c).fill = _FILL_TITLE
    ws.merge_cells(start_row=1, end_row=1, start_column=2, end_column=_NCOL - 1)
    t = ws.cell(row=1, column=2, value="Rapport journalier")
    t.font = _F_TITLE
    t.alignment = _LEFT
    sub = ws.cell(row=2, column=2, value="Ondel")
    sub.font = _F_SUB
    sub.alignment = _LEFT
    p = ws.cell(row=1, column=_NCOL, value=f"Projet {projet.get('no') or ''}".strip())
    p.font = _F_SUB
    p.alignment = _RIGHT
    pg = ws.cell(row=2, column=_NCOL, value="Page 1 de 1")
    pg.font = _F_SUB
    pg.alignment = _RIGHT
    ws.row_dimensions[1].height = 30
    ws.row_dimensions[2].height = 16
    _add_logo(ws)
    return 4  # ligne 3 laissée vide, méta démarre en 4


def _meta_block(ws, row, projet, jour_name, day):
    """Bloc méta jour : Date, Adresse. Renvoie la prochaine ligne libre."""
    d = day.get("date")
    date_txt = app.fr_date_long(d) if d else ""
    ws.cell(row=row, column=1, value="Date :").font = _F_LABEL
    ws.cell(row=row, column=2, value=f"{jour_name} {date_txt}".strip())
    row += 1
    ws.cell(row=row, column=1, value="Adresse :").font = _F_LABEL
    ws.cell(row=row, column=2, value=projet.get("adresse") or "")
    return row + 2  # une ligne vide avant le premier quart


def _stamp(ws, exported_by):
    """Estampille discrète en pied de feuille."""
    last = ws.max_row + 2
    cell = ws.cell(row=last, column=1, value=f"Exporté par {exported_by or '—'}")
    cell.font = Font(name="Calibri", size=8, italic=True, color="6B7B7E")
```

- [ ] **Step 5 : Recâbler le haut de `_build_day_sheet`**

Remplacer, dans `_build_day_sheet`, tout le bloc allant de `ws.title = ...` jusqu'à `row = 7` (inclus la création du titre, des lignes No Projet/Date/Adresse) par :

```python
def _build_day_sheet(ws, projet, jour_name, day, exported_by=""):
    """Écrit le rapport d'une journée dans la feuille `ws`."""
    ws.title = _safe_title(jour_name)
    _apply_widths(ws, _PERS_COLS)

    row = _title_band(ws, projet)
    row = _meta_block(ws, row, projet, jour_name, day)

    for qname in app._day_quart_names(day):
        quart = day["quarts"][qname]
        if app._quart_total(quart) <= 0:
            continue
        _banner(ws, row, _quart_info(qname, quart, exported_by))
        row += 1
        if quart.get("description"):
            ws.merge_cells(start_row=row, end_row=row, start_column=1, end_column=_NCOL)
            ws.cell(row=row, column=1,
                    value=f"Note : {quart['description']}").alignment = _LEFT
            row += 1

        if quart.get("personnel"):
            row = _write_resource_table(ws, row, quart, quart["personnel"],
                                        _PERS_COLS, with_equip=True)
            row += 1
        if quart.get("equipements"):
            row = _write_resource_table(ws, row, quart, quart["equipements"],
                                        _EQUIP_COLS, with_equip=False)
            row += 1
        row += 1

    _stamp(ws, exported_by)
```

(Le reste du fichier — `_write_resource_table`, `build_*` — est inchangé à ce stade. L'ancienne estampille inline en fin de fonction est supprimée au profit de `_stamp`.)

- [ ] **Step 6 : Lancer toute la suite excel_report**

Run : `.venv/bin/pytest tests/test_excel_report.py -v`
Expected : PASS (tous les tests, y compris grouping/plages/prime/largeurs/hebdo/email).

- [ ] **Step 7 : Commit**

```bash
git add excel_report.py tests/test_excel_report.py
git commit -m "feat(export): bandeau titre teal + bloc méta modernisés"
```

---

### Task 2 : Bandeau de quart avec température et conditions

**Files:**
- Modify: `excel_report.py` (nouveau `_quart_header` ; remplace `_banner(...)` dans `_build_day_sheet`)
- Test: `tests/test_excel_report.py`

**Interfaces:**
- Consumes : `_banner`, `_quart_info`, `_FILL_BAND`, `_F_LABEL`, `_LEFT`, `_NCOL`.
- Produces : `_quart_header(ws, row, qname, quart, exported_by="") -> int`.

- [ ] **Step 1 : Écrire le test du bloc température/conditions**

Ajouter dans `tests/test_excel_report.py` :

```python
def test_build_day_workbook_temperature_et_conditions():
    buf = excel_report.build_day_workbook(_projet(), "Lundi", _day_rempli(), "")
    txt = _all_text(openpyxl.load_workbook(buf)["Lundi"])
    assert "Température" in txt
    assert "Ensoleillé" in txt        # condition saisie (_day_rempli)
    assert "12" in txt                # temp_am = 12.0
```

- [ ] **Step 2 : Lancer le test pour le voir échouer**

Run : `.venv/bin/pytest tests/test_excel_report.py::test_build_day_workbook_temperature_et_conditions -v`
Expected : FAIL — `_quart_info` place actuellement la température/condition sur la même ligne de bandeau, mais vérifions : si déjà présent, forcer l'échec en attendant le libellé « Température : ». (Le bandeau actuel affiche `Temp. AM 12.0 / PM —`, pas `Température`.) FAIL sur `"Température" in txt`.

- [ ] **Step 3 : Écrire `_quart_header`**

Ajouter dans `excel_report.py` (avant `_build_day_sheet`) :

```python
def _quart_header(ws, row, qname, quart, exported_by=""):
    """Bandeau de quart (teal foncé) : 'Quart X · Resp. Y', puis une sous-ligne
    Température AM/PM + Conditions (bande claire). Renvoie la prochaine ligne."""
    resp = quart.get("responsable") or exported_by
    label = f"Quart {qname}"
    if resp:
        label += f"    ·    Resp. : {resp}"
    _banner(ws, row, label)
    row += 1

    tam, tpm = quart.get("temp_am"), quart.get("temp_pm")
    conds = ", ".join(quart.get("conditions") or [])
    parts = []
    if tam is not None or tpm is not None:
        a = tam if tam is not None else "—"
        p = tpm if tpm is not None else "—"
        parts.append(f"Température : AM {a} / PM {p}")
    if conds:
        parts.append(f"Conditions : {conds}")
    if parts:
        ws.merge_cells(start_row=row, end_row=row, start_column=1, end_column=_NCOL)
        cell = ws.cell(row=row, column=1, value="    ·    ".join(parts))
        cell.font = _F_LABEL
        cell.fill = _FILL_BAND
        cell.alignment = _LEFT
        ws.row_dimensions[row].height = 18
        row += 1
    return row
```

- [ ] **Step 4 : Utiliser `_quart_header` dans `_build_day_sheet`**

Dans la boucle des quarts de `_build_day_sheet`, remplacer les deux lignes :

```python
        _banner(ws, row, _quart_info(qname, quart, exported_by))
        row += 1
```

par :

```python
        row = _quart_header(ws, row, qname, quart, exported_by)
```

Simplifier `_quart_info` pour qu'il ne produise plus que la partie responsable (la température/les conditions passent dans `_quart_header`). Remplacer le corps de `_quart_info` par :

```python
def _quart_info(qname, quart, exported_by=""):
    parts = [f"Quart {qname}"]
    resp = quart.get("responsable") or exported_by
    if resp:
        parts.append(f"Resp. : {resp}")
    return "    ·    ".join(parts)
```

(Conservé pour compatibilité/appels éventuels ; `_quart_header` fabrique désormais son propre libellé.)

- [ ] **Step 5 : Lancer la suite complète**

Run : `.venv/bin/pytest tests/test_excel_report.py -v`
Expected : PASS (dont `test_build_day_workbook_responsable_repli_sur_exportateur` : `Resp. : Marie-Pier Arsenault` toujours présent, et le nouveau test température/conditions).

- [ ] **Step 6 : Commit**

```bash
git add excel_report.py tests/test_excel_report.py
git commit -m "feat(export): bandeau de quart avec température et conditions"
```

---

### Task 3 : En-tête de tableau « Travaux effectués »

**Files:**
- Modify: `excel_report.py` (`_PERS_COLS`, `_col_width`)
- Test: `tests/test_excel_report.py`

**Interfaces:**
- Consumes : `_write_resource_table` (inchangé), `_col_width`.
- Produces : `_PERS_COLS` avec dernière colonne `"Travaux effectués"`.

- [ ] **Step 1 : Écrire le test de l'en-tête renommé**

Ajouter dans `tests/test_excel_report.py` :

```python
def test_build_day_workbook_entete_travaux_effectues():
    buf = excel_report.build_day_workbook(_projet(), "Lundi", _day_rempli(), "")
    txt = _all_text(openpyxl.load_workbook(buf)["Lundi"])
    assert "Travaux effectués" in txt
```

- [ ] **Step 2 : Lancer le test pour le voir échouer**

Run : `.venv/bin/pytest tests/test_excel_report.py::test_build_day_workbook_entete_travaux_effectues -v`
Expected : FAIL — la colonne s'appelle encore `Commentaire`.

- [ ] **Step 3 : Renommer la colonne personnel et régler sa largeur**

Dans `excel_report.py`, remplacer :

```python
_PERS_COLS = ["Nom / Activité", "Plage", "TR", "TS", "Hrs Éq.", "Code Éq.", "Prime", "Commentaire"]
```

par :

```python
_PERS_COLS = ["Nom / Activité", "Plage", "TR", "TS", "Hrs Éq.", "Code Éq.", "Prime", "Travaux effectués"]
```

Dans `_col_width`, ajouter l'entrée pour la nouvelle colonne (garder `"Commentaire": 30` pour le tableau des équipements) :

```python
        "Commentaire": 30, "Travaux effectués": 30,
```

- [ ] **Step 4 : Lancer la suite complète**

Run : `.venv/bin/pytest tests/test_excel_report.py -v`
Expected : PASS (le regroupement nom/activité/Total et les largeurs restent valides ; `_EQUIP_COLS` garde `Commentaire`).

- [ ] **Step 5 : Commit**

```bash
git add excel_report.py tests/test_excel_report.py
git commit -m "feat(export): colonne 'Travaux effectués' (terminologie officielle)"
```

---

### Task 4 : Ligne « Total de la journée »

**Files:**
- Modify: `excel_report.py` (`_quart_hour_totals`, `_day_total_row`, boucle de `_build_day_sheet`)
- Test: `tests/test_excel_report.py`

**Interfaces:**
- Consumes : `app._norm_entry`, `_write_row`, `_THIN`, `_TEAL`, `_HOURS_FMT`, `_NCOL`.
- Produces :
  - `_quart_hour_totals(quart) -> (tr: float, ts: float, eq: float)`
  - `_day_total_row(ws, row, tr, ts, eq) -> int`

- [ ] **Step 1 : Écrire le test de la ligne total du jour**

Ajouter dans `tests/test_excel_report.py` :

```python
def test_build_day_workbook_total_de_la_journee():
    q = app._empty_quart()
    q["personnel"] = ["A", "B"]
    q["heures"] = {"A": {"Excavation": {"TR": 4.0, "TS": 0.0}},
                   "B": {"Excavation": {"TR": 4.0, "TS": 1.0}}}
    day = {"date": date(2026, 6, 22), "quarts": {"Jour": q}}
    ws = openpyxl.load_workbook(
        excel_report.build_day_workbook(_projet(), "Lundi", day, ""))["Lundi"]
    # Trouver la ligne « Total de la journée » et vérifier ses totaux TR/TS.
    row = next(r for r in range(1, ws.max_row + 1)
               if ws.cell(r, 1).value == "Total de la journée")
    assert ws.cell(row, 3).value == 8.0    # TR : 4 + 4
    assert ws.cell(row, 4).value == 1.0    # TS : 0 + 1
```

- [ ] **Step 2 : Lancer le test pour le voir échouer**

Run : `.venv/bin/pytest tests/test_excel_report.py::test_build_day_workbook_total_de_la_journee -v`
Expected : FAIL — `StopIteration` (aucune ligne « Total de la journée »).

- [ ] **Step 3 : Écrire les helpers de total**

Ajouter dans `excel_report.py` (avant `_build_day_sheet`) :

```python
def _quart_hour_totals(quart):
    """Totaux (TR, TS, heures d'équipement) d'un quart, dérivés des heures saisies."""
    tr = ts = 0.0
    for acts in (quart.get("heures") or {}).values():
        for entry in (acts or {}).values():
            norm = app._norm_entry(entry)
            tr += float(norm.get("TR") or 0)
            ts += float(norm.get("TS") or 0)
    eq = sum(float(v) for v in (quart.get("equip_hours") or {}).values() if v is not None)
    return tr, ts, eq


def _day_total_row(ws, row, tr, ts, eq):
    """Ligne 'Total de la journée' (gras, filet teal au-dessus). Prochaine ligne."""
    row += 1  # espace avant le total
    vals = ["Total de la journée", None, tr, ts, (eq or None)] + [None] * (_NCOL - 5)
    _write_row(ws, row, vals, bold=True, fmt=_HOURS_FMT)
    top = Side(style="medium", color=_TEAL)
    for c in range(1, _NCOL + 1):
        ws.cell(row=row, column=c).border = Border(
            left=_THIN, right=_THIN, top=top, bottom=_THIN)
    return row + 1
```

- [ ] **Step 4 : Accumuler et écrire le total dans `_build_day_sheet`**

Dans `_build_day_sheet`, initialiser les accumulateurs avant la boucle des quarts :

```python
    day_tr = day_ts = day_eq = 0.0
    for qname in app._day_quart_names(day):
```

À la fin du corps de boucle (juste avant le `row += 1` final de la boucle), ajouter :

```python
        tr, ts, eq = _quart_hour_totals(quart)
        day_tr += tr
        day_ts += ts
        day_eq += eq
```

Après la boucle (avant `_stamp`), ajouter :

```python
    row = _day_total_row(ws, row, day_tr, day_ts, day_eq)
```

- [ ] **Step 5 : Lancer la suite complète**

Run : `.venv/bin/pytest tests/test_excel_report.py -v`
Expected : PASS.

- [ ] **Step 6 : Commit**

```bash
git add excel_report.py tests/test_excel_report.py
git commit -m "feat(export): ligne 'Total de la journée'"
```

---

### Task 5 : Légende équipement + commentaires + signatures

**Files:**
- Modify: `excel_report.py` (`_equip_legend`, `_comments_block`, `_signature_block`, fin de `_build_day_sheet`)
- Test: `tests/test_excel_report.py`

**Interfaces:**
- Consumes : `_F_LABEL`, `_F_LEGEND`, `_F_SIGN`, `_LEFT`, `_NCOL`, `_GREY`, `_SIGN_LINE`.
- Produces :
  - `_equip_legend(ws, row) -> int`
  - `_comments_block(ws, row) -> int`
  - `_signature_block(ws, row) -> int`

- [ ] **Step 1 : Écrire les tests des trois blocs de bas de page**

Ajouter dans `tests/test_excel_report.py` :

```python
def test_build_day_workbook_bas_de_page():
    buf = excel_report.build_day_workbook(_projet(), "Lundi", _day_rempli(), "")
    txt = _all_text(openpyxl.load_workbook(buf)["Lundi"])
    assert "Codes d'équipement" in txt
    assert "Commentaires / plaintes / suggestions" in txt
    assert "Revu par" in txt
    assert "Approuvé par" in txt
```

- [ ] **Step 2 : Lancer le test pour le voir échouer**

Run : `.venv/bin/pytest tests/test_excel_report.py::test_build_day_workbook_bas_de_page -v`
Expected : FAIL — aucun de ces blocs n'existe encore.

- [ ] **Step 3 : Écrire les trois helpers**

Ajouter dans `excel_report.py` (avant `_build_day_sheet`) :

```python
_EQUIP_LEGEND = ("Codes d'équipement :  BT chariot · C camion · D détecteur · "
                 "É échafaudage · G grue · N nacelle")


def _equip_legend(ws, row):
    """Légende des codes d'équipement (petite police grise). Prochaine ligne."""
    row += 1
    ws.merge_cells(start_row=row, end_row=row, start_column=1, end_column=_NCOL)
    cell = ws.cell(row=row, column=1, value=_EQUIP_LEGEND)
    cell.font = _F_LEGEND
    cell.alignment = _LEFT
    return row + 1


def _comments_block(ws, row):
    """Libellé 'Commentaires / plaintes / suggestions :' + cadre vide (3 lignes)."""
    row += 1
    ws.cell(row=row, column=1,
            value="Commentaires / plaintes / suggestions :").font = _F_LABEL
    row += 1
    ws.merge_cells(start_row=row, end_row=row + 2, start_column=1, end_column=_NCOL)
    dash = Side(style="dashed", color=_GREY)
    box = Border(left=dash, right=dash, top=dash, bottom=dash)
    for r in range(row, row + 3):
        for c in range(1, _NCOL + 1):
            ws.cell(row=r, column=c).border = box
    return row + 3


def _signature_block(ws, row):
    """Deux blocs de signature vides : 'Revu par' et 'Approuvé par'."""
    row += 2  # espace au-dessus des lignes de signature
    half = _NCOL // 2
    line = Border(bottom=Side(style="thin", color=_SIGN_LINE))
    for c in range(1, _NCOL + 1):
        ws.cell(row=row, column=c).border = line
    row += 1
    ws.cell(row=row, column=1, value="Revu par").font = _F_SIGN
    ws.cell(row=row, column=half + 1, value="Approuvé par").font = _F_SIGN
    return row + 1
```

- [ ] **Step 4 : Enchaîner les blocs dans `_build_day_sheet`**

Dans `_build_day_sheet`, entre la ligne `row = _day_total_row(...)` et l'appel `_stamp(...)`, ajouter :

```python
    row = _equip_legend(ws, row)
    row = _comments_block(ws, row)
    row = _signature_block(ws, row)
```

- [ ] **Step 5 : Lancer la suite complète**

Run : `.venv/bin/pytest tests/test_excel_report.py -v`
Expected : PASS.

- [ ] **Step 6 : Commit**

```bash
git add excel_report.py tests/test_excel_report.py
git commit -m "feat(export): légende équipement, commentaires et blocs de signature"
```

---

### Task 6 : Cohérence de l'export hebdomadaire

**Files:**
- Test: `tests/test_excel_report.py`

**Interfaces:**
- Consumes : `build_week_workbook` (inchangé ; réutilise `_build_day_sheet`, donc déjà modernisé).
- Produces : aucun nouveau code de production — vérification que les feuilles hebdo portent les éléments modernes.

- [ ] **Step 1 : Écrire le test hebdomadaire moderne**

Ajouter dans `tests/test_excel_report.py` :

```python
def test_build_week_workbook_feuilles_modernisees():
    jours = {j: _day_vide() for j in app.JOURS}
    jours["Lundi"] = _day_rempli()
    buf = excel_report.build_week_workbook(_projet(), jours, app.JOURS, "")
    txt = _all_text(openpyxl.load_workbook(buf)["Lundi"])
    assert "Rapport journalier" in txt
    assert "Total de la journée" in txt
    assert "Revu par" in txt
```

- [ ] **Step 2 : Lancer le test**

Run : `.venv/bin/pytest tests/test_excel_report.py::test_build_week_workbook_feuilles_modernisees -v`
Expected : PASS (l'export hebdo réutilise `_build_day_sheet`, déjà modernisé). Si FAIL, corriger `build_week_workbook` pour qu'il appelle bien `_build_day_sheet` sur chaque feuille.

- [ ] **Step 3 : Lancer toute la suite du projet**

Run : `.venv/bin/pytest -q`
Expected : PASS (aucune régression ailleurs — auth, reports, ui, mailer, envoi_ui, etc.).

- [ ] **Step 4 : Commit**

```bash
git add tests/test_excel_report.py
git commit -m "test(export): cohérence moderne de l'export hebdomadaire"
```

---

## Validation manuelle finale (optionnelle mais recommandée)

Générer un `.xlsx` réel et l'ouvrir pour vérifier l'aspect visuel (bandeau teal, alignement, bloc température/conditions, total du jour, signatures) :

```bash
.venv/bin/python -c "
from datetime import date
import app, excel_report
q = app._empty_quart()
q['personnel'] = ['Jean-Paul Jobin', 'Marc Tremblay']
q['temp_am'] = -18; q['temp_pm'] = -12
q['conditions'] = ['Neige', 'Venteux']
q['heures'] = {'Jean-Paul Jobin': {'Supervision': {'mode':'plage','ranges':[{'debut':'07:00','fin':'12:00','type':'TR'},{'debut':'12:30','fin':'14:00','type':'TS'}]}},
               'Marc Tremblay': {'Montage': {'mode':'plage','ranges':[{'debut':'07:00','fin':'15:30','type':'TR'}]}}}
q['prime'] = {'Jean-Paul Jobin': 25.0}
q['equip_hours'] = {'Marc Tremblay': 2.0}; q['equip_codes'] = {'Marc Tremblay': ['É','N']}
day = {'date': date(2026,3,2), 'quarts': {'Jour': q}}
projet = {'no':'8914','adresse':\"1450 rue de l'Industrie\",'id_project':1,'semaine':date(2026,3,1)}
open('/tmp/rj_moderne.xlsx','wb').write(excel_report.build_day_workbook(projet,'Lundi',day,'Marie-Pier Arsenault').getvalue())
print('écrit /tmp/rj_moderne.xlsx')
"
open /tmp/rj_moderne.xlsx
```

---

## Self-review (couverture spec)

- Bandeau titre teal + logo + projet/pagination → Task 1.
- Bloc méta Date/Adresse (niveau jour) → Task 1.
- Bandeau de quart + Température AM/PM + Conditions (niveau quart) → Task 2.
- Tableau groupé par employé (nom/activité/plages/Total), colonnes → conservé (Task 3 renomme l'en-tête).
- Total de la journée → Task 4.
- Légende codes d'équipement → Task 5.
- Commentaires / plaintes / suggestions → Task 5.
- Blocs de signature Revu par / Approuvé par → Task 5.
- Estampille → Task 1 (`_stamp`).
- Export journée ET hebdomadaire, même style → hebdo réutilise `_build_day_sheet` ; vérifié Task 6.
- API publique inchangée, invariant d'import `app`/`excel_report` conservé → aucune modification des signatures publiques ni des imports.
- Ne montrer que les données de l'app ; champs officiels non saisis retirés → aucune colonne Code Empl./No Contrat/Réf./Pu/Co/Mat./Surv. ajoutée.
