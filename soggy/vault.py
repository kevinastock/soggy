from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import difflib
from datetime import date, datetime
from pathlib import Path, PurePosixPath
import logging
import re
import shutil

import yaml

from soggy.minify import minify_html_text, minify_text_for_path, should_minify_path

_UNSAFE_URL_CHARS = re.compile(r"[^A-Za-z0-9/_\-.]")
_LOGGER = logging.getLogger(__name__)


def _parse_front_matter_date(value: object, field_name: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"Invalid {field_name}: {value}") from exc
    raise ValueError(f"Missing or invalid {field_name}: {value!r}")


def _sanitize_output_path(path: Path | PurePosixPath) -> PurePosixPath:
    safe = path.as_posix().replace(" ", "_")
    return PurePosixPath(_UNSAFE_URL_CHARS.sub("_", safe))


def update_front_matter(source_path: Path, meta: dict[str, object], body: str) -> None:
    rendered = yaml.safe_dump(meta, sort_keys=True).strip()
    updated_content = f"---\n{rendered}\n---{body}"
    original_content = source_path.read_text(encoding="utf-8")

    if not original_content.startswith("---"):
        raise ValueError("Missing front matter.")

    try:
        _, front, _ = original_content.split("---", 2)
    except ValueError as exc:
        raise ValueError("Missing closing front matter delimiter.") from exc

    original_meta = yaml.safe_load(front) or {}
    if not isinstance(original_meta, dict):
        raise ValueError("Invalid front matter.")

    baseline_rendered = yaml.safe_dump(original_meta, sort_keys=True).strip()
    baseline_content = f"---\n{baseline_rendered}\n---{body}"
    baseline_lines = baseline_content.splitlines()
    updated_lines = updated_content.splitlines()
    matcher = difflib.SequenceMatcher(a=baseline_lines, b=updated_lines)
    changes = [op for op in matcher.get_opcodes() if op[0] != "equal"]

    if not (
        len(changes) == 1
        and changes[0][0] == "insert"
        and (changes[0][4] - changes[0][3]) == 1
    ):
        raise ValueError(
            "Updating front matter must only add one line to the front matter."
        )

    expected_line = f"permalink: {meta.get('permalink')}"
    if updated_lines[changes[0][3]] != expected_line:
        raise ValueError("Updating front matter must only add the permalink line.")

    source_path.write_text(updated_content, encoding="utf-8")


