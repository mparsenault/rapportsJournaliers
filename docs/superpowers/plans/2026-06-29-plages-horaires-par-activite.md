# Plages horaires par activité — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre de saisir les heures d'une activité par plages horaires (HH:MM début→fin, durée calculée, bascule TR/TS par plage), au choix par activité, en gardant la saisie directe TR/TS et en persistant les plages.

**Architecture:** Trois couches. (1) Helpers purs dans `app.py` : conversion HH:MM↔minutes, durée d'une plage, somme TR/TS, normalisation d'entrée. (2) UI dans `_render_resource_card` : un bloc par activité avec bascule de mode et éditeur de plages dynamique. (3) Persistance dans `reports.py` : nouvelle table `report_hour_ranges`, écrite par `save_report` et relue par `load_report`. Les totaux TR/TS restent stockés dans `report_hours` — l'export Excel est inchangé.

**Tech Stack:** Python, Streamlit (`st.time_input`, `st.radio`), SQLAlchemy/Neon, tests via `pytest` + `streamlit.testing.v1.AppTest`.

## Global Constraints

- Widgets pilotables sous `AppTest` : `st.radio`, `st.time_input`, `st.number_input`, `st.button` (jamais `st.pills`/`segmented_control` pour une sélection).
- `report_hours` et l'export Excel restent inchangés (totaux TR/TS = source de vérité des heures).
- Pas de dépendance circulaire : `reports.py` n'importe pas `app.py` (ses convertisseurs HH:MM sont définis localement).
- Heures décimales au format `%.2f`, pas de 0.25 ; plages au pas de 15 min.
- Rétrocompat : un ancien format d'entrée (`{"TR","TS"}` ou scalaire) se lit comme mode `direct`.
- Commande de test : `.venv/bin/python -m pytest`.

---

### Task 1 : Helpers purs (calcul + normalisation)

**Files:**
- Modify: `app.py` (ajouter les helpers près de `_norm_pair`, ~ligne 334)
- Test: `tests/test_model.py`

**Interfaces:**
- Produit : `_hhmm_to_min(s) -> int|None`, `_min_to_hhmm(m) -> str`, `_range_hours(debut, fin) -> float`, `_ranges_to_pair(ranges) -> {"TR":float,"TS":float}`, `_norm_entry(entry) -> {"mode","ranges","TR","TS"}`.
- Consomme : `_to_hours` (existant, `app.py:318`).
- Note : `_norm_pair` (`app.py:325-334`) **n'est pas modifié** — il tolère déjà le nouveau format (un dict avec clés `TR`/`TS`), donc `_pair_total`, `_resource_total`, l'export et `save_report` continuent de fonctionner. Le nouveau `_norm_entry` est le normalisateur complet utilisé par l'UI.

- [ ] **Step 1 : Écrire les tests des helpers**

Ajouter dans `tests/test_model.py` :

```python
import app


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
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `.venv/bin/python -m pytest tests/test_model.py -k "hhmm or range_hours or ranges_to_pair or norm_entry" -v`
Expected: FAIL (`AttributeError: module 'app' has no attribute '_hhmm_to_min'`).

- [ ] **Step 3 : Implémenter les helpers**

Dans `app.py`, juste après `_norm_pair` (après la ligne 334), ajouter :

```python
def _hhmm_to_min(s):
    """'HH:MM' -> minutes depuis minuit ; None si invalide."""
    try:
        h, m = str(s).split(":")
        h, m = int(h), int(m)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h * 60 + m
    except (ValueError, AttributeError):
        pass
    return None


def _min_to_hhmm(mins):
    """minutes depuis minuit -> 'HH:MM' (borné 00:00..23:59)."""
    mins = max(0, min(int(mins), 23 * 60 + 59))
    return f"{mins // 60:02d}:{mins % 60:02d}"


def _range_hours(debut, fin):
    """Durée en heures décimales entre deux 'HH:MM' ; 0.0 si fin<=début ou invalide."""
    a, b = _hhmm_to_min(debut), _hhmm_to_min(fin)
    if a is None or b is None or b <= a:
        return 0.0
    return (b - a) / 60.0


