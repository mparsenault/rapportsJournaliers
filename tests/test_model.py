import app

import pandas as pd


def test_empty_day_shape():
    d = app._empty_day()
    assert d["date"] is None
    assert list(d["quarts"].keys()) == ["Jour"]
    q = d["quarts"]["Jour"]
    assert q["heures"] == {} and q["prime_codes"] == {} and q["commentaire_ligne"] == {}
    assert "prime" not in q
    assert q["equip_codes"] == {} and q["equip_hours"] == {}
    assert q["personnel"] == [] and q["equipements"] == []
    assert q["responsable"] == "" and q["description"] == ""
    assert q["conditions"] == []
    assert q["temp_am"] is None and q["temp_pm"] is None


def test_prime_code_label():
    import app
    assert app._prime_code_label("H") == "H — Hauteur"
    assert set(app.PRIME_CODE_VALUES) == {"I", "S", "G", "T", "A", "Pa", "P", "H", "R", "Pu", "Co"}


def _sample_quart():
    q = app._empty_quart()
    q["personnel"] = ["Mathis", "Roy"]
    q["equipements"] = ["Camion v1892"]
    q["heures"] = {"Mathis": {"Excavation": {"TR": 4.0, "TS": 0.0},
                              "P-77": {"TR": 2.0, "TS": 1.0}},
                   "Camion v1892": {"Excavation": {"TR": 8.0, "TS": 0.0}}}
    q["prime_codes"] = {"Mathis": ["H"]}
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
    assert mathis["Prime"] == "H" and mathis["Commentaire"] == "test"
    assert list(equip["Véhicule"]) == ["Camion v1892"]
    camion = equip[equip["Véhicule"] == "Camion v1892"].iloc[0]
    assert camion["h0"] == 8.0


def test_legacy_day_joins_multiple_prime_codes():
    q = _sample_quart()
    q["prime_codes"] = {"Mathis": ["H", "R"]}
    leg = app._legacy_day(q)
    mathis = leg["pers"][leg["pers"]["Nom"] == "Mathis"].iloc[0]
    assert mathis["Prime"] == "H, R"


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


def test_hhmm_min_roundtrip():
    assert app._hhmm_to_min("10:00") == 600
    assert app._hhmm_to_min("10:15") == 615
    assert app._hhmm_to_min("00:00") == 0
    assert app._hhmm_to_min("bidon") is None
    assert app._hhmm_to_min("99:99") is None
    assert app._min_to_hhmm(600) == "10:00"
    assert app._min_to_hhmm(615) == "10:15"
    assert app._min_to_hhmm(-5) == "00:00"


def test_range_hours():
    assert app._range_hours("10:00", "12:00") == 2.0
    assert app._range_hours("13:00", "14:30") == 1.5
    assert app._range_hours("10:00", "10:15") == 0.25
    assert app._range_hours("12:00", "10:00") == 0.0   # fin <= début
    assert app._range_hours("10:00", "10:00") == 0.0
    assert app._range_hours("x", "12:00") == 0.0


def test_ranges_to_pair():
    ranges = [
        {"debut": "10:00", "fin": "12:00", "type": "TR"},
        {"debut": "13:00", "fin": "14:30", "type": "TR"},
        {"debut": "16:00", "fin": "17:00", "type": "TS"},
    ]
    assert app._ranges_to_pair(ranges) == {"TR": 3.5, "TS": 1.0}
    assert app._ranges_to_pair([]) == {"TR": 0.0, "TS": 0.0}


def test_norm_entry_backward_compat():
    # ancien format dict
    assert app._norm_entry({"TR": 5.0, "TS": 1.0}) == {
        "mode": "direct", "ranges": [], "TR": 5.0, "TS": 1.0}
    # scalaire hérité
    assert app._norm_entry(7.5) == {"mode": "direct", "ranges": [], "TR": 7.5, "TS": 0.0}
    # nouveau format plage -> TR/TS dérivés des plages
    e = app._norm_entry({"mode": "plage",
                         "ranges": [{"debut": "10:00", "fin": "12:00", "type": "TR"}]})
    assert e["mode"] == "plage" and e["TR"] == 2.0 and e["TS"] == 0.0


def test_apply_dict_copies_to_empty_dest():
    q = app._empty_quart()
    q["personnel"] = ["Alice", "Bob"]
    hours = {"Excavation": {"mode": "direct", "ranges": [], "TR": 4.0, "TS": 1.0}}
    changed = app._apply_hours_dict_to_resources(q, hours, ["Bob"])
    assert changed == ["Bob"]
    assert q["heures"]["Bob"]["Excavation"]["TR"] == 4.0
    assert q["heures"]["Bob"]["Excavation"]["TS"] == 1.0


def test_apply_dict_ranges_are_independent():
    q = app._empty_quart()
    hours = {"Excavation": {"mode": "plage",
                            "ranges": [{"debut": "08:00", "fin": "12:00", "type": "TR"}],
                            "TR": 4.0, "TS": 0.0}}
    app._apply_hours_dict_to_resources(q, hours, ["Alice", "Bob"])
    # muter la source ne doit pas toucher les destinataires
    hours["Excavation"]["ranges"][0]["fin"] = "16:00"
    assert q["heures"]["Alice"]["Excavation"]["ranges"][0]["fin"] == "12:00"
    assert q["heures"]["Bob"]["Excavation"]["ranges"][0]["fin"] == "12:00"
    # les deux destinataires sont indépendants l'un de l'autre
    q["heures"]["Alice"]["Excavation"]["ranges"][0]["fin"] = "10:00"
    assert q["heures"]["Bob"]["Excavation"]["ranges"][0]["fin"] == "12:00"


def test_apply_dict_merges_without_erasing():
    q = app._empty_quart()
    q["heures"] = {"Bob": {"Coffrage": {"mode": "direct", "ranges": [], "TR": 2.0, "TS": 0.0},
                           "Excavation": {"mode": "direct", "ranges": [], "TR": 1.0, "TS": 0.0}}}
    hours = {"Excavation": {"mode": "direct", "ranges": [], "TR": 4.0, "TS": 0.0}}
    app._apply_hours_dict_to_resources(q, hours, ["Bob"])
    assert q["heures"]["Bob"]["Coffrage"]["TR"] == 2.0   # propre à Bob conservée
    assert q["heures"]["Bob"]["Excavation"]["TR"] == 4.0  # commune écrasée


def test_apply_dict_empty_hours_noop():
    q = app._empty_quart()
    q["heures"] = {"Bob": {"Coffrage": {"mode": "direct", "ranges": [], "TR": 2.0, "TS": 0.0}}}
    changed = app._apply_hours_dict_to_resources(q, {}, ["Bob"])
    assert changed == []
    assert q["heures"]["Bob"]["Coffrage"]["TR"] == 2.0


def test_apply_dict_dedupes_dests():
    q = app._empty_quart()
    hours = {"Excavation": {"mode": "direct", "ranges": [], "TR": 4.0, "TS": 0.0}}
    changed = app._apply_hours_dict_to_resources(q, hours, ["Bob", "Bob", "Alice"])
    assert changed == ["Bob", "Alice"]
