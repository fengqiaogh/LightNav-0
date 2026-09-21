from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import translate_md  # noqa: E402


def test_zh_path_for_readme(tmp_path: Path) -> None:
    assert translate_md.zh_path_for(Path("README.md")) == Path("README.zh.md")
    assert translate_md.zh_path_for(Path("docs/FOO.md")) == Path("docs/FOO.zh.md")


def test_is_english_md_skips_notices_and_zh() -> None:
    assert translate_md.is_english_md(Path("docs/GETTING_STARTED.md"))
    assert not translate_md.is_english_md(Path("docs/JETSON_THOR.zh.md"))
    assert not translate_md.is_english_md(Path("AGENTS.md"))
    assert not translate_md.is_english_md(Path("THIRD_PARTY_NOTICES.md"))


def test_should_skip_marker(tmp_path: Path) -> None:
    en = tmp_path / "note.md"
    zh = tmp_path / "note.zh.md"
    en.write_text("# Hello\n", encoding="utf-8")
    zh.write_text("<!-- translate: skip -->\n# 你好\n", encoding="utf-8")
    assert translate_md.should_skip(en, zh)


def test_extract_and_restore_fences() -> None:
    src = "See:\n\n```bash\npip install -e .\n```\n\nDone.\n"
    masked, blocks = translate_md.extract_fences(src)
    assert "pip install" not in masked
    assert translate_md.restore_fences(masked, blocks) == src


def test_wrap_zh_injects_english_link() -> None:
    out = translate_md.wrap_zh(Path("docs/FOO.md"), "[English](FOO.md)\n\n正文\n")
    assert out.startswith("<!--")
    assert "[English](FOO.md)" in out
    assert out.count("[English](FOO.md)") == 1
