import pytest

from app.password_policy import MIN_LENGTH, validate_password


def test_strong_password_has_no_errors():
    assert validate_password("Tr0ub4dor&Horse!", username="amr", email="amr@example.com") == []


@pytest.mark.parametrize("password, expected", [
    ("Sh0rt!a", f"at least {MIN_LENGTH}"),
    ("alllowercase1!", "uppercase"),
    ("ALLUPPERCASE1!", "lowercase"),
    ("NoDigitsHere!!", "number"),
    ("NoSymbol12345A", "symbol"),
    ("Password123!", "too common"),
    ("Aa1!" + "x" * 80, "too long"),
])
def test_weak_passwords_are_rejected_with_a_reason(password, expected):
    errors = validate_password(password)
    assert any(expected in error for error in errors), errors


def test_password_must_not_contain_username():
    errors = validate_password("Zq9!Buyer!Rocks", username="buyer")
    assert any("username or email" in e for e in errors)


def test_password_must_not_contain_email_name():
    errors = validate_password("Jordan#2026Abc", email="jordan@example.com")
    assert any("username or email" in e for e in errors)


def test_very_short_username_is_ignored():
    errors = validate_password("Zab9!Strong#Pwd", username="ab")
    assert not any("username or email" in e for e in errors)