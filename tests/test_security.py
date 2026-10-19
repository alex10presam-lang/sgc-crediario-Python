import pytest
from sqlalchemy import select

from sgc.models import User, LoginAttempt
from sgc.security import authenticate, DomainError, password_hash, verify_password, Actor
from sgc.services import Services


def test_password_format_and_no_plaintext(hashed):
    assert verify_password("TesteLocal!2026", hashed)
    assert not verify_password("incorreta", hashed)
    assert not verify_password("admin", "admin")
    assert not verify_password("password", "deadbeef")
    assert "TesteLocal" not in hashed
    with pytest.raises(DomainError):
        password_hash("admin")


def test_authentication_and_lockout(environment):
    database, _ = environment
    assert authenticate(database, "alpha", "admin", "TesteLocal!2026").company == "alpha"
    for _ in range(5):
        with pytest.raises(DomainError):
            authenticate(database, "alpha", "admin", "wrong")
    with pytest.raises(DomainError, match="Aguarde"):
        authenticate(database, "alpha", "admin", "TesteLocal!2026")
    with database.session() as session:
        assert session.scalar(select(LoginAttempt)).failures == 5


def test_company_and_role_isolation(environment):
    database, services = environment
    alpha, beta = services["alpha", "admin"], services["beta", "admin"]
    client = beta.add_customer("Somente beta")
    product = beta.add_product("Somente beta", "25", 4)
    beta_sale = beta.create_sale(client, "Outra empresa", amount="500", request_key="beta-sale")
    assert alpha.customers() == []
    assert alpha.summary()["total"] == 0
    assert alpha.products() == []
    with pytest.raises(DomainError):
        alpha.create_sale(client, "Inválida", amount=20, request_key="cross")
    local_client = alpha.add_customer("Alpha")
    with pytest.raises(DomainError):
        alpha.create_sale(local_client, "Inválida", items=[(product, 1)], request_key="cross-item")
    row = beta.installments()[0]
    with pytest.raises(DomainError):
        alpha.receive(row["id"], 1, "cross-pay")
    with pytest.raises(DomainError):
        alpha.reschedule(row["id"], row["due_date"])
    with pytest.raises(DomainError):
        alpha.cancel_sale(beta_sale)
    fake = Services(database, Actor(alpha.actor.user_id, "beta"))
    with pytest.raises(DomainError):
        fake.summary()
    collector = services["alpha", "cobrador"]
    with pytest.raises(DomainError):
        collector.add_customer("Proibido")
    with pytest.raises(DomainError):
        collector.add_product("Produto", 1, 1)
    with pytest.raises(DomainError):
        services["alpha", "vendedor"].receive(row["id"], 1, "wrong-role")


def test_password_change_and_deactivation(environment):
    database, services = environment
    admin = services["alpha", "admin"]
    identifier = admin.add_user("Nova pessoa", "novapessoa", "SenhaNova!2026", "vendedor")
    new = Services(database, authenticate(database, "alpha", "novapessoa", "SenhaNova!2026"))
    new.change_password("SenhaNova!2026", "SenhaAlterada!2026")
    with pytest.raises(DomainError):
        new.customers()
    assert authenticate(database, "alpha", "novapessoa", "SenhaAlterada!2026")
    with pytest.raises(DomainError):
        authenticate(database, "alpha", "novapessoa", "SenhaNova!2026")
    admin.deactivate_user(identifier)
    with pytest.raises(DomainError):
        new.customers()
    with pytest.raises(DomainError):
        authenticate(database, "alpha", "novapessoa", "SenhaAlterada!2026")
    with pytest.raises(DomainError):
        admin.deactivate_user(admin.actor.user_id)


def test_company_users_and_audit(environment):
    database, services = environment
    alpha, beta = services["alpha", "admin"], services["beta", "admin"]
    beta.add_customer("Beta")
    alpha.add_customer("Alpha")
    assert len(alpha.users()) == 3
    assert len(alpha.audit()) == 1
    with database.session() as session:
        users = list(session.scalars(select(User)))
        assert all(user.password_hash.startswith("pbkdf2_sha256$") for user in users)
