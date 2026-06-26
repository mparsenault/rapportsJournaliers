import app

import pandas as pd


def test_empty_day_shape():
    d = app._empty_day()
    assert d["date"] is None
    assert list(d["quarts"].keys()) == ["Jour"]
    q = d["quarts"]["Jour"]
    assert q["heures"] == {} and q["prime"] == {} and q["commentaire_ligne"] == {}
    assert q["equip_codes"] == {} and q["equip_hours"] == {}
    assert q["personnel"] == [] and q["equipements"] == []
    assert q["responsable"] == "" and q["description"] == ""
    assert q["conditions"] == []
    assert q["temp_am"] is None and q["temp_pm"] is None


def _sample_quart():
    q = app._empty_quart()
    q["personnel"] = ["Mathis", "Roy"]
    q["equipements"] = ["Camion v1892"]
    q["heures"] = {"Mathis": {"Excavation": {"TR": 4.0, "TS": 0.0},
                              "P-77": {"TR": 2.0, "TS": 1.0}},
                   "Camion v1892": {"Excavation": {"TR": 8.0, "TS": 0.0}}}
    q["prime"] = {"Mathis": 2.0}
    q["commentaire_ligne"] = {"Mathis": "test"}
    q["equip_codes"] = {"Mathis": ["C", "N"]}
    q["equip_hours"] = {"Mathis": 10.0}
    return q


def test_equip_codes_constant():
    assert app.EQUIP_CODE_VALUES == ["C", "N", "É", "D", "G", "BT"]
    assert app._equip_code_label("C") == "C — Camion"


def test_pair_total():
    assert app._pair_total({"TR": 4.0, "TS": 1.0}) == 5.0
    assert app._pair_total({}) == 0.0


def test_pair_total_tolerates_legacy_scalar():
    # Un état hérité (ancien format {activité: heures}) ne doit pas planter :
    # une valeur scalaire est comptée comme du temps régulier.
    assert app._pair_total(8.0) == 8.0
    assert app._pair_total(None) == 0.0
    assert app._norm_pair(8.0) == {"TR": 8.0, "TS": 0.0}


def test_resource_total_tolerates_legacy_scalar_heures():
    q = app._empty_quart()
    q["heures"] = {"Alice": {"Excavation": 6.0}}   # ancien format scalaire
    assert app._resource_total(q, "Alice") == 6.0
    assert app._quart_total(q) == 6.0


def test_resource_total():
    q = _sample_quart()
    assert app._resource_total(q, "Mathis") == 7.0      # (4+0) + (2+1)
    assert app._resource_total(q, "Camion v1892") == 8.0
    assert app._resource_total(q, "Inconnu") == 0.0


def test_quart_total():
    assert app._quart_total(_sample_quart()) == 15.0    # 7 + 8


def test_quart_activities_union_sorted():
    assert app._quart_activities(_sample_quart()) == ["Excavation", "P-77"]
    assert app._quart_activities(app._empty_quart()) == []


def _sample_day():
    d = app._empty_day()
    d["quarts"]["Jour"] = _sample_quart()
    return d


def test_roster_order_and_types():
    assert app._roster(_sample_quart()) == [("Mathis", "P"), ("Roy", "P"), ("Camion v1892", "E")]


def test_day_total_sums_quarts():
    d = _sample_day()
    d["quarts"]["Soir"] = app._empty_quart()
    d["quarts"]["Soir"]["heures"] = {"Roy": {"Excavation": {"TR": 3.0, "TS": 0.0}}}
    assert app._day_total(d) == 18.0   # 15 (Jour) + 3 (Soir)


def test_day_quart_names_ordered():
    d = app._empty_day()
    d["quarts"]["Nuit"] = app._empty_quart()
    d["quarts"]["Soir"] = app._empty_quart()
    assert app._day_quart_names(d) == ["Jour", "Soir", "Nuit"]



