#!/usr/bin/env python3

import argparse
import logging
import shutil
import sys
from pathlib import Path

from soggy.markdown import render_markdown
from soggy.minify import minify_html_text, minify_text_for_path, should_minify_path
from soggy.templates import IndexEntry, TemplateRenderer
from soggy.vault import VaultMarkdown, load_vault


DEFAULT_SITE_TITLE = "Kevin Stock"
_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
_LOG_LEVEL_MAP = {name: getattr(logging, name) for name in _LOG_LEVELS}
_LOGGER = logging.getLogger(__name__)


def _resolve_log_level(log_level: str | None, verbose: int, quiet: int) -> int:
    if log_level:
        return _LOG_LEVEL_MAP[log_level]

    level = logging.WARNING
    if verbose:
        level = logging.DEBUG
    if quiet == 1:
        level = logging.ERROR
    elif quiet >= 2:
        level = logging.CRITICAL
    return level


def _configure_logging(level: int) -> None:
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(message)s",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow deleting an existing output directory before running.",
    )
    parser.add_argument(
        "--ignore-output",
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "Top-level relative path under the output directory to preserve when "
            "overwriting. Repeatable."
        ),
    )
    parser.add_argument(
        "--site-title",
        default=DEFAULT_SITE_TITLE,
        help="Title to use for the generated site.",
    )
    parser.add_argument(
        "--log-level",
        choices=_LOG_LEVELS,
        help="Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (use -v for DEBUG).",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="count",
        default=0,
        help="Reduce output (use -q for ERROR, -qq for CRITICAL).",
    )
    return parser.parse_args()


def _normalize_ignore_output_paths(
    output_dir: Path, ignore_output: list[str]
) -> list[Path]:
    output_root = output_dir.resolve(strict=False)
    normalized: list[Path] = []
    for raw in ignore_output:
        resolved = (output_root / Path(raw)).resolve(strict=False)
        if resolved.parent != output_root:
            raise ValueError(
                "Ignore output path must be a top-level entry within "
                f"{output_dir.as_posix()}: {raw}"
            )
        normalized.append(resolved)
    return normalized


def _clear_directory(output_dir: Path, ignore_output: list[str]) -> None:
    ignore_paths = _normalize_ignore_output_paths(output_dir, ignore_output)
    ignore_set = {path.resolve(strict=False) for path in ignore_paths}
    for item in output_dir.iterdir():
        if item.resolve(strict=False) in ignore_set:
            continue
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink()


def _prepare_output_dir(
    output_dir: Path, overwrite: bool, ignore_output: list[str]
) -> None:
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(
                f"Output directory already exists: {output_dir}. Use --overwrite to replace it."
            )
        if not output_dir.is_dir():
            raise NotADirectoryError(
                f"Output path exists but is not a directory: {output_dir}"
            )
        _clear_directory(output_dir, ignore_output)
    output_dir.mkdir(parents=True, exist_ok=True)
    _LOGGER.info("Prepared output directory: %s", output_dir.as_posix())


def _validate_output_dir(input_dir: Path, output_dir: Path) -> None:
    input_root = input_dir.resolve()
    output_root = output_dir.resolve()
    if (
        output_root == input_root
        or output_root.is_relative_to(input_root)
        or input_root.is_relative_to(output_root)
    ):
        raise ValueError(
            "Output directory must not be the same as or nested within the input directory."
        )


def _copy_static_files(output_dir: Path) -> None:
    static_root = Path(__file__).resolve().parent.parent / "static"
    if not static_root.is_dir():
        raise FileNotFoundError(f"Static directory not found: {static_root}")
    destination_root = output_dir / "static"
    for path in sorted(static_root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_dir():
            continue
        rel_path = path.relative_to(static_root)
        destination = destination_root / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if should_minify_path(path):
            content = path.read_text(encoding="utf-8")
            destination.write_text(
                minify_text_for_path(path, content), encoding="utf-8"
            )
        else:
            shutil.copy2(path, destination)
    _LOGGER.info("Copied static assets to %s", destination_root.as_posix())


def _write_index(
    files: list[VaultMarkdown], output_dir: Path, renderer: TemplateRenderer
) -> None:
    posts = sorted(files, key=lambda file: file.date_created, reverse=True)
    entries = [
        IndexEntry(
            title=post.title,
            link=f"/{post.output_path.as_posix().lstrip('/')}",
        )
        for post in posts
    ]
    index_path = output_dir / "index.html"
    if index_path.exists():
        raise FileExistsError(f"Output file already exists: {index_path}")
    index_path.write_text(
        minify_html_text(renderer.render_index(entries)),
        encoding="utf-8",
    )
    _LOGGER.info("Wrote index: %s", index_path.as_posix())


def build_site(
    input_dir: Path,
    output_dir: Path,
    *,
    overwrite: bool = False,
    ignore_output: list[str] | None = None,
    site_title: str = DEFAULT_SITE_TITLE,
) -> None:
    if ignore_output is None:
        ignore_output = []
    _validate_output_dir(input_dir, output_dir)
    _prepare_output_dir(output_dir, overwrite, ignore_output)
    _LOGGER.info(
        "Building site from %s to %s",
        input_dir.as_posix(),
        output_dir.as_posix(),
    )
    files = load_vault(input_dir)
    renderer = TemplateRenderer(site_title)
    render_markdown(files, renderer)
    for file in files:
        file.write_out(input_dir, output_dir)
    _copy_static_files(output_dir)
    published_posts = [
        file for file in files if isinstance(file, VaultMarkdown) and file.publish
    ]
    _write_index(published_posts, output_dir, renderer)
    for file in published_posts:
        file.update_permalink_source(input_dir)
    _LOGGER.info("Site build complete")


def main() -> None:
    args = _parse_args()
    _configure_logging(_resolve_log_level(args.log_level, args.verbose, args.quiet))
    try:
        build_site(
            args.input_dir,
            args.output_dir,
            overwrite=args.overwrite,
            ignore_output=args.ignore_output,
            site_title=args.site_title,
        )
    except (FileExistsError, NotADirectoryError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
