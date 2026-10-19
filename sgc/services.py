"""Business operations enforce tenant and role boundaries independently of the UI."""

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from sgc.models import (
    Allocation,
    Audit,
    Customer,
    Installment,
    Payment,
    Product,
    Sale,
    SaleItem,
    User,
)
from sgc.money import add_months, cents, split_cents
from sgc.security import DomainError, authorize, password_hash, verify_password

SALES = {"admin", "vendedor"}
COLLECTIONS = {"admin", "cobrador"}


def required(value, label, limit=160):
    value = str(value).strip()
    if not value or len(value) > limit:
        raise DomainError(f"{label}: informe de 1 a {limit} caracteres.")
    return value


class Services:
    def __init__(self, database, actor):
        self.db = database
        self.actor = actor

    def _record(self, session, model, identifier):
        row = session.scalar(
            select(model).where(model.id == identifier, model.company == self.actor.company)
        )
        if row is None:
            raise DomainError("Registro não encontrado nesta empresa.")
        return row

    def _audit(self, session, action, details):
        session.add(
            Audit(
                company=self.actor.company,
                user_id=self.actor.user_id,
                action=action,
                details=details,
            )
        )

    def identity(self):
        with self.db.session() as session:
            user = authorize(session, self.actor)
            return {
                "name": user.name,
                "username": user.username,
                "role": user.role,
                "company": user.company,
            }

    def customers(self):
        with self.db.session() as session:
            authorize(session, self.actor)
            return [
                {"id": r.id, "name": r.name, "phone": r.phone}
                for r in session.scalars(
                    select(Customer)
                    .where(Customer.company == self.actor.company)
                    .order_by(Customer.name)
                )
            ]

    def add_customer(self, name, phone=""):
        with self.db.transaction() as session:
            authorize(session, self.actor, SALES)
            row = Customer(
                company=self.actor.company,
                name=required(name, "Nome"),
                phone=str(phone).strip()[:40],
            )
            session.add(row)
            session.flush()
            self._audit(session, "CLIENTE", f"Cadastro #{row.id}")
            return row.id

    def products(self):
        with self.db.session() as session:
            authorize(session, self.actor, SALES)
            return [
                {"id": r.id, "name": r.name, "price": r.price, "stock": r.stock}
                for r in session.scalars(
                    select(Product)
                    .where(Product.company == self.actor.company)
                    .order_by(Product.name)
                )
            ]

    def add_product(self, name, price, stock):
        price = cents(price)
        if price <= 0 or not isinstance(stock, int) or not 0 <= stock <= 1_000_000:
            raise DomainError("Preço deve ser positivo e estoque deve ser um inteiro não negativo.")
        with self.db.transaction() as session:
            authorize(session, self.actor, {"admin"})
            row = Product(
                company=self.actor.company,
                name=required(name, "Produto"),
                price=price,
                stock=stock,
            )
            session.add(row)
            session.flush()
            self._audit(session, "PRODUTO", f"Cadastro #{row.id}; estoque {stock}")
            return row.id

    def restock(self, identifier, quantity):
        if not isinstance(quantity, int) or not 1 <= quantity <= 1_000_000:
            raise DomainError("Informe uma quantidade inteira positiva.")
        with self.db.transaction() as session:
            authorize(session, self.actor, {"admin"})
            product = self._record(session, Product, identifier)
            product.stock += quantity
            self._audit(session, "ESTOQUE", f"Produto #{identifier}: entrada de {quantity}")

    def create_sale(
        self,
        customer_id,
        description,
        *,
        amount=0,
        items=None,
        entry=0,
        count=1,
        first_due=None,
        interest_percent=0,
        request_key,
    ):
        description = required(description, "Descrição")
        request_key = required(request_key, "Identificador", 100)
        first_due = first_due or add_months(date.today(), 1)
        if not isinstance(first_due, date) or not 1900 <= first_due.year <= 2100:
            raise DomainError("Informe um vencimento válido.")
        if not isinstance(count, int) or not 1 <= count <= 48:
            raise DomainError("Use de 1 a 48 parcelas.")
        rate = cents(interest_percent)
        if rate > 10_000:
            raise DomainError("A demonstração aceita acréscimo de 0 a 100%.")
        amount, entry = cents(amount), cents(entry)
        quantities = {}
        for product_id, quantity in items or []:
            if not isinstance(quantity, int) or not 1 <= quantity <= 1_000_000:
                raise DomainError("Quantidade inválida.")
            quantities[product_id] = quantities.get(product_id, 0) + quantity
        digest = hashlib.sha256(
            json.dumps(
                [
                    customer_id,
                    description,
                    amount,
                    sorted(quantities.items()),
                    entry,
                    count,
                    first_due.isoformat(),
                    rate,
                ]
            ).encode()
        ).hexdigest()
        with self.db.transaction() as session:
            authorize(session, self.actor, SALES)
            previous = session.scalar(
                select(Sale).where(
                    Sale.company == self.actor.company, Sale.request_key == request_key
                )
            )
            if previous:
                if previous.request_digest != digest or previous.user_id != self.actor.user_id:
                    raise DomainError("Este identificador já foi utilizado em outra operação.")
                return previous.id
            self._record(session, Customer, customer_id)
            products = []
            if quantities:
                amount = 0
                for identifier, quantity in quantities.items():
                    product = self._record(session, Product, identifier)
                    if product.stock < quantity:
                        raise DomainError(f"Estoque insuficiente: {product.name}.")
                    amount += product.price * quantity
                    products.append((product, quantity))
            if amount <= 0 or amount > 99_999_999_999 or entry > amount:
                raise DomainError("O total deve ser positivo e a entrada não pode superar o preço.")
            interest = cents(Decimal(amount - entry) / 100 * Decimal(rate) / 10_000)
            total = amount + interest
            installments = split_cents(total - entry, count) if total > entry else []
            sale = Sale(
                company=self.actor.company,
                customer_id=customer_id,
                user_id=self.actor.user_id,
                description=description,
                total=total,
                principal=amount,
                interest=interest,
                request_key=request_key,
                request_digest=digest,
            )
            session.add(sale)
            session.flush()
            for product, quantity in products:
                product.stock -= quantity
                session.add(
                    SaleItem(
                        sale_id=sale.id,
                        product_id=product.id,
                        description=product.name,
                        quantity=quantity,
                        unit_price=product.price,
                    )
                )
            if not products:
                session.add(
                    SaleItem(
                        sale_id=sale.id,
                        description=description,
                        quantity=1,
                        unit_price=amount,
                    )
                )
            if entry:
                paid = Installment(
                    company=self.actor.company,
                    sale_id=sale.id,
                    number=0,
                    amount=entry,
                    paid=entry,
                    due_date=date.today(),
                )
                payment = Payment(
                    company=self.actor.company,
                    sale_id=sale.id,
                    user_id=self.actor.user_id,
                    amount=entry,
                    is_entry=True,
                    request_key="entry:" + request_key,
                )
                session.add_all([paid, payment])
                session.flush()
                session.add(Allocation(payment_id=payment.id, installment_id=paid.id, amount=entry))
            for i, value in enumerate(installments):
                session.add(
                    Installment(
                        company=self.actor.company,
                        sale_id=sale.id,
                        number=i + 1,
                        amount=value,
                        paid=0,
                        due_date=add_months(first_due, i),
                    )
                )
            self._audit(session, "VENDA", f"Venda #{sale.id}: {total} centavos")
            return sale.id

    def installments(self):
        with self.db.session() as session:
            authorize(session, self.actor)
            query = (
                select(Installment, Sale, Customer)
                .join(Sale, Installment.sale_id == Sale.id)
                .join(Customer, Sale.customer_id == Customer.id)
                .where(
                    Installment.company == self.actor.company,
                    Sale.company == self.actor.company,
                    Customer.company == self.actor.company,
                    Sale.cancelled.is_(False),
                )
                .order_by(Installment.due_date, Installment.id)
            )
            result = []
            for installment, sale, customer in session.execute(query):
                balance = installment.amount - installment.paid
                status = (
                    "Quitada"
                    if balance == 0
                    else ("Atrasada" if installment.due_date < date.today() else "Em aberto")
                )
                result.append(
                    {
                        "id": installment.id,
                        "sale_id": sale.id,
                        "number": installment.number,
                        "customer": customer.name,
                        "description": sale.description,
                        "amount": installment.amount,
                        "paid": installment.paid,
                        "balance": balance,
                        "due_date": installment.due_date,
                        "status": status,
                    }
                )
            return result

    def summary(self):
        rows = self.installments()
        return {
            "total": sum(r["amount"] for r in rows),
            "paid": sum(r["paid"] for r in rows),
            "balance": sum(r["balance"] for r in rows),
            "overdue": sum(r["balance"] for r in rows if r["due_date"] < date.today()),
        }

    def receive(self, installment_id, amount, request_key):
        amount = cents(amount)
        request_key = required(request_key, "Identificador", 100)
        if amount <= 0:
            raise DomainError("O recebimento deve ser maior que zero.")
        with self.db.transaction() as session:
            authorize(session, self.actor, COLLECTIONS)
            old = session.scalar(
                select(Payment).where(
                    Payment.company == self.actor.company,
                    Payment.request_key == request_key,
                )
            )
            if old:
                if (
                    old.amount != amount
                    or old.start_installment_id != installment_id
                    or old.user_id != self.actor.user_id
                ):
                    raise DomainError("Este identificador já foi utilizado em outra operação.")
                return old.id
            selected = self._record(session, Installment, installment_id)
            sale = self._record(session, Sale, selected.sale_id)
            if sale.cancelled or selected.amount == selected.paid:
                raise DomainError("Esta parcela não está disponível para recebimento.")
            rows = list(
                session.scalars(
                    select(Installment)
                    .where(
                        Installment.sale_id == sale.id,
                        Installment.company == self.actor.company,
                        Installment.number >= selected.number,
                    )
                    .order_by(Installment.number)
                )
            )
            if amount > sum(row.amount - row.paid for row in rows):
                raise DomainError(
                    "O valor supera o saldo desta parcela e das seguintes. Nenhum recebimento foi gravado."
                )
            payment = Payment(
                company=self.actor.company,
                sale_id=sale.id,
                user_id=self.actor.user_id,
                amount=amount,
                request_key=request_key,
                start_installment_id=installment_id,
            )
            session.add(payment)
            session.flush()
            remaining = amount
            for row in rows:
                allocated = min(remaining, row.amount - row.paid)
                if allocated:
                    row.paid += allocated
                    session.add(
                        Allocation(
                            payment_id=payment.id,
                            installment_id=row.id,
                            amount=allocated,
                        )
                    )
                    remaining -= allocated
            self._audit(
                session,
                "RECEBIMENTO",
                f"Recebimento #{payment.id}: {amount} centavos; venda #{sale.id}",
            )
            return payment.id

    def reverse_payment(self, identifier):
        with self.db.transaction() as session:
            user = authorize(session, self.actor, COLLECTIONS)
            payment = self._record(session, Payment, identifier)
            if (
                payment.is_entry
                or payment.reversed
                or datetime.now() - payment.created_at > timedelta(minutes=5)
            ):
                raise DomainError(
                    "Só é possível desfazer um recebimento recente, em até cinco minutos. Entradas não são estornadas por este fluxo."
                )
            if user.role != "admin" and payment.user_id != user.id:
                raise DomainError("Você só pode desfazer seus próprios recebimentos.")
            newer = session.scalar(
                select(Payment.id).where(
                    Payment.sale_id == payment.sale_id,
                    Payment.id > payment.id,
                    Payment.reversed.is_(False),
                )
            )
            if newer:
                raise DomainError(
                    "Há um recebimento posterior nesta venda. Desfaça primeiro o mais recente."
                )
            for allocation in session.scalars(
                select(Allocation).where(Allocation.payment_id == payment.id)
            ):
                row = self._record(session, Installment, allocation.installment_id)
                row.paid -= allocation.amount
            payment.reversed = True
            self._audit(
                session,
                "ESTORNO",
                f"Recebimento #{identifier} desfeito; valor {payment.amount} centavos",
            )

    def reschedule(self, identifier, due_date):
        if not isinstance(due_date, date) or due_date < date.today() or due_date.year > 2100:
            raise DomainError("Escolha uma data a partir de hoje, até 2100.")
        with self.db.transaction() as session:
            authorize(session, self.actor, COLLECTIONS)
            row = self._record(session, Installment, identifier)
            sale = self._record(session, Sale, row.sale_id)
            if row.paid == row.amount or sale.cancelled:
                raise DomainError("Esta parcela não está em aberto.")
            old = row.due_date
            row.due_date = due_date
            self._audit(session, "VENCIMENTO", f"Parcela #{identifier}: {old} → {due_date}")

    def cancel_sale(self, identifier):
        with self.db.transaction() as session:
            authorize(session, self.actor, {"admin"})
            sale = self._record(session, Sale, identifier)
            if sale.cancelled:
                raise DomainError("Esta venda já foi cancelada.")
            paid = (
                session.scalar(
                    select(func.sum(Installment.paid)).where(Installment.sale_id == identifier)
                )
                or 0
            )
            if paid:
                raise DomainError(
                    "A venda possui recebimentos. Não pode ser cancelada neste fluxo."
                )
            for item in session.scalars(select(SaleItem).where(SaleItem.sale_id == identifier)):
                if item.product_id:
                    self._record(session, Product, item.product_id).stock += item.quantity
            sale.cancelled = True
            self._audit(session, "CANCELAMENTO", f"Venda #{identifier}; estoque devolvido")

    def users(self):
        with self.db.session() as session:
            authorize(session, self.actor, {"admin"})
            return [
                {
                    "id": u.id,
                    "name": u.name,
                    "username": u.username,
                    "role": u.role,
                    "active": u.active,
                }
                for u in session.scalars(select(User).where(User.company == self.actor.company))
            ]

    def add_user(self, name, username, password, role):
        username = str(username).strip().lower()
        if not re.fullmatch(r"[a-z0-9_.-]{3,40}", username) or role not in {
            "admin",
            "vendedor",
            "cobrador",
        }:
            raise DomainError("Use um usuário de 3 a 40 caracteres simples e um perfil válido.")
        hashed = password_hash(password)
        with self.db.transaction() as session:
            authorize(session, self.actor, {"admin"})
            if session.scalar(
                select(User.id).where(User.company == self.actor.company, User.username == username)
            ):
                raise DomainError("Este usuário já existe na empresa.")
            user = User(
                company=self.actor.company,
                name=required(name, "Nome"),
                username=username,
                password_hash=hashed,
                role=role,
            )
            session.add(user)
            session.flush()
            self._audit(session, "USUÁRIO", f"Cadastro #{user.id}; perfil {role}")
            return user.id

    def deactivate_user(self, identifier):
        with self.db.transaction() as session:
            authorize(session, self.actor, {"admin"})
            user = self._record(session, User, identifier)
            if user.id == self.actor.user_id:
                raise DomainError("Você não pode desativar a própria conta.")
            user.active = False
            self._audit(session, "USUÁRIO", f"Conta #{identifier} desativada")

    def change_password(self, current, new):
        hashed = password_hash(new)
        with self.db.transaction() as session:
            user = authorize(session, self.actor)
            if not verify_password(current, user.password_hash):
                raise DomainError("Senha atual incorreta.")
            user.password_hash = hashed
            user.auth_version += 1
            self._audit(session, "SENHA", "Senha alterada")

    def audit(self):
        with self.db.session() as session:
            authorize(session, self.actor, {"admin"})
            return [
                {
                    "date": r.created_at,
                    "user_id": r.user_id,
                    "action": r.action,
                    "details": r.details,
                }
                for r in session.scalars(
                    select(Audit)
                    .where(Audit.company == self.actor.company)
                    .order_by(Audit.id.desc())
                    .limit(200)
                )
            ]

    def payment_details(self, identifier):
        with self.db.session() as session:
            authorize(session, self.actor, COLLECTIONS)
            payment = self._record(session, Payment, identifier)
            sale = self._record(session, Sale, payment.sale_id)
            customer = self._record(session, Customer, sale.customer_id)
            allocations = list(
                session.execute(
                    select(Allocation, Installment)
                    .join(Installment, Allocation.installment_id == Installment.id)
                    .where(Allocation.payment_id == payment.id)
                )
            )
            return {
                "id": payment.id,
                "company": payment.company,
                "date": payment.created_at,
                "amount": payment.amount,
                "reversed": payment.reversed,
                "customer": customer.name,
                "sale_id": sale.id,
                "description": sale.description,
                "allocations": [{"number": i.number, "amount": a.amount} for a, i in allocations],
            }

    def payments(self):
        with self.db.session() as session:
            authorize(session, self.actor, COLLECTIONS)
            return [
                {
                    "id": p.id,
                    "sale_id": p.sale_id,
                    "amount": p.amount,
                    "date": p.created_at,
                    "reversed": p.reversed,
                    "is_entry": p.is_entry,
                }
                for p in session.scalars(
                    select(Payment)
                    .where(Payment.company == self.actor.company)
                    .order_by(Payment.id.desc())
                    .limit(100)
                )
            ]
