from datetime import date
import logging
from pathlib import Path, PurePosixPath

import pytest

from tests.conftest import WriteMarkdown
from soggy.vault import VaultMarkdown, VaultOther, load_vault
from soggy.minify import minify_css_text, minify_html_text


def test_vault_markdown_publish_true(
    tmp_path: Path, write_markdown: WriteMarkdown
) -> None:
    root = tmp_path
    post_path = write_markdown(
        root,
        "notes/My Post.md",
        "# Title\n",
        {
            "publish": True,
            "date created": "2024-01-02",
            "date modified": "2024-01-03",
        },
    )

    loaded = VaultMarkdown(PurePosixPath(post_path.relative_to(root).as_posix()), root)

    assert loaded.content == "\n# Title\n"
    assert loaded.path == PurePosixPath("notes/My Post.md")
    assert loaded.output_path == PurePosixPath("notes/My_Post")
    assert loaded.update_source is True
    assert loaded.publish is True
    assert loaded.title == "My Post"
    assert loaded.date_created == date(2024, 1, 2)
    assert loaded.date_updated == date(2024, 1, 3)


def test_vault_markdown_missing_permalink_warns(
    tmp_path: Path, write_markdown: WriteMarkdown, caplog: pytest.LogCaptureFixture
) -> None:
    root = tmp_path
    post_path = write_markdown(
        root,
        "notes/My Post.md",
        "# Title\n",
        {
            "publish": True,
            "date created": "2024-01-02",
            "date modified": "2024-01-03",
        },
    )

    with caplog.at_level(logging.WARNING):
        loaded = VaultMarkdown(
            PurePosixPath(post_path.relative_to(root).as_posix()), root
        )
        loaded.update_permalink_source(root)

    assert "Missing permalink in front matter" in caplog.text
    assert "set to notes/My_Post" in caplog.text


def test_vault_markdown_update_permalink_writes_back(
    tmp_path: Path, write_markdown: WriteMarkdown
) -> None:
    root = tmp_path
    post_path = write_markdown(
        root,
        "notes/My Post.md",
        "# Title\n",
        {
            "publish": True,
            "date created": "2024-01-02",
            "date modified": "2024-01-03",
        },
    )

    loaded = VaultMarkdown(PurePosixPath(post_path.relative_to(root).as_posix()), root)
    loaded.update_permalink_source(root)

    updated = post_path.read_text(encoding="utf-8")
    assert "permalink: notes/My_Post" in updated


def test_vault_markdown_publish_false(
    tmp_path: Path, write_markdown: WriteMarkdown
) -> None:
    root = tmp_path
    post_path = write_markdown(
        root,
        "notes/draft.md",
        "# Draft\n",
        {
            "publish": False,
            "date created": "2024-01-02",
            "date modified": "2024-01-03",
        },
    )

    loaded = VaultMarkdown(PurePosixPath(post_path.relative_to(root).as_posix()), root)

    assert loaded.publish is False
    assert loaded.update_source is False
    with pytest.raises(ValueError, match="Unpublished markdown"):
        _ = loaded.output_path


def test_vault_markdown_invalid_front_matter(
    tmp_path: Path, write_markdown: WriteMarkdown
) -> None:
    root = tmp_path
    list_meta_path = write_markdown(root, "list-meta.md", "# List\n", ["a", "b"])

    with pytest.raises(ValueError, match="Invalid front matter"):
        VaultMarkdown(PurePosixPath(list_meta_path.relative_to(root).as_posix()), root)


def test_vault_markdown_missing_front_matter(
    tmp_path: Path, write_markdown: WriteMarkdown
) -> None:
    root = tmp_path
    no_front_path = write_markdown(root, "plain.md", "# Plain\n", None)

    with pytest.raises(ValueError, match="Missing front matter"):
        VaultMarkdown(PurePosixPath(no_front_path.relative_to(root).as_posix()), root)


def test_vault_markdown_missing_closing_delimiter(tmp_path: Path) -> None:
    root = tmp_path
    broken_path = root / "broken.md"
    broken_path.write_text("---\npublish: true\n# Missing\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Missing closing front matter delimiter"):
        VaultMarkdown(PurePosixPath(broken_path.relative_to(root).as_posix()), root)


