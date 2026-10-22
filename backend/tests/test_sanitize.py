from app.sanitize import sanitize_content


def test_ampersand_and_text_preserved():
    # Plain text (incl. & < >) must survive verbatim — not become &amp; / &lt;.
    assert sanitize_content("Tom & Jerry") == "Tom & Jerry"
    assert sanitize_content("Deal: buy & sell 50% off") == "Deal: buy & sell 50% off"
    assert sanitize_content("A < B and C > D") == "A < B and C > D"


def test_html_tags_stripped():
    assert sanitize_content("<b>bold</b> & <i>italic</i>") == "bold & italic"
    assert "<script" not in sanitize_content("<script>alert(1)</script>hello")


def test_dangerous_schemes_blocked():
    assert "javascript:" not in sanitize_content("[x](javascript:alert(1))")
    # entity-encoded scheme must also be neutralized (decoded before the check)
    assert "javascript:" not in sanitize_content("click javascript&colon;alert(1)")


def test_none_passthrough():
    assert sanitize_content(None) is None