def test_legacy_day_maps_labels_to_keys():
    leg = app._legacy_day(_sample_quart())
    assert leg["headers"]["h0"] == "Excavation"
    assert leg["headers"]["h1"] == "P-77"
    pers, equip = leg["pers"], leg["equip"]
    for k in app.HOUR_KEYS:
        assert k in pers.columns and k in equip.columns
    assert list(pers["Nom"]) == ["Mathis", "Roy"]
    mathis = pers[pers["Nom"] == "Mathis"].iloc[0]
    assert mathis["h0"] == 4.0          # Excavation : TR+TS = 4+0
    assert mathis["h1"] == 3.0          # P-77 : TR+TS = 2+1
    assert mathis["TR"] == 6.0 and mathis["TS"] == 1.0
    assert mathis["Hrs Éq."] == 10.0 and mathis["Code Éq."] == "C, N"
    assert mathis["Prime"] == 2.0 and mathis["Commentaire"] == "test"
    assert list(equip["Véhicule"]) == ["Camion v1892"]
    camion = equip[equip["Véhicule"] == "Camion v1892"].iloc[0]
    assert camion["h0"] == 8.0


def test_week_start_snaps_to_sunday():
    import datetime
    # 2026-06-18 est un jeudi -> dimanche de la semaine = 2026-06-14
    assert app._week_start(datetime.date(2026, 6, 18)) == datetime.date(2026, 6, 14)
    # un dimanche reste inchangé
    assert app._week_start(datetime.date(2026, 6, 14)) == datetime.date(2026, 6, 14)
    # un samedi -> le dimanche de la même semaine
    assert app._week_start(datetime.date(2026, 6, 20)) == datetime.date(2026, 6, 14)


def test_fill_week_weather_fills_empty_days(monkeypatch):
    import datetime
    monkeypatch.setattr(app, "_fetch_day_weather",
                        lambda lat, lon, d: {"temp_am": 12.0, "temp_pm": 18.0,
                                             "conditions": ["Ensoleillé"]})
    proj = {"lat": 46.8, "lon": -71.2}
    jours = {j: app._empty_day() for j in app.JOURS}
    for j in app.JOURS:
        jours[j]["date"] = datetime.date(2026, 6, 14)
    app._fill_week_weather(proj, jours)
    q = jours["Lundi"]["quarts"]["Jour"]
    assert q["temp_am"] == 12.0 and q["temp_pm"] == 18.0
    assert q["conditions"] == ["Ensoleillé"]


def test_fill_week_weather_noop_without_position(monkeypatch):
    calls = []
    monkeypatch.setattr(app, "_fetch_day_weather",
                        lambda *a: calls.append(a) or {"temp_am": 1, "temp_pm": 2, "conditions": []})
    proj = {"lat": None, "lon": None}
    jours = {j: app._empty_day() for j in app.JOURS}
    app._fill_week_weather(proj, jours)
    assert not calls


def test_wmo_to_condition():
    assert app._wmo_to_condition(0) == "Ensoleillé"
    assert app._wmo_to_condition(2) == "Partiellement nuageux"
    assert app._wmo_to_condition(3) == "Couvert"
    assert app._wmo_to_condition(45) == "Brouillard"
    assert app._wmo_to_condition(63) == "Pluie"
    assert app._wmo_to_condition(66) == "Verglas"
    assert app._wmo_to_condition(75) == "Neige"
    assert app._wmo_to_condition(81) == "Averses"
    # toutes les valeurs retournées sont des conditions valides de l'app
    for code in (0, 1, 2, 3, 45, 48, 51, 61, 65, 56, 71, 80, 95, 1234):
        assert app._wmo_to_condition(code) in app.CONDITIONS


def test_codes_to_condition_picks_most_significant_daytime():
    # journée surtout dégagée mais pluie l'après-midi -> on retient la pluie
    codes = [0] * 13 + [63] + [0] * 10   # code 63 (pluie) à 13h
    assert app._codes_to_condition(codes) == "Pluie"
    # journée entièrement dégagée
    assert app._codes_to_condition([0] * 24) == "Ensoleillé"
    # données absentes -> repli
    assert app._codes_to_condition([]) == "Ensoleillé"
