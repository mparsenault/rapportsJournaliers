import sync_projects


def test_rows_to_payload_dedups_projects():
    rows = [
        (1, "P-1", "Projet 1", "C01", "A"),
        (1, "P-1", "Projet 1", "C02", "B"),
        (2, "P-2", "Projet 2", "C03", "C"),
    ]
    projects, activities = sync_projects.rows_to_payload(rows)
    assert projects == [(1, "P-1", "Projet 1"), (2, "P-2", "Projet 2")]
    assert activities == [(1, "C01", "A"), (1, "C02", "B"), (2, "C03", "C")]


def test_rows_to_payload_skips_null_activity():
    projects, activities = sync_projects.rows_to_payload([(3, "P-3", "Projet 3", None, None)])
    assert projects == [(3, "P-3", "Projet 3")]
    assert activities == []


def test_rows_to_payload_skips_blank_activity_code():
    projects, activities = sync_projects.rows_to_payload([(4, "P-4", "Projet 4", "   ", "desc")])
    assert projects == [(4, "P-4", "Projet 4")]
    assert activities == []


def test_rows_to_payload_empty():
    assert sync_projects.rows_to_payload([]) == ([], [])


def test_parse_dotenv():
    text = (
        "# commentaire\n"
        "SQLSERVER_HOST=srv1\n"
        "POSTGRES_URL=postgresql://u:p@h/db?sslmode=require&channel_binding=require\n"
        "\n"
        "EMPTY=\n"
        'QUOTED="val"\n'
    )
    d = sync_projects._parse_dotenv(text)
    assert d["SQLSERVER_HOST"] == "srv1"
    # la valeur garde ses '=' et '&'
    assert d["POSTGRES_URL"] == "postgresql://u:p@h/db?sslmode=require&channel_binding=require"
    assert d["EMPTY"] == ""
    assert d["QUOTED"] == "val"
    assert "# commentaire" not in d


def test_staff_rows_to_payload_formats_and_dedups():
    rows = [
        (1, "Jean", "Tremblay", "Électricien"),
        (1, "Jean", "Tremblay", "Électricien"),   # doublon
        (1, "Marie", "Roy", None),                 # métier NULL
        (2, "Luc", "Côté", ""),                    # métier vide
    ]
    assert sync_projects.staff_rows_to_payload(rows) == [
        (1, "Jean Tremblay (Électricien)"),
        (1, "Marie Roy"),
        (2, "Luc Côté"),
    ]


def test_staff_rows_to_payload_skips_missing_project():
    assert sync_projects.staff_rows_to_payload([(None, "X", "Y", "Z")]) == []


def test_staff_rows_to_payload_empty():
    assert sync_projects.staff_rows_to_payload([]) == []
