# Saisie par quart — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faire d'un jour un conteneur de 1 à 3 quarts (Jour/Soir/Nuit), chacun étant un mini-rapport autonome (équipe, équipements, activités, météo, heures, primes, commentaires, note, responsable), avec persistance par quart.

**Architecture:** Le modèle en mémoire passe de `jours[j] = {champs…}` à `jours[j] = {"date", "quarts": {nom_quart: <quart>}}`. Tout ce qui était au niveau jour/semaine passe par quart. L'UID de saisie travaille sur le **quart courant** ; un sélecteur permet d'ajouter/retirer/basculer les quarts. La persistance introduit le grain `report_quarts` entre `report_days` et `report_hours/lines/resources`, avec migration non destructive (anciennes données repliées dans un quart « Jour »).

**Tech Stack:** Python, Streamlit (`st.radio`, `st.tabs`, `st.multiselect`, `st.pills`), SQLAlchemy + Postgres (Neon), pytest + `streamlit.testing.v1.AppTest`.

## Global Constraints

- Textes d'interface en **français**.
- Cibles tactiles tablette : boutons ≥ 42px (réutiliser les styles existants).
- **Source unique** des quarts : `QUART_NAMES = ["Jour", "Soir", "Nuit"]` (ordre Jour<Soir<Nuit). Ne pas dupliquer la liste.
- Un jour a **toujours ≥ 1 quart** ; défaut « Jour ». **Interdit de retirer le dernier quart.**
- Quart actif de l'UI = `st.session_state`, **jamais** dans le modèle de données.
- Migration de schéma **idempotente et non destructive** : aucune heure saisie n'est perdue (repli dans un quart « Jour »).
- Commande de test : `.venv/bin/python -m pytest`.
- La persistance BD réelle (Neon) n'est PAS testée en unitaire (convention `test_reports.py` : types Postgres non reproductibles hors ligne) → vérif manuelle.

## File Structure

- `app.py` — modèle/état (`_empty_quart`, `_empty_day`, helpers), météo par quart, `view_dashboard`, `view_day_entry` (sélecteur de quart + onglets branchés sur le quart courant), export (`_legacy_day` par quart, `build_workbook` itère jours×quarts).
- `reports.py` — schéma (`report_quarts`, `report_quart_resources`, repointage `report_hours`/`report_lines`), `save_report`, `load_report`, migration.
- `tests/test_model.py` — fixtures et signatures par quart.
- `tests/test_ui.py` — setups d'état par quart, clés de widgets, nouveaux tests multi-quarts.

## Task Ordering

- **Task 1** migre tout le modèle en mémoire + UI + tableau de bord + export vers le grain « quart », avec **un seul quart par défaut (Jour)** et **sans** encore le sélecteur d'ajout. Comportement identique à aujourd'hui pour l'utilisateur, mais interne par quart. Tous les tests verts.
- **Task 2** expose le **multi-quart** : sélecteur, ➕ ajouter (avec copie équipe+activités), retrait, indicateur au tableau de bord.
- **Task 3** réécrit la **persistance** + migration (reports.py) + hydratation + purge.

Task 1 est volumineuse mais atomique : le changement de forme de l'état touche simultanément l'UI, l'export et les tests ; les scinder laisserait la suite rouge entre tâches.

---

### Task 1 : Modèle par quart (état + UI + tableau de bord + export, quart unique par défaut)

**Files:**
- Modify: `app.py` — constantes (~46), helpers (`_roster`/`_resource_total`/`_day_columns`/`_day_total` ~293-305), `_legacy_day`/`build_workbook` (~310-371), météo (`_fill_weather_for_day` ~255, `_fill_week_weather` ~276), état (`init_state` ~85, `_empty_day` ~188, `_apply_week_dates` ~199), `view_dashboard` (~755), `view_day_entry` (~827).
- Modify: `tests/test_model.py`, `tests/test_ui.py`.

**Interfaces produites (utilisées par Task 2 & 3) :**
- `QUART_NAMES = ["Jour", "Soir", "Nuit"]`
- `_empty_quart() -> dict` ; `_empty_day() -> {"date": None, "quarts": {"Jour": _empty_quart()}}`
- `_day_quart_names(day) -> list[str]` (ordonné Jour<Soir<Nuit, restreint aux présents)
- `_quart_columns(quart) -> list[str]` ; `_quart_total(quart) -> float` ; `_day_total(day) -> float`
- `_roster(quart) -> list[(name, 'P'|'E')]` ; `_resource_total(quart, name) -> float`
- `_legacy_day(quart) -> dict` (signature mono-argument : le quart porte tout)
- `_current_quart_name(jour) -> str` : nom du quart courant pour l'UI (lit `st.session_state[f"active_quart_{jour}"]`, défaut = 1ᵉʳ quart présent)
- Clés de widgets par quart : `acts_{jour}_{q}`, `{jour}_{q}_temp_am`, `{jour}_{q}_temp_pm`, `{jour}_{q}_cond`, `h_{jour}_{q}_{name}_{col}`, `p_{jour}_{q}_{name}`, `c_{jour}_{q}_{name}`, `note_{jour}_{q}`, `roster_search_{jour}_{q}`, `personnel_pills_{jour}_{q}`, etc.

- [ ] **Step 1 : Tests modèle — réécrire `tests/test_model.py` (RED)**

Remplacer `_sample_config`/`_sample_day` et les tests de forme/total/colonnes/roster/legacy par la version par quart :

```python
import app

import pandas as pd


def test_empty_day_shape():
    d = app._empty_day()
    assert d["date"] is None
    assert list(d["quarts"].keys()) == ["Jour"]
    q = d["quarts"]["Jour"]
    assert q["activites"] == [] and q["autres"] == []
    assert q["heures"] == {} and q["prime"] == {} and q["commentaire_ligne"] == {}
    assert q["personnel"] == [] and q["equipements"] == []
    assert q["responsable"] == "" and q["description"] == ""
    assert q["conditions"] == []
    assert q["temp_am"] is None and q["temp_pm"] is None


def _sample_quart():
    q = app._empty_quart()
    q["personnel"] = ["Mathis", "Roy"]
    q["equipements"] = ["Camion v1892"]
    q["activites"] = ["Excavation"]
    q["autres"] = ["P-77"]
    q["heures"] = {"Mathis": {"Excavation": 4.0, "P-77": 2.0},
                   "Camion v1892": {"Excavation": 8.0}}
    q["prime"] = {"Mathis": 2.0}
    q["commentaire_ligne"] = {"Mathis": "test"}
    return q


def _sample_day():
    d = app._empty_day()
    d["quarts"]["Jour"] = _sample_quart()
    return d


def test_roster_order_and_types():
    assert app._roster(_sample_quart()) == [("Mathis", "P"), ("Roy", "P"), ("Camion v1892", "E")]


def test_quart_total():
    assert app._quart_total(_sample_quart()) == 14.0  # (4+2) + 8


def test_day_total_sums_quarts():
    d = _sample_day()
    d["quarts"]["Soir"] = app._empty_quart()
    d["quarts"]["Soir"]["activites"] = ["Excavation"]
    d["quarts"]["Soir"]["heures"] = {"Roy": {"Excavation": 3.0}}
    assert app._day_total(d) == 17.0  # 14 (Jour) + 3 (Soir)


def test_day_quart_names_ordered():
    d = app._empty_day()
    d["quarts"]["Nuit"] = app._empty_quart()
    d["quarts"]["Soir"] = app._empty_quart()
    assert app._day_quart_names(d) == ["Jour", "Soir", "Nuit"]


def test_quart_columns():
    assert app._quart_columns(_sample_quart()) == ["Excavation", "P-77"]


def test_resource_total():
    q = _sample_quart()
    assert app._resource_total(q, "Mathis") == 6.0
    assert app._resource_total(q, "Camion v1892") == 8.0
    assert app._resource_total(q, "Inconnu") == 0.0


def test_legacy_day_maps_labels_to_keys():
    leg = app._legacy_day(_sample_quart())
    assert leg["headers"]["h0"] == "Excavation"
    assert leg["headers"]["a0"] == "P-77"
    pers, equip = leg["pers"], leg["equip"]
    for k in app.HOUR_KEYS:
        assert k in pers.columns and k in equip.columns
    assert list(pers["Nom"]) == ["Mathis", "Roy"]
    mathis = pers[pers["Nom"] == "Mathis"].iloc[0]
    assert mathis["h0"] == 4.0 and mathis["a0"] == 2.0
    assert mathis["Prime"] == 2.0 and mathis["Commentaire"] == "test"
    assert list(equip["Véhicule"]) == ["Camion v1892"]
    camion = equip[equip["Véhicule"] == "Camion v1892"].iloc[0]
    assert camion["h0"] == 8.0
```

