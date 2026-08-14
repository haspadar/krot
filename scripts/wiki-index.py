#!/usr/bin/env python3
"""Собирает индексы вики из ролей, openspec и git-истории.

Источники правды, ни один из которых не ведётся руками:
  - roles/<role>/                              — какие роли существуют
  - roles/<role>/defaults/main.yml             — какими переменными роль настраивается
  - openspec/changes/<change>/                  — что сейчас в работе
  - openspec/changes/archive/<дата>-<change>/   — когда change заархивирован
  - git log --merges                            — ветка и номер PR

Связь change → PR восстанавливается из merge-коммита: GitHub пишет
«Merge pull request #NNN from <owner>/<branch>», то есть номер и ветка в одной строке.

⚠️ Совпадение имени ветки с именем change здесь ЧАСТИЧНОЕ: ветки называют близко по смыслу,
но короче (change `2026-08-13-cron-assert-silent-skip` — ветка `fix/cron-assert-silent-skip`).
Поэтому сравнение идёт по имени БЕЗ даты и без префикса ветки (`feat/`, `fix/`), но остаётся
СТРОГИМ: нестрогое приписало бы change чужой PR, и прочерк честнее неверного номера.

⚠️ У krot нет `openspec/specs/`. Это не пробел, а следствие предмета: krot описывает не
поведение приложения, а машину, и его единица знания — роль. Поэтому индекс строится по
`roles/`, а не по capability.

Запуск: python3 scripts/wiki-index.py
"""

from __future__ import annotations

import re
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"
REPOSITORY = "https://github.com/haspadar/krot"

GENERATED_NOTE = (
    "> **Сгенерировано.** Руками не править — правка будет затёрта.\n"
    "> Обновить: `python3 scripts/wiki-index.py`"
)

DATED_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)$")
MERGE_SUBJECT_RE = re.compile(r"^Merge pull request #(\d+) from [^/]+/(.+)$")
BRANCH_PREFIX_RE = re.compile(r"^(?:feat|fix|chore|docs|refactor|test)/")
FRONTMATTER_LINE_RE = re.compile(r"^([a-z_]+):\s*(.*)$")
HEADING_RE = re.compile(r"^#\s+(.+)$")
# Ключ верхнего уровня в defaults/main.yml — переменная роли. Вложенные (с отступом)
# не в счёт: они части значения, а не отдельные ручки.
VARIABLE_RE = re.compile(r"^([a-z][a-z0-9_]*):", re.MULTILINE)


def list_directories(path: Path) -> list[str]:
    if not path.is_dir():
        return []

    return sorted(entry.name for entry in path.iterdir() if entry.is_dir())


def read_frontmatter(file: Path) -> dict[str, object]:
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


def title_of(file: Path) -> str | None:
    """Первый заголовок документа — человеческое название."""
    if not file.is_file():
        return None

    for line in file.read_text(encoding="utf-8", errors="replace").split("\n"):
        match = HEADING_RE.match(line)
        if match:
            return match.group(1).strip()

    return None


