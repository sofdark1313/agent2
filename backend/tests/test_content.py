from app.services.content import apply_wechat_style, extract_image_sources, markdown_to_html


def test_markdown_to_html_strips_script() -> None:
    html = markdown_to_html("# Hi\n\n<script>alert(1)</script>\n\n![x](./a.png)")
    assert "<script>" not in html
    assert "<h1>Hi</h1>" in html
    assert "./a.png" in html


def test_apply_wechat_style_keeps_safe_html() -> None:
    html = apply_wechat_style("<h2>Title</h2><p>Hello</p>")
    assert "Title" in html
    assert "line-height" in html


def test_extract_image_sources() -> None:
    sources = extract_image_sources('<p><img src="https://example.com/a.png"></p>')
    assert sources == ["https://example.com/a.png"]
