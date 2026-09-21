#!/usr/bin/env python3
"""Translate English Markdown into Simplified Chinese ``*.zh.md`` siblings.

Used by ``.github/workflows/translate-docs.yml``. Talks to any OpenAI-compatible
Chat Completions API (OpenAI, DeepSeek, SiliconFlow, …). Set:

  TRANSLATE_API_KEY     required (DeepSeek sk-...)
  TRANSLATE_BASE_URL    default https://api.deepseek.com/v1
  TRANSLATE_MODEL       default deepseek-chat
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

SKIP_NAMES = frozenset(
    {
        "AGENTS.md",
        "THIRD_PARTY_NOTICES.md",
    }
)
SKIP_COMMENT_RE = re.compile(r"<!--\s*translate:\s*skip\s*-->")
FENCE_RE = re.compile(r"```[\s\S]*?```")
CHUNK_CHARS = 12_000

SYSTEM_PROMPT = """\
You translate technical Markdown from English into Simplified Chinese.

Rules:
- Keep Markdown structure: headings, lists, tables, blockquotes, HTML, badges.
- Do not translate fenced or inline code, CLI flags, file paths, URLs, image
  alt text that is a filename, or identifiers such as LightNav-0, Qwen3-VL,
  Habitat, MuJoCo, vLLM, ROS 2.
- Keep link targets and image src unchanged. You may translate link titles.
- Keep a blank line around headings. Use Chinese punctuation (，。；：).
- Do not wrap the whole document in an extra code fence.
- Do not add a preamble or commentary. Output only the translated Markdown.
- If the source starts with a "[中文版](...)" link, drop that line; the
  pipeline injects an "[English](...)" link itself.
"""


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def is_english_md(path: Path) -> bool:
    if path.suffix.lower() != ".md":
        return False
    if path.name.endswith(".zh.md"):
        return False
    return path.name not in SKIP_NAMES


def zh_path_for(english: Path) -> Path:
    return english.with_name(english.stem + ".zh.md")


def should_skip(english: Path, chinese: Path) -> bool:
    if not is_english_md(english):
        return True
    for candidate in (english, chinese):
        if candidate.is_file() and SKIP_COMMENT_RE.search(
            candidate.read_text(encoding="utf-8")
        ):
            return True
    return False


def extract_fences(text: str) -> tuple[str, dict[str, str]]:
    blocks: dict[str, str] = {}

    def repl(match: re.Match[str]) -> str:
        key = f"@@FENCE{len(blocks)}@@"
        blocks[key] = match.group(0)
        return key

    return FENCE_RE.sub(repl, text), blocks


def restore_fences(text: str, blocks: dict[str, str]) -> str:
    for key, body in blocks.items():
        text = text.replace(key, body)
    return text


def split_chunks(text: str) -> list[str]:
    if len(text) <= CHUNK_CHARS:
        return [text]
    parts = re.split(r"(?m)(?=^## )", text)
    chunks: list[str] = []
    buf = ""
    for part in parts:
        if buf and len(buf) + len(part) > CHUNK_CHARS:
            chunks.append(buf)
            buf = part
        else:
            buf += part
    if buf:
        chunks.append(buf)
    return chunks or [text]


def _api_config() -> tuple[str, str, str]:
    key = os.environ.get("TRANSLATE_API_KEY", "").strip()
    if not key:
        raise SystemExit("TRANSLATE_API_KEY is not set")
    base = (
        os.environ.get("TRANSLATE_BASE_URL", "").strip().rstrip("/")
        or "https://api.deepseek.com/v1"
    )
    model = os.environ.get("TRANSLATE_MODEL", "").strip() or "deepseek-chat"
    return key, base, model


def chat_complete(messages: list[dict[str, str]]) -> str:
    key, base, model = _api_config()
    payload = json.dumps(
        {"model": model, "temperature": 0.2, "messages": messages},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"translate API HTTP {exc.code}: {body}") from exc
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise SystemExit(f"unexpected API response: {data!r}") from exc


def translate_markdown(source: str) -> str:
    masked, fences = extract_fences(source)
    translated_parts: list[str] = []
    for chunk in split_chunks(masked):
        translated_parts.append(
            chat_complete(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": chunk},
                ]
            )
        )
    merged = "\n\n".join(translated_parts)
    return restore_fences(merged, fences)


def strip_language_switch_link(text: str) -> str:
    return re.sub(
        r"(?m)^\[(?:English|中文版|中文)\]\([^)]+\)\s*\n+",
        "",
        text,
        count=1,
    )


def wrap_zh(english: Path, body: str) -> str:
    rel = english.as_posix()
    body = strip_language_switch_link(body).lstrip()
    header = (
        f"<!--\n"
        f"  Auto-translated from {rel}. Edit the English source, not this file.\n"
        f"  Frozen human translations: put translate: skip in an HTML comment.\n"
        f"-->\n\n"
        f"[English]({english.name})\n\n"
    )
    return header + body.rstrip() + "\n"


def iter_english_markdown(root: Path) -> list[Path]:
    found = [
        p
        for p in root.rglob("*.md")
        if ".git" not in p.parts and is_english_md(p)
    ]
    return sorted(found)


def translate_file(english: Path, *, dry_run: bool = False) -> Path | None:
    chinese = zh_path_for(english)
    if should_skip(english, chinese):
        print(f"skip  {english}")
        return None
    print(f"translate  {english} -> {chinese}")
    if dry_run:
        return chinese
    source = english.read_text(encoding="utf-8")
    zh_body = translate_markdown(source)
    chinese.write_text(wrap_zh(english, zh_body), encoding="utf-8")
    return chinese


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="English Markdown files (relative to repo root or absolute)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Translate every English Markdown file in the repo",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = repo_root()
    os.chdir(root)
    if args.all:
        targets = iter_english_markdown(root)
    else:
        targets = []
        for raw in args.files:
            path = raw if raw.is_absolute() else root / raw
            if not path.is_file():
                print(f"missing  {raw}", file=sys.stderr)
                continue
            targets.append(path.resolve().relative_to(root))
    if not targets:
        print("no markdown files to translate")
        return 0
    for path in targets:
        translate_file(path, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
