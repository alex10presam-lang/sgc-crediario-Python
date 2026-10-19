import pytest
from sqlalchemy import select

from sgc.database import Database
from sgc.models import User
from sgc.security import Actor, password_hash
from sgc.services import Services

PASSWORD = "TesteLocal!2026"


@pytest.fixture(scope="session")
def hashed():
    return password_hash(PASSWORD)


@pytest.fixture
def environment(tmp_path, hashed):
    database = Database(tmp_path)
    with database.transaction() as session:
        for company in ["alpha", "beta"]:
            for role in ["admin", "vendedor", "cobrador"]:
                session.add(
                    User(
                        company=company,
                        name=company + " " + role,
                        username=role,
                        password_hash=hashed,
                        role=role,
                        active=True,
                    )
                )
    with database.session() as session:
        services = {
            (u.company, u.role): Services(database, Actor(u.id, u.company))
            for u in session.scalars(select(User))
        }
    yield database, services
    database.engine.dispose()


@pytest.fixture
def service(environment):
    return environment[1]["alpha", "admin"]


@pytest.fixture
def credit(service):
    customer = service.add_customer("Cliente fictício")
    sale = service.create_sale(
        customer, "Venda de teste", amount="100.01", count=3, request_key="sale-1"
    )
    return sale, [r for r in service.installments() if r["sale_id"] == sale]