def _ranges_to_pair(ranges):
    """{'TR': Σ durées TR, 'TS': Σ durées TS} pour une liste de plages."""
    tr = ts = 0.0
    for r in ranges or []:
        d = _range_hours((r or {}).get("debut"), (r or {}).get("fin"))
        if (r or {}).get("type") == "TS":
            ts += d
        else:
            tr += d
    return {"TR": tr, "TS": ts}


def _norm_entry(entry):
    """Normalise une entrée d'heures d'activité -> {'mode','ranges','TR','TS'}.

    Tolère l'ancien format ({'TR','TS'} ou scalaire hérité) -> mode 'direct'.
    En mode 'plage', TR/TS sont dérivés des plages.
    """
    if isinstance(entry, dict):
        ranges = list(entry.get("ranges") or [])
        mode = entry.get("mode") or ("plage" if ranges else "direct")
        if mode == "plage":
            pair = _ranges_to_pair(ranges)
        else:
            pair = {"TR": _to_hours(entry.get("TR")), "TS": _to_hours(entry.get("TS"))}
        return {"mode": mode, "ranges": ranges, "TR": pair["TR"], "TS": pair["TS"]}
    return {"mode": "direct", "ranges": [], "TR": _to_hours(entry), "TS": 0.0}
```

- [ ] **Step 4 : Lancer les tests pour vérifier qu'ils passent**

Run: `.venv/bin/python -m pytest tests/test_model.py -k "hhmm or range_hours or ranges_to_pair or norm_entry" -v`
Expected: PASS.

- [ ] **Step 5 : Commit**

```bash
git add app.py tests/test_model.py
git commit -m "feat: helpers de calcul des plages horaires (HH:MM, durée, TR/TS)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2 : UI — éditeur de plages par activité

