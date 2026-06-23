import pandas as pd

import data_source


def test_activity_label_with_description():
    assert data_source.activity_label("C01", "Excavation") == "C01 - Excavation"


def test_activity_label_without_description():
    assert data_source.activity_label("C01", "") == "C01"
    assert data_source.activity_label("C01", None) == "C01"


def test_filter_known_keeps_order_and_drops_unknown():
    assert data_source.filter_known(["b", "x", "a"], ["a", "b", "c"]) == ["b", "a"]


def test_projects_from_df():
    df = pd.DataFrame({"id_project": [2, 1], "project_no": ["P-2", "P-1"],
                       "description": ["Deux", None]})
    assert data_source.projects_from_df(df) == [(2, "P-2", "Deux"), (1, "P-1", "")]


def test_activity_labels_from_df():
    df = pd.DataFrame({"activity_code": ["C01", "C02"], "description": ["A", ""]})
    assert data_source.activity_labels_from_df(df) == ["C01 - A", "C02"]


def test_get_activities_none_returns_empty():
    assert data_source.get_activities(None) == []


class _FakeConn:
    def __init__(self, df):
        self._df = df

    def query(self, sql, **kwargs):
        return self._df


def test_get_projects_happy(monkeypatch):
    df = pd.DataFrame({"id_project": [1], "project_no": ["P-1"], "description": ["Projet 1"]})
    monkeypatch.setattr(data_source, "_connection", lambda: _FakeConn(df))
    assert data_source.get_projects() == [(1, "P-1", "Projet 1")]


def test_get_projects_unreachable_returns_empty(monkeypatch):
    def boom():
        raise RuntimeError("no db")
    monkeypatch.setattr(data_source, "_connection", boom)
    assert data_source.get_projects() == []


def test_get_activities_happy(monkeypatch):
    df = pd.DataFrame({"activity_code": ["C01"], "description": ["X"]})
    monkeypatch.setattr(data_source, "_connection", lambda: _FakeConn(df))
    assert data_source.get_activities(1) == ["C01 - X"]


def test_get_project_staff_none_returns_empty():
    assert data_source.get_project_staff(None) == []


def test_get_project_staff_happy(monkeypatch):
    df = pd.DataFrame({"employee": ["Jean Tremblay (Électricien)", "Marie Roy"]})
    monkeypatch.setattr(data_source, "_connection", lambda: _FakeConn(df))
    assert data_source.get_project_staff(1) == ["Jean Tremblay (Électricien)", "Marie Roy"]


def test_get_project_staff_unreachable_returns_empty(monkeypatch):
    def boom():
        raise RuntimeError("no db")
    monkeypatch.setattr(data_source, "_connection", boom)
    assert data_source.get_project_staff(1) == []


def test_get_all_staff_happy(monkeypatch):
    df = pd.DataFrame({"employee": ["Alice Dubois", "Bob Martin", "Alice Dubois"]})
    monkeypatch.setattr(data_source, "_connection", lambda: _FakeConn(df))
    assert data_source.get_all_staff() == ["Alice Dubois", "Bob Martin", "Alice Dubois"]


def test_get_all_staff_unreachable_returns_empty(monkeypatch):
    def boom():
        raise RuntimeError("no db")
    monkeypatch.setattr(data_source, "_connection", boom)
    assert data_source.get_all_staff() == []