@dataclass
class VaultFile(ABC):
    path: PurePosixPath

    def __post_init__(self) -> None:
        if type(self) is VaultFile:
            raise TypeError("VaultFile cannot be instantiated directly.")

    def matches_url(self, url: str) -> bool:
        if not url:
            return False
        return self.path.as_posix().lower().endswith(url.lower())

    @property
    @abstractmethod
    def output_path(self) -> PurePosixPath:
        raise NotImplementedError

    @abstractmethod
    def target(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def write_out(self, root: Path, output_dir: Path) -> None:
        raise NotImplementedError


@dataclass(init=False)
class VaultMarkdown(VaultFile):
    content: str
    publish: bool
    update_source: bool
    date_created: date
    date_updated: date
    tags: set[str]
    title: str
    html: str | None
    _output_path: PurePosixPath
    _meta: dict[str, object]
    _missing_permalink: bool
    _permalink_value: str | None

    def __init__(self, path: PurePosixPath, root: Path) -> None:
        self.path = path
        output_path = _sanitize_output_path(path.with_suffix(""))
        source_path = root / path
        content = source_path.read_text(encoding="utf-8")

        if not content.startswith("---"):
            raise ValueError("Missing front matter.")

        try:
            _, front, self.content = content.split("---", 2)
        except ValueError as exc:
            raise ValueError("Missing closing front matter delimiter.") from exc

        meta = yaml.safe_load(front) or {}
        if not isinstance(meta, dict):
            raise ValueError("Invalid front matter.")

        _LOGGER.debug("Front matter meta for %s: %s", path.as_posix(), meta)

        if "aliases" in meta:
            raise ValueError(
                "Front matter 'aliases' is not supported yet; remove it to continue."
            )

        self.publish = meta.get("publish") is True
        self.title = path.stem
        self.tags = self._parse_tags(meta.get("tags"))

        self._meta = meta
        self._missing_permalink = False
        self._permalink_value = None

        if permalink := meta.get("permalink"):
            output_path = PurePosixPath(permalink)
            update_source = False
        else:
            update_source = self.publish
            if self.publish:
                self._missing_permalink = True
                self._permalink_value = output_path.as_posix().lstrip("/")

        self.update_source = update_source
        self.date_created = _parse_front_matter_date(
            meta.get("date created"), "date created"
        )
        self.date_updated = _parse_front_matter_date(
            meta.get("date modified"), "date modified"
        )
        self.html = None
        self._output_path = output_path

    def update_permalink_source(self, root: Path) -> None:
        if not self.publish or not self._missing_permalink:
            return
        permalink_value = self._permalink_value or self._output_path.as_posix().lstrip(
            "/"
        )
        self._meta["permalink"] = permalink_value
        update_front_matter(root / self.path, self._meta, self.content)
        _LOGGER.warning(
            "Missing permalink in front matter for %s; set to %s",
            self.path.as_posix(),
            permalink_value,
        )

    @staticmethod
    def _parse_tags(value: object) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, str):
            return {value}
        if isinstance(value, list):
            tags = set()
            for item in value:
                if not isinstance(item, str):
                    raise ValueError(f"Invalid tag entry: {item!r}")
                tags.add(item)
            return tags
        raise ValueError(f"Invalid tags: {value!r}")

    @property
    def output_path(self) -> PurePosixPath:
        if not self.publish:
            raise ValueError("Unpublished markdown does not have an output path.")
        return self._output_path

    def set_html(self, html: str) -> None:
        self.html = html

    def target(self) -> None:
        if not self.publish:
            raise ValueError("Unpublished markdown cannot be targeted.")

    def write_out(self, root: Path, output_dir: Path) -> None:
        if not self.publish:
            return
        if self.html is None:
            raise ValueError("Published markdown is missing rendered html.")
        destination = (
            output_dir / self.output_path.as_posix().lstrip("/") / "index.html"
        )
        if destination.exists():
            raise FileExistsError(f"Output file already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(minify_html_text(self.html), encoding="utf-8")
        _LOGGER.info("Wrote page: %s", destination.as_posix())


@dataclass
class VaultOther(VaultFile):
    targeted: bool = False

    @property
    def output_path(self) -> PurePosixPath:
        return self.path

    def target(self) -> None:
        self.targeted = True

    def write_out(self, root: Path, output_dir: Path) -> None:
        if not self.targeted:
            return
        source = root / self.path
        destination = output_dir / self.output_path.as_posix().lstrip("/")
        if destination.exists():
            raise FileExistsError(f"Output file already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if should_minify_path(self.path):
            content = source.read_text(encoding="utf-8")
            destination.write_text(
                minify_text_for_path(self.path, content), encoding="utf-8"
            )
        else:
            shutil.copy2(source, destination)
        _LOGGER.info("Copied asset: %s", destination.as_posix())


def load_vault(directory: Path | str) -> list[VaultFile]:
    root = Path(directory)
    if not root.is_dir():
        raise NotADirectoryError(f"{root} is not a directory")

    _LOGGER.info("Loading vault: %s", root.as_posix())
    files: list[VaultFile] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file():
            continue
        if {".git", ".obsidian"}.intersection(path.parts):
            continue
        rel_path = PurePosixPath(path.relative_to(root).as_posix())
        _LOGGER.info("Processing file: %s", rel_path.as_posix())
        if path.suffix.lower() == ".md":
            files.append(VaultMarkdown(rel_path, root))
        else:
            files.append(VaultOther(rel_path))

    _LOGGER.info("Discovered %d files", len(files))
    return files
