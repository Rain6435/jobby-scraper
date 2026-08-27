from pathlib import Path
from typing import Callable
from unittest.mock import MagicMock, patch

import pytest
import responses

import scraper.summarize as summarize_module
from scraper.summarize import summarize_company, summarize_role

OLLAMA_URL = "https://ollama.com/api/chat"


@pytest.fixture(autouse=True)
def _isolated_ollama_key_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Every test in this file gets its own rotation-state file — never the
    real shared data/ollama_key_rotation.json, which would make tests
    non-hermetic (state leaking between test runs, or interfering with a
    concurrent real scraper run)."""
    monkeypatch.setenv("OLLAMA_KEY_ROTATION_STATE_FILE", str(tmp_path / "ollama_state.json"))


def setup_function(_fn: Callable[..., None]) -> None:
    # Each test gets a clean lazily-constructed client cache.
    summarize_module._anthropic_client = None


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_API_ENDPOINT", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)


def _text_response(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


def test_summarize_role_no_provider_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    with patch("anthropic.Anthropic") as mock_anthropic:
        result = summarize_role("Engineer", "Acme", "Do engineering things.")
        assert result == ""
        mock_anthropic.assert_not_called()


def test_summarize_role_success_with_auth_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test-token")
    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _text_response("Builds APIs.")
        mock_anthropic.return_value = mock_client

        result = summarize_role("Engineer", "Acme", "Do engineering things.")

        assert result == "Builds APIs."
        mock_anthropic.assert_called_once_with(auth_token="test-token")


def test_get_client_prefers_api_key_over_auth_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test-token")
    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _text_response("Builds APIs.")
        mock_anthropic.return_value = mock_client

        summarize_role("Engineer", "Acme", "Do engineering things.")

        mock_anthropic.assert_called_once_with(api_key="sk-test")


def test_summarize_role_empty_description_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    with patch("anthropic.Anthropic") as mock_anthropic:
        result = summarize_role("Engineer", "Acme", "")
        assert result == ""
        mock_anthropic.assert_not_called()


def test_summarize_role_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _text_response("  Builds APIs.  ")
        mock_anthropic.return_value = mock_client

        result = summarize_role("Engineer", "Acme", "Do engineering things.")

        assert result == "Builds APIs."
        mock_client.messages.create.assert_called_once()


def test_summarize_company_no_provider_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    with patch("anthropic.Anthropic") as mock_anthropic:
        result = summarize_company("Acme")
        assert result == ""
        mock_anthropic.assert_not_called()


def test_summarize_company_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _text_response("Makes widgets.")
        mock_anthropic.return_value = mock_client

        result = summarize_company("Acme", "https://acme.example/careers")

        assert result == "Makes widgets."


def test_client_is_cached_across_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _text_response("x")
        mock_anthropic.return_value = mock_client

        summarize_role("A", "B", "desc")
        summarize_role("C", "D", "desc2")

        mock_anthropic.assert_called_once()


# --- Ollama fallback ---

def test_falls_back_to_ollama_when_no_anthropic_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test-key")
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.POST, OLLAMA_URL,
            json={"message": {"content": "Builds APIs via Ollama."}}, status=200,
        )
        result = summarize_role("Engineer", "Acme", "Do engineering things.")

        assert result == "Builds APIs via Ollama."
        assert len(rsps.calls) == 1
        assert rsps.calls[0].request.headers["Authorization"] == "Bearer ollama-test-key"


def test_falls_back_to_ollama_when_anthropic_call_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test-key")
    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("401 unauthorized")
        mock_anthropic.return_value = mock_client

        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST, OLLAMA_URL,
                json={"message": {"content": "Builds APIs via Ollama."}}, status=200,
            )
            result = summarize_role("Engineer", "Acme", "Do engineering things.")

            assert result == "Builds APIs via Ollama."
            assert len(rsps.calls) == 1


def test_anthropic_success_never_calls_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test-key")
    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _text_response("Builds APIs.")
        mock_anthropic.return_value = mock_client

        with responses.RequestsMock() as rsps:
            result = summarize_role("Engineer", "Acme", "Do engineering things.")

            assert result == "Builds APIs."
            assert len(rsps.calls) == 0


def test_ollama_retries_once_on_429_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test-key")
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.POST, OLLAMA_URL,
            json={"error": "too many concurrent requests"}, status=429,
            headers={"Retry-After": "0"},
        )
        rsps.add(
            responses.POST, OLLAMA_URL,
            json={"message": {"content": "Builds APIs."}}, status=200,
        )
        result = summarize_role("Engineer", "Acme", "Do engineering things.")

        assert result == "Builds APIs."
        assert len(rsps.calls) == 2


def test_ollama_api_error_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test-key")
    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, OLLAMA_URL, json={"error": "boom"}, status=500)
        result = summarize_role("Engineer", "Acme", "Do engineering things.")

        assert result == ""


def test_ollama_no_key_returns_empty_without_request(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    with responses.RequestsMock() as rsps:
        result = summarize_role("Engineer", "Acme", "Do engineering things.")

        assert result == ""
        assert len(rsps.calls) == 0


def test_summarize_company_falls_back_to_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test-key")
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.POST, OLLAMA_URL,
            json={"message": {"content": "Makes widgets."}}, status=200,
        )
        result = summarize_company("Acme")

        assert result == "Makes widgets."


# --- LLM_PROVIDER pinning ---

def test_llm_provider_anthropic_never_calls_ollama_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test-key")
    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("401 unauthorized")
        mock_anthropic.return_value = mock_client

        with responses.RequestsMock() as rsps:
            result = summarize_role("Engineer", "Acme", "Do engineering things.")

            assert result == ""
            assert len(rsps.calls) == 0


def test_llm_provider_ollama_never_calls_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test-key")
    with patch("anthropic.Anthropic") as mock_anthropic:
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST, OLLAMA_URL,
                json={"message": {"content": "Builds APIs via Ollama."}}, status=200,
            )
            result = summarize_role("Engineer", "Acme", "Do engineering things.")

            assert result == "Builds APIs via Ollama."
            mock_anthropic.assert_not_called()


def test_llm_provider_ollama_returns_empty_without_key_even_with_anthropic_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    with patch("anthropic.Anthropic") as mock_anthropic:
        with responses.RequestsMock() as rsps:
            result = summarize_role("Engineer", "Acme", "Do engineering things.")

            assert result == ""
            assert len(rsps.calls) == 0
            mock_anthropic.assert_not_called()


def test_llm_provider_unrecognized_value_falls_back_to_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "bogus")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _text_response("Builds APIs.")
        mock_anthropic.return_value = mock_client

        result = summarize_role("Engineer", "Acme", "Do engineering things.")

        assert result == "Builds APIs."


def test_llm_provider_auto_is_same_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test-key")
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.POST, OLLAMA_URL,
            json={"message": {"content": "Builds APIs via Ollama."}}, status=200,
        )
        result = summarize_role("Engineer", "Acme", "Do engineering things.")

        assert result == "Builds APIs via Ollama."


# --- Ollama key rotation ---

HOURLY_LIMIT_BODY = {"error": "you've reached your hourly usage limit, please wait or upgrade to continue"}


def test_rotates_to_next_key_on_hourly_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("OLLAMA_API_KEY", "key-one,key-two")
    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, OLLAMA_URL, json=HOURLY_LIMIT_BODY, status=429)
        rsps.add(
            responses.POST, OLLAMA_URL,
            json={"message": {"content": "Builds APIs."}}, status=200,
        )
        result = summarize_role("Engineer", "Acme", "Do engineering things.")

        assert result == "Builds APIs."
        assert len(rsps.calls) == 2
        first_auth = rsps.calls[0].request.headers["Authorization"]
        second_auth = rsps.calls[1].request.headers["Authorization"]
        assert first_auth == "Bearer key-one"
        assert second_auth == "Bearer key-two"


def test_rotation_does_not_wait_between_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unlike the transient-429 retry (which sleeps), rotating to the next
    key on an hourly-limit 429 should be immediate."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("OLLAMA_API_KEY", "key-one,key-two")
    sleep_calls: list[float] = []

    def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr("scraper.summarize.time.sleep", _fake_sleep)
    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, OLLAMA_URL, json=HOURLY_LIMIT_BODY, status=429)
        rsps.add(
            responses.POST, OLLAMA_URL,
            json={"message": {"content": "Builds APIs."}}, status=200,
        )
        summarize_role("Engineer", "Acme", "Do engineering things.")

        assert sleep_calls == []


def test_all_keys_exhausted_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("OLLAMA_API_KEY", "key-one,key-two")
    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, OLLAMA_URL, json=HOURLY_LIMIT_BODY, status=429)
        rsps.add(responses.POST, OLLAMA_URL, json=HOURLY_LIMIT_BODY, status=429)
        result = summarize_role("Engineer", "Acme", "Do engineering things.")

        assert result == ""
        assert len(rsps.calls) == 2


def test_already_exhausted_key_skipped_without_a_request(monkeypatch: pytest.MonkeyPatch) -> None:
    from scraper import ollama_keys

    _clear_env(monkeypatch)
    monkeypatch.setenv("OLLAMA_API_KEY", "key-one,key-two")
    ollama_keys.mark_exhausted("key-one")

    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.POST, OLLAMA_URL,
            json={"message": {"content": "Builds APIs."}}, status=200,
        )
        result = summarize_role("Engineer", "Acme", "Do engineering things.")

        assert result == "Builds APIs."
        assert len(rsps.calls) == 1
        assert rsps.calls[0].request.headers["Authorization"] == "Bearer key-two"


def test_no_request_at_all_when_every_key_already_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    from scraper import ollama_keys

    _clear_env(monkeypatch)
    monkeypatch.setenv("OLLAMA_API_KEY", "key-one,key-two")
    ollama_keys.mark_exhausted("key-one")
    ollama_keys.mark_exhausted("key-two")

    with responses.RequestsMock() as rsps:
        result = summarize_role("Engineer", "Acme", "Do engineering things.")

        assert result == ""
        assert len(rsps.calls) == 0


def test_single_key_hourly_limit_behaves_like_before(monkeypatch: pytest.MonkeyPatch) -> None:
    """No comma in OLLAMA_API_KEY — one key, exhausts, nothing left to
    rotate to, same observable result as the pre-rotation single-key path."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("OLLAMA_API_KEY", "only-key")
    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, OLLAMA_URL, json=HOURLY_LIMIT_BODY, status=429)
        result = summarize_role("Engineer", "Acme", "Do engineering things.")

        assert result == ""
        assert len(rsps.calls) == 1
