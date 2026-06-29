import datetime

import pytest
from streamlit.testing.v1 import AppTest

def app_quarts(at, jour):
    import app
    return app._day_quart_names(at.session_state["jours"][jour])



def _run():
    return AppTest.from_file("app.py", default_timeout=30).run()


def _run_with_project(monkeypatch, project_no="P-1", id_project=1, description="Projet 1"):
    """Lance l'app avec un projet disponible ET sélectionné (sinon tout est grisé)."""
    import data_source
    monkeypatch.setattr(data_source, "get_projects", lambda: [(id_project, project_no, description)])
    monkeypatch.setattr(data_source, "get_project_staff", lambda pid: [])
    at = AppTest.from_file("app.py", default_timeout=30).run()
    sb = [s for s in at.selectbox if s.label == "Projet"][0]
    label = f"{project_no} — {description}" if description else project_no
    sb.set_value(label).run()
    return at


def _empty_quart_dict():
    return {
        "responsable": "", "activites": [], "autres": [], "personnel": [], "equipements": [],
        "temp_am": None, "temp_pm": None, "conditions": [], "heures": {}, "prime": {},
        "commentaire_ligne": {}, "equip_codes": {}, "equip_hours": {}, "description": ""}


def _open_day_for_entry(monkeypatch, jour="Lundi", personnel=("Alice",)):
    import data_source
    monkeypatch.setattr(data_source, "get_projects", lambda: [(1, "P-100", "Alpha")])
    monkeypatch.setattr(data_source, "get_activities", lambda pid: ["C01 - Test"])
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["projet"] = {"no": "P-100", "id_project": 1,
                                  "semaine": datetime.date(2026, 6, 7),
                                  "adresse": "", "lat": None, "lon": None}
    day = {"date": datetime.date(2026, 6, 8),
           "quarts": {"Jour": {"responsable": "", "activites": [], "autres": [],
                               "personnel": list(personnel), "equipements": [],
                               "temp_am": None, "temp_pm": None, "conditions": [],
                               "heures": {}, "prime": {}, "commentaire_ligne": {},
                               "equip_codes": {}, "equip_hours": {},
                               "description": ""}}}
    at.session_state["jours"] = {j: {"date": None, "quarts": {"Jour": {
        "responsable": "", "activites": [], "autres": [], "personnel": [], "equipements": [],
        "temp_am": None, "temp_pm": None, "conditions": [], "heures": {}, "prime": {},
        "commentaire_ligne": {}, "equip_codes": {}, "equip_hours": {}, "description": ""}}} for j in ["Dimanche", "Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]}
    at.session_state["jours"][jour] = day
    at.session_state["active_day"] = jour
    at.session_state["view"] = "day_entry"
    at.run()
    return at


def _goto_saisie(at):
    """Passe à l'étape Saisie des heures (le flux n'a plus d'onglets)."""
    at.session_state["day_entry_step"] = "saisie"
    return at.run()


def _goto_config(at):
    """Revient à l'étape Configuration."""
    at.session_state["day_entry_step"] = "config"
    return at.run()


def test_day_entry_starts_on_config_step(monkeypatch):
    """À l'ouverture d'une journée, on est sur la Configuration (pas de grille d'heures)."""
    at = _open_day_for_entry(monkeypatch)
    assert at.session_state["day_entry_step"] == "config"
    assert any(b.key == "save_next_Lundi" for b in at.button)
    assert not any(b.key == "back_config_Lundi" for b in at.button)
    assert not any(b.key == "save_Lundi" for b in at.button)
    assert not any((t.key or "") == "roster_search_Lundi_Jour" for t in at.text_input)
    assert not at.exception


def test_save_and_navigate_advances_to_saisie(monkeypatch):
    """Le bouton « Enregistrer et saisir les heures → » enregistre puis ouvre la Saisie."""
    import reports
    monkeypatch.setattr(reports, "save_report", lambda *a, **k: None)
    at = _open_day_for_entry(monkeypatch)   # personnel Alice présent
    # Prérequis désormais : personnel + température (plus d'activité en config).
    [n for n in at.number_input if n.key == "Lundi_Jour_temp_am"][0].set_value(5.0).run()
    [b for b in at.button if b.key == "save_next_Lundi"][0].click().run()
    assert at.session_state["day_entry_step"] == "saisie"
    assert at.session_state["dirty"] is False
    assert any(b.key == "back_config_Lundi" for b in at.button)
    assert any(b.key == "save_Lundi" for b in at.button)
    assert not at.exception


def test_back_returns_to_config(monkeypatch):
    """« ← Retour à la configuration » ramène à l'étape 1 sans perdre l'état."""
    at = _open_day_for_entry(monkeypatch)
    _goto_saisie(at)
    assert at.session_state["day_entry_step"] == "saisie"
    [b for b in at.button if b.key == "back_config_Lundi"][0].click().run()
    assert at.session_state["day_entry_step"] == "config"
    assert any(b.key == "save_next_Lundi" for b in at.button)
    assert not at.exception


def test_save_next_disabled_until_requirements_met(monkeypatch):
    """Le bouton de l'étape Config est bloqué tant qu'il manque température
    OU personnel ; il s'active une fois les deux remplis."""
    at = _open_day_for_entry(monkeypatch, personnel=())   # rien de rempli
    assert [b for b in at.button if b.key == "save_next_Lundi"][0].disabled
    [t for t in at.text_input if t.key == "new_employee_Lundi_Jour"][0].set_value("Alice").run()
    [b for b in at.button if b.key == "add_manual_Lundi_Jour"][0].click().run()
    [n for n in at.number_input if n.key == "Lundi_Jour_temp_am"][0].set_value(12.0).run()
    assert not [b for b in at.button if b.key == "save_next_Lundi"][0].disabled
    assert not at.exception


def test_save_next_requires_temperature(monkeypatch):
    """Règle température isolée : personnel présent mais température vide
    → bouton bloqué ; une température (même 0/négative) le débloque."""
    at = _open_day_for_entry(monkeypatch, personnel=("Alice",))
    assert [b for b in at.button if b.key == "save_next_Lundi"][0].disabled  # temp vide
    [n for n in at.number_input if n.key == "Lundi_Jour_temp_am"][0].set_value(0.0).run()
    assert not [b for b in at.button if b.key == "save_next_Lundi"][0].disabled
    assert not at.exception


def test_dashboard_is_default_view():
    at = _run()
    assert at.session_state["view"] == "dashboard"
    assert not at.exception


def test_header_retour_button_returns_to_dashboard(monkeypatch):
    """Le bouton Retour de la bannière ramène au tableau de bord."""
    at = _open_day_for_entry(monkeypatch)
    assert at.session_state["view"] == "day_entry"
    btn = [b for b in at.button if b.key == "hdr_retour"][0]
    btn.click().run()
    assert at.session_state["view"] == "dashboard"
    assert not at.exception


def test_dashboard_has_no_header_retour():
    """Pas de bouton Retour dans la bannière sur le tableau de bord."""
    at = _run()
    assert at.session_state["view"] == "dashboard"
    assert not any(b.key == "hdr_retour" for b in at.button)


def test_day_config_shows_project_personnel(monkeypatch):
    """La configuration du jour propose les employés du projet (pills)."""
    import data_source
    monkeypatch.setattr(data_source, "get_projects", lambda: [(1, "P-100", "Alpha")])
    monkeypatch.setattr(data_source, "get_activities", lambda pid: ["C01 - Test"])
    monkeypatch.setattr(data_source, "get_project_staff",
                        lambda pid: ["Alice"] if pid == 1 else [])
    monkeypatch.setattr(data_source, "get_all_staff", lambda: ["Alice", "Bob"])
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["projet"] = {"no": "P-100", "id_project": 1,
                                  "semaine": datetime.date(2026, 6, 7),
                                  "adresse": "", "lat": None, "lon": None}
    at.session_state["jours"] = {"Dimanche": {"date": None, "quarts": {"Jour": _empty_quart_dict()}},
                                  "Lundi": {"date": datetime.date(2026, 6, 8),
                                            "quarts": {"Jour": _empty_quart_dict()}},
                                  "Mardi": {"date": None, "quarts": {"Jour": _empty_quart_dict()}},
                                  "Mercredi": {"date": None, "quarts": {"Jour": _empty_quart_dict()}},
                                  "Jeudi": {"date": None, "quarts": {"Jour": _empty_quart_dict()}},
                                  "Vendredi": {"date": None, "quarts": {"Jour": _empty_quart_dict()}},
                                  "Samedi": {"date": None, "quarts": {"Jour": _empty_quart_dict()}}}
    at.session_state["active_day"] = "Lundi"
    at.session_state["view"] = "day_entry"
    at.run()
    # le button_group des pills personnel expose "Alice" parmi ses options
    opts = [getattr(o, "content", o) for bg in at.button_group for o in getattr(bg, "options", [])]
    assert "Alice" in opts
    assert not at.exception


def test_setting_personnel_updates_config(monkeypatch):
    """Pré-charger personnel dans le quart se reflète dans le modèle après run."""
    import data_source
    monkeypatch.setattr(data_source, "get_projects", lambda: [(1, "P-100", "Alpha")])
    monkeypatch.setattr(data_source, "get_activities", lambda pid: ["C01 - Test"])
    monkeypatch.setattr(data_source, "get_project_staff",
                        lambda pid: ["Alice"] if pid == 1 else [])
    monkeypatch.setattr(data_source, "get_all_staff", lambda: ["Alice"])
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["projet"] = {"no": "P-1", "id_project": 1,
                                  "semaine": datetime.date(2026, 6, 7),
                                  "adresse": "", "lat": None, "lon": None}
    q = _empty_quart_dict()
    q["personnel"] = ["Alice"]
    at.session_state["jours"] = {"Dimanche": {"date": None, "quarts": {"Jour": _empty_quart_dict()}},
                                  "Lundi": {"date": datetime.date(2026, 6, 8),
                                            "quarts": {"Jour": q}},
                                  "Mardi": {"date": None, "quarts": {"Jour": _empty_quart_dict()}},
                                  "Mercredi": {"date": None, "quarts": {"Jour": _empty_quart_dict()}},
                                  "Jeudi": {"date": None, "quarts": {"Jour": _empty_quart_dict()}},
                                  "Vendredi": {"date": None, "quarts": {"Jour": _empty_quart_dict()}},
                                  "Samedi": {"date": None, "quarts": {"Jour": _empty_quart_dict()}}}
    at.session_state["active_day"] = "Lundi"
    at.session_state["view"] = "day_entry"
    at.run()
    assert at.session_state["jours"]["Lundi"]["quarts"]["Jour"]["personnel"] == ["Alice"]
    assert not at.exception


def test_export_view_generates_without_error():
    at = _run()
    at.session_state["view"] = "export"
    at.run()
    btns = [b for b in at.button if "Générer" in b.label]
    assert btns
    btns[0].click().run()
    assert not at.exception
    assert any(getattr(el, "type", None) == "download_button" for el in at.main)  # build_workbook() a produit le fichier -> bouton de téléchargement présent


def test_project_selectbox_lists_db_projects(monkeypatch):
    import data_source
    monkeypatch.setattr(data_source, "get_projects",
                        lambda: [(1, "P-100", "Alpha"), (2, "P-200", "Beta")])
    monkeypatch.setattr(data_source, "get_project_staff", lambda pid: [])
    at = _run()
    sb = [s for s in at.selectbox if s.label == "Projet"][0]
    assert list(sb.options) == ["P-100 — Alpha", "P-200 — Beta"]
    assert not at.exception


def test_selecting_project_sets_id(monkeypatch):
    import data_source
    monkeypatch.setattr(data_source, "get_projects",
                        lambda: [(1, "P-100", "Alpha"), (2, "P-200", "Beta")])
    monkeypatch.setattr(data_source, "get_project_staff", lambda pid: [])
    at = _run()
    sb = [s for s in at.selectbox if s.label == "Projet"][0]
    sb.set_value("P-200 — Beta").run()
    assert at.session_state["projet"]["id_project"] == 2
    assert at.session_state["projet"]["no"] == "P-200"


def test_dashboard_shows_error_when_db_unreachable(monkeypatch):
    import data_source
    monkeypatch.setattr(data_source, "get_projects", lambda: [])
    at = _run()
    assert any("projets" in (e.value or "").lower() for e in at.error)
    assert not at.exception



def test_day_cards_are_clickable_and_no_saisir_button(monkeypatch):
    at = _run_with_project(monkeypatch)
    # plus de bouton « Saisir » : toute la carte est cliquable
    assert not any((b.label or "") == "Saisir" for b in at.button)
    lundi = [b for b in at.button if "Lundi" in (b.label or "")]
    assert lundi, "la carte Lundi doit être un bouton cliquable"
    lundi[0].click().run()
    assert at.session_state["view"] == "day_entry"
    assert at.session_state["active_day"] == "Lundi"


def test_today_card_is_flagged():
    at = _run()
    today_name = ["Lundi", "Mardi", "Mercredi", "Jeudi",
                  "Vendredi", "Samedi", "Dimanche"][datetime.date.today().weekday()]
    # la carte du jour existe
    assert any(today_name in (b.label or "") for b in at.button)
    # le badge « Aujourd'hui » est injecté en CSS (::after) sur la carte du jour
    styles = " ".join((m.value or "") for m in at.markdown)
    assert f".st-key-go_{today_name} button::after" in styles
    assert "AUJOURD'HUI" in styles


def test_week_dates_align_to_real_weekday(monkeypatch):
    at = _run_with_project(monkeypatch)
    sem = [d for d in at.date_input if d.label == "Semaine du"][0]
    sem.set_value(datetime.date(2026, 6, 18)).run()   # un jeudi
    jours = at.session_state["jours"]
    assert jours["Dimanche"]["date"] == datetime.date(2026, 6, 14)
    assert jours["Jeudi"]["date"] == datetime.date(2026, 6, 18)
    # le champ « Semaine du » affiche le dimanche
    sem2 = [d for d in at.date_input if d.label == "Semaine du"][0]
    assert sem2.value == datetime.date(2026, 6, 14)


def test_fields_disabled_until_project_selected():
    at = _run()  # base injoignable en test -> aucun projet -> rien de sélectionné
    cards = [b for b in at.button if "Lundi" in (b.label or "")]
    assert cards and cards[0].disabled, "les cartes de jour doivent être grisées sans projet"
    sem = [d for d in at.date_input if d.label == "Semaine du"][0]
    assert sem.disabled, "« Semaine du » doit être grisé sans projet"
    export = [b for b in at.button if "EXPORT" in (b.label or "")][0]
    assert export.disabled, "les boutons du bas doivent être grisés sans projet"


def test_fields_enabled_after_project_selected(monkeypatch):
    at = _run_with_project(monkeypatch)
    cards = [b for b in at.button if "Lundi" in (b.label or "")]
    assert cards and not cards[0].disabled
    sem = [d for d in at.date_input if d.label == "Semaine du"][0]
    assert not sem.disabled
    export = [b for b in at.button if "EXPORT" in (b.label or "")][0]
    assert not export.disabled



def test_day_hours_entry_updates_model(monkeypatch):
    at = _open_day_for_entry(monkeypatch)   # personnel Alice, activité dispo "C01 - Test"
    _goto_saisie(at)
    # choisir l'activité pour Alice puis saisir TR/TS
    ms = [m for m in at.multiselect if m.key == "acts_Lundi_Jour_Alice"][0]
    ms.set_value(["C01 - Test"]).run()
    [n for n in at.number_input if n.key == "tr_Lundi_Jour_Alice_C01 - Test"][0].set_value(8.0).run()
    [n for n in at.number_input if n.key == "ts_Lundi_Jour_Alice_C01 - Test"][0].set_value(1.5).run()
    q = at.session_state["jours"]["Lundi"]["quarts"]["Jour"]
    assert q["heures"]["Alice"]["C01 - Test"] == {"TR": 8.0, "TS": 1.5}
    assert not at.exception


def test_day_equip_codes_and_hours(monkeypatch):
    at = _open_day_for_entry(monkeypatch)
    _goto_saisie(at)
    [n for n in at.number_input if n.key == "eqh_Lundi_Jour_Alice"][0].set_value(10.0).run()
    q = at.session_state["jours"]["Lundi"]["quarts"]["Jour"]
    assert q["equip_hours"]["Alice"] == 10.0
    # les pills de code d'équipement existent pour l'employé
    assert any((bg.key or "") == "eqc_Lundi_Jour_Alice" for bg in at.button_group)
    assert not at.exception


def test_day_prime_inline(monkeypatch):
    at = _open_day_for_entry(monkeypatch)
    _goto_saisie(at)
    [n for n in at.number_input if n.key == "p_Lundi_Jour_Alice"][0].set_value(2.0).run()
    assert at.session_state["jours"]["Lundi"]["quarts"]["Jour"]["prime"]["Alice"] == 2.0
    assert not at.exception


def test_day_comment_inline(monkeypatch):
    at = _open_day_for_entry(monkeypatch)
    _goto_saisie(at)
    [t for t in at.text_input if t.key == "c_Lundi_Jour_Alice"][0].set_value("RAS").run()
    assert at.session_state["jours"]["Lundi"]["quarts"]["Jour"]["commentaire_ligne"]["Alice"] == "RAS"
    assert not at.exception


@pytest.mark.skip(reason="Badge « Total » retiré temporairement de l'en-tête de saisie journalière")
def test_day_total_badge_reflects_entered_hours(monkeypatch):
    """Le badge « Total » en haut doit refléter immédiatement les heures saisies,
    même quand elles sont réparties sur plusieurs activités (pas de retard d'une
    interaction dû à l'ordre de rendu)."""
    import data_source
    monkeypatch.setattr(data_source, "get_projects", lambda: [(1, "P-100", "Alpha")])
    monkeypatch.setattr(data_source, "get_activities",
                        lambda pid: ["C01 - Test", "C02 - Autre"])
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["projet"] = {"no": "P-100", "id_project": 1,
                                  "semaine": datetime.date(2026, 6, 7),
                                  "adresse": "", "lat": None, "lon": None}
    q = _empty_quart_dict()
    q["personnel"] = ["Alice"]
    at.session_state["jours"] = {j: {"date": None, "quarts": {"Jour": _empty_quart_dict()}}
                                  for j in ["Dimanche", "Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]}
    at.session_state["jours"]["Lundi"] = {"date": datetime.date(2026, 6, 8),
                                           "quarts": {"Jour": q}}
    at.session_state["active_day"] = "Lundi"
    at.session_state["view"] = "day_entry"
    at.run()
    acts = [m for m in at.multiselect if "C01 - Test" in (m.options or [])][0]
    acts.set_value(["C01 - Test", "C02 - Autre"]).run()
    c1 = [n for n in at.number_input if n.key == "h_Lundi_Jour_Alice_C01 - Test"][0]
    c1.set_value(3.0).run()
    c2 = [n for n in at.number_input if n.key == "h_Lundi_Jour_Alice_C02 - Autre"][0]
    c2.set_value(0.5).run()
    badge = " ".join((m.value or "") for m in at.markdown if "Total:" in (m.value or ""))
    assert "3.5 h" in badge, f"badge attendu 3.5 h, obtenu : {badge!r}"
    assert not at.exception


def test_day_header_date_is_french(monkeypatch):
    """Le badge de date en haut du jour affiche le mois en français (pas en anglais)."""
    at = _open_day_for_entry(monkeypatch)  # semaine du 2026-06-07 -> Lundi = 08 juin
    badge = " ".join((m.value or "") for m in at.markdown if "juin" in (m.value or ""))
    assert "08 juin 2026" in badge, f"date française attendue, obtenu : {badge!r}"
    assert "June" not in badge
    assert not at.exception


def test_manual_add_employee_confirms_and_clears_field(monkeypatch):
    """Ajout manuel d'un employé : le nom est ajouté, le champ est vidé,
    et l'état est marqué « non enregistré » (la confirmation visuelle est un
    toast, non capturé par AppTest — on vérifie l'effet sur l'état)."""
    at = _open_day_for_entry(monkeypatch, personnel=())
    field = [t for t in at.text_input if t.key == "new_employee_Lundi_Jour"][0]
    field.set_value("Marie Tremblay").run()
    [b for b in at.button if b.key == "add_manual_Lundi_Jour"][0].click().run()
    q = at.session_state["jours"]["Lundi"]["quarts"]["Jour"]
    assert "Marie Tremblay" in q["personnel"]
    assert at.session_state["new_employee_Lundi_Jour"] == ""   # champ vidé
    assert at.session_state["dirty"] is True
    assert not at.exception


def test_manual_add_equipment_confirms_and_clears_field(monkeypatch):
    """Ajout d'un équipement : ajouté, champ vidé, état marqué « non enregistré »
    (même principe que l'ajout manuel de personnel ; toast non capturé par AppTest)."""
    at = _open_day_for_entry(monkeypatch)
    field = [t for t in at.text_input if t.key == "new_equipment_Lundi_Jour"][0]
    field.set_value("Camion").run()
    [b for b in at.button if b.key == "add_equipment_Lundi_Jour"][0].click().run()
    q = at.session_state["jours"]["Lundi"]["quarts"]["Jour"]
    assert "Camion" in q["equipements"]
    assert at.session_state["new_equipment_Lundi_Jour"] == ""   # champ vidé
    assert at.session_state["dirty"] is True
    assert not at.exception


def test_resource_selector_shows_selected_card(monkeypatch):
    """Le sélecteur d'employé affiche la fiche du membre choisi (et masque les autres).
    On pilote la sélection via session_state (st.pills non cliquable sous AppTest)."""
    at = _open_day_for_entry(monkeypatch, personnel=("Alice", "Bob"))
    _goto_saisie(at)
    # Alice (premier du roster) est sélectionnée par défaut -> sa fiche est rendue
    assert any(m.key == "acts_Lundi_Jour_Alice" for m in at.multiselect)
    assert not any(m.key == "acts_Lundi_Jour_Bob" for m in at.multiselect)
    # Sélectionner Bob -> sa fiche s'affiche, celle d'Alice disparaît
    at.session_state["resource_sel_Lundi_Jour"] = "Bob"
    at.run()
    assert any(m.key == "acts_Lundi_Jour_Bob" for m in at.multiselect)
    assert not any(m.key == "acts_Lundi_Jour_Alice" for m in at.multiselect)
    assert not at.exception


def test_resource_search_filters_rail(monkeypatch):
    """La recherche filtre les boutons du rail sans changer la sélection."""
    at = _open_day_for_entry(monkeypatch, personnel=("Alice", "Bob", "Charlie"))
    _goto_saisie(at)
    # Sans filtre : un bouton pick_ par ressource
    pick_keys = {b.key for b in at.button if b.key and b.key.startswith("pick_Lundi_Jour_")}
    assert pick_keys == {"pick_Lundi_Jour_Alice", "pick_Lundi_Jour_Bob", "pick_Lundi_Jour_Charlie"}
    # Filtre "ali" -> seule Alice reste, la sélection par défaut (Alice) est inchangée
    search = [t for t in at.text_input if t.key == "res_search_Lundi_Jour"][0]
    search.set_value("ali").run()
    pick_keys = {b.key for b in at.button if b.key and b.key.startswith("pick_Lundi_Jour_")}
    assert pick_keys == {"pick_Lundi_Jour_Alice"}
    assert at.session_state["resource_sel_Lundi_Jour"] == "Alice"
    assert not at.exception


def test_resource_pick_button_selects_and_survives_filter(monkeypatch):
    """Cliquer un bouton du rail sélectionne la ressource ; un filtre qui l'exclut
    n'efface pas la fiche affichée."""
    at = _open_day_for_entry(monkeypatch, personnel=("Alice", "Bob"))
    _goto_saisie(at)
    # Cliquer Bob -> sa fiche s'affiche
    [b for b in at.button if b.key == "pick_Lundi_Jour_Bob"][0].click().run()
    assert at.session_state["resource_sel_Lundi_Jour"] == "Bob"
    assert any(m.key == "acts_Lundi_Jour_Bob" for m in at.multiselect)
    # Filtrer sur "ali" (exclut Bob du rail) -> la fiche de Bob reste affichée
    [t for t in at.text_input if t.key == "res_search_Lundi_Jour"][0].set_value("ali").run()
    assert at.session_state["resource_sel_Lundi_Jour"] == "Bob"
    assert any(m.key == "acts_Lundi_Jour_Bob" for m in at.multiselect)
    assert not at.exception


def test_project_selection_prefills_team(monkeypatch):
    import data_source
    monkeypatch.setattr(data_source, "get_projects", lambda: [(1, "P-100", "Alpha")])
    monkeypatch.setattr(data_source, "get_project_staff",
                        lambda pid: ["Jean Tremblay (Électricien)"] if pid == 1 else [])
    at = _run()
    sb = [s for s in at.selectbox if s.label == "Projet"][0]
    sb.set_value("P-100 — Alpha").run()
    # La suggestion d'équipe est désormais par quart (pills dans l'onglet Config) ;
    # au niveau tableau de bord on vérifie que le garde de pré-remplissage a bien
    # enregistré le projet traité.
    assert at.session_state["staff_prefilled_for"] == 1
    assert not at.exception


def test_config_personnel_options_include_suggested(monkeypatch):
    """Après sélection projet, le personnel suggéré apparaît dans les pills du jour."""
    import data_source
    monkeypatch.setattr(data_source, "get_projects", lambda: [(1, "P-100", "Alpha")])
    monkeypatch.setattr(data_source, "get_activities", lambda pid: ["C01 - Test"])
    monkeypatch.setattr(data_source, "get_project_staff",
                        lambda pid: ["Jean Tremblay (Électricien)"] if pid == 1 else [])
    monkeypatch.setattr(data_source, "get_all_staff",
                        lambda: ["Jean Tremblay (Électricien)"])
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["projet"] = {"no": "P-100", "id_project": 1,
                                  "semaine": datetime.date(2026, 6, 7),
                                  "adresse": "", "lat": None, "lon": None}
    at.session_state["jours"] = {j: {"date": None, "quarts": {"Jour": _empty_quart_dict()}}
                                  for j in ["Dimanche", "Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]}
    at.session_state["jours"]["Lundi"] = {"date": datetime.date(2026, 6, 8),
                                           "quarts": {"Jour": _empty_quart_dict()}}
    at.session_state["active_day"] = "Lundi"
    at.session_state["view"] = "day_entry"
    at.run()
    opts = [getattr(o, "content", o) for bg in at.button_group for o in getattr(bg, "options", [])]
    assert "Jean Tremblay (Électricien)" in opts


def test_day_entry_no_activity_shows_info(monkeypatch):
    import data_source
    monkeypatch.setattr(data_source, "get_projects", lambda: [(1, "P-100", "Alpha")])
    monkeypatch.setattr(data_source, "get_activities", lambda pid: [])
    monkeypatch.setattr(data_source, "get_project_staff", lambda pid: [])
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["projet"] = {"no": "P-100", "id_project": 1,
                                  "semaine": datetime.date(2026, 6, 7),
                                  "adresse": "", "lat": None, "lon": None}
    q = _empty_quart_dict()
    q["personnel"] = ["Alice"]
    at.session_state["jours"] = {j: {"date": None, "quarts": {"Jour": _empty_quart_dict()}}
                                  for j in ["Dimanche", "Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]}
    at.session_state["jours"]["Lundi"] = {"date": datetime.date(2026, 6, 8),
                                           "quarts": {"Jour": q}}
    at.session_state["active_day"] = "Lundi"
    at.session_state["view"] = "day_entry"
    at.run()
    _goto_saisie(at)
    # aucune activité disponible -> aucun champ TR pour Alice
    assert not any((n.key or "").startswith("tr_Lundi_Jour_Alice_") for n in at.number_input)
    assert not at.exception


def test_add_quart_creates_second_quart(monkeypatch):
    at = _open_day_for_entry(monkeypatch)
    assert list(at.session_state["jours"]["Lundi"]["quarts"].keys()) == ["Jour"]
    [b for b in at.button if b.key == "empty_quart_Lundi_Soir"][0].click().run()
    assert app_quarts(at, "Lundi") == ["Jour", "Soir"]
    # la vue bascule immédiatement sur le quart ajouté : le bouton de quart « Soir » est actif (primary)
    assert at.session_state["active_quart_Lundi"] == "Soir"
    assert any(b.key == "quart_pick_Lundi_Soir" for b in at.button)
    assert not at.exception


def test_hours_are_distinct_per_quart(monkeypatch):
    at = _open_day_for_entry(monkeypatch)
    # activité + heures sur Jour (carte par ressource)
    _goto_saisie(at)
    [m for m in at.multiselect if m.key == "acts_Lundi_Jour_Alice"][0].set_value(["C01 - Test"]).run()
    [n for n in at.number_input if n.key == "tr_Lundi_Jour_Alice_C01 - Test"][0].set_value(8.0).run()
    # le sélecteur de quart est sur l'étape Configuration : y revenir pour ajouter Soir
    _goto_config(at)
    # ajouter Soir (vide) via le popover ＋ ; la vue bascule dessus
    [b for b in at.button if b.key == "empty_quart_Lundi_Soir"][0].click().run()
    assert at.session_state["active_quart_Lundi"] == "Soir"
    # Soir : pas d'heures, activités à choisir indépendamment
    qj = at.session_state["jours"]["Lundi"]["quarts"]["Jour"]
    qs = at.session_state["jours"]["Lundi"]["quarts"]["Soir"]
    assert qj["heures"]["Alice"]["C01 - Test"] == {"TR": 8.0, "TS": 0.0}
    assert qs["heures"] == {}
    assert not at.exception


def test_no_quart_remove_button(monkeypatch):
    """Le retrait d'un quart n'est plus proposé dans l'UI, même avec plusieurs quarts."""
    at = _open_day_for_entry(monkeypatch)
    # ajouter un 2e quart via le popover ＋
    [b for b in at.button if b.key == "empty_quart_Lundi_Soir"][0].click().run()
    assert app_quarts(at, "Lundi") == ["Jour", "Soir"]
    # aucun bouton de retrait de quart, quel que soit le nombre de quarts
    assert not any((b.key or "").startswith("remove_quart_") for b in at.button)
    assert not at.exception


def test_add_quart_can_copy_team_and_activities(monkeypatch):
    at = _open_day_for_entry(monkeypatch, personnel=("Alice",))
    # enrichir le quart Jour (équipement + responsable + activités) pour vérifier la copie complète
    jour_q = at.session_state["jours"]["Lundi"]["quarts"]["Jour"]
    jour_q["equipements"] = ["Camion v1"]
    jour_q["responsable"] = "M. Roy"
    jour_q["activites"] = ["C01 - Test"]
    at.run()
    # saisir des heures sur Jour (carte) -> elles ne doivent PAS être copiées
    _goto_saisie(at)
    [m for m in at.multiselect if m.key == "acts_Lundi_Jour_Alice"][0].set_value(["C01 - Test"]).run()
    [n for n in at.number_input if n.key == "tr_Lundi_Jour_Alice_C01 - Test"][0].set_value(5.0).run()
    # le popover de copie est sur l'étape Configuration : y revenir
    _goto_config(at)
    # ajouter Soir en copiant depuis Jour via le popover ＋ « Copier depuis Jour »
    [b for b in at.button if b.key == "copy_quart_Lundi_Soir"][0].click().run()
    qs = at.session_state["jours"]["Lundi"]["quarts"]["Soir"]
    assert qs["personnel"] == ["Alice"]
    assert qs["equipements"] == ["Camion v1"]
    assert qs["responsable"] == "M. Roy"
    assert qs["heures"] == {}     # les heures ne sont PAS copiées
    assert qs["prime"] == {}
    assert not at.exception


def test_saisie_card_table_header_and_no_repeated_labels(monkeypatch):
    """Étape Saisie : une activité sélectionnée affiche l'en-tête de tableau
    Activité/TR/TS, sans étiquette répétée « TR — … », et la saisie écrit
    toujours dans la forme {"TR","TS"}."""
    at = _open_day_for_entry(monkeypatch)   # personnel Alice, activité "C01 - Test"
    _goto_saisie(at)
    ms = [m for m in at.multiselect if m.key == "acts_Lundi_Jour_Alice"][0]
    ms.set_value(["C01 - Test"]).run()
    md = " ".join((m.value or "") for m in at.markdown)
    assert "Activité" in md and "TR" in md and "TS" in md   # ligne d'en-tête présente
    labels = [(n.label or "") for n in at.number_input]
    assert not any(l.startswith("TR —") or l.startswith("TS —") for l in labels)
    tr = [n for n in at.number_input if n.key == "tr_Lundi_Jour_Alice_C01 - Test"][0]
    tr.set_value(8.0).run()
    q = at.session_state["jours"]["Lundi"]["quarts"]["Jour"]
    assert q["heures"]["Alice"]["C01 - Test"] == {"TR": 8.0, "TS": 0.0}
    assert not at.exception


def test_copy_day_copies_hours_and_equipment(monkeypatch):
    at = _open_day_for_entry(monkeypatch, jour="Mardi", personnel=("Alice",))
    # préparer Lundi (jour précédent) avec heures TR/TS + équipement
    lundi = at.session_state["jours"]["Lundi"]
    lundi["date"] = datetime.date(2026, 6, 8)
    ql = lundi["quarts"]["Jour"]
    ql["personnel"] = ["Alice"]
    ql["heures"] = {"Alice": {"C01 - Test": {"TR": 6.0, "TS": 0.0}}}
    ql["equip_codes"] = {"Alice": ["C"]}
    ql["equip_hours"] = {"Alice": 4.0}
    at.run()
    [b for b in at.button if b.key == "copy_Mardi"][0].click().run()
    qm = at.session_state["jours"]["Mardi"]["quarts"]["Jour"]
    assert qm["heures"] == {"Alice": {"C01 - Test": {"TR": 6.0, "TS": 0.0}}}
    assert qm["equip_codes"] == {"Alice": ["C"]}
    assert qm["equip_hours"] == {"Alice": 4.0}
    assert not at.exception


