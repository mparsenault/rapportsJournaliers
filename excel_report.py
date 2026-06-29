"""Génération Excel des rapports journaliers (présentation).

La mise en forme des DONNÉES reste dans app.py (`_legacy_day`) ; ce module
construit les classeurs openpyxl. Il importe `app` ; app NE DOIT PAS importer
excel_report au niveau module (import paresseux dans les vues) pour éviter un
import circulaire.
"""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

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


def _build_day_sheet(ws, projet, jour_name, day, exported_by=""):
    """Écrit le rapport d'une journée dans la feuille `ws`."""
    ws.title = _safe_title(jour_name)
    _add_logo(ws)
    ws.column_dimensions["A"].width = 28

    ws.merge_cells("B1:H1")
    t = ws["B1"]
    t.value = "RAPPORT JOURNALIER — ONDEL"
    t.font = _F_TITLE
    t.fill = _FILL_TITLE

    d = day.get("date")
    date_txt = app.fr_date_long(d) if d else ""
    ws.cell(row=3, column=1, value="No Projet :").font = _F_LABEL
    ws.cell(row=3, column=2, value=str(projet.get("no") or ""))
    ws.cell(row=4, column=1, value="Date :").font = _F_LABEL
    ws.cell(row=4, column=2, value=f"{jour_name} {date_txt}".strip())
    ws.cell(row=5, column=1, value="Adresse :").font = _F_LABEL
    ws.cell(row=5, column=2, value=projet.get("adresse") or "")

    row = 7
    for qname in app._day_quart_names(day):
        quart = day["quarts"][qname]
        if app._quart_total(quart) <= 0:
            continue
        leg = app._legacy_day(quart)

        ws.cell(row=row, column=1, value=f"Quart : {qname}").font = _F_LABEL
        ws.cell(row=row, column=3,
                value=f"Resp. : {leg.get('responsable', '')}").font = _F_LABEL
        ws.cell(row=row, column=5,
                value=f"Temp. AM : {leg.get('temp_am')}  PM : {leg.get('temp_pm')}")
        ws.cell(row=row, column=7,
                value="Conditions : " + ", ".join(leg.get("conditions", [])))
        row += 1
        if leg.get("description"):
            ws.cell(row=row, column=1, value=f"Note : {leg['description']}")
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
    act_cols = [k for k in app.HOUR_KEYS if headers.get(k)]
    cols = [label_col] + act_cols + ["TR", "TS"]
    if with_equip:
        cols += ["Hrs Éq.", "Code Éq."]
    cols += ["Prime", "Commentaire"]

    titles = [label_col] + [headers[k] for k in act_cols] + cols[1 + len(act_cols):]
    _write_row(ws, row, titles, bold=True, fill=_FILL_HEAD)
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
