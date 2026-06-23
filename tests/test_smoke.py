def test_import_app():
    import app
    assert hasattr(app, "JOURS")
    assert app.JOURS[0] == "Dimanche"
