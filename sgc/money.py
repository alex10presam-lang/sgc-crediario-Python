from calendar import monthrange
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sgc.security import DomainError


def cents(value):
    try:
        amount = Decimal(str(value).replace(",", "."))
        if not amount.is_finite() or amount < 0 or amount > Decimal("999999999.99"):
            raise ValueError
        return int((amount * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError):
        raise DomainError("Informe um valor monetário não negativo e finito.") from None


def brl(value):
    formatted = f"{value / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return "R$ " + formatted


def split_cents(total, count):
    if not 1 <= count <= 48 or total < count:
        raise DomainError("Use de 1 a 48 parcelas, com pelo menos um centavo por parcela.")
    base, remainder = divmod(total, count)
    return [base + (index < remainder) for index in range(count)]


def add_months(original, months):
    year, month = divmod(original.year * 12 + original.month - 1 + months, 12)
    month += 1
    return date(year, month, min(original.day, monthrange(year, month)[1]))
