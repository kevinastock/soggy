from __future__ import annotations

import logging
from pathlib import Path, PurePosixPath

import minify_html


_LOGGER = logging.getLogger(__name__)
_MINIFY_SUFFIXES = {".html", ".htm", ".css"}


def should_minify_path(path: Path | PurePosixPath) -> bool:
    return path.suffix.lower() in _MINIFY_SUFFIXES


def minify_html_text(html: str) -> str:
    try:
        return minify_html.minify(html, minify_css=True, minify_js=True)
    except Exception:
        _LOGGER.exception("Failed to minify HTML; leaving output as-is.")
        return html


def minify_css_text(css: str) -> str:
    wrapped = f"<style>{css}</style>"
    try:
        minified = minify_html.minify(
            wrapped,
            minify_css=True,
            keep_closing_tags=True,
            keep_html_and_head_opening_tags=True,
        )
    except Exception:
        _LOGGER.exception("Failed to minify CSS; leaving output as-is.")
        return css

    prefix = "<style>"
    suffix = "</style>"
    if minified.startswith(prefix) and minified.endswith(suffix):
        return minified[len(prefix) : -len(suffix)]

    _LOGGER.warning("CSS minifier returned unexpected wrapper; leaving output as-is.")
    return css


def minify_text_for_path(path: Path | PurePosixPath, content: str) -> str:
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        return minify_html_text(content)
    if suffix == ".css":
        return minify_css_text(content)
    return content
