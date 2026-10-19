"""An explicit, repeatable dataset. Never opens the legacy database."""

from datetime import date, timedelta

from sqlalchemy import select

from sgc.database import Database
from sgc.models import User
from sgc.security import Actor, password_hash
from sgc.services import Services

DEMO_PASSWORD = "DemoLocal!2026"


def seed(database):
    with database.transaction() as session:
        if session.scalar(select(User.id)):
            return False
        for company, name in [
            ("aurora", "Loja Aurora · demonstração"),
            ("horizonte", "Loja Horizonte · demonstração"),
        ]:
            for username, role in [
                ("admin", "admin"),
                ("vendas", "vendedor"),
                ("cobranca", "cobrador"),
            ]:
                session.add(
                    User(
                        company=company,
                        name=name if role == "admin" else "Equipe Demo · " + role,
                        username=username,
                        role=role,
                        password_hash=password_hash(DEMO_PASSWORD),
                        active=True,
                    )
                )
    with database.session() as session:
        admins = list(session.scalars(select(User).where(User.role == "admin")))
    for user in admins:
        service = Services(database, Actor(user.id, user.company))
        customers = [
            service.add_customer(f"Cliente Demonstração {n:02d}", "00000000000")
            for n in range(1, 4)
        ]
        if user.company == "horizonte":
            service.create_sale(
                customers[0],
                "Registro exclusivo da segunda empresa",
                amount="9000",
                entry="9000",
                request_key="seed-horizonte",
            )
            continue
        service.add_product("Luminária de mesa · exemplo", "129.90", 12)
        service.add_product("Cadeira de escritório · exemplo", "699.90", 6)
        service.add_product("Organizador modular · exemplo", "89.90", 20)
        service.create_sale(
            customers[0],
            "Conjunto para escritório",
            amount="1200",
            entry="200",
            count=4,
            first_due=date.today() - timedelta(days=15),
            request_key="seed-1",
        )
        service.create_sale(
            customers[1],
            "Itens para casa",
            amount="650",
            entry="150",
            count=2,
            first_due=date.today() + timedelta(days=12),
            request_key="seed-2",
        )
        service.create_sale(
            customers[2],
            "Compra à vista",
            amount="320",
            entry="320",
            request_key="seed-3",
        )
        installment = next(
            row for row in service.installments() if row["balance"] and row["sale_id"] == 1
        )
        service.receive(installment["id"], "100", "seed-payment")
    return True


if __name__ == "__main__":
    database = Database()
    print(
        "Base fictícia criada. Empresa: aurora | usuário: admin | senha: " + DEMO_PASSWORD
        if seed(database)
        else "A base já contém usuários; nenhum dado foi sobrescrito."
    )
    database.engine.dispose()
