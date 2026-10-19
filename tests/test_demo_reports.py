import sqlite3
from sgc.demo import seed
from sgc.database import Database
from sgc.security import authenticate
from sgc.services import Services
from sgc.reports import payment_pdf
from sgc.backup import create_backup


def test_demo_is_repeatable_and_backup_valid(tmp_path):
    db = Database(tmp_path)
    try:
        assert seed(db)
        assert not seed(db)
        service = Services(db, authenticate(db, "aurora", "admin", "DemoLocal!2026"))
        assert service.summary() == {
            "total": 217000,
            "paid": 77000,
            "balance": 140000,
            "overdue": 15000,
        }
        other = Services(db, authenticate(db, "horizonte", "admin", "DemoLocal!2026"))
        assert other.summary()["total"] == 900000
        assert len(service.users()) == 3
        backup = create_backup(tmp_path)
        with sqlite3.connect(backup) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert connection.execute("select count(*) from users").fetchone()[0] == 6
    finally:
        db.engine.dispose()


def test_pdf_uses_scoped_payment_data(service, credit):
    _, rows = credit
    payment = service.receive(rows[0]["id"], 10, "pdf")
    details = service.payment_details(payment)
    assert details["amount"] == 1000 and details["company"] == "alpha"
    pdf = payment_pdf(details)
    assert pdf.startswith(b"%PDF") and len(pdf) > 1000