def test_vault_markdown_permalink_disables_update_source(
    tmp_path: Path, write_markdown: WriteMarkdown
) -> None:
    root = tmp_path
    post_path = write_markdown(
        root,
        "notes/post.md",
        "# Title\n",
        {
            "publish": True,
            "permalink": "/custom/post",
            "date created": "bad-date",
            "date modified": "2024-01-03",
        },
    )

    with pytest.raises(ValueError, match="date created"):
        VaultMarkdown(PurePosixPath(post_path.relative_to(root).as_posix()), root)


def test_vault_markdown_missing_dates_raise(
    tmp_path: Path, write_markdown: WriteMarkdown
) -> None:
    root = tmp_path
    post_path = write_markdown(
        root,
        "notes/post.md",
        "# Title\n",
        {"publish": True, "date created": "2024-01-03"},
    )

    with pytest.raises(ValueError, match="date modified"):
        VaultMarkdown(PurePosixPath(post_path.relative_to(root).as_posix()), root)


def test_vault_markdown_set_html_and_target(
    tmp_path: Path, write_markdown: WriteMarkdown
) -> None:
    root = tmp_path
    post_path = write_markdown(
        root,
        "notes/post.md",
        "# Title\n",
        {
            "publish": True,
            "date created": "2024-01-02",
            "date modified": "2024-01-03",
        },
    )

    loaded = VaultMarkdown(PurePosixPath(post_path.relative_to(root).as_posix()), root)

    assert loaded.html is None
    loaded.set_html("<p>Rendered</p>")
    assert loaded.html == "<p>Rendered</p>"
    loaded.target()


def test_vault_markdown_target_unpublished_raises(
    tmp_path: Path, write_markdown: WriteMarkdown
) -> None:
    root = tmp_path
    post_path = write_markdown(
        root,
        "notes/draft.md",
        "# Draft\n",
        {
            "publish": False,
            "date created": "2024-01-02",
            "date modified": "2024-01-03",
        },
    )

    loaded = VaultMarkdown(PurePosixPath(post_path.relative_to(root).as_posix()), root)

    with pytest.raises(ValueError, match="Unpublished markdown cannot be targeted"):
        loaded.target()


def test_vault_other_target_flags_instance() -> None:
    other = VaultOther(PurePosixPath("assets/image.png"))

    assert other.targeted is False
    other.target()
    assert other.targeted


def test_load_vault_builds_file_types(tmp_path: Path) -> None:
    root = tmp_path
    md_path = root / "notes/post.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(
        "---\npublish: true\ndate created: 2024-01-01\ndate modified: 2024-01-02\n---\n# Post\n",
        encoding="utf-8",
    )
    other_path = root / "assets/image.png"
    other_path.parent.mkdir(parents=True, exist_ok=True)
    other_path.write_bytes(b"\x89PNG")

    files = load_vault(root)

    assert any(isinstance(item, VaultMarkdown) for item in files)
    assert any(isinstance(item, VaultOther) for item in files)
    assert any(item.path == PurePosixPath("notes/post.md") for item in files)
    assert any(item.path == PurePosixPath("assets/image.png") for item in files)


def test_vault_markdown_write_out(
    tmp_path: Path, write_markdown: WriteMarkdown
) -> None:
    root = tmp_path / "vault"
    output_dir = tmp_path / "site"
    root.mkdir()
    post_path = write_markdown(
        root,
        "notes/My Post.md",
        "# Title\n",
        {
            "publish": True,
            "date created": "2024-01-02",
            "date modified": "2024-01-03",
        },
    )

    loaded = VaultMarkdown(PurePosixPath(post_path.relative_to(root).as_posix()), root)
    loaded.set_html("<p>Rendered</p>")
    loaded.write_out(root, output_dir)

    output_file = output_dir / "notes" / "My_Post" / "index.html"
    assert output_file.read_text(encoding="utf-8") == minify_html_text(
        "<p>Rendered</p>"
    )

    with pytest.raises(FileExistsError, match="Output file already exists"):
        loaded.write_out(root, output_dir)


