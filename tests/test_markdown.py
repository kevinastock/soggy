from pathlib import Path, PurePosixPath

import pytest

from soggy.markdown import SoggyRenderer, render_markdown
from soggy.templates import TemplateRenderer
from soggy.vault import VaultFile, VaultMarkdown, VaultOther, load_vault
from tests.conftest import WriteMarkdown


_DEFAULT_FRONT_MATTER = {
    "publish": True,
    "date created": "2024-01-01",
    "date modified": "2024-01-02",
}


def _load_markdown(root: Path, relative_path: str) -> VaultMarkdown:
    return VaultMarkdown(PurePosixPath(relative_path), root)


def _get_markdown(files: list[VaultFile], path: str) -> VaultMarkdown:
    return next(
        file
        for file in files
        if isinstance(file, VaultMarkdown) and file.path == PurePosixPath(path)
    )


def _renderer_with_posts(root: Path, write_markdown: WriteMarkdown) -> SoggyRenderer:
    write_markdown(root, "notes/post.md", "# Post\n", _DEFAULT_FRONT_MATTER)
    write_markdown(root, "archive/post.md", "# Post\n", _DEFAULT_FRONT_MATTER)
    files = [
        _load_markdown(root, "notes/post.md"),
        _load_markdown(root, "archive/post.md"),
    ]
    return SoggyRenderer(files)


def test_resolve_url_external_passthrough() -> None:
    renderer = SoggyRenderer([])

    assert (
        renderer._resolve_url("https://example.com/path?query=1")
        == "https://example.com/path?query=1"
    )
    assert renderer._resolve_url("//example.com/path") == "//example.com/path"


def test_resolve_url_rejects_query_or_params(tmp_path: Path) -> None:
    renderer = SoggyRenderer([VaultOther(PurePosixPath("assets/image.png"))])

    with pytest.raises(ValueError, match="Query or params are not allowed"):
        renderer._resolve_url("notes/post.md?version=1")

    with pytest.raises(ValueError, match="Query or params are not allowed"):
        renderer._resolve_url("notes/post.md;version=1")


def test_resolve_url_rejects_empty_path() -> None:
    renderer = SoggyRenderer([])

    with pytest.raises(ValueError, match="Empty link url is not allowed"):
        renderer._resolve_url("")


def test_resolve_url_missing_and_ambiguous(
    tmp_path: Path, write_markdown: WriteMarkdown
) -> None:
    renderer = _renderer_with_posts(tmp_path, write_markdown)

    with pytest.raises(ValueError, match="No vault file matches link url"):
        renderer._resolve_url("missing.md")

    with pytest.raises(ValueError, match="Ambiguous link url"):
        renderer._resolve_url("post")


def test_resolve_url_matches_and_targets(
    tmp_path: Path, write_markdown: WriteMarkdown
) -> None:
    root = tmp_path
    write_markdown(root, "notes/My Post.md", "# Post\n", _DEFAULT_FRONT_MATTER)
    image = VaultOther(PurePosixPath("assets/image.png"))
    files = [_load_markdown(root, "notes/My Post.md"), image]
    renderer = SoggyRenderer(files)

    assert renderer._resolve_url("notes/My Post") == "/notes/My_Post"
    assert renderer._resolve_url("assets/image.png") == "/assets/image.png"
    assert image.targeted is True


def test_resolve_url_suffix_matching(
    tmp_path: Path, write_markdown: WriteMarkdown
) -> None:
    renderer = _renderer_with_posts(tmp_path, write_markdown)

    assert renderer._resolve_url("/notes/post") == "/notes/post"
    assert renderer._resolve_url("s/post") == "/notes/post"
    assert renderer._resolve_url("e/post") == "/archive/post"
    assert renderer._resolve_url("ve/post.md") == "/archive/post"


def test_render_markdown_resolves_links_and_images(
    tmp_path: Path, write_markdown: WriteMarkdown
) -> None:
    root = tmp_path
    write_markdown(
        root,
        "notes/First Post.md",
        "See [[notes/Second-Post|Second]] and ![Alt](assets/image.png).\n",
        _DEFAULT_FRONT_MATTER,
    )
    write_markdown(root, "notes/Second-Post.md", "# Second\n", _DEFAULT_FRONT_MATTER)
    write_markdown(
        root,
        "notes/Draft.md",
        "# Draft\n",
        {
            "publish": False,
            "date created": "2024-01-01",
            "date modified": "2024-01-02",
        },
    )
    image_path = root / "assets/image.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"\x89PNG")

    files = load_vault(root)
    render_markdown(files, TemplateRenderer("Test Site"))

    first = _get_markdown(files, "notes/First Post.md")
    second = _get_markdown(files, "notes/Second-Post.md")
    draft = _get_markdown(files, "notes/Draft.md")
    image = next(file for file in files if isinstance(file, VaultOther))

    assert first.html is not None
    assert 'href="/notes/Second-Post"' in first.html
    assert 'alt="Alt"' in first.html
    assert 'src="/assets/image.png"' in first.html
    assert second.html is not None
    assert draft.html is None
    assert image.targeted is True


def test_render_markdown_relative_asset_link_is_rooted(
    tmp_path: Path, write_markdown: WriteMarkdown
) -> None:
    root = tmp_path
    write_markdown(
        root,
        "Website/Word Clock.md",
        "![pic](word-clock.webp)\n",
        _DEFAULT_FRONT_MATTER,
    )
    asset_path = root / "Website" / "word-clock.webp"
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_bytes(b"\x89PNG")

    files = load_vault(root)
    render_markdown(files, TemplateRenderer("Test Site"))

    note = _get_markdown(files, "Website/Word Clock.md")
    assert note.html is not None
    assert 'src="/Website/word-clock.webp"' in note.html


def test_render_markdown_strips_percent_comments(
    tmp_path: Path, write_markdown: WriteMarkdown
) -> None:
    root = tmp_path
    write_markdown(
        root,
        "notes/Percent Commented.md",
        "Hello %%hidden%% World\n\n%%\nblock comment\n%%\n\nDone\n",
        _DEFAULT_FRONT_MATTER,
    )

    files = load_vault(root)
    render_markdown(files, TemplateRenderer("Test Site"))

    note = _get_markdown(files, "notes/Percent Commented.md")
    assert note.html is not None
    assert "hidden" not in note.html
    assert "block comment" not in note.html
    assert "Hello" in note.html
    assert "World" in note.html
    assert "Done" in note.html


def test_render_markdown_hides_created_date_with_tag(
    tmp_path: Path, write_markdown: WriteMarkdown
) -> None:
    root = tmp_path
    write_markdown(
        root,
        "notes/Hidden Date.md",
        "# Post\n",
        {
            "publish": True,
            "date created": "2024-01-01",
            "date modified": "2024-01-02",
            "tags": ["hide-created-date"],
        },
    )

    files = load_vault(root)
    render_markdown(files, TemplateRenderer("Test Site"))

    note = _get_markdown(files, "notes/Hidden Date.md")
    assert note.html is not None
    assert 'datetime="2024-01-01"' not in note.html
    assert 'datetime="2024-01-02"' in note.html
