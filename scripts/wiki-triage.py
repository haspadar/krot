#!/usr/bin/env python3
"""Показывает накопленное в wiki/raw/ и куда каждая запись просится.

Ничего не переносит. Перенос — решение человека или агента, читающего смысл; скрипт лишь
снимает механическую часть: что лежит, сколько лежит, какие страницы кандидаты.

Кандидаты подбираются по совпадению слов записи с заголовками и содержимым страниц. Это
подсказка, а не диагноз: слово «логи» встречается и у nginx, и у cron, и у postgresql.

Запуск: python3 scripts/wiki-triage.py
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"
RAW = WIKI / "raw"

WORD_RE = re.compile(r"[^\W_]{6,}", re.UNICODE)
STOP_WORDS = frozenset(
    {
        "который",
        "которая",
        "потому",
        "поэтому",
        "значит",
        "нужно",
        "сделать",
        "проверить",
    }
)


def raw_entries() -> list[Path]:
    if not RAW.is_dir():
        return []

    return sorted(
        entry
        for entry in RAW.iterdir()
        if entry.is_file() and entry.name != "README.md"
    )


def keywords(text: str) -> list[str]:
    """Значимые слова: длиннее пяти символов, чтобы отсеять предлоги и служебное."""
    found = {word.lower() for word in WORD_RE.findall(text)}

    return sorted(found - STOP_WORDS)


def candidates(words: list[str]) -> list[tuple[str, int]]:
    scores: list[tuple[str, int]] = []

    for file in sorted(WIKI.rglob("*.md")):
        relative = file.relative_to(WIKI).as_posix()
        # index/ генерируется, raw/ — источник; ни туда, ни туда класть нельзя.
        if relative.startswith("index/") or relative.startswith("raw/"):
            continue

        haystack = file.read_text(encoding="utf-8", errors="replace").lower()
        lowered_path = relative.lower()

        score = 0
        for word in words:
            if word in haystack:
                # Слово в заголовке весит больше, чем в теле.
                score += 5 if word in lowered_path else 1

        if score > 0:
            scores.append((relative, score))

    scores.sort(key=lambda item: item[1], reverse=True)

    return scores[:3]


def main() -> int:
    entries = raw_entries()

    if not entries:
        print("В wiki/raw/ пусто — разбирать нечего.")

        return 0

    print(f"Записей к разбору: {len(entries)}\n")

    for file in entries:
        contents = file.read_text(encoding="utf-8", errors="replace")
        line_count = contents.count("\n") + 1
        age = int((time.time() - file.stat().st_mtime) / 86400)

        print(f"── {file.name}")
        print(
            f"   {line_count} строк, лежит "
            f"{'со вчера или меньше' if age == 0 else f'{age} дн.'}"
        )

        # Первая непустая строка — обычно суть.
        for line in contents.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                print(f"   «{stripped[:90]}»")
                break

        found = candidates(keywords(contents))
        if not found:
            print("   кандидатов нет — возможно, нужна новая страница")
        else:
            print("   ложится в:")
            for path, score in found:
                print(f"     {path} (совпадений: {score})")

        print()

    print("Что дальше: перенести содержимое в страницу, затем удалить запись из raw/.")
    print("Кандидаты — подсказка по словам, а не диагноз: решает тот, кто понимает смысл.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
