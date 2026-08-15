#!/usr/bin/env python3
"""Говорит, что в вики устарело после архивации change.

Момент архивации — единственный, когда точно известно, что именно изменилось. Отсюда
точечная правка вместо сплошной сверки документации с кодом.

⚠️ Связь change → страница здесь идёт через РОЛИ, а не через capability: у krot нет
`openspec/specs/`, и changes не объявляют capability через `specs/`. Какие роли трогал
change, берётся из git — по путям `roles/<role>/...` в его коммитах, а не из текста
proposal: текст называет роли и в разборе причин, а тронутый файл — факт.

Скрипт ничего не правит сам. Он готовит задание: какие страницы открыть и что с каждой
сделать — правки в документацию должны проходить ревью вместе с кодом, а не появляться
молча.

Запуск: python3 scripts/wiki-after-archive.py <имя-change>
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"

DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")
FRONTMATTER_LINE_RE = re.compile(r"^([a-z_]+):\s*(.*)$")
ROLE_PATH_RE = re.compile(r"^roles/([^/]+)/")


def frontmatter_of(file: Path) -> dict[str, object]:
    contents = file.read_text(encoding="utf-8", errors="replace")
    if not contents.startswith("---\n"):
        return {}

    end = contents.find("\n---", 4)
    if end == -1:
        return {}

    result: dict[str, object] = {}
    for line in contents[4:end].split("\n"):
        match = FRONTMATTER_LINE_RE.match(line)
        if match is None:
            continue

        key, value = match.group(1), match.group(2).strip()
        if value.startswith("["):
            inner = value.strip("[]").strip()
            result[key] = [item.strip() for item in inner.split(",")] if inner else []
            continue

        result[key] = value.strip("\"'")

    return result


def roles_touched_by(change_directory: str, bare: str) -> list[str]:
    """Роли, которые change правил на самом деле.

    Ищем коммиты по ПАПКЕ change в openspec: она заводится и правится тем же PR, который
    правит роли. Из найденных коммитов берём пути вида `roles/<role>/`.

    ⚠️ Поиск по имени change в тексте коммита (`git log --grep`) отсюда убран намеренно.
    `--grep` — незаякоренная регулярка по всему телу сообщения, поэтому любое упоминание
    вскользь тянет чужой коммит вместе со всеми его ролями. Замерено на `2026-08-02-goaccess`:
    поиск по папке даёт 1 коммит, `--grep` — 20, и список ролей разрастается с `goaccess` до
    `bootstrap, geoip, goaccess, nginx`. Виноват, среди прочих, коммит «Оболочка оператора —
    bash вместо fish», который лишь упоминает goaccess в разборе причин, а правит `bootstrap`.

    Цена ошибки здесь несимметрична: лишняя роль в списке заставляет открыть непричастную
    страницу и поставить ей свежий `verified` — то есть объявить проверенным то, что никто не
    сверял. Пропущенная роль всего лишь оставляет страницу на прежней дате.
    """
    roles: set[str] = set()

    command = [
        "git",
        "log",
        "--all",
        "--format=%H",
        "--",
        f"openspec/changes/archive/{change_directory}",
        f"openspec/changes/{bare}",
        f"openspec/changes/{change_directory}",
    ]

    try:
        output = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    commits = [line for line in output.split("\n") if line]

    for commit in dict.fromkeys(commits):
        try:
            files = subprocess.run(
                ["git", "show", "--name-only", "--format=", commit],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue

        for path in files.split("\n"):
            match = ROLE_PATH_RE.match(path.strip())
            if match:
                roles.add(match.group(1))

    return sorted(roles)


def main() -> int:
    if len(sys.argv) < 2:
        print("Укажи имя заархивированного change.", file=sys.stderr)
        print(
            "  python3 scripts/wiki-after-archive.py cron-assert-silent-skip",
            file=sys.stderr,
        )

        return 2

    change_name = sys.argv[1]

    # Change уже в архиве: имя папки — <дата>-<имя>. Имя может быть передано и с датой,
    # и без неё — команда `openspec archive` печатает его в разных формах.
    archive_root = ROOT / "openspec" / "changes" / "archive"
    bare = DATE_PREFIX_RE.sub("", change_name)

    found = None
    if archive_root.is_dir():
        for entry in sorted(archive_root.iterdir()):
            if entry.name == change_name or entry.name.endswith(f"-{bare}"):
                found = entry.name
                break

    if found is None:
        print(f"В архиве нет change `{change_name}`.", file=sys.stderr)
        print("Сначала `openspec archive <name>`, потом этот скрипт.", file=sys.stderr)

        return 1

    archived_on = found[:10]
    roles = roles_touched_by(found, bare)

    print(f"Change `{bare}`, заархивирован {archived_on}")

    if not roles:
        print("\nВ коммитах, тронувших папку этого change, правок ролей нет.")
        print("Так бывает у изменений в CI, документации или структуре репозитория —")
        print("а ещё у change, заведённого задним числом, когда работа по ролям уже")
        print("уехала отдельным коммитом. Во втором случае сверять всё же есть что:")
        print("посмотри `git log -- roles/` за даты change и реши сам.")

        return 0

    print(f"Тронутые роли: {', '.join(roles)}\n")

    affected = []
    for file in sorted(WIKI.rglob("*.md")):
        relative = file.relative_to(ROOT).as_posix()
        if relative.startswith("wiki/index/"):
            continue

        frontmatter = frontmatter_of(file)
        declared = frontmatter.get("roles", [])
        if not isinstance(declared, list):
            continue

        overlap = [role for role in declared if role in roles]
        if not overlap:
            continue

        affected.append(
            {
                "path": relative,
                "kind": frontmatter.get("kind", "?"),
                "owner": frontmatter.get("owner", "?"),
                "verified": frontmatter.get("verified", "?"),
                "roles": overlap,
            }
        )

    if not affected:
        print("Ни одна страница вики не объясняет эти роли.\n")
        print("Это пробел, а не ошибка: изменилось поведение, которое вики не описывает.")
        print("Если знание стоит записать — заведи страницу и объяви в ней роль.")

        return 0

    print("Что открыть и что с этим сделать:\n")

    for page in affected:
        print(f"  {page['path']}")
        print(
            f"    kind: {page['kind']}, владелец: {page['owner']}, "
            f"проверялась: {page['verified']}"
        )
        print(f"    затронутые роли: {', '.join(page['roles'])}")  # type: ignore[arg-type]

        # Правило из CONVENTIONS: описания правят, замеры не переписывают.
        if page["kind"] == "research":
            print("    → ЗАМЕР: находки не трогать. Дописать статус сверху:")
            print(
                f"      «реализовано в `{bare}`, {archived_on}». Дату verified НЕ менять."
            )
        elif page["kind"] in ("guide", "runbook"):
            print("    → ОПИСАНИЕ: привести в соответствие с тем, как стало,")
            print(f"      затем поставить verified: {date.today():%Y-%m-%d}")
        else:
            print("    → неизвестный kind, решить вручную")

        print()

    print(f"Страниц к правке: {len(affected)}")
    print("\nПравки идут в тот же PR, что и архивация: документация ревьюится вместе с кодом.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
