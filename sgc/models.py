from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("company", "username"),)
    id = Column(Integer, primary_key=True)
    company = Column(String, nullable=False, index=True)
    username = Column(String, nullable=False)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    auth_version = Column(Integer, nullable=False, default=1)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    key = Column(String, primary_key=True)
    failures = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime, nullable=True)


class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True)
    company = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False, default="")


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    company = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    price = Column(Integer, nullable=False)
    stock = Column(Integer, nullable=False, default=0)


class Sale(Base):
    __tablename__ = "sales"
    __table_args__ = (UniqueConstraint("company", "request_key"),)
    id = Column(Integer, primary_key=True)
    company = Column(String, nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    description = Column(String, nullable=False)
    total = Column(Integer, nullable=False)
    principal = Column(Integer, nullable=False)
    interest = Column(Integer, nullable=False, default=0)
    request_key = Column(String, nullable=False)
    request_digest = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    cancelled = Column(Boolean, nullable=False, default=False)


class SaleItem(Base):
    __tablename__ = "sale_items"
    id = Column(Integer, primary_key=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    description = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Integer, nullable=False)


class Installment(Base):
    __tablename__ = "installments"
    __table_args__ = (UniqueConstraint("sale_id", "number"),)
    id = Column(Integer, primary_key=True)
    company = Column(String, nullable=False, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    number = Column(Integer, nullable=False)
    amount = Column(Integer, nullable=False)
    paid = Column(Integer, nullable=False, default=0)
    due_date = Column(Date, nullable=False)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("company", "request_key"),)
    id = Column(Integer, primary_key=True)
    company = Column(String, nullable=False, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Integer, nullable=False)
    start_installment_id = Column(Integer, ForeignKey("installments.id"), nullable=True)
    request_key = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    reversed = Column(Boolean, nullable=False, default=False)
    is_entry = Column(Boolean, nullable=False, default=False)


class Allocation(Base):
    __tablename__ = "allocations"
    id = Column(Integer, primary_key=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False)
    installment_id = Column(Integer, ForeignKey("installments.id"), nullable=False)
    amount = Column(Integer, nullable=False)


class Audit(Base):
    __tablename__ = "audit"
    id = Column(Integer, primary_key=True)
    company = Column(String, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String, nullable=False)
    details = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