Conserver tels quels : `test_week_start_snaps_to_sunday`, `test_wmo_to_condition`, `test_codes_to_condition_picks_most_significant_daytime`.
Adapter les deux tests météo (les heures météo sont désormais dans le 1ᵉʳ quart) :

```python
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
```

- [ ] **Step 2 : Lancer les tests modèle (RED)**

Run: `.venv/bin/python -m pytest tests/test_model.py -q`
Expected: FAIL (`_empty_quart`, `_quart_total`, `_quart_columns`, `_day_quart_names` n'existent pas ; `_day_total`/`_roster`/`_resource_total`/`_legacy_day` ont l'ancienne signature).

- [ ] **Step 3 : Modèle & helpers (`app.py`)**

Sous `QUARTS = ["", "Jour", "Soir", "Nuit"]` (app.py:46), ajouter :

```python
QUART_NAMES = [q for q in QUARTS if q]  # ["Jour", "Soir", "Nuit"], ordonné
```

Remplacer `_empty_day()` (app.py:188-192) par :

```python
def _empty_quart():
    return {
        "responsable": "", "activites": [], "autres": [],
        "personnel": [], "equipements": [],
        "temp_am": None, "temp_pm": None, "conditions": [],
        "heures": {}, "prime": {}, "commentaire_ligne": {},
        "description": "",
    }

def _empty_day():
    return {"date": None, "quarts": {"Jour": _empty_quart()}}

def _day_quart_names(day):
    return [q for q in QUART_NAMES if q in day["quarts"]]
```

Remplacer les helpers métier (app.py:293-305) par :

```python
def _roster(quart):
    return ([(n, "P") for n in quart.get("personnel", [])]
            + [(e, "E") for e in quart.get("equipements", [])])

def _resource_total(quart, name):
    return float(sum(float(v or 0) for v in quart["heures"].get(name, {}).values()))

def _quart_columns(quart):
    return list(quart["activites"]) + list(quart["autres"])

def _quart_total(quart):
    cols = _quart_columns(quart)
    return float(sum(sum(float(h.get(c) or 0) for c in cols) for h in quart["heures"].values()))

def _day_total(day):
    return float(sum(_quart_total(q) for q in day["quarts"].values()))
```

Mettre à jour `_apply_week_dates` (app.py:199-203) — seul `day["date"]` change, indépendant des quarts : inchangé (il écrit `st.session_state.jours[jour]["date"]`). Vérifier qu'il n'accède pas à d'autres champs (c'est le cas).

`init_state` (app.py:85-102) : retirer `st.session_state.config` (plus de niveau semaine). Remplacer le bloc `if "config" not in st.session_state: ...` par rien (supprimer ces 2 lignes). Les autres clés (`projet`, `jours`, `view`, `active_day`, `dirty`, `loaded_key`, `schema_ready`) restent.

- [ ] **Step 4 : Météo par quart (`app.py`)**

Remplacer `_fill_weather_for_day(jour_name)` (app.py:255-274) par une version qui écrit dans un quart :

```python
def _fill_weather_for_quart(jour_name, quart_name):
    proj = st.session_state.projet
    day = st.session_state.jours[jour_name]
    quart = day["quarts"][quart_name]

    if (not proj.get("lat") or not proj.get("lon")) and proj.get("adresse"):
        coords = _geocode_address(proj["adresse"])
        if coords:
            proj["lat"], proj["lon"] = coords

    if proj.get("lat") and proj.get("lon") and day.get("date"):
        w = _fetch_day_weather(proj["lat"], proj["lon"], day["date"].isoformat())
        if w:
            quart["temp_am"] = w["temp_am"]
            quart["temp_pm"] = w["temp_pm"]
            quart["conditions"] = list(w["conditions"]) if w["conditions"] else []
            return True
        return False
    return False
```

Remplacer `_fill_week_weather(proj, jours)` (app.py:276-288) — remplit le 1ᵉʳ quart de chaque jour :

```python
def _fill_week_weather(proj, jours):
    if not (proj.get("lat") and proj.get("lon")):
        return
    for jour in JOURS:
        day = jours[jour]
        quart = day["quarts"][_day_quart_names(day)[0]]
        if day.get("date") and not quart.get("temp_am"):
            w = _fetch_day_weather(proj["lat"], proj["lon"], day["date"].isoformat())
            if w:
                quart["temp_am"] = w["temp_am"]
                quart["temp_pm"] = w["temp_pm"]
                quart["conditions"] = w["conditions"]
```

- [ ] **Step 5 : Export par quart (`app.py`)**

Remplacer `_legacy_day(config, day)` (app.py:310-345) par `_legacy_day(quart)` :

```python
def _legacy_day(quart):
    acts = list(quart["activites"])[:8]
    autres = list(quart["autres"])[:4]
    headers = {f"h{i}": "" for i in range(8)}
    headers.update({f"a{i}": "" for i in range(4)})
    label_to_key = {}
    for i, lbl in enumerate(acts):
        headers[f"h{i}"] = lbl
        label_to_key[lbl] = f"h{i}"
    for i, lbl in enumerate(autres):
        headers[f"a{i}"] = lbl
        label_to_key[lbl] = f"a{i}"

    def build_df(resources, label_col):
        recs = []
        for name in resources:
            h = quart["heures"].get(name, {})
            rec = {label_col: name}
            for k in HOUR_KEYS:
                rec[k] = None
            for label, key in label_to_key.items():
                if label in h:
                    rec[key] = float(h[label])
            rec["Prime"] = quart["prime"].get(name)
            rec["Commentaire"] = quart["commentaire_ligne"].get(name, "")
            recs.append(rec)
        return pd.DataFrame(recs, columns=[label_col] + HOUR_KEYS + ["Prime", "Commentaire"])

    return {
        "description": quart.get("description", ""),
        "responsable": quart.get("responsable", ""),
        "temp_am": quart.get("temp_am"), "temp_pm": quart.get("temp_pm"),
        "conditions": quart.get("conditions", []), "headers": headers,
        "pers": build_df(quart.get("personnel", []), "Nom"),
        "equip": build_df(quart.get("equipements", []), "Véhicule"),
    }
```

Remplacer `build_workbook()` (app.py:366-371) — itère jours×quarts :

