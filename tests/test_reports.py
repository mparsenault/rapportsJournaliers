"""Tests de reports.py — logique pure (gardes d'entrée).

La persistance réelle (SQL Postgres avec text[]/serial/on conflict) est
validée end-to-end contre Neon ; ces types ne sont pas reproductibles en
SQLite, donc on couvre ici les chemins qui ne touchent pas la BD.
"""
from datetime import date

import pytest

import reports


def test_module_exposes_api():
    assert hasattr(reports, "ensure_schema")
    assert hasattr(reports, "save_report")
    assert hasattr(reports, "load_report")


def test_load_report_none_inputs_returns_none():
    assert reports.load_report(None, date(2026, 6, 21)) is None
    assert reports.load_report(123, None) is None
    assert reports.load_report(123, "pas une date") is None


def test_save_report_without_project_raises():
    projet = {"id_project": None, "semaine": date(2026, 6, 21)}
    with pytest.raises(ValueError):
        reports.save_report(projet, {}, {}, reports.__dict__.get("JOURS", []))


def test_save_report_invalid_week_raises():
    projet = {"id_project": 1, "no": "X", "semaine": "lundi"}
    with pytest.raises(ValueError):
        reports.save_report(projet, {}, {}, [])


def test_ddl_has_tr_ts_and_equip_migrations():
    ddl = " ".join(reports._DDL_STATEMENTS)
    assert "report_hours add column if not exists hours_ts" in ddl
    assert "report_lines add column if not exists equip_hours" in ddl
    assert "report_lines add column if not exists equip_codes" in ddl
