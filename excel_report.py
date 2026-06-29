"""Génération Excel des rapports journaliers (présentation).

La mise en forme des DONNÉES reste dans app.py (`_legacy_day`) ; ce module
construit les classeurs openpyxl. Il importe `app` ; app NE DOIT PAS importer
excel_report au niveau module (import paresseux dans les vues) pour éviter un
import circulaire.
"""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import app

# --- Styles Ondel (déplacés depuis app.py) -------------------------------
_TEAL = "0999AA"
_TEAL_DK = "077A88"
_BAND = "EEF8F9"
_GREY = "D9E2E4"
_THIN = Side(style="thin", color=_GREY)
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_F_TITLE = Font(name="Calibri", size=16, bold=True, color="FFFFFF")
_F_HEAD = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
_F_LABEL = Font(name="Calibri", size=10, bold=True, color=_TEAL_DK)
_F_TOTAL = Font(name="Calibri", size=10, bold=True, color="0E2A2E")
_FILL_TITLE = PatternFill("solid", fgColor=_TEAL)
_FILL_HEAD = PatternFill("solid", fgColor=_TEAL_DK)
_FILL_BAND = PatternFill("solid", fgColor=_BAND)
_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
_LEFT = Alignment(horizontal="left", vertical="center")
_HOURS_FMT = "0.00"


def _add_logo(ws, height_px=58):
    import os
    if not os.path.exists(app.LOGO_PATH):
        return
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
    from openpyxl.drawing.xdr import XDRPositiveSize2D
    from openpyxl.utils.units import pixels_to_EMU
    img = XLImage(app.LOGO_PATH)
    w = round(292 / 280 * height_px)
    marker = AnchorMarker(col=0, colOff=pixels_to_EMU(12), row=0, rowOff=pixels_to_EMU(8))
    img.anchor = OneCellAnchor(_from=marker,
                               ext=XDRPositiveSize2D(pixels_to_EMU(w), pixels_to_EMU(height_px)))
    ws.add_image(img)


def _safe_title(name):
    """Titre de feuille Excel : ≤31 car., sans caractères interdits."""
    bad = '[]:*?/\\'
    return "".join(c for c in str(name) if c not in bad)[:31] or "Feuille"


def _write_row(ws, row, values, *, bold=False, fill=None, fmt=None):
    for col, val in enumerate(values, start=1):
        cell = ws.cell(row=row, column=col, value=val)
        cell.border = _BORDER
        cell.alignment = _LEFT if col == 1 else _CENTER
        if bold:
            cell.font = _F_HEAD if fill is _FILL_HEAD else _F_TOTAL
        if fill is not None:
            cell.fill = fill
        if fmt and isinstance(val, (int, float)):
            cell.number_format = fmt


def _table_cols(headers, label_col, with_equip):
    """Colonnes (clés) du tableau : label + activités présentes + totaux + extras."""
    act_cols = [k for k in app.HOUR_KEYS if headers.get(k)]
    cols = [label_col] + act_cols + ["TR", "TS"]
    if with_equip:
        cols += ["Hrs Éq.", "Code Éq."]
    cols += ["Prime", "Commentaire"]
    return cols, act_cols


def _col_width(name):
    """Largeur de colonne selon son rôle (les clés hX/aX = activités = larges)."""
    return {
        "Nom": 34, "Véhicule": 34,
        "TR": 6.5, "TS": 6.5, "Hrs Éq.": 9, "Code Éq.": 13, "Prime": 9,
        "Commentaire": 32,
    }.get(name, 28)  # défaut = colonne d'activité (libellé long)


def _apply_widths(ws, cols):
    for i, name in enumerate(cols, start=1):
        ws.column_dimensions[get_column_letter(i)].width = _col_width(name)


def _banner(ws, row, last_col, text):
    """Bande d'info (fusionnée A:last_col), fond teal, texte blanc — pas de chevauchement."""
    ws.merge_cells(start_row=row, end_row=row, start_column=1, end_column=last_col)
    cell = ws.cell(row=row, column=1, value=text)
    cell.font = _F_HEAD
    cell.fill = _FILL_HEAD
    cell.alignment = _LEFT
    ws.row_dimensions[row].height = 20


def _quart_info(qname, leg):
    parts = [f"Quart {qname}"]
    if leg.get("responsable"):
        parts.append(f"Resp. : {leg['responsable']}")
    tam, tpm = leg.get("temp_am"), leg.get("temp_pm")
    if tam is not None or tpm is not None:
        a = tam if tam is not None else "—"
        p = tpm if tpm is not None else "—"
        parts.append(f"Temp. AM {a} / PM {p}")
    if leg.get("conditions"):
        parts.append(", ".join(leg["conditions"]))
    return "    ·    ".join(parts)


