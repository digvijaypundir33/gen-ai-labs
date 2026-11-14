from decimal import Decimal

from conftest import import_lambda

get_ticket = import_lambda("get-ticket")


def test_decimal_safe_converts_integer_decimal_to_int():
    assert get_ticket._decimal_safe(Decimal("5")) == 5
    assert isinstance(get_ticket._decimal_safe(Decimal("5")), int)


def test_decimal_safe_converts_fractional_decimal_to_float():
    assert get_ticket._decimal_safe(Decimal("5.5")) == 5.5
    assert isinstance(get_ticket._decimal_safe(Decimal("5.5")), float)


def test_decimal_safe_recurses_into_nested_dict():
    result = get_ticket._decimal_safe({"a": Decimal("1"), "b": {"c": Decimal("2.5")}})
    assert result == {"a": 1, "b": {"c": 2.5}}


def test_decimal_safe_recurses_into_list():
    result = get_ticket._decimal_safe([Decimal("1"), Decimal("2")])
    assert result == [1, 2]


def test_missing_ticket_id_returns_400():
    result = get_ticket.lambda_handler({"pathParameters": {}}, None)
    assert result["statusCode"] == 400


def test_ticket_not_found_returns_404():
    from unittest.mock import patch

    with patch.object(get_ticket, "tickets_table") as mock_table:
        mock_table.get_item.return_value = {}
        result = get_ticket.lambda_handler({"pathParameters": {"ticketId": "nonexistent"}}, None)
        assert result["statusCode"] == 404
