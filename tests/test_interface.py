from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

from sgc.database import Database
from sgc.demo import seed


@pytest.fixture
def ui_data(tmp_path, monkeypatch):
    monkeypatch.setenv("SGC_DATA_DIR", str(tmp_path))
    db = Database(tmp_path)
    seed(db)
    from sgc.ui import database

    database.clear()
    yield
    database.clear()
    db.engine.dispose()


def login(username="admin"):
    app = AppTest.from_file(str(Path(__file__).parents[1] / "dashboard.py")).run(timeout=20)
    assert not app.exception
    app.text_input[1].set_value(username)
    app.text_input[2].set_value("DemoLocal!2026")
    app.button[0].click().run(timeout=20)
    assert not app.exception
    return app


def test_admin_navigation_and_summary(ui_data):
    app = login()
    assert app.metric[0].value == "R$ 2.170,00"
    assert app.metric[1].value == "R$ 770,00"
    for section in ["Clientes", "Nova venda", "Estoque", "Cobrança", "Minha conta"]:
        app.sidebar.radio[0].set_value(section).run(timeout=20)
        assert not app.exception, section


def test_collection_role_navigation(ui_data):
    app = login("cobranca")
    assert app.sidebar.radio[0].options == ["Visão geral", "Clientes", "Cobrança", "Minha conta"]
    app.sidebar.radio[0].set_value("Cobrança").run(timeout=20)
    assert not app.exception
