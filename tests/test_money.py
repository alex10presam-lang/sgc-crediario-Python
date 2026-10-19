from datetime import date
import pytest
from sgc.money import cents, split_cents, add_months, brl
from sgc.security import DomainError


@pytest.mark.parametrize("value", ["-1", "NaN", "inf", "-inf", "texto", "1000000000"])
def test_invalid_money(value):
    with pytest.raises(DomainError):
        cents(value)


def test_decimal_rounding_and_split():
    assert cents("1,005") == 101
    assert cents("10.10") == 1010
    assert split_cents(10001, 3) == [3334, 3334, 3333]
    assert brl(123456) == "R$ 1.234,56"


@pytest.mark.parametrize("count", [0, 49])
def test_invalid_count(count):
    with pytest.raises(DomainError):
        split_cents(100, count)


def test_calendar_months():
    first = date(2028, 1, 31)
    assert add_months(first, 1) == date(2028, 2, 29)
    assert add_months(first, 2) == date(2028, 3, 31)
