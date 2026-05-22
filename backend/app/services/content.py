from pathlib import Path
from urllib.parse import urljoin

import bleach
from bs4 import BeautifulSoup
from bleach.css_sanitizer import CSSSanitizer
from markdown_it import MarkdownIt
from premailer import transform

ALLOWED_TAGS = [
    "a",
    "blockquote",
    "br",
    "code",
    "div",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "hr",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "section",
    "span",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
]

ALLOWED_ATTRIBUTES = {
    "*": ["class", "style"],
    "a": ["href", "title", "target"],
    "img": ["src", "alt", "title"],
}

ALLOWED_CSS = [
    "background-color",
    "border",
    "border-bottom",
    "border-left",
    "border-radius",
    "color",
    "display",
    "font-size",
    "font-weight",
    "line-height",
    "margin",
    "margin-bottom",
    "margin-top",
    "max-width",
    "padding",
    "padding-left",
    "text-align",
    "word-break",
]


def markdown_to_html(markdown: str) -> str:
    md = MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": True})
    try:
        md.enable("table")
    except ValueError:
        pass
    rendered = md.render(markdown)
    return sanitize_html(rendered)


def apply_wechat_style(html: str) -> str:
    wrapped = f"""
    <section class="wx-article">
      {html}
    </section>
    <style>
      .wx-article {{ color: #1f2933; font-size: 16px; line-height: 1.85; }}
      .wx-article h1 {{ font-size: 24px; line-height: 1.35; margin: 0 0 18px; }}
      .wx-article h2 {{ font-size: 20px; margin: 28px 0 12px; border-left: 4px solid #1f7a5a; padding-left: 10px; }}
      .wx-article h3 {{ font-size: 18px; margin: 24px 0 10px; }}
      .wx-article p {{ margin: 0 0 16px; }}
      .wx-article blockquote {{ margin: 18px 0; padding: 10px 14px; background-color: #f3f7f5; border-left: 4px solid #8db7a3; }}
      .wx-article code {{ background-color: #f3f4f6; padding: 2px 4px; border-radius: 4px; }}
      .wx-article pre {{ background-color: #f3f4f6; padding: 12px; border-radius: 6px; word-break: break-word; }}
      .wx-article img {{ max-width: 100%; display: block; margin: 18px auto; }}
      .wx-article table {{ width: 100%; border: 1px solid #d7dde4; border-radius: 6px; }}
      .wx-article th, .wx-article td {{ border-bottom: 1px solid #d7dde4; padding: 8px; }}
    </style>
    """
    return sanitize_html(transform(wrapped, remove_classes=False))


def sanitize_html(html: str) -> str:
    css_sanitizer = CSSSanitizer(allowed_css_properties=ALLOWED_CSS)
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=["http", "https", "data"],
        css_sanitizer=css_sanitizer,
        strip=True,
    )


def extract_image_sources(html: str, base_dir: Path | None = None) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    sources: list[str] = []
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        if base_dir and not src.startswith(("http://", "https://", "data:")):
            sources.append(str((base_dir / src).resolve()))
        else:
            sources.append(src)
    return sources


def replace_image_sources(html: str, replacements: dict[str, str], base_url: str | None = None) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        normalized = urljoin(base_url, src) if base_url else src
        if src in replacements:
            img["src"] = replacements[src]
        elif normalized in replacements:
            img["src"] = replacements[normalized]
    return sanitize_html(str(soup))
