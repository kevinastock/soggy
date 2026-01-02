from pathlib import Path

from tests.conftest import WriteMarkdown
from soggy import cli
from soggy.minify import minify_css_text


def test_cli_builds_site(tmp_path: Path, write_markdown: WriteMarkdown) -> None:
    vault_root = tmp_path / "vault"
    output_root = tmp_path / "site"
    vault_root.mkdir()

    asset_path = vault_root / "assets" / "image.png"
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_bytes(b"\x89PNG")

    write_markdown(
        vault_root,
        "notes/My Post.md",
        "![Alt](assets/image.png)\n",
        {
            "publish": True,
            "date created": "2024-01-02",
            "date modified": "2024-01-03",
        },
    )
    write_markdown(
        vault_root,
        "notes/Draft.md",
        "# Draft\n",
        {
            "publish": False,
            "date created": "2024-01-02",
            "date modified": "2024-01-03",
        },
    )
    write_markdown(
        vault_root,
        "notes/Linked Note.md",
        "See [[My Post]]\n",
        {
            "publish": True,
            "date created": "2024-01-02",
            "date modified": "2024-01-03",
        },
    )

    cli.build_site(vault_root, output_root, site_title="Test Site")

    page_path = output_root / "notes" / "My_Post" / "index.html"
    assert page_path.exists()
    linked_note = output_root / "notes" / "Linked_Note" / "index.html"
    linked_html = linked_note.read_text(encoding="utf-8")
    assert (
        "href=/notes/My_Post" in linked_html or 'href="/notes/My_Post"' in linked_html
    )
    assert (output_root / "assets" / "image.png").read_bytes() == b"\x89PNG"
    static_output = output_root / "static" / "style.css"
    assert static_output.exists()
    static_source = Path(__file__).resolve().parent.parent / "static" / "style.css"
    assert static_output.read_text(encoding="utf-8") == minify_css_text(
        static_source.read_text(encoding="utf-8")
    )
    assert "My Post" in (output_root / "index.html").read_text(encoding="utf-8")
    assert not (output_root / "notes" / "Draft" / "index.html").exists()


def test_cli_preserves_asset_filenames_with_spaces(
    tmp_path: Path, write_markdown: WriteMarkdown
) -> None:
    vault_root = tmp_path / "vault"
    output_root = tmp_path / "site"
    vault_root.mkdir()

    asset_path = vault_root / "Website" / "Name Smile.otf"
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_bytes(b"OTF")

    write_markdown(
        vault_root,
        "notes/Font Link.md",
        "[Name Smile](Website/Name%20Smile.otf)\n",
        {
            "publish": True,
            "date created": "2024-01-02",
            "date modified": "2024-01-03",
        },
    )

    cli.build_site(vault_root, output_root, site_title="Test Site")

    assert (output_root / "Website" / "Name Smile.otf").read_bytes() == b"OTF"
    assert not (output_root / "Website" / "Name_Smile.otf").exists()
    font_link = output_root / "notes" / "Font_Link" / "index.html"
    font_html = font_link.read_text(encoding="utf-8")
    assert (
        "href=/Website/Name%20Smile.otf" in font_html
        or 'href="/Website/Name%20Smile.otf"' in font_html
    )