**Files:**
- Modify: `app.py` — `_render_resource_card` (boucle d'activités, 1038-1061) + nouveaux helpers `_render_activity_hours` et `_render_ranges_editor`
- Test: `tests/test_ui.py`

**Interfaces:**
- Consomme (Task 1) : `_norm_entry`, `_ranges_to_pair`, `_range_hours`.
- Produit : par activité, un `st.radio` de mode clé `mode_{jour}_{quart_name}_{name}_{act}` (options `"TR/TS direct"`, `"⏱ Plage"`) ; en mode plage des `st.time_input` clés `rg_deb_{base}_{id}` / `rg_fin_{base}_{id}`, un `st.radio` `rg_knd_{base}_{id}`, un bouton retrait `rg_del_{base}_{id}`, un bouton `rg_add_{base}` ; en mode direct des `number_input` `tr_{base}` / `ts_{base}` (où `base = f"{jour}_{quart_name}_{name}_{act}"`). Écrit `quart["heures"][name][act] = {"mode","ranges","TR","TS"}`.

- [ ] **Step 1 : Écrire les tests UI**

Ajouter dans `tests/test_ui.py` (les helpers `_open_day_for_entry`, `_goto_saisie` existent ; le projet a l'activité `"C01 - Test"`) :

```python
def test_activity_hours_default_direct_mode(monkeypatch):
    """Une activité sélectionnée démarre en mode TR/TS direct : champs TR/TS présents,
    pas de time_input."""
    at = _open_day_for_entry(monkeypatch, personnel=("Alice",))
    _goto_saisie(at)
    at.session_state["acts_Lundi_Jour_Alice"] = ["C01 - Test"]
    at.run()
    base = "Lundi_Jour_Alice_C01 - Test"
    mode = [r for r in at.radio if r.key == f"mode_{base}"]
    assert mode and mode[0].value == "TR/TS direct"
    assert any(n.key == f"tr_{base}" for n in at.number_input)
    assert not at.time_input
    assert not at.exception


def test_activity_plage_mode_shows_time_inputs_and_adds_range(monkeypatch):
    """En mode Plage : le bouton d'ajout crée une plage avec deux time_input."""
    at = _open_day_for_entry(monkeypatch, personnel=("Alice",))
    _goto_saisie(at)
    at.session_state["acts_Lundi_Jour_Alice"] = ["C01 - Test"]
    at.run()
    base = "Lundi_Jour_Alice_C01 - Test"
    [r for r in at.radio if r.key == f"mode_{base}"][0].set_value("⏱ Plage").run()
    # Aucune plage au départ -> bouton d'ajout présent, pas de time_input
    assert any(b.key == f"rg_add_{base}" for b in at.button)
    assert not at.time_input
    # Ajouter une plage -> deux time_input apparaissent
    [b for b in at.button if b.key == f"rg_add_{base}"][0].click().run()
    assert len(at.time_input) == 2
    assert not at.exception


def test_plage_duration_feeds_tr_total(monkeypatch):
    """Une plage 10:00->12:00 alimente TR=2.0 dans quart['heures']."""
    import datetime
    at = _open_day_for_entry(monkeypatch, personnel=("Alice",))
    _goto_saisie(at)
    at.session_state["acts_Lundi_Jour_Alice"] = ["C01 - Test"]
    at.run()
    base = "Lundi_Jour_Alice_C01 - Test"
    [r for r in at.radio if r.key == f"mode_{base}"][0].set_value("⏱ Plage").run()
    [b for b in at.button if b.key == f"rg_add_{base}"][0].click().run()
    # Régler la plage sur 10:00 -> 12:00
    tis = sorted(at.time_input, key=lambda t: t.key)
    [t for t in at.time_input if t.key.startswith(f"rg_deb_{base}")][0].set_value(datetime.time(10, 0)).run()
    [t for t in at.time_input if t.key.startswith(f"rg_fin_{base}")][0].set_value(datetime.time(12, 0)).run()
    q = at.session_state["jours"]["Lundi"]["quarts"]["Jour"]
    entry = q["heures"]["Alice"]["C01 - Test"]
    assert entry["mode"] == "plage"
    assert entry["TR"] == 2.0 and entry["TS"] == 0.0
    assert not at.exception
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `.venv/bin/python -m pytest tests/test_ui.py -k "activity_hours_default or plage_mode_shows or plage_duration" -v`
Expected: FAIL (pas de `mode_…` / `rg_add_…` ; la boucle rend encore l'ancien tableau TR/TS).

- [ ] **Step 3 : Ajouter les helpers de rendu**

Dans `app.py`, ajouter ces deux fonctions juste avant `_render_resource_card` (vers la ligne 1028) :

```python
def _render_ranges_editor(base, initial):
    """Éditeur dynamique de plages (liste de {'debut','fin','type'}).

    Garde une liste à ids stables dans session_state pour que l'ajout/retrait
    ne décale pas les clés de widgets. Renvoie la liste courante des plages.
    """
    import datetime as _dt
    lst_key = f"ranges_{base}"
    seq_key = f"rangeseq_{base}"
    if lst_key not in st.session_state:
        seeded = [{"id": i, "debut": (r or {}).get("debut", "08:00"),
                   "fin": (r or {}).get("fin", "08:00"), "type": (r or {}).get("type", "TR")}
                  for i, r in enumerate(initial or [])]
        st.session_state[lst_key] = seeded
        st.session_state[seq_key] = len(seeded)
    rows = st.session_state[lst_key]
    result = []
    for row in rows:
        rid = row["id"]
        dk, fk, kk = f"rg_deb_{base}_{rid}", f"rg_fin_{base}_{rid}", f"rg_knd_{base}_{rid}"
        if dk not in st.session_state:
            _h, _m = (int(x) for x in row["debut"].split(":"))
            st.session_state[dk] = _dt.time(_h, _m)
        if fk not in st.session_state:
            _h, _m = (int(x) for x in row["fin"].split(":"))
            st.session_state[fk] = _dt.time(_h, _m)
        if kk not in st.session_state:
            st.session_state[kk] = row["type"]
        c1, c2, c3, c4, c5 = st.columns([3, 3, 2, 2, 1], vertical_alignment="center")
        deb = c1.time_input("Début", key=dk, step=_dt.timedelta(minutes=15),
                            label_visibility="collapsed", on_change=_mark_dirty)
        fin = c2.time_input("Fin", key=fk, step=_dt.timedelta(minutes=15),
                            label_visibility="collapsed", on_change=_mark_dirty)
        knd = c3.radio("Type", ["TR", "TS"], key=kk, horizontal=True,
                       label_visibility="collapsed", on_change=_mark_dirty)
        deb_s, fin_s = deb.strftime("%H:%M"), fin.strftime("%H:%M")
        dur = _range_hours(deb_s, fin_s)
        c4.markdown(f"**{dur:.2f} h**" if dur > 0 else "⚠️ fin ≤ début")
        if c5.button("✕", key=f"rg_del_{base}_{rid}", help="Retirer la plage"):
            st.session_state[lst_key] = [r for r in rows if r["id"] != rid]
            _mark_dirty()
            st.rerun()
        result.append({"debut": deb_s, "fin": fin_s, "type": knd})
    if st.button("＋ Ajouter une plage", key=f"rg_add_{base}", use_container_width=True):
        nid = st.session_state[seq_key]
        st.session_state[seq_key] = nid + 1
        st.session_state[lst_key] = rows + [{"id": nid, "debut": "08:00", "fin": "08:00", "type": "TR"}]
        _mark_dirty()
        st.rerun()
    return result


def _render_activity_hours(jour, quart_name, name, act, raw):
    """Rend l'éditeur d'heures d'une activité (mode direct ou plage).

    Renvoie l'entrée normalisée {'mode','ranges','TR','TS'}.
    """
    e = _norm_entry(raw)
    base = f"{jour}_{quart_name}_{name}_{act}"
    with st.container(border=True):
        c1, c2 = st.columns([2, 3], vertical_alignment="center")
        c1.markdown(f"**{act}**")
        mode_key = f"mode_{base}"
        if mode_key not in st.session_state:
            st.session_state[mode_key] = "⏱ Plage" if e["mode"] == "plage" else "TR/TS direct"
        mode = c2.radio("Mode de saisie", ["TR/TS direct", "⏱ Plage"], key=mode_key,
                        horizontal=True, label_visibility="collapsed", on_change=_mark_dirty)
        if mode == "⏱ Plage":
            ranges = _render_ranges_editor(base, e["ranges"])
            pair = _ranges_to_pair(ranges)
            st.caption(f"Total : TR {pair['TR']:.2f} h · TS {pair['TS']:.2f} h")
            return {"mode": "plage", "ranges": ranges, "TR": pair["TR"], "TS": pair["TS"]}
        hc1, hc2 = st.columns(2)
        tr_key, ts_key = f"tr_{base}", f"ts_{base}"
        st.session_state.setdefault(tr_key, e["TR"])
        st.session_state.setdefault(ts_key, e["TS"])
        tr = hc1.number_input("TR", key=tr_key, min_value=0.0, step=0.25,
                              format="%.2f", on_change=_mark_dirty)
        ts = hc2.number_input("TS", key=ts_key, min_value=0.0, step=0.25,
                              format="%.2f", on_change=_mark_dirty)
        return {"mode": "direct", "ranges": [], "TR": float(tr), "TS": float(ts)}
```

- [ ] **Step 4 : Brancher la boucle d'activités sur le nouvel éditeur**

Dans `app.py`, remplacer le bloc actuel (1038-1061, de `if sel_acts:` jusqu'à
`del quart["heures"][name]`) par :

```python
    new_heures = {}
    for act in (sel_acts or []):
        entry = _render_activity_hours(jour, quart_name, name, act,
                                       quart["heures"].get(name, {}).get(act, {}))
        if entry["TR"] > 0 or entry["TS"] > 0 or entry["ranges"]:
            new_heures[act] = entry
    if new_heures:
        quart["heures"][name] = new_heures
    elif name in quart["heures"]:
        del quart["heures"][name]
```

(L'ancien en-tête de tableau `hc1/hc2/hc3` et les colonnes `_HOURS_COLS` ne sont plus
utilisés ici ; laisser la constante `_HOURS_COLS` définie, elle est inoffensive.)

- [ ] **Step 5 : Lancer les tests UI ciblés pour vérifier qu'ils passent**

Run: `.venv/bin/python -m pytest tests/test_ui.py -k "activity_hours_default or plage_mode_shows or plage_duration" -v`
Expected: PASS.

- [ ] **Step 6 : Lancer la suite UI complète (anti-régression)**

Run: `.venv/bin/python -m pytest tests/test_ui.py -q`
Expected: tous PASS (sauf le skip préexistant). Si un test de la fiche supposait
l'ancien tableau (clés `tr_…`/`ts_…` sans bloc conteneur), il reste valide : les clés
`tr_{base}`/`ts_{base}` sont conservées en mode direct (défaut).

- [ ] **Step 7 : Commit**

```bash
git add app.py tests/test_ui.py
git commit -m "feat: saisie des heures par plages horaires (mode par activité)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3 : Persistance des plages

**Files:**
- Modify: `reports.py` — `_DDL_STATEMENTS` (table), `save_report` (~279-289), `load_report` (~350-357), + convertisseurs locaux
- Test: `tests/test_reports.py`

**Interfaces:**
- Consomme : structure d'entrée `{"mode","ranges","TR","TS"}` produite par l'UI (Task 2), `ranges` = liste de `{"debut":"HH:MM","fin":"HH:MM","type":"TR"|"TS"}`.
- Produit : table `report_hour_ranges` ; convertisseurs `reports._hhmm_to_min`, `reports._min_to_hhmm` (locaux à `reports.py` pour éviter une dépendance circulaire avec `app.py`).
- Note : la persistance SQL réelle est validée end-to-end contre Neon (SQLite ne reproduit pas les types Postgres) ; ici on teste la présence du DDL et les convertisseurs purs, comme les tests existants (`tests/test_reports.py`).

- [ ] **Step 1 : Écrire les tests (DDL + convertisseurs)**

Ajouter dans `tests/test_reports.py` :

```python
def test_ddl_has_hour_ranges_table():
    ddl = " ".join(reports._DDL_STATEMENTS)
    assert "create table if not exists report_hour_ranges" in ddl
    assert "quart_id" in ddl and "start_min" in ddl and "end_min" in ddl and "kind" in ddl


def test_reports_hhmm_converters():
    assert reports._hhmm_to_min("10:00") == 600
    assert reports._hhmm_to_min("10:15") == 615
    assert reports._hhmm_to_min("bidon") is None
    assert reports._min_to_hhmm(600) == "10:00"
    assert reports._min_to_hhmm(615) == "10:15"
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `.venv/bin/python -m pytest tests/test_reports.py -k "hour_ranges or hhmm_converters" -v`
Expected: FAIL (table absente du DDL, convertisseurs inexistants).

- [ ] **Step 3 : Ajouter le DDL de la table et les convertisseurs**

Dans `reports.py`, ajouter une entrée à la liste `_DDL_STATEMENTS` (après le bloc
`create table if not exists report_quart_resources`, vers la ligne 106-122) :

```python
    """
    create table if not exists report_hour_ranges (
        quart_id       integer references report_quarts(id) on delete cascade,
        resource_name  text not null,
        activity_label text not null,
        seq            integer not null,
        start_min      integer not null,
        end_min        integer not null,
        kind           text not null
    )
    """,
```

Et, près du haut du module (après les imports / avant `ensure_schema`), ajouter :

```python
def _hhmm_to_min(s):
    """'HH:MM' -> minutes depuis minuit ; None si invalide. (Local à reports
    pour éviter une dépendance circulaire avec app.py.)"""
    try:
        h, m = str(s).split(":")
        h, m = int(h), int(m)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h * 60 + m
    except (ValueError, AttributeError):
        pass
    return None


def _min_to_hhmm(mins):
    """minutes depuis minuit -> 'HH:MM' (borné 00:00..23:59)."""
    mins = max(0, min(int(mins), 23 * 60 + 59))
    return f"{mins // 60:02d}:{mins % 60:02d}"
```

- [ ] **Step 4 : Écrire les plages dans `save_report`**

Dans `reports.py`, dans la boucle d'insertion des heures (après le bloc
`insert into report_hours … {"q","rn","al","h","hts"}`, vers la ligne 289), ajouter
l'insertion des plages de l'entrée courante `pair` :

```python
                        for seq, rg in enumerate((pair or {}).get("ranges") or []):
                            sm = _hhmm_to_min((rg or {}).get("debut"))
                            em = _hhmm_to_min((rg or {}).get("fin"))
                            if sm is None or em is None:
                                continue
                            s.execute(text(
                                "insert into report_hour_ranges "
                                "(quart_id, resource_name, activity_label, seq, start_min, end_min, kind) "
                                "values (:q, :rn, :al, :sq, :sm, :em, :k)"),
                                {"q": quart_id, "rn": resource_name, "al": activity_label,
                                 "sq": seq, "sm": sm, "em": em,
                                 "k": "TS" if (rg or {}).get("type") == "TS" else "TR"})
```

(Le `continue` qui saute les heures à 0 TR/TS, lignes 283-284, saute aussi les plages
d'une entrée dont le total est nul — acceptable : une plage de durée nulle n'est pas
persistée.)

- [ ] **Step 5 : Relire les plages dans `load_report`**

Dans `reports.py`, dans `load_report`, juste après la boucle qui construit `heures`
depuis `report_hours` (après la ligne 357), ajouter :

```python
                rng = s.execute(
                    text("select resource_name, activity_label, seq, start_min, end_min, kind "
                         "from report_hour_ranges where quart_id = :q order by seq"),
                    {"q": q["id"]}).mappings().all()
                for r in rng:
                    entry = heures.setdefault(r["resource_name"], {}).setdefault(
                        r["activity_label"], {"TR": 0.0, "TS": 0.0})
                    entry.setdefault("ranges", []).append({
                        "debut": _min_to_hhmm(r["start_min"]),
                        "fin": _min_to_hhmm(r["end_min"]),
                        "type": r["kind"]})
                    entry["mode"] = "plage"
```

(Les totaux TR/TS proviennent toujours de `report_hours` ; on n'y attache que les
plages. Une activité sans plage reste un `{"TR","TS"}` = mode direct implicite, lu
correctement par `_norm_entry`.)

- [ ] **Step 6 : Lancer les tests reports + suite complète**

Run: `.venv/bin/python -m pytest tests/test_reports.py -k "hour_ranges or hhmm_converters" -v && .venv/bin/python -m pytest -q`
Expected: les tests ciblés PASS, puis toute la suite PASS (sauf le skip préexistant).

- [ ] **Step 7 : Commit**

```bash
git add reports.py tests/test_reports.py
git commit -m "feat: persistance des plages horaires (table report_hour_ranges)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Couverture de la spec :**
- Modèle `{mode, ranges, TR, TS}` + rétrocompat → Task 1 (`_norm_entry`). ✓
- `_range_hours` / `_ranges_to_pair` purs → Task 1. ✓
- Choix du mode par activité, défaut direct → Task 2 (`_render_activity_hours`, radio défaut « TR/TS direct »). ✓
- Mode plage : time_input HH:MM 15 min, bascule TR/TS, durée, ajout/retrait, sous-total → Task 2 (`_render_ranges_editor`). ✓
- Mode direct : number_input 0.25 / %.2f → Task 2. ✓
- Helper `_render_activity_hours` extrait → Task 2. ✓
- `report_hours` inchangée + nouvelle table `report_hour_ranges` → Task 3. ✓
- `save_report` écrit / `load_report` relit + mode déduit → Task 3 Steps 4-5. ✓
- Export Excel inchangé → aucune modification de `_legacy_day`/`build_df` (lit TR/TS via `_norm_pair`, non modifié). ✓
- Validation fin > début souple → Task 2 (`_range_hours`→0 + « ⚠️ fin ≤ début »). ✓
- Tests unitaires / UI / persistance → Tasks 1, 2, 3. ✓

**2. Placeholders :** aucun — tout le code et les commandes sont fournis. Le seul écart assumé à la spec : `_norm_pair` n'est **pas** modifié (il tolère déjà le nouveau dict TR/TS) ; on ajoute `_norm_entry` à la place — plus propre, mêmes garanties de rétrocompat.

**3. Cohérence des types :** `base = f"{jour}_{quart_name}_{name}_{act}"` partagé entre `_render_activity_hours` (clés `mode_/tr_/ts_`) et `_render_ranges_editor` (clés `rg_deb_/rg_fin_/rg_knd_/rg_del_/rg_add_`, ids stables). Forme des plages `{"debut","fin","type"}` identique entre Task 1 (`_ranges_to_pair`), Task 2 (UI), Task 3 (save/load). Convertisseurs : `_hhmm_to_min`/`_min_to_hhmm` dans `app.py` (Task 1) et copies locales dans `reports.py` (Task 3), volontairement dupliquées pour éviter l'import circulaire.
