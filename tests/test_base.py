from requests.adapters import HTTPAdapter

from scraper.boards.base import make_session, slugify


def test_slugify_normalizes_company_name():
    assert slugify("TD Bank") == "td-bank"


def test_make_session_configures_retry_with_backoff():
    session = make_session()
    adapter = session.get_adapter("https://example.com")
    assert isinstance(adapter, HTTPAdapter)
    retry = adapter.max_retries

    assert retry.total == 4
    assert set(retry.status_forcelist) == {429, 500, 502, 503, 504}
    assert retry.allowed_methods is not None
    assert "GET" in retry.allowed_methods
    assert "POST" in retry.allowed_methods
    assert retry.respect_retry_after_header is True


def test_make_session_mounts_retrying_adapter_for_http_and_https():
    session = make_session()
    http_adapter = session.get_adapter("http://example.com")
    https_adapter = session.get_adapter("https://example.com")
    assert isinstance(http_adapter, HTTPAdapter)
    assert isinstance(https_adapter, HTTPAdapter)
    assert http_adapter.max_retries.total == 4
    assert https_adapter.max_retries.total == 4
