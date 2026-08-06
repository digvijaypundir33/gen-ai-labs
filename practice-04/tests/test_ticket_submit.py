import json
from unittest.mock import MagicMock, patch

from conftest import import_lambda

ticket_submit = import_lambda("ticket-submit")


def _event(body):
    return {"body": json.dumps(body)}


def test_missing_subject_returns_400():
    result = ticket_submit.lambda_handler(_event({"description": "long enough description"}), None)
    assert result["statusCode"] == 400


def test_short_description_returns_400():
    result = ticket_submit.lambda_handler(_event({"subject": "x", "description": "short"}), None)
    assert result["statusCode"] == 400


def test_invalid_category_and_priority_default():
    with patch.object(ticket_submit, "tickets_table") as mock_table, \
         patch.object(ticket_submit, "stepfunctions") as mock_sf:
        mock_sf.start_sync_execution.return_value = {
            "status": "SUCCEEDED",
            "output": json.dumps({"crm": {"status": "responded"}, "classification": {}, "generation": {}}),
        }
        ticket_submit.lambda_handler(
            _event({"subject": "x", "description": "a valid description here", "category": "nonsense", "priority": "nonsense"}),
            None,
        )
        written_item = mock_table.put_item.call_args.kwargs["Item"]
        assert written_item["category"] == "other"
        assert written_item["priority"] == "medium"


def test_token_limit_exceeded_returns_413():
    with patch.object(ticket_submit, "MAX_TOKENS", 3):
        result = ticket_submit.lambda_handler(
            _event({"subject": "x", "description": "this description has way more than three tokens in it"}),
            None,
        )
        assert result["statusCode"] == 413


def test_successful_submission_returns_workflow_result():
    with patch.object(ticket_submit, "tickets_table") as mock_table, \
         patch.object(ticket_submit, "stepfunctions") as mock_sf:
        mock_sf.start_sync_execution.return_value = {
            "status": "SUCCEEDED",
            "output": json.dumps(
                {
                    "classification": {"category": "technical", "urgency": "high"},
                    "generation": {"response": "Here is help", "modelUsed": "standard"},
                    "crm": {"status": "responded", "crm_update_id": "crm-123"},
                }
            ),
        }
        result = ticket_submit.lambda_handler(
            _event({"subject": "Login broken", "description": "Cannot log in at all today"}),
            None,
        )
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["status"] == "responded"
        assert body["aiResponse"] == "Here is help"
        assert mock_table.put_item.called


def test_workflow_failure_returns_502():
    with patch.object(ticket_submit, "tickets_table") as mock_table, \
         patch.object(ticket_submit, "stepfunctions") as mock_sf:
        mock_sf.start_sync_execution.return_value = {"status": "FAILED", "output": "{}"}
        result = ticket_submit.lambda_handler(
            _event({"subject": "x", "description": "a perfectly valid description"}),
            None,
        )
        assert result["statusCode"] == 502
