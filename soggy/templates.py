from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

from jinja2 import Environment, FileSystemLoader, select_autoescape


@dataclass(frozen=True)
class IndexEntry:
    title: str
    link: str


class TemplateRenderer:
    def __init__(self, site_title: str) -> None:
        self._site_title = site_title
        templates_dir = Path(__file__).resolve().parent / "templates"
        self._env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def _format_human_date(self, value: date) -> str:
        return f"{value:%B} {value:%Y}"

    def render_page(
        self,
        title: str,
        body_html: str,
        date_created: date,
        date_updated: date,
        show_created_date: bool = True,
    ) -> str:
        template = self._env.get_template("page.html")
        return template.render(
            page_title=title,
            site_title=self._site_title,
            created_iso=date_created.isoformat(),
            created_human=self._format_human_date(date_created),
            updated_iso=date_updated.isoformat(),
            updated_human=self._format_human_date(date_updated),
            show_created_date=show_created_date,
            body=body_html,
        )

    def render_index(self, entries: Iterable[IndexEntry]) -> str:
        template = self._env.get_template("index.html")
        return template.render(
            page_title="Home",
            site_title=self._site_title,
            posts=[
                {
                    "title": entry.title,
                    "link": entry.link,
                }
                for entry in entries
            ],
        )
