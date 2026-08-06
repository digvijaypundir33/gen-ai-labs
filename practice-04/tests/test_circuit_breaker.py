import time
from unittest.mock import patch

from conftest import import_lambda

kb_lookup = import_lambda("ticket-kb-lookup")


def test_circuit_closed_when_no_item_exists():
    with patch.object(kb_lookup, "circuit_breaker_table") as mock_table:
        mock_table.get_item.return_value = {}
        assert kb_lookup._circuit_is_open("bedrock-kb-retrieve") is False


def test_circuit_closed_when_circuit_open_flag_false():
    with patch.object(kb_lookup, "circuit_breaker_table") as mock_table:
        mock_table.get_item.return_value = {"Item": {"circuit_open": False}}
        assert kb_lookup._circuit_is_open("bedrock-kb-retrieve") is False


def test_circuit_open_within_cooldown():
    with patch.object(kb_lookup, "circuit_breaker_table") as mock_table:
        mock_table.get_item.return_value = {
            "Item": {"circuit_open": True, "last_failure": int(time.time())}
        }
        assert kb_lookup._circuit_is_open("bedrock-kb-retrieve") is True


def test_circuit_half_open_after_cooldown_expires():
    with patch.object(kb_lookup, "circuit_breaker_table") as mock_table:
        stale_failure = int(time.time()) - kb_lookup.COOLDOWN_SECONDS - 5
        mock_table.get_item.return_value = {
            "Item": {"circuit_open": True, "last_failure": stale_failure}
        }
        assert kb_lookup._circuit_is_open("bedrock-kb-retrieve") is False


def test_record_failure_opens_circuit_at_threshold():
    with patch.object(kb_lookup, "circuit_breaker_table") as mock_table:
        mock_table.update_item.return_value = {"Attributes": {"failure_count": kb_lookup.FAILURE_THRESHOLD}}
        kb_lookup._record_failure("bedrock-kb-retrieve")
        calls = mock_table.update_item.call_args_list
        assert any("circuit_open" in str(c) for c in calls)


def test_record_failure_below_threshold_does_not_open_circuit():
    with patch.object(kb_lookup, "circuit_breaker_table") as mock_table:
        mock_table.update_item.return_value = {"Attributes": {"failure_count": 1}}
        kb_lookup._record_failure("bedrock-kb-retrieve")
        assert mock_table.update_item.call_count == 1


def test_retrieve_chunks_returns_empty_when_circuit_open():
    with patch.object(kb_lookup, "circuit_breaker_table") as mock_table, \
         patch.object(kb_lookup, "bedrock_agent_runtime") as mock_bedrock:
        mock_table.get_item.return_value = {
            "Item": {"circuit_open": True, "last_failure": int(time.time())}
        }
        result = kb_lookup.retrieve_chunks("some query")
        assert result == []
        mock_bedrock.retrieve.assert_not_called()


def test_retrieve_chunks_returns_text_on_success():
    with patch.object(kb_lookup, "circuit_breaker_table") as mock_table, \
         patch.object(kb_lookup, "bedrock_agent_runtime") as mock_bedrock:
        mock_table.get_item.return_value = {}
        mock_bedrock.retrieve.return_value = {
            "retrievalResults": [{"content": {"text": "chunk one"}}, {"content": {"text": "chunk two"}}]
        }
        result = kb_lookup.retrieve_chunks("some query")
        assert result == ["chunk one", "chunk two"]