def pull_requests_by_branch() -> dict[str, str]:
    """Merge-коммиты GitHub: ветка → номер PR."""
    try:
        output = subprocess.run(
            ["git", "log", "--merges", "--format=%s"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}

    by_branch: dict[str, str] = {}
    for subject in output.split("\n"):
        match = MERGE_SUBJECT_RE.match(subject.strip())
        if match is None:
            continue

        branch = match.group(2)
        # Первый встреченный — самый свежий: git log идёт от новых к старым.
        by_branch.setdefault(branch, match.group(1))
        # Ветки здесь называют с префиксом типа, а change — с датой. Кладём и голое имя,
        # чтобы сопоставление работало без нестрогого сравнения.
        by_branch.setdefault(BRANCH_PREFIX_RE.sub("", branch), match.group(1))

    return by_branch


def pages_by_role() -> dict[str, list[str]]:
    """Какая страница вики объясняет роль — по frontmatter."""
    by_role: dict[str, list[str]] = {}
    if not WIKI.is_dir():
        return by_role

    for file in sorted(WIKI.rglob("*.md")):
        relative = file.relative_to(WIKI).as_posix()
        if relative.startswith("index/"):
            continue

        declared = read_frontmatter(file).get("roles", [])
        if not isinstance(declared, list):
            continue
        for role in declared:
            by_role.setdefault(role, []).append(relative)

    return by_role


def role_variables(role: str) -> int:
    """Сколько ручек у роли. Число, а не список: список дублировал бы defaults/main.yml,
    который и так читается, а число показывает масштаб настройки.
    """
    defaults = ROOT / "roles" / role / "defaults" / "main.yml"
    if not defaults.is_file():
        return 0

    contents = defaults.read_text(encoding="utf-8", errors="replace")
    return len(set(VARIABLE_RE.findall(contents)))


def write_index(path: Path, lines: list[str]) -> None:
    """Пишет индекс, сохраняя прежний `verified`, если изменилась только дата.

    `verified` для генерируемой страницы — дата прогона, и она не значит ничего: никто
    ничего не сверял. Зато без этой оговорки CI начинает падать на следующий день после
    любого коммита — проверка «индекс пересобран» превращается в календарный будильник.

    Дата вдобавок не даётся уменьшать. Раннер GitHub живёт в UTC, автор — нет: прогон
    вечером по местному времени видит на календаре вчерашний день и переписал бы дату
    назад, а CI сравнивает результат с закоммиченным файлом и падает на разнице в сутки.
    Проверка при этом жалуется на устаревший индекс, хотя устарел часовой пояс.
    """
    new_contents = "\n".join(lines) + "\n"

    if path.is_file():
        old_contents = path.read_text(encoding="utf-8")
        old_verified = read_frontmatter(path).get("verified")
        if isinstance(old_verified, str):
            with_old_date = re.sub(
                r"^verified: .*$",
                f"verified: {old_verified}",
                new_contents,
                count=1,
                flags=re.MULTILINE,
            )
            if with_old_date == old_contents:
                return

            # Содержимое изменилось — дату обновляем, но только вперёд.
            if old_verified > f"{date.today():%Y-%m-%d}":
                new_contents = with_old_date

    path.write_text(new_contents, encoding="utf-8")


def without_date(name: str) -> tuple[str | None, str]:
    match = DATED_NAME_RE.match(name)
    if match:
        return match.group(1), match.group(2)

    return None, name


def pr_link(pr: str | None) -> str:
    return "—" if pr is None else f"[#{pr}]({REPOSITORY}/pull/{pr})"


def main() -> None:
    roles = list_directories(ROOT / "roles")

    active_changes = [
        name
        for name in list_directories(ROOT / "openspec" / "changes")
        if name != "archive"
    ]
    archived_changes = list_directories(ROOT / "openspec" / "changes" / "archive")

    pull_requests = pull_requests_by_branch()
    wiki_pages = pages_by_role()

    all_changes: list[dict[str, object]] = []

    for directory in active_changes:
        # Активный change тоже может нести дату в имени папки — она не значит архивации.
        _, bare = without_date(directory)
        path = f"openspec/changes/{directory}"
        all_changes.append(
            {
                "name": directory,
                "path": path,
                "archived": None,
                "pr": pull_requests.get(bare) or pull_requests.get(directory),
                "title": title_of(ROOT / path / "proposal.md"),
            }
        )

    for directory in archived_changes:
        archived_on, bare = without_date(directory)
        path = f"openspec/changes/archive/{directory}"
        all_changes.append(
            {
                "name": bare,
                "path": path,
                "archived": archived_on,
                "pr": pull_requests.get(bare),
                "title": title_of(ROOT / path / "proposal.md"),
            }
        )

    # --- index/roles.md ------------------------------------------------------

    lines = [
        "---",
        "kind: index",
        "title: Роли коллекции",
        "owner: generated",
        f"verified: {date.today():%Y-%m-%d}",
        "roles: []",
        "---",
        "",
        "# Роли коллекции",
        "",
        GENERATED_NOTE,
        "",
        (
            f"Всего **{len(roles)}**. Источник — `roles/`. Роль отвечает на вопрос «что "
            "ставится на машину»; страница вики — «как с этим работать и что кусается»."
        ),
        "",
        "| Роль | Ручек в `defaults` | Объясняет страница |",
        "|---|---|---|",
    ]

    uncovered: list[str] = []
    for role in roles:
        pages = wiki_pages.get(role, [])
        if pages:
            page_cell = ", ".join(f"[{page}](../{page})" for page in pages)
        else:
            uncovered.append(role)
            page_cell = "— *не объяснена*"

        lines.append(
            f"| [`{role}`](../../roles/{role}/) | {role_variables(role)} | {page_cell} |"
        )

    if uncovered:
        lines += [
            "",
            f"## Не объяснены ни одной страницей — {len(uncovered)}",
            "",
            "Нормальное состояние для новой роли. Ненормальное — если так остаётся долго.",
            "",
        ]
        lines += [f"- `{role}`" for role in uncovered]

    write_index(WIKI / "index" / "roles.md", lines)

    # --- index/changes.md ----------------------------------------------------

    # Активные сверху, затем архив от свежих к старым.
    all_changes.sort(
        key=lambda change: (
            change["archived"] is not None,
            change["name"] if change["archived"] is None else "",
            "" if change["archived"] is None else str(change["archived"]),
        ),
    )
    archived_part = [c for c in all_changes if c["archived"] is not None]
    archived_part.sort(key=lambda change: str(change["archived"]), reverse=True)
    all_changes = [c for c in all_changes if c["archived"] is None] + archived_part

    unresolved = sum(1 for change in all_changes if change["pr"] is None)

    lines = [
        "---",
        "kind: index",
        "title: Changes",
        "owner: generated",
        f"verified: {date.today():%Y-%m-%d}",
        "roles: []",
        "---",
        "",
        "# Changes",
        "",
        GENERATED_NOTE,
        "",
        (
            f"В работе — **{len(active_changes)}**, заархивировано — "
            f"**{len(archived_changes)}**."
        ),
        "",
        (
            "Номер PR восстановлен из merge-коммита по совпадению имени ветки с именем "
            "change после отбрасывания даты и префикса типа (`feat/`, `fix/`). Сравнение "
            f"остаётся строгим, поэтому не восстановлен у **{unresolved}** из "
            f"{len(all_changes)}: нестрогое приписало бы change чужой PR — прочерк честнее "
            "неверного номера."
        ),
        "",
        (
            "**Строка «влит, не заархивирован» — это долг**: работа в `main`, а "
            "`openspec archive` не выполнен, значит вики не узнала, что устарело."
        ),
        "",
        "| Change | Состояние | PR | О чём |",
        "|---|---|---|---|",
    ]

    for change in all_changes:
        if change["archived"] is not None:
            state = str(change["archived"])
        elif change["pr"] is not None:
            state = "**влит, не заархивирован**"
        else:
            state = "**в работе**"

        lines.append(
            f"| [`{change['name']}`](../../{change['path']}/proposal.md) | {state} "
            f"| {pr_link(change['pr'])} | {change['title'] or '—'} |"  # type: ignore[arg-type]
        )

    write_index(WIKI / "index" / "changes.md", lines)

    # --- отчёт ---------------------------------------------------------------

    print(f"wiki/index/roles.md — {len(roles)} ролей, {len(uncovered)} без страницы")
    print(
        f"wiki/index/changes.md — {len(all_changes)} changes "
        f"({len(active_changes)} в работе, {len(archived_changes)} в архиве)"
    )
    print(f"PR не восстановлен у {unresolved} changes")

    merged_not_archived = [
        change
        for change in all_changes
        if change["archived"] is None and change["pr"] is not None
    ]
    if merged_not_archived:
        print(f"\nВлиты, но не заархивированы — {len(merged_not_archived)}:")
        for change in merged_not_archived:
            print(f"  {change['name']} (PR #{change['pr']})")


if __name__ == "__main__":
    main()
