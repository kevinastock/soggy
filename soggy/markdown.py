from __future__ import annotations

from pathlib import PurePosixPath
from typing import Match, Sequence, cast
from urllib.parse import unquote, urlparse

import logging

from mistune import HTMLRenderer, Markdown, create_markdown
from mistune.core import InlineState
from mistune.inline_parser import InlineParser
from mistune.util import escape_url

from soggy.vault import VaultFile, VaultMarkdown
from soggy.templates import TemplateRenderer

_WIKILINK_PATTERN = r"\[\[(?P<page>[^|\]]+)(?:\|(?P<display>[^\]]+))?\]\]"
_LOGGER = logging.getLogger(__name__)
_INLINE_COMMENT_PATTERN = r"%%.+?%%"
_BLOCK_COMMENT_PATTERN = r"^ {0,3}%%[ \t]*\n[\s\S]+?\n%%[ \t]*$"


class SoggyRenderer(HTMLRenderer):
    def __init__(
        self,
        files: Sequence[VaultFile],
    ) -> None:
        super().__init__()
        self._files = files

    def _match_files(self, path: str) -> list[VaultFile]:
        return [file for file in self._files if file.matches_url(path)]

    def _resolve_url(self, url: str) -> str:
        parsed = urlparse(url)

        if parsed.scheme or parsed.netloc:
            return url

        if parsed.params or parsed.query:
            raise ValueError(f"Query or params are not allowed in internal urls: {url}")

        decoded_path = unquote(parsed.path)
        trimmed = decoded_path.lstrip("/")
        if not trimmed:
            raise ValueError("Empty link url is not allowed.")

        matches: dict[str, VaultFile] = {}
        for file in self._match_files(trimmed):
            matches[file.path.as_posix()] = file

        if not trimmed.lower().endswith(".md"):
            for file in self._match_files(f"{trimmed}.md"):
                matches[file.path.as_posix()] = file

        if not matches:
            raise ValueError(f"No vault file matches link url: {decoded_path}")
        if len(matches) > 1:
            details = ", ".join(file.path.as_posix() for file in matches.values())
            raise ValueError(f"Ambiguous link url {decoded_path!r}; matches: {details}")

        selected = next(iter(matches.values()))
        selected.target()
        _LOGGER.debug(
            "Resolved internal link %s -> %s",
            decoded_path,
            selected.output_path.as_posix(),
        )
        resolved_path = selected.output_path.as_posix()
        if not resolved_path.startswith("/"):
            resolved_path = f"/{resolved_path}"
        return escape_url(resolved_path)

    def link(self, text: str, url: str, title: str | None = None) -> str:
        resolved = self._resolve_url(url)
        return super().link(text, resolved, title)

    def image(self, text: str, url: str, title: str | None = None) -> str:
        resolved = self._resolve_url(url)
        return super().image(text, resolved, title)


def parse_wikilink(inline: InlineParser, m: Match[str], state: InlineState) -> int:
    page_title = m.group("page").strip()
    display = m.group("display")
    text = display.strip() if display is not None else page_title

    url = page_title
    if PurePosixPath(url).suffix.lower() != ".md":
        url = f"{url}.md"

    state.append_token(
        {
            "type": "link",
            "children": [{"type": "text", "raw": text}],
            "attrs": {"url": escape_url(url)},
        }
    )
    return m.end()


def wikilink_plugin(md: Markdown) -> None:
    md.inline.register("wikilink", _WIKILINK_PATTERN, parse_wikilink, before="link")


def parse_inline_comment(
    inline: InlineParser, m: Match[str], state: InlineState
) -> int:
    return m.end()


def parse_block_comment(block: object, m: Match[str], state: object) -> int:
    return m.end()


def comment_plugin(md: Markdown) -> None:
    md.block.register(
        "comment",
        _BLOCK_COMMENT_PATTERN,
        parse_block_comment,
        before="paragraph",
    )
    md.inline.register(
        "comment",
        _INLINE_COMMENT_PATTERN,
        parse_inline_comment,
        before="link",
    )


def render_markdown(files: Sequence[VaultFile], renderer: TemplateRenderer) -> None:
    for file in files:
        if not isinstance(file, VaultMarkdown) or not file.publish:
            continue
        _LOGGER.info("Rendering markdown: %s", file.path.as_posix())
        md_renderer = SoggyRenderer(files)
        markdown = create_markdown(
            renderer=md_renderer,
            plugins=["mark", "task_lists", "def_list", comment_plugin, wikilink_plugin],
        )
        body_html = cast(str, markdown(file.content))
        file.set_html(
            renderer.render_page(
                file.title,
                body_html,
                file.date_created,
                file.date_updated,
                show_created_date="hide-created-date" not in file.tags,
            )
        )
