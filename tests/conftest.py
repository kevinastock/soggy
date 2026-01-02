from pathlib import Path
from typing import Callable
import yaml

import pytest

_DEFAULT_FRONT_MATTER = object()
_DEFAULT_DATES = {
    "date created": "2024-01-01",
    "date modified": "2024-01-02",
}

WriteMarkdown = Callable[[Path, str, str, object | None], Path]


@pytest.fixture
def write_markdown() -> WriteMarkdown:
    def _write_markdown(
        root: Path,
        relative_path: str,
        body: str,
        front_matter: object | None = _DEFAULT_FRONT_MATTER,
    ) -> Path:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if front_matter is _DEFAULT_FRONT_MATTER:
            front_matter = {"publish": True, **_DEFAULT_DATES}
        if front_matter is None:
            content = body
        else:
            rendered = yaml.safe_dump(front_matter, sort_keys=False).strip()
            content = f"---\n{rendered}\n---\n{body}"
        path.write_text(content, encoding="utf-8")
        return path

    return _write_markdown
