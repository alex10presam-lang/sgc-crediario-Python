from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import pytest
from sqlalchemy import select

from sgc.models import Sale, Installment, Payment
from sgc.security import DomainError


def test_installments_exact_and_interest(service, credit):
    _, rows = credit
    assert [r["amount"] for r in rows] == [3334, 3334, 3333]
    customer = service.customers()[0]["id"]
    service.create_sale(
        customer,
        "Financiada",
        amount=100,
        entry=20,
        count=3,
        interest_percent=10,
        request_key="interest",
    )
    with service.db.session() as session:
        sale = session.scalar(select(Sale).where(Sale.request_key == "interest"))
        assert sale.principal == 10000 and sale.interest == 800 and sale.total == 10800
        assert (
            sum(
                r.amount
                for r in session.scalars(select(Installment).where(Installment.sale_id == sale.id))
            )
            == 10800
        )
    assert service.summary()["paid"] == 2000


def test_partial_then_excess_and_reversal(service, credit):
    _, rows = credit
    identifier = service.receive(rows[0]["id"], "10", "partial")
    current = service.installments()
    assert current[0]["paid"] == 1000 and current[0]["balance"] == 2334
    assert current[0]["status"] != "Quitada"
    next_payment = service.receive(rows[0]["id"], "50", "overpay")
    current = service.installments()
    assert current[0]["balance"] == 0 and current[1]["paid"] == 2666
    assert service.summary()["paid"] == 6000
    with pytest.raises(DomainError):
        service.reverse_payment(identifier)
    service.reverse_payment(next_payment)
    assert service.summary()["paid"] == 1000
    service.reverse_payment(identifier)
    assert service.summary()["paid"] == 0
    with pytest.raises(DomainError):
        service.reverse_payment(identifier)


@pytest.mark.parametrize("value", ["0", "-10", "NaN", "1000"])
def test_invalid_payment_does_not_change_balances(service, credit, value):
    _, rows = credit
    with pytest.raises(DomainError):
        service.receive(rows[0]["id"], value, "invalid")
    assert service.summary()["paid"] == 0


def test_idempotent_payment_and_sale(service, credit):
    sale, rows = credit
    customer = service.customers()[0]["id"]
    assert (
        service.create_sale(
            customer, "Venda de teste", amount="100.01", count=3, request_key="sale-1"
        )
        == sale
    )
    first = service.receive(rows[0]["id"], 10, "same")
    assert service.receive(rows[0]["id"], 10, "same") == first
    assert service.summary()["paid"] == 1000
    with pytest.raises(DomainError):
        service.receive(rows[0]["id"], 11, "same")
    with pytest.raises(DomainError):
        service.create_sale(customer, "Diferente", amount=1, request_key="sale-1")


def test_stock_atomic_sale_and_cancellation(service):
    customer = service.add_customer("Teste")
    product = service.add_product("Último item", 10, 1)
    sale = service.create_sale(customer, "Com estoque", items=[(product, 1)], request_key="stock")
    assert service.products()[0]["stock"] == 0
    with pytest.raises(DomainError):
        service.create_sale(customer, "Sem estoque", items=[(product, 1)], request_key="stock2")
    service.cancel_sale(sale)
    assert service.products()[0]["stock"] == 1 and service.summary()["total"] == 0
    with pytest.raises(DomainError):
        service.cancel_sale(sale)
    assert service.products()[0]["stock"] == 1


def test_concurrent_stock_purchase(service):
    customer = service.add_customer("Teste")
    product = service.add_product("Último item", 10, 1)

    def buy(index):
        try:
            return service.create_sale(
                customer, "Concorrente", items=[(product, 1)], request_key=f"concurrent-{index}"
            )
        except DomainError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(buy, [1, 2]))
    assert len([x for x in outcomes if x]) == 1
    assert service.products()[0]["stock"] == 0


def test_concurrent_payment_same_key(service, credit):
    _, rows = credit
    with ThreadPoolExecutor(max_workers=2) as pool:
        identifiers = list(
            pool.map(lambda _: service.receive(rows[0]["id"], 10, "parallel"), range(2))
        )
    assert identifiers[0] == identifiers[1]
    assert service.summary()["paid"] == 1000


def test_reschedule_and_cancel_paid_sale(service, credit):
    sale, rows = credit
    due = date.today() + timedelta(days=20)
    service.reschedule(rows[0]["id"], due)
    assert next(r for r in service.installments() if r["id"] == rows[0]["id"])["due_date"] == due
    service.receive(rows[0]["id"], 1, "one")
    with pytest.raises(DomainError):
        service.cancel_sale(sale)


def test_cash_sale_records_receipt(service):
    customer = service.add_customer("Vista")
    service.create_sale(customer, "À vista", amount="19.99", entry="19.99", request_key="cash")
    assert service.summary() == {"total": 1999, "paid": 1999, "balance": 0, "overdue": 0}
    payment = service.payments()[0]
    assert payment["is_entry"]
    with pytest.raises(DomainError):
        service.reverse_payment(payment["id"])


def test_expired_reversal(service, credit):
    _, rows = credit
    identifier = service.receive(rows[0]["id"], 1, "aged")
    with service.db.transaction() as session:
        session.get(Payment, identifier).created_at -= timedelta(minutes=6)
    with pytest.raises(DomainError):
        service.reverse_payment(identifier)
