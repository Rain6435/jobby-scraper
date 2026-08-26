from scraper.text import html_to_text


def test_empty_input():
    assert html_to_text("") == ""


def test_strips_tags():
    assert html_to_text("<p>Hello <strong>world</strong></p>") == "Hello world"


def test_unescapes_entities():
    assert html_to_text("<p>Tom &amp; Jerry &gt; cats</p>") == "Tom & Jerry > cats"


def test_block_tags_become_newlines():
    html = "<ul><li>First</li><li>Second</li></ul><p>Para</p>"
    assert html_to_text(html) == "First\nSecond\nPara"


def test_br_becomes_newline():
    assert html_to_text("Line one<br>Line two<br/>Line three") == "Line one\nLine two\nLine three"


def test_collapses_blank_lines():
    html = "<p>First</p><p></p><p></p><p>Second</p>"
    assert html_to_text(html) == "First\n\nSecond"


def test_truncates_at_word_boundary_with_ellipsis():
    text = "word " * 500  # far longer than max_chars
    result = html_to_text(f"<p>{text}</p>", max_chars=20)
    assert len(result) <= 21  # 20 chars + ellipsis char
    assert result.endswith("…")
    assert " " not in result[-2:-1]  # didn't cut mid-word before the ellipsis


def test_no_truncation_when_under_limit():
    result = html_to_text("<p>Short text</p>", max_chars=1500)
    assert result == "Short text"


def test_does_not_truncate_by_default():
    """max_chars defaults to None. It used to default to 1500, which silently
    capped essentially every job description — discarding exactly the
    requirements text downstream consumers parse for skills."""
    body = "word " * 2000
    result = html_to_text(f"<p>{body}</p>")
    assert len(result) > 1500
    assert not result.endswith("…")
    assert result == body.strip()