def _build_day_sheet(ws, projet, jour_name, day, exported_by=""):
    """Écrit le rapport d'une journée dans la feuille `ws`."""
    ws.title = _safe_title(jour_name)
    _add_logo(ws)

    # Quarts remplis + largeurs basées sur le tableau personnel le plus large.
    filled = [(q, app._legacy_day(day["quarts"][q]))
              for q in app._day_quart_names(day)
              if app._quart_total(day["quarts"][q]) > 0]
    width_cols = ["Nom"]
    for _, leg in filled:
        cols, _ = _table_cols(leg["headers"], "Nom", with_equip=True)
        if len(cols) > len(width_cols):
            width_cols = cols
    _apply_widths(ws, width_cols)
    last_col = max(len(width_cols), 8)

    # Titre (sur toute la largeur du tableau).
    ws.merge_cells(start_row=1, end_row=1, start_column=2, end_column=last_col)
    t = ws.cell(row=1, column=2, value="RAPPORT JOURNALIER — ONDEL")
    t.font = _F_TITLE
    t.fill = _FILL_TITLE
    ws.row_dimensions[1].height = 38

    d = day.get("date")
    date_txt = app.fr_date_long(d) if d else ""
    ws.cell(row=3, column=1, value="No Projet :").font = _F_LABEL
    ws.cell(row=3, column=2, value=str(projet.get("no") or ""))
    ws.cell(row=4, column=1, value="Date :").font = _F_LABEL
    ws.cell(row=4, column=2, value=f"{jour_name} {date_txt}".strip())
    ws.cell(row=5, column=1, value="Adresse :").font = _F_LABEL
    ws.cell(row=5, column=2, value=projet.get("adresse") or "")

    row = 7
    for qname, leg in filled:
        _banner(ws, row, last_col, _quart_info(qname, leg))
        row += 1
        if leg.get("description"):
            ws.merge_cells(start_row=row, end_row=row, start_column=1, end_column=last_col)
            ws.cell(row=row, column=1, value=f"Note : {leg['description']}").alignment = _LEFT
            row += 1

        row = _write_table(ws, row, leg["headers"], leg["pers"], with_equip=True)
        row += 1
        row = _write_table(ws, row, leg["headers"], leg["equip"], with_equip=False)
        row += 2

    # Estampille (dernière écriture)
    last = ws.max_row + 2
    cell = ws.cell(row=last, column=1, value=f"Exporté par {exported_by or '—'}")
    cell.font = Font(name="Calibri", size=8, italic=True, color="6B7B7E")


def _write_table(ws, row, headers, df, *, with_equip):
    """Écrit un tableau (personnel ou équipement) ; renvoie la prochaine ligne libre.

    `headers` mappe les clés hX/aX -> libellés d'activité (vides à ignorer).
    `df` est le DataFrame produit par app._legacy_day (build_df)."""
    label_col = df.columns[0]                      # "Nom" ou "Véhicule"
    cols, act_cols = _table_cols(headers, label_col, with_equip)

    titles = [label_col] + [headers[k] for k in act_cols] + cols[1 + len(act_cols):]
    _write_row(ws, row, titles, bold=True, fill=_FILL_HEAD)
    ws.row_dimensions[row].height = 30          # libellés d'activité longs (wrap)
    row += 1
    for _, rec in df.iterrows():
        values = [rec.get(c) for c in cols]
        _write_row(ws, row, values, fmt=_HOURS_FMT, fill=_FILL_BAND)
        row += 1
    return row


def build_day_workbook(projet, jour_name, day, exported_by=""):
    wb = Workbook()
    _build_day_sheet(wb.active, projet, jour_name, day, exported_by)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def build_week_workbook(projet, jours, jours_order, exported_by=""):
    wb = Workbook()
    wb.remove(wb.active)
    for jour_name in jours_order:
        day = jours.get(jour_name) or {}
        if app._day_total(day) <= 0:
            continue
        ws = wb.create_sheet(title=_safe_title(jour_name))
        _build_day_sheet(ws, projet, jour_name, day, exported_by)
    if not wb.sheetnames:                       # aucune journée remplie
        wb.create_sheet(title="Vide")
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def build_day_email(projet, jour_name, day, exported_by=""):
    """Renvoie (subject, html_body, filename, xlsx_bytes) pour une journée."""
    no = str(projet.get("no") or "")
    d = day.get("date")
    date_iso = d.isoformat() if d else "sans-date"
    date_txt = app.fr_date_long(d) if d else ""
    subject = f"Rapport journalier — {no} — {date_txt} ({jour_name})"
    html_body = (
        f"<p>Bonjour,</p>"
        f"<p>Veuillez trouver ci-joint le rapport journalier du projet "
        f"<b>{no}</b> pour le <b>{jour_name} {date_txt}</b>.</p>"
        f"<p style='color:#6B7B7E;font-size:12px'>Exporté par {exported_by or '—'}.</p>"
    )
    filename = f"Rapport_{no}_{date_iso}.xlsx"
    data = build_day_workbook(projet, jour_name, day, exported_by).getvalue()
    return subject, html_body, filename, data