```python
def build_workbook():
    wb = Workbook()
    legacy = {(j, q): _legacy_day(st.session_state.jours[j]["quarts"][q])
              for j in JOURS for q in _day_quart_names(st.session_state.jours[j])}
    _build_synthese(wb.active, st.session_state.projet, legacy)
    buf = BytesIO(); wb.save(buf); buf.seek(0)
    return buf
```

(`_build_synthese` ne lit pas le détail aujourd'hui ; il reçoit le dict `legacy` re-clavé par (jour, quart) — signature inchangée, contenu non lu.)

- [ ] **Step 6 : `view_dashboard` (`app.py`)**

Dans `view_dashboard` (app.py:755-825) :
- Supprimer le bloc de pré-remplissage `config["personnel"]` (app.py:778-781) — il n'y a plus de config semaine. (La suggestion projet est ré-appliquée par quart à la création, Task 2 ; en Task 1 on retire simplement ce bloc.)
- Remplacer les 2 appels `_day_total(st.session_state.config, day)` (app.py:800 et 812) par `_day_total(day)`.
- Remplacer le déclencheur météo à l'ouverture (app.py:820) :
  `if not day["temp_am"] and proj["lat"]: _fill_weather_for_day(jour)`
  par :
  ```python
  _q0 = _day_quart_names(day)[0]
  if not day["quarts"][_q0]["temp_am"] and proj["lat"]:
      _fill_weather_for_quart(jour, _q0)
  ```

- [ ] **Step 7 : `view_day_entry` branché sur le quart courant (`app.py`)**

Remplacer le **corps** de `view_day_entry` (app.py:827-1169) par la version ci-dessous. Elle résout un **quart courant** (défaut = 1ᵉʳ quart présent ; en Task 1 il n'y en a qu'un, « Jour »), et lit/écrit `quart[...]` au lieu de `day[...]`/`config[...]`. Les clés de widgets incluent le quart. Le bloc « sélecteur de quart » n'affiche en Task 1 que le quart courant (le ➕/retrait arrive en Task 2). Conserver la navigation jour, le bouton « Copier de [jour] » (copie le quart courant depuis le 1ᵉʳ quart du jour précédent), et la barre d'enregistrement.

```python
def _current_quart_name(jour):
    day = st.session_state.jours[jour]
    names = _day_quart_names(day)
    key = f"active_quart_{jour}"
    if st.session_state.get(key) not in names:
        st.session_state[key] = names[0]
    return st.session_state[key]


def view_day_entry():
    jour = st.session_state.active_day
    day_idx = JOURS.index(jour)
    day = st.session_state.jours[jour]
    prev_day = JOURS[day_idx - 1] if day_idx > 0 else None
    next_day = JOURS[day_idx + 1] if day_idx < 6 else None

    with st.container(key="nav_card"):
        n1, n2, n3 = st.columns([1, 6, 1], vertical_alignment="center")
        if n1.button(f"◀ {prev_day}" if prev_day else "◀", disabled=not prev_day,
                     use_container_width=True, key=f"nav_prev_{jour}", help="Jour précédent"):
            st.session_state.active_day = prev_day
            st.rerun()
        n2.markdown(
            f'<div class="nav-date">'
            f'<span class="nav-date-day">{jour}</span>'
            f'<span class="nav-date-full">{fr_date_long(day["date"]) if day["date"] else ""}</span>'
            f'</div>', unsafe_allow_html=True)
        if n3.button(f"{next_day} ▶" if next_day else "▶", disabled=not next_day,
                     use_container_width=True, key=f"nav_next_{jour}", help="Jour suivant"):
            st.session_state.active_day = next_day
            st.rerun()

    # Sélecteur de quart (Task 1 : un seul bouton, le quart courant ; ➕/retrait en Task 2)
    quart_name = _current_quart_name(jour)
    quart = day["quarts"][quart_name]
    _render_quart_selector(jour, day)   # défini en Task 2 ; en Task 1, voir note ci-dessous

    # Copier le quart courant depuis le 1er quart du jour précédent
    if prev_day:
        _, cc, _ = st.columns([2, 3, 2])
        if cc.button(f"📋 Copier de {prev_day}", use_container_width=True,
                     key=f"copy_{jour}", help="Copie activités et heures du jour précédent"):
            prev_day_obj = st.session_state.jours[prev_day]
            src = prev_day_obj["quarts"][_day_quart_names(prev_day_obj)[0]]
            quart["activites"] = list(src["activites"])
            quart["heures"] = {k: dict(v) for k, v in src["heures"].items()}
            _clear_quart_widget_state(jour, quart_name)
            st.success("Données copiées !")
            st.rerun()

    tab_config, tab_saisie = st.tabs(["⚙️ Configuration", "🕐 Saisie des heures"])

    with tab_config:
        st.markdown("### Configuration du quart")
        st.caption("Configurez les activités, la météo et le personnel avant de saisir les heures.")
        col_act, col_meteo = st.columns(2)

        with col_act:
            with st.container(border=True, key="acts_box"):
                st.markdown("🏗️ **Activités du quart**")
                _acts_options = sorted(set(data_source.get_activities(st.session_state.projet.get("id_project")))
                                       | set(quart["activites"]))
                quart["activites"] = st.multiselect(
                    "🚀 Activités du quart", _acts_options,
                    default=quart["activites"], key=f"acts_{jour}_{quart_name}",
                    label_visibility="collapsed", help="Maximum 7 activités")

        with col_meteo:
            with st.container(border=True, key="meteo_card"):
                header_cols = st.columns([3, 1], vertical_alignment="center")
                header_cols[0].markdown("🌤️ **Météo**")
                proj = st.session_state.projet
                has_date = day.get("date") is not None
                if not has_date:
                    st.caption("⚠️ Date non définie")
                _geo_msg = st.session_state.pop(f"geo_msg_{jour}_{quart_name}", None)
                if _geo_msg:
                    (st.success if _geo_msg[0] == "success" else st.warning)(_geo_msg[1])
                if header_cols[1].button("📍 GPS", key=f"{jour}_{quart_name}_geo",
                            disabled=not has_date, help="Utiliser ma position GPS actuelle",
                            use_container_width=True):
                    st.session_state[f"show_geoloc_{jour}_{quart_name}"] = True
                    st.rerun()
                if st.session_state.get(f"show_geoloc_{jour}_{quart_name}"):
                    from streamlit_js_eval import get_geolocation
                    loc = get_geolocation(component_key=f"geoloc_{jour}_{quart_name}")
                    if loc and isinstance(loc, dict) and loc.get("coords"):
                        lat = loc["coords"].get("latitude")
                        lon = loc["coords"].get("longitude")
                        st.session_state.pop(f"show_geoloc_{jour}_{quart_name}", None)
                        if lat is not None and lon is not None:
                            proj["lat"] = float(lat); proj["lon"] = float(lon)
                            success = _fill_weather_for_quart(jour, quart_name)
                            st.session_state[f"{jour}_{quart_name}_temp_am"] = quart["temp_am"]
                            st.session_state[f"{jour}_{quart_name}_temp_pm"] = quart["temp_pm"]
                            st.session_state[f"{jour}_{quart_name}_cond"] = ", ".join(quart["conditions"]) if isinstance(quart["conditions"], list) else (quart["conditions"] or "")
                            st.session_state[f"geo_msg_{jour}_{quart_name}"] = (
                                ("success", f"Position {proj['lat']:.4f}, {proj['lon']:.4f} — météo récupérée.")
                                if success else
                                ("warning", "Position trouvée mais météo indisponible pour cette date."))
                            st.rerun()
                    else:
                        st.caption("📡 Autorisez la géolocalisation dans le navigateur…")
                temp_cols = st.columns(2)
                st.session_state.setdefault(f"{jour}_{quart_name}_temp_am", quart["temp_am"])
                st.session_state.setdefault(f"{jour}_{quart_name}_temp_pm", quart["temp_pm"])
                st.session_state.setdefault(
                    f"{jour}_{quart_name}_cond",
                    ", ".join(quart["conditions"]) if isinstance(quart["conditions"], list) else (quart["conditions"] or ""))
                quart["temp_am"] = temp_cols[0].number_input("Température AM (°C)",
                                          key=f"{jour}_{quart_name}_temp_am", step=1.0, format="%.1f")
                quart["temp_pm"] = temp_cols[1].number_input("Température PM (°C)",
                                          key=f"{jour}_{quart_name}_temp_pm", step=1.0, format="%.1f")
                _cond_input = st.text_input("Conditions météo", key=f"{jour}_{quart_name}_cond",
                                            placeholder="Ex: Ensoleillé, Nuageux, Pluie...")
                quart["conditions"] = [c.strip() for c in _cond_input.split(",") if c.strip()]

        col_personnel, col_equipements = st.columns(2)
        with col_personnel:
            with st.container(border=True, key="equipe_box"):
                st.markdown("👷 **Personnel présent**")
                _staff_project = set(data_source.get_project_staff(st.session_state.projet.get("id_project")))
                _staff_all = set(data_source.get_all_staff())
                _staff_current = set(quart.get("personnel", []))
                if _staff_project:
                    st.caption("Employés du projet (cliquez pour sélectionner)")
                    _current_from_project = [e for e in quart.get("personnel", []) if e in _staff_project]
                    selected_pills = st.pills(
                        "Employés du projet", sorted(_staff_project), selection_mode="multi",
                        default=_current_from_project, key=f"personnel_pills_{jour}_{quart_name}",
                        label_visibility="collapsed")
                    _non_project = [e for e in quart.get("personnel", []) if e not in _staff_project]
                    quart["personnel"] = list(selected_pills or []) + _non_project
                _staff_other = sorted(_staff_all - _staff_project - _staff_current)
                if _staff_other:
                    st.caption("Ajouter un employé d'un autre projet")
                    other_employee = st.selectbox(
                        "Autres employés", [""] + _staff_other,
                        key=f"other_employee_{jour}_{quart_name}", label_visibility="collapsed",
                        placeholder="Rechercher un employé...", index=0)
                    if other_employee and other_employee not in quart["personnel"]:
                        quart["personnel"].append(other_employee)
                        st.rerun()
                st.caption("Ou ajouter manuellement")
                col_input, col_btn = st.columns([4, 1])
                new_employee = col_input.text_input("Nom", key=f"new_employee_{jour}_{quart_name}",
                                                    placeholder="Nom de l'employé...", label_visibility="collapsed")
                if col_btn.button("➕", key=f"add_manual_{jour}_{quart_name}", disabled=not new_employee.strip(),
                                  help="Ajouter", use_container_width=True):
                    if new_employee.strip() and new_employee.strip() not in quart["personnel"]:
                        quart["personnel"].append(new_employee.strip())
                        st.rerun()

        with col_equipements:
            with st.container(border=True):
                st.markdown("🚜 **Équipements sur place**")
                if quart.get("equipements"):
                    st.caption(f"{len(quart['equipements'])} équipement(s) sélectionné(s)")
                    for eq in quart["equipements"]:
                        cols = st.columns([5, 1])
                        cols[0].text(eq)
                        if cols[1].button("🗑️", key=f"remove_eq_{jour}_{quart_name}_{eq}",
                                          help="Retirer", use_container_width=True):
                            quart["equipements"].remove(eq)
                            st.rerun()
                else:
                    st.caption("Aucun équipement sélectionné")
                st.caption("Ajouter un équipement")
                col_input_eq, col_btn_eq = st.columns([4, 1])
                new_equipment = col_input_eq.text_input("Équipement", key=f"new_equipment_{jour}_{quart_name}",
                                                        placeholder="Ex: Camion, Excavatrice...", label_visibility="collapsed")
                if col_btn_eq.button("➕", key=f"add_equipment_{jour}_{quart_name}", disabled=not new_equipment.strip(),
                                     help="Ajouter", use_container_width=True):
                    if new_equipment.strip() and new_equipment.strip() not in quart["equipements"]:
                        quart["equipements"].append(new_equipment.strip())
                        st.rerun()

    with tab_saisie:
        cols_labels = _quart_columns(quart)
        hd1, hd2 = st.columns([2, 1])
        hd1.markdown("#### 🕐 Saisie des heures")
        query = hd2.text_input("Rechercher une ressource", key=f"roster_search_{jour}_{quart_name}",
                               placeholder="🔍 Rechercher une ressource…",
                               label_visibility="collapsed").strip().lower()
        full_roster = _roster(quart)
        roster = [(name, typ) for name, typ in full_roster if query in name.lower()] if query else full_roster
        n = len(cols_labels)
        grid_widths = [3] + [1]*n + [1, 2, 1]
        if not full_roster:
            st.info("💡 Commencez par sélectionner le **personnel / équipements** dans l'onglet Configuration.")
        elif not cols_labels:
            st.info("💡 Sélectionnez une ou plusieurs **Activités** dans l'onglet Configuration.")
        elif not roster:
            st.info("🔍 Aucune ressource ne correspond à la recherche.")
        else:
            h_cols = st.columns(grid_widths)
            h_cols[0].caption("Ressource")
            for i, c in enumerate(cols_labels):
                h_cols[i+1].caption(c.split(" - ")[0][:10])
            h_cols[n+1].caption("Prime ($)")
            h_cols[n+2].caption("Commentaire")
            h_cols[n+3].caption("Total")
            for name, typ in roster:
                h = quart["heures"].get(name, {})
                with st.container():
                    r_cols = st.columns(grid_widths)
                    icon = '👷' if typ == 'P' else '🚜'
                    r_cols[0].markdown(f"{icon} **{name}**")
                    new_h = {}
                    for i, c in enumerate(cols_labels):
                        k = f"h_{jour}_{quart_name}_{name}_{c}"
                        if k not in st.session_state:
                            st.session_state[k] = float(h.get(c) or 0.0)
                        v = r_cols[i+1].number_input("H", min_value=0.0, max_value=24.0, step=0.5,
                                                     format="%.1f", key=k, label_visibility="collapsed",
                                                     on_change=_mark_dirty)
                        if v > 0:
                            new_h[c] = float(v)
                    pk = f"p_{jour}_{quart_name}_{name}"
                    if pk not in st.session_state:
                        st.session_state[pk] = float(quart["prime"].get(name) or 0.0)
                    prime = r_cols[n+1].number_input("Prime", min_value=0.0, step=0.5, format="%.1f",
                                                     key=pk, label_visibility="collapsed", on_change=_mark_dirty)
                    ck = f"c_{jour}_{quart_name}_{name}"
                    if ck not in st.session_state:
                        st.session_state[ck] = quart["commentaire_ligne"].get(name, "")
                    comment = r_cols[n+2].text_input("Commentaire", key=ck, placeholder="…",
                                                     label_visibility="collapsed", on_change=_mark_dirty)
                    line_total = sum(new_h.values())
                    r_cols[n+3].markdown(f"**{line_total:.1f}**")
                    if new_h: quart["heures"][name] = new_h
                    else: quart["heures"].pop(name, None)
                    if prime > 0: quart["prime"][name] = float(prime)
                    else: quart["prime"].pop(name, None)
                    if comment.strip(): quart["commentaire_ligne"][name] = comment
                    else: quart["commentaire_ligne"].pop(name, None)
                st.markdown('<div style="height:1px; background:#f1f5f9; margin:5px 0;"></div>', unsafe_allow_html=True)
        st.divider()
        quart["description"] = st.text_input("📝 Note du quart", quart["description"],
                                             placeholder="Commentaire sur le quart...",
                                             key=f"note_{jour}_{quart_name}", on_change=_mark_dirty)

    st.divider()
    sb1, sb2 = st.columns([3, 1], vertical_alignment="center")
    if st.session_state.get("dirty"):
        sb1.warning("⚠️ Modifications non enregistrées — pensez à enregistrer avant de quitter.")
    else:
        sb1.caption("✓ Toutes les modifications sont enregistrées.")
    if sb2.button("💾 Enregistrer", use_container_width=True, type="primary", key=f"save_{jour}"):
        ok, msg = save_report_from_state()
        (st.success if ok else st.error)(msg)
```

Ajouter le helper de purge des clés de widgets d'**un quart** (utilisé par « Copier » et, en Task 2, par retrait/bascule) près de `_clear_grid_widget_state` :

```python
def _clear_quart_widget_state(jour, quart_name):
    prefixes = (f"h_{jour}_{quart_name}_", f"p_{jour}_{quart_name}_",
                f"c_{jour}_{quart_name}_", f"acts_{jour}_{quart_name}",
                f"{jour}_{quart_name}_temp_am", f"{jour}_{quart_name}_temp_pm",
                f"{jour}_{quart_name}_cond", f"roster_search_{jour}_{quart_name}",
                f"personnel_pills_{jour}_{quart_name}", f"note_{jour}_{quart_name}")
    for k in list(st.session_state.keys()):
        if any(k.startswith(p) for p in prefixes):
            del st.session_state[k]
```

**Note Task 1 pour `_render_quart_selector`** : en Task 1, définir un stub minimal qui affiche seulement le quart courant (pas d'ajout/retrait) :

```python
def _render_quart_selector(jour, day):
    names = _day_quart_names(day)
    st.caption("Quart")
    st.session_state.setdefault(f"active_quart_{jour}", names[0])
    # Task 1 : un seul quart possible -> simple libellé. Remplacé en Task 2.
    st.radio("Quart", names, key=f"active_quart_{jour}",
             horizontal=True, label_visibility="collapsed")
```

- [ ] **Step 8 : `tests/test_ui.py` — adapter setups, clés et assertions**

Transformation systématique (s'applique à TOUS les tests du fichier) :
1. Tout setup `at.session_state["config"] = {...}` est **supprimé** (plus de config semaine).
2. Tout setup d'un jour passe par quart. Le helper d'ouverture devient :

```python
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
                               "description": ""}}}
    at.session_state["jours"] = {j: {"date": None, "quarts": {"Jour": {
        "responsable": "", "activites": [], "autres": [], "personnel": [], "equipements": [],
        "temp_am": None, "temp_pm": None, "conditions": [], "heures": {}, "prime": {},
        "commentaire_ligne": {}, "description": ""}}} for j in ["Dimanche","Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi"]}
    at.session_state["jours"][jour] = day
    at.session_state["active_day"] = jour
    at.session_state["view"] = "day_entry"
    at.run()
    return at
```

3. Clés de widgets : insérer le quart `Jour` :
   - `h_Lundi_Alice_C01 - Test` → `h_Lundi_Jour_Alice_C01 - Test`
   - `p_Lundi_Alice` → `p_Lundi_Jour_Alice`
   - `c_Lundi_Alice` → `c_Lundi_Jour_Alice`
   - `roster_search_Lundi` → `roster_search_Lundi_Jour`
4. Assertions sur le modèle : `jours["Lundi"]["heures"]` → `jours["Lundi"]["quarts"]["Jour"]["heures"]` (idem prime, commentaire_ligne, activites).
5. Tests utilisant `config` directement (`test_day_config_shows_project_personnel`, `test_setting_personnel_updates_config`, `test_config_personnel_options_include_suggested`) : remplacer la pré-charge `config["personnel"]` par le personnel du quart Jour dans `jours[...]["quarts"]["Jour"]["personnel"]`, et les assertions `config["personnel"]` par `jours[jour]["quarts"]["Jour"]["personnel"]`.

Exemples complets (à appliquer ; les autres suivent la même transformation) :

```python
def test_day_hours_entry_updates_model(monkeypatch):
    at = _open_day_for_entry(monkeypatch)
    acts = [m for m in at.multiselect if m.label == "🚀 Activités du quart"][0]
    acts.set_value(["C01 - Test"]).run()
    champ = [n for n in at.number_input if n.key == "h_Lundi_Jour_Alice_C01 - Test"][0]
    champ.set_value(8.0).run()
    q = at.session_state["jours"]["Lundi"]["quarts"]["Jour"]
    assert q["heures"]["Alice"]["C01 - Test"] == 8.0
    assert not at.exception


def test_day_prime_inline_column(monkeypatch):
    at = _open_day_for_entry(monkeypatch)
    acts = [m for m in at.multiselect if m.label == "🚀 Activités du quart"][0]
    acts.set_value(["C01 - Test"]).run()
    prime = [n for n in at.number_input if n.key == "p_Lundi_Jour_Alice"][0]
    prime.set_value(2.0).run()
    assert at.session_state["jours"]["Lundi"]["quarts"]["Jour"]["prime"]["Alice"] == 2.0
    assert not at.exception
```

Le label du multiselect activités devient « 🚀 Activités du quart » (Step 7) : mettre à jour les tests qui filtrent par ce label (`test_day_activities_come_from_db`, `test_multiselect_keeps_incremental_activities`, `test_day_hours_no_grid_data_editor`, `test_roster_search_filters_resources`, `test_day_comment_inline_column`, `test_day_config_*`).

Mettre à jour les tests qui pré-construisent `jours`/`config` inline (`test_day_activities_come_from_db`, `test_day_entry_no_activity_shows_info`, `test_multiselect_keeps_incremental_activities`) selon la même forme par quart, et leurs clés/labels.

- [ ] **Step 9 : Lancer toute la suite (GREEN)**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — tous les tests modèle et UI adaptés passent ; le `test_reports.py` (logique pure) reste vert. L'app fonctionne comme avant, avec un seul quart « Jour » par jour, mais l'état est par quart.

- [ ] **Step 10 : NE PAS commiter** (voir note d'exécution en tête de session : mode no-commit tant que l'utilisateur ne le demande pas). Marquer la tâche prête pour revue.

---

### Task 2 : Multi-quart — sélecteur, ajout (copie), retrait, indicateur tableau de bord

**Files:**
- Modify: `app.py` — `_render_quart_selector` (remplace le stub de Task 1), helper `_add_quart`/`_remove_quart`, indicateur dans `view_dashboard`.
- Modify: `tests/test_ui.py` — nouveaux tests multi-quarts.

**Interfaces consommées :** `QUART_NAMES`, `_empty_quart`, `_day_quart_names`, `_current_quart_name`, `_clear_quart_widget_state`, `_day_total` (Task 1).

- [ ] **Step 1 : Tests multi-quarts (RED) — `tests/test_ui.py`**

```python
def test_add_quart_creates_second_quart(monkeypatch):
    at = _open_day_for_entry(monkeypatch)
    # un seul quart au départ
    assert list(at.session_state["jours"]["Lundi"]["quarts"].keys()) == ["Jour"]
    # ajouter « Soir »
    sel = [s for s in at.selectbox if s.key == "add_quart_choice_Lundi"][0]
    sel.set_value("Soir").run()
    btn = [b for b in at.button if b.key == "add_quart_Lundi"][0]
    btn.click().run()
    assert app_quarts(at, "Lundi") == ["Jour", "Soir"]
    assert not at.exception


def test_hours_are_distinct_per_quart(monkeypatch):
    at = _open_day_for_entry(monkeypatch)
    # activité + heures sur Jour
    acts = [m for m in at.multiselect if m.label == "🚀 Activités du quart"][0]
    acts.set_value(["C01 - Test"]).run()
    [n for n in at.number_input if n.key == "h_Lundi_Jour_Alice_C01 - Test"][0].set_value(8.0).run()
    # ajouter Soir, basculer dessus
    [s for s in at.selectbox if s.key == "add_quart_choice_Lundi"][0].set_value("Soir").run()
    [b for b in at.button if b.key == "add_quart_Lundi"][0].click().run()
    [r for r in at.radio if r.key == "active_quart_Lundi"][0].set_value("Soir").run()
    # Soir : pas d'heures, activités à choisir indépendamment
    qj = at.session_state["jours"]["Lundi"]["quarts"]["Jour"]
    qs = at.session_state["jours"]["Lundi"]["quarts"]["Soir"]
    assert qj["heures"]["Alice"]["C01 - Test"] == 8.0
    assert qs["heures"] == {}
    assert not at.exception


def test_cannot_remove_last_quart(monkeypatch):
    at = _open_day_for_entry(monkeypatch)
    # pas de bouton de retrait quand il ne reste qu'un quart
    assert not any(b.key == "remove_quart_Lundi_Jour" for b in at.button)


def test_add_quart_can_copy_team_and_activities(monkeypatch):
    at = _open_day_for_entry(monkeypatch, personnel=("Alice",))
    acts = [m for m in at.multiselect if m.label == "🚀 Activités du quart"][0]
    acts.set_value(["C01 - Test"]).run()
    # cocher « copier l'équipe + activités », choisir Soir, ajouter
    cp = [c for c in at.checkbox if c.key == "add_quart_copy_Lundi"][0]
    cp.set_value(True).run()
    [s for s in at.selectbox if s.key == "add_quart_choice_Lundi"][0].set_value("Soir").run()
    [b for b in at.button if b.key == "add_quart_Lundi"][0].click().run()
    qs = at.session_state["jours"]["Lundi"]["quarts"]["Soir"]
    assert qs["personnel"] == ["Alice"]
    assert qs["activites"] == ["C01 - Test"]
    assert qs["heures"] == {}     # les heures ne sont PAS copiées
    assert not at.exception
```

Ajouter en haut du fichier le helper de lecture ordonnée :

```python
def app_quarts(at, jour):
    import app
    return app._day_quart_names(at.session_state["jours"][jour])
```

- [ ] **Step 2 : Lancer (RED)**

Run: `.venv/bin/python -m pytest tests/test_ui.py -k "quart" -q`
Expected: FAIL (sélecteur d'ajout/retrait absent).

- [ ] **Step 3 : Implémenter le sélecteur (`app.py`)**

Remplacer le stub `_render_quart_selector` (Task 1, Step 7) par :

```python
def _add_quart(jour, new_quart, copy_from=None):
    day = st.session_state.jours[jour]
    q = _empty_quart()
    if copy_from and copy_from in day["quarts"]:
        src = day["quarts"][copy_from]
        q["personnel"] = list(src["personnel"])
        q["equipements"] = list(src["equipements"])
        q["activites"] = list(src["activites"])
        q["autres"] = list(src["autres"])
        q["responsable"] = src["responsable"]
    day["quarts"][new_quart] = q
    st.session_state[f"active_quart_{jour}"] = new_quart
    _mark_dirty()


def _remove_quart(jour, quart_name):
    day = st.session_state.jours[jour]
    if len(day["quarts"]) <= 1:
        return
    _clear_quart_widget_state(jour, quart_name)
    day["quarts"].pop(quart_name, None)
    st.session_state.pop(f"active_quart_{jour}", None)
    _mark_dirty()


def _render_quart_selector(jour, day):
    names = _day_quart_names(day)
    st.session_state.setdefault(f"active_quart_{jour}", names[0])
    st.caption("Quart")
    st.radio("Quart", names, key=f"active_quart_{jour}",
             horizontal=True, label_visibility="collapsed")

    current = st.session_state[f"active_quart_{jour}"]
    remaining = [q for q in QUART_NAMES if q not in names]
    cols = st.columns([3, 2, 1, 2])
    if remaining:
        cols[0].selectbox("Ajouter un quart", remaining, key=f"add_quart_choice_{jour}",
                          label_visibility="collapsed", placeholder="Ajouter un quart…")
        cols[1].checkbox("Copier équipe + activités", key=f"add_quart_copy_{jour}", value=True)
        if cols[2].button("➕", key=f"add_quart_{jour}", help="Ajouter ce quart"):
            choice = st.session_state.get(f"add_quart_choice_{jour}")
            if choice:
                _add_quart(jour, choice, copy_from=current if st.session_state.get(f"add_quart_copy_{jour}") else None)
                st.rerun()
    if len(names) > 1:
        if cols[3].button(f"🗑️ Retirer {current}", key=f"remove_quart_{jour}_{current}",
                          help="Retirer ce quart"):
            _remove_quart(jour, current)
            st.rerun()
```

(Le `st.selectbox` de remaining renvoie le 1ᵉʳ élément par défaut ; le test `add_quart_choice` le règle explicitement. `placeholder` ne s'applique qu'avec `index=None` — ici on garde le 1ᵉʳ choix par défaut, simple et testable.)

- [ ] **Step 4 : Indicateur de quarts au tableau de bord (`app.py`)**

Dans `view_dashboard`, là où la carte du jour est construite (app.py:809-821), ajouter sous le total un libellé des quarts présents ayant des heures. Modifier le texte du bouton :

```python
        day = st.session_state.jours[jour]
        total = _day_total(day)
        date_str = fr_date_short(day["date"]) if day["date"] else ""
        quarts_actifs = [q for q in _day_quart_names(day) if _quart_total(day["quarts"][q]) > 0]
        quarts_str = " · ".join(quarts_actifs)
        with cols[i % 4]:
            label = f"**{jour}**\n\n{date_str}\n\n" + (
                f"✅ {round(total, 1)} h" + (f"\n\n{quarts_str}" if quarts_str else "")
                if total > 0 else "—")
            if st.button(label, key=f"go_{jour}", use_container_width=True, disabled=not projet_choisi):
                st.session_state.active_day = jour
                st.session_state.view = "day_entry"
                _q0 = _day_quart_names(day)[0]
                if not day["quarts"][_q0]["temp_am"] and proj["lat"]:
                    _fill_weather_for_quart(jour, _q0)
                st.rerun()
```

- [ ] **Step 5 : Lancer la suite (GREEN)**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — nouveaux tests multi-quarts verts, aucun régression.

- [ ] **Step 6 : NE PAS commiter.** Prêt pour revue.

---

### Task 3 : Persistance par quart + migration (`reports.py`)

**Files:**
- Modify: `reports.py` — `_DDL_STATEMENTS`, `save_report`, `load_report`, + migration.
- Modify: `app.py` — `load_report_into_state` (hydratation par quart), `_clear_grid_widget_state` (purge par jour×quart) ou réutilisation de `_clear_quart_widget_state` par quart chargé.

**Interfaces consommées :** structure d'état `jours[j]["quarts"][q]` (Task 1).

> **Pas de test unitaire BD** (convention `test_reports.py`). Vérif : suite verte (chargement inerte hors-ligne) + vérif manuelle Neon (Step 7).

- [ ] **Step 1 : Schéma — `reports.py` `_DDL_STATEMENTS`**

Ajouter, après la création de `report_days`, la table `report_quarts` puis `report_quart_resources` ; et garder `report_hours`/`report_lines` mais référençant `report_quarts(id)`. Comme l'ancien schéma référence `report_days(id)`, prévoir une **création conditionnelle** + migration (Step 2). Nouveau bloc DDL (création si absentes) :

```python
    """
    create table if not exists report_quarts (
        id         serial primary key,
        day_id     integer not null references report_days(id) on delete cascade,
        quart      text not null,
        ordinal    integer not null default 0,
        responsable text,
        note       text,
        temp_am    numeric,
        temp_pm    numeric,
        conditions text[] not null default '{}',
        activites  text[] not null default '{}',
        autres     text[] not null default '{}',
        unique (day_id, quart)
    )
    """,
    """
    create table if not exists report_quart_resources (
        quart_id  integer not null references report_quarts(id) on delete cascade,
        name      text not null,
        kind      char(1) not null check (kind in ('P', 'E')),
        primary key (quart_id, name)
    )
    """,
    "create index if not exists idx_report_quarts_day on report_quarts(day_id)",
```

- [ ] **Step 2 : Migration idempotente — `reports.py` (dans `ensure_schema`, après les DDL)**

Repointer `report_hours`/`report_lines` de `day_id` vers `quart_id`, en repliant l'existant dans un quart « Jour ». Ajouter ces instructions (idempotentes) à `_DDL_STATEMENTS` **après** les créations :

```python
    # Migration : 1 quart « Jour » par jour existant (no-op si déjà fait)
    """
    insert into report_quarts (day_id, quart, ordinal, note, temp_am, temp_pm,
                               conditions, activites, autres)
    select d.id, 'Jour', 0, d.note, d.temp_am, d.temp_pm,
           d.conditions, d.activites, d.autres
    from report_days d
    where not exists (select 1 from report_quarts q where q.day_id = d.id)
    """,
    # report_hours : ajouter quart_id et le backfiller depuis day_id
    "alter table report_hours add column if not exists quart_id integer references report_quarts(id) on delete cascade",
    """
    update report_hours h set quart_id = q.id
    from report_quarts q
    where q.day_id = h.day_id and q.quart = 'Jour' and h.quart_id is null
    """,
    # report_lines : idem
    "alter table report_lines add column if not exists quart_id integer references report_quarts(id) on delete cascade",
    """
    update report_lines l set quart_id = q.id
    from report_quarts q
    where q.day_id = l.day_id and q.quart = 'Jour' and l.quart_id is null
    """,
    # report_quart_resources : backfill depuis report_resources (équipe semaine -> quart Jour de chaque jour)
    """
    insert into report_quart_resources (quart_id, name, kind)
    select q.id, r.name, r.kind
    from report_quarts q
    join report_days d on d.id = q.day_id
    join report_resources r on r.report_id = d.report_id
    where q.quart = 'Jour'
      and not exists (select 1 from report_quart_resources x where x.quart_id = q.id and x.name = r.name)
    """,
```

> Les anciennes colonnes `report_days.quart`, `report_days.note/temp_am/...`, `report_hours.day_id`, `report_lines.day_id`, la table `report_resources`, et `reports.quart/responsable` restent en base (inoffensives) après migration ; on ne les `drop` PAS pour rester non destructif et idempotent. Le code n'écrit/lit plus que le nouveau grain.

- [ ] **Step 3 : `save_report` — réécrire l'insertion des enfants (`reports.py`)**

Conserver l'upsert d'en-tête `reports` (sans `quart`/`responsable` désormais : passer `None`). Remplacer la boucle jours par : pour chaque jour, insérer `report_days` (sans note/météo/activités au niveau jour — ces colonnes restent mais on n'y écrit plus), puis pour chaque quart insérer `report_quarts`, ses `report_quart_resources`, `report_hours` (par `quart_id`), `report_lines` (par `quart_id`). Code de la boucle :

```python
        for jour in jours_order:
            day = jours.get(jour) or {}
            d_date = day.get("date")
            if not isinstance(d_date, date):
                continue
            day_id = s.execute(
                text("insert into report_days (report_id, day_date) values (:r, :d) returning id"),
                {"r": report_id, "d": d_date},
            ).scalar()
            for ordinal, qname in enumerate(
                    [q for q in ("Jour", "Soir", "Nuit") if q in day.get("quarts", {})]):
                quart = day["quarts"][qname]
                quart_id = s.execute(
                    text(
                        """
                        insert into report_quarts
                            (day_id, quart, ordinal, responsable, note,
                             temp_am, temp_pm, conditions, activites, autres)
                        values (:d, :q, :o, :resp, :note, :tam, :tpm, :cond, :acts, :autres)
                        returning id
                        """
                    ),
                    {"d": day_id, "q": qname, "o": ordinal,
                     "resp": quart.get("responsable") or None,
                     "note": quart.get("description") or None,
                     "tam": quart.get("temp_am"), "tpm": quart.get("temp_pm"),
                     "cond": list(quart.get("conditions") or []),
                     "acts": list(quart.get("activites") or []),
                     "autres": list(quart.get("autres") or [])},
                ).scalar()
                for name in quart.get("personnel", []):
                    s.execute(text("insert into report_quart_resources (quart_id, name, kind) "
                                   "values (:q, :n, 'P') on conflict do nothing"),
                              {"q": quart_id, "n": name})
                for name in quart.get("equipements", []):
                    s.execute(text("insert into report_quart_resources (quart_id, name, kind) "
                                   "values (:q, :n, 'E') on conflict do nothing"),
                              {"q": quart_id, "n": name})
                for resource_name, acts in (quart.get("heures") or {}).items():
                    for activity_label, hrs in (acts or {}).items():
                        if hrs is None:
                            continue
                        s.execute(text("insert into report_hours (quart_id, resource_name, activity_label, hours) "
                                       "values (:q, :rn, :al, :h)"),
                                  {"q": quart_id, "rn": resource_name, "al": activity_label, "h": float(hrs)})
                prime = quart.get("prime") or {}
                commentaire = quart.get("commentaire_ligne") or {}
                for resource_name in set(prime) | set(commentaire):
                    s.execute(text("insert into report_lines (quart_id, resource_name, prime, commentaire) "
                                   "values (:q, :rn, :p, :c)"),
                              {"q": quart_id, "rn": resource_name,
                               "p": float(prime[resource_name]) if resource_name in prime else None,
                               "c": commentaire.get(resource_name) or None})
```

Et la suppression des enfants en début de réécriture devient : `delete from report_days where report_id = :r` (cascade vers report_quarts → resources/hours/lines). Retirer la suppression/insertion de `report_resources` (table semaine) et de l'usage de `config["personnel"]/["equipements"]` (l'équipe est par quart). L'en-tête `reports` : retirer `quart`/`responsable` des colonnes upsert (ou passer `None`).

- [ ] **Step 4 : `load_report` — reconstruire les quarts (`reports.py`)**

Remplacer la lecture par jour par une lecture jour→quarts→hours/lines/resources :

```python
        days = s.execute(
            text("select id, day_date from report_days where report_id = :r"),
            {"r": report_id},
        ).mappings().all()

        days_by_date = {}
        for d in days:
            quarts = s.execute(
                text("select id, quart, responsable, note, temp_am, temp_pm, "
                     "conditions, activites, autres from report_quarts "
                     "where day_id = :d order by ordinal"),
                {"d": d["id"]},
            ).mappings().all()
            quarts_dict = {}
            for q in quarts:
                hrs = s.execute(
                    text("select resource_name, activity_label, hours from report_hours where quart_id = :q"),
                    {"q": q["id"]}).mappings().all()
                heures = {}
                for h in hrs:
                    heures.setdefault(h["resource_name"], {})[h["activity_label"]] = float(h["hours"])
                lines = s.execute(
                    text("select resource_name, prime, commentaire from report_lines where quart_id = :q"),
                    {"q": q["id"]}).mappings().all()
                prime = {l["resource_name"]: float(l["prime"]) for l in lines if l["prime"] is not None}
                commentaire = {l["resource_name"]: l["commentaire"] for l in lines if l["commentaire"]}
                res = s.execute(
                    text("select name, kind from report_quart_resources where quart_id = :q order by name"),
                    {"q": q["id"]}).mappings().all()
                quarts_dict[q["quart"]] = {
                    "responsable": q["responsable"] or "",
                    "description": q["note"] or "",
                    "temp_am": float(q["temp_am"]) if q["temp_am"] is not None else None,
                    "temp_pm": float(q["temp_pm"]) if q["temp_pm"] is not None else None,
                    "conditions": list(q["conditions"] or []),
                    "activites": list(q["activites"] or []),
                    "autres": list(q["autres"] or []),
                    "personnel": [r["name"] for r in res if r["kind"] == "P"],
                    "equipements": [r["name"] for r in res if r["kind"] == "E"],
                    "heures": heures, "prime": prime, "commentaire_ligne": commentaire,
                }
            if not quarts_dict:
                quarts_dict = {"Jour": None}  # jour sans quart enregistré -> sera vide
            days_by_date[d["day_date"]] = {"date": d["day_date"], "quarts": quarts_dict}

        return {
            "meta": dict(rep),
            "days_by_date": days_by_date,
        }
```

Retirer du retour la clé `config` (plus de niveau semaine) et l'usage de `rep["responsable"]/["quart"]`.

- [ ] **Step 5 : `load_report_into_state` — hydratation par quart (`app.py`)**

Remplacer le corps de chargement (app.py:135-172) par :

```python
def load_report_into_state():
    key = _report_key()
    if key is None or st.session_state.loaded_key == key:
        return
    idp, wk = key
    try:
        data = reports.load_report(idp, wk)
    except Exception:
        data = None

    st.session_state.jours = {j: _empty_day() for j in JOURS}
    _apply_week_dates(wk)

    if data:
        for jour in JOURS:
            day = st.session_state.jours[jour]
            saved = data["days_by_date"].get(day["date"])
            if saved and saved.get("quarts"):
                day["quarts"] = {}
                for qname, q in saved["quarts"].items():
                    nq = _empty_quart()
                    if q:
                        nq.update(q)
                    day["quarts"][qname] = nq
                if not day["quarts"]:
                    day["quarts"] = {"Jour": _empty_quart()}

    # Purge des clés de widgets de tous les jours/quarts
    for jour in JOURS:
        for qname in _day_quart_names(st.session_state.jours[jour]):
            _clear_quart_widget_state(jour, qname)
        st.session_state.pop(f"active_quart_{jour}", None)
    st.session_state.pop("team_pers", None)
    st.session_state.pop("team_equip", None)

    st.session_state.loaded_key = key
    st.session_state.dirty = False
```

Supprimer l'ancien `_clear_grid_widget_state` s'il n'est plus appelé ailleurs (sinon le laisser ; vérifier les appels).

- [ ] **Step 6 : Lancer la suite (GREEN)**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (chargement inerte hors-ligne ; aucune régression). `test_reports.py` (gardes d'entrée) reste vert : `save_report`/`load_report` conservent leurs gardes `id_project`/semaine.

- [ ] **Step 7 : Vérification manuelle Neon**

Lancer `.venv/bin/streamlit run app.py`. (a) Migration : ouvrir un rapport existant → ses anciennes données apparaissent dans le quart « Jour ». (b) Nouveau : sur un jour, ajouter un quart « Soir », saisir des heures différentes sur Jour et Soir, **Enregistrer**, changer de semaine et revenir → les deux quarts et leurs heures distinctes sont restaurés. (c) Retirer un quart, enregistrer, recharger → cohérent.

- [ ] **Step 8 : NE PAS commiter.** Prêt pour revue finale.

---

## Self-Review

**Couverture spec :**
- Modèle jour→quarts, tout par quart → Task 1 (état, helpers, UI, export). ✓
- 1 quart par défaut, ajout au besoin → Task 1 (défaut Jour) + Task 2 (ajout). ✓
- Sélecteur de quart + onglets Config/Saisie branchés sur quart courant → Task 1 (branchement) + Task 2 (sélecteur/ajout/retrait). ✓
- Copier équipe+activités à l'ajout (pas les heures) → Task 2, `_add_quart`/test. ✓
- Retrait, interdiction du dernier → Task 2, `_remove_quart`/tests. ✓
- Persistance nouveau grain + migration non destructive → Task 3. ✓
- Tableau de bord agrégé + indicateur quarts → Task 1 (total) + Task 2 (indicateur). ✓
- Export bloc par quart → Task 1 (`_legacy_day` par quart, `build_workbook` itère quarts). ✓
- Retrait du quart unique / report_days.quart / config semaine → Task 1 (état/UI) + Task 3 (schéma : colonnes laissées inertes, non destructif). ✓
- Tests UI distincts par quart → Task 2. ✓

**Placeholder scan :** code complet à chaque step. Les rewrites de tests UI répétitifs (Step 8 Task 1) sont spécifiés par une transformation exhaustive + exemples complets (renommage mécanique de clés/labels) plutôt que dupliqués à l'identique.

**Cohérence des types/clés :** clés de widgets `..._{jour}_{quart}...` cohérentes entre `view_day_entry`, `_clear_quart_widget_state` et les tests. Helpers : `_quart_columns`/`_quart_total`/`_roster(quart)`/`_resource_total(quart,name)`/`_day_total(day)`/`_legacy_day(quart)` cohérents entre Task 1 (def), tests modèle et appels UI/export. Persistance : grain `quart_id` cohérent entre `save_report`, `load_report`, migration.

## Risques

- **Ampleur de Task 1** (atomique) : touche état + UI + export + ~tous les tests. Revue attentive nécessaire.
- **Migration FK** (Task 3) : `report_hours.day_id → quart_id` par backfill ; idempotente, non destructive, mais à valider manuellement contre Neon avant usage réel.
- **Mode no-commit + WIP préexistant** : isole le diff via instantané de référence (cf. exécution). Recommandation : committer le WIP d'abord (à confirmer avec l'utilisateur).