def test_vault_other_write_out(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    output_dir = tmp_path / "site"
    root.mkdir()
    asset_path = root / "assets" / "image.png"
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_bytes(b"\x89PNG")

    other = VaultOther(PurePosixPath("assets/image.png"))
    other.target()
    other.write_out(root, output_dir)

    output_file = output_dir / "assets" / "image.png"
    assert output_file.read_bytes() == b"\x89PNG"

    with pytest.raises(FileExistsError, match="Output file already exists"):
        other.write_out(root, output_dir)


def test_vault_other_write_out_minifies_html(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    output_dir = tmp_path / "site"
    root.mkdir()
    asset_path = root / "assets" / "page.html"
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    original = "<div>  <span>Rendered</span> </div>"
    asset_path.write_text(original, encoding="utf-8")

    other = VaultOther(PurePosixPath("assets/page.html"))
    other.target()
    other.write_out(root, output_dir)

    output_file = output_dir / "assets" / "page.html"
    assert output_file.read_text(encoding="utf-8") == minify_html_text(original)


def test_vault_other_write_out_minifies_css(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    output_dir = tmp_path / "site"
    root.mkdir()
    asset_path = root / "assets" / "site.css"
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    original = "body { color: #fff; }\n\nh1 { font-weight: 600; }\n"
    asset_path.write_text(original, encoding="utf-8")

    other = VaultOther(PurePosixPath("assets/site.css"))
    other.target()
    other.write_out(root, output_dir)

    output_file = output_dir / "assets" / "site.css"
    assert output_file.read_text(encoding="utf-8") == minify_css_text(original)


def test_vault_markdown_write_out_skips_unpublished(
    tmp_path: Path, write_markdown: WriteMarkdown
) -> None:
    root = tmp_path / "vault"
    output_dir = tmp_path / "site"
    root.mkdir()
    post_path = write_markdown(
        root,
        "notes/draft.md",
        "# Draft\n",
        {
            "publish": False,
            "date created": "2024-01-02",
            "date modified": "2024-01-03",
        },
    )

    loaded = VaultMarkdown(PurePosixPath(post_path.relative_to(root).as_posix()), root)
    loaded.write_out(root, output_dir)

    assert not output_dir.exists()


def test_vault_markdown_write_out_requires_html(
    tmp_path: Path, write_markdown: WriteMarkdown
) -> None:
    root = tmp_path / "vault"
    output_dir = tmp_path / "site"
    root.mkdir()
    post_path = write_markdown(
        root,
        "notes/post.md",
        "# Title\n",
        {
            "publish": True,
            "date created": "2024-01-02",
            "date modified": "2024-01-03",
        },
    )

    loaded = VaultMarkdown(PurePosixPath(post_path.relative_to(root).as_posix()), root)

    with pytest.raises(ValueError, match="missing rendered html"):
        loaded.write_out(root, output_dir)


def test_vault_other_write_out_skips_untargeted(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    output_dir = tmp_path / "site"
    root.mkdir()
    asset_path = root / "assets" / "image.png"
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_bytes(b"\x89PNG")

    other = VaultOther(PurePosixPath("assets/image.png"))
    other.write_out(root, output_dir)

    assert not output_dir.exists()


def test_vault_markdown_write_out_leading_slash_permalink(
    tmp_path: Path, write_markdown: WriteMarkdown
) -> None:
    root = tmp_path / "vault"
    output_dir = tmp_path / "site"
    root.mkdir()
    post_path = write_markdown(
        root,
        "notes/post.md",
        "# Title\n",
        {
            "publish": True,
            "permalink": "/custom/post",
            "date created": "2024-01-02",
            "date modified": "2024-01-03",
        },
    )

    loaded = VaultMarkdown(PurePosixPath(post_path.relative_to(root).as_posix()), root)
    loaded.set_html("<p>Rendered</p>")
    loaded.write_out(root, output_dir)

    output_file = output_dir / "custom" / "post" / "index.html"
    assert output_file.read_text(encoding="utf-8") == minify_html_text(
        "<p>Rendered</p>"
    )
