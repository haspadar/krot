#!/usr/bin/env python3
"""Проверяет вики. Валит на том, что делает её вредной, и лишь сообщает о том,
что делает её неполной.

Валит:  битые внутренние ссылки, отсутствующий frontmatter, секреты, ручные правки в index/.
Сообщает: роль без страницы, страницы за горизонтом, недостижимые страницы.

Разделение намеренное. Роль без страницы — нормальное состояние в день, когда она
появилась; падение на этом заставляло бы писать заглушку раньше, чем появилось знание.
Битая ссылка нормальным состоянием не бывает никогда.

Запуск: python3 scripts/wiki-lint.py
"""

from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"

STALE_DAYS = 90
KINDS = ("guide", "runbook", "research", "index")

# Ловим форму секрета, а не конкретные значения: список известных ключей устаревает ровно
# тогда, когда заводят новый.
SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"""-u\s+["']?[\w.-]+:[^\s"']{6,}"""), "логин:пароль в команде"),
    # Подстановка переменной ($VAR, ${VAR}, <плейсхолдер>) — это ПРАВИЛЬНЫЙ способ показать
    # команду без секрета. Ругаться на него нельзя: линтер, мешающий писать верно,
    # начинают обходить.
    (
        re.compile(
            r"""(?:password|passwd|secret|api[_-]?key|token)\s*[:=]\s*["'`]?"""
            r"""(?!\$\{?[A-Za-z_]|<)[A-Za-z0-9!@#$%^&*_\-]{6,}""",
            re.IGNORECASE,
        ),
        "значение секрета",
    ),
    # Пара «логин / пароль» в бэктиках: форма, в которой секрет попадает в таблицу,
    # где ни одно из правил выше его не видит.
    #
    # Второй элемент обязан выглядеть ЗНАЧЕНИЕМ, а не именем: перечисления вида
    # `nginx`/`php` или `LOGIN`/`PASSWORD` — обычная проза, и ловить их нельзя.
    # Признак значения: пунктуация, характерная для пароля, либо смесь регистра с цифрами.
    # Набор пунктуации намеренно узкий: скобки, точки, `<>` — синтаксис кода, а не пароля.
    (
        re.compile(
            r"`[\w.+-]{3,}`\s*/\s*`(?=[^`\s]{6,}`)"
            r"(?:[^`\s]*[!@#$%^&*?~][^`\s]*"
            r"|(?=[^`\s]*[a-z])(?=[^`\s]*[A-Z])(?=[^`\s]*\d)[^`\s]+)`"
        ),
        "пара логин/пароль в бэктиках",
    ),
    # `ключ:значение` в бэктиках — форма basic-auth из curl, перенесённая в текст.
    # Значение должно выглядеть СЛУЧАЙНЫМ, а не читаемым: имена ansible-переменных
    # и команд устроены так же, но секретом не являются. Признак случайности —
    # цифра вперемешку с буквами.
    (
        re.compile(
            r"`[\w.-]+:(?=[a-z0-9-]*\d)(?=[a-z0-9-]*[a-f])[a-f0-9-]{12,}`",
            re.IGNORECASE,
        ),
        "пара ключ:секрет в бэктиках",
    ),
    # base64 требует смешанного регистра И цифр: без этого под правило попадают
    # длинные имена и идентификаторы. Приватные ключи и ssh-ключи ловятся тем же:
    # тело ключа — это base64.
    (
        re.compile(
            r"\b(?=[A-Za-z0-9+/]*[a-z])(?=[A-Za-z0-9+/]*[A-Z])(?=[A-Za-z0-9+/]*\d)"
            r"[A-Za-z0-9+/]{40,}={0,2}\b"
        ),
        "похоже на base64-секрет",
    ),
)

# Строки, которые ПОКАЗЫВАЮТ, где лежит секрет, — это правильный способ, а не находка.
INTENTIONAL_MARKERS = ("bw get", "bw list", "BITWARDEN", "Bitwarden", "BW_SESSION")

UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)

# Публичный ssh-ключ секретом не является: он и предназначен для раздачи. В роли
# bootstrap он стоит в примерах инвентаря, и ловить его — значит ругаться на верное.
PUBLIC_KEY_RE = re.compile(r"ssh-(?:ed25519|rsa)\s+AAAA")

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
EXTERNAL_RE = re.compile(r"^(https?:|mailto:|#)")
FRONTMATTER_LINE_RE = re.compile(r"^([a-z_]+):\s*(.*)$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def looks_intentional(line: str) -> bool:
    if any(marker in line for marker in INTENTIONAL_MARKERS):
        return True
    if PUBLIC_KEY_RE.search(line):
        return True

    return UUID_RE.search(line) is not None


def parse_frontmatter(contents: str) -> dict[str, object]:
    """Свой минимальный парсер: нужны строки и плоские списки, тащить ради этого
    YAML-зависимость незачем.
    """
    if not contents.startswith("---\n"):
        return {}

    end = contents.find("\n---", 4)
    if end == -1:
        return {}

    data: dict[str, object] = {}
    for line in contents[4:end].split("\n"):
        match = FRONTMATTER_LINE_RE.match(line)
        if match is None:
            continue

        key, value = match.group(1), match.group(2).strip()
        if value.startswith("["):
            inner = value.strip("[]").strip()
            data[key] = [item.strip() for item in inner.split(",")] if inner else []
            continue

        data[key] = value.strip("\"'")

    return data


def directories_in(path: Path) -> list[str]:
    """Имена папок внутри пути. Пустой список, если пути нет: роли могут отсутствовать
    вовсе, и это не повод падать — вики заводится раньше первой роли.
    """
    if not path.is_dir():
        return []

    return sorted(entry.name for entry in path.iterdir() if entry.is_dir())


def wiki_files() -> list[Path]:
    return sorted(WIKI.rglob("*.md"))


def read_page(file: Path) -> tuple[str, str | None]:
    """Содержимое страницы и жалоба, если её пришлось читать с потерями.

    Не-UTF-8 в markdown — это почти всегда сломанная кодировка при копировании из
    терминала, и линтер обязан о ней СКАЗАТЬ, а не упасть трейсбеком: упавший линтер не
    проверит ни секреты, ни ссылки в остальных файлах. Читаем с заменой негодных байтов,
    чтобы проверки на секреты всё же отработали — утечка не должна пережить кривой байт.
    """
    raw = file.read_bytes()
    try:
        return raw.decode("utf-8"), None
    except UnicodeDecodeError as error:
        return (
            raw.decode("utf-8", errors="replace"),
            f"{file.relative_to(ROOT)}: не UTF-8 ({error.reason} на байте {error.start})",
        )


def main() -> int:
    if not WIKI.is_dir():
        print("Папки wiki/ нет.", file=sys.stderr)

        return 1

    errors: list[str] = []
    notices: list[str] = []

    files = wiki_files()
    link_graph: dict[Path, list[Path]] = {}
    today = date.today()

    for file in files:
        contents, encoding_error = read_page(file)
        if encoding_error is not None:
            errors.append(encoding_error)
        shown = file.relative_to(ROOT)
        relative_to_wiki = file.relative_to(WIKI).as_posix()
        is_generated = relative_to_wiki.startswith("index/")
        # raw/ — сырьё до разбора, правил там намеренно нет: требование структуры подняло бы
        # порог записи ровно там, где он должен быть нулевым. README самой папки — обычная
        # страница.
        is_raw = (
            relative_to_wiki.startswith("raw/") and relative_to_wiki != "raw/README.md"
        )
        lines = contents.split("\n")

        # Секреты проверяем и в raw/ — там нет линтера на форму, но утечка одинаково
        # необратима.
        if is_raw:
            for number, line in enumerate(lines, start=1):
                if looks_intentional(line):
                    continue
                for pattern, description in SECRET_PATTERNS:
                    if pattern.search(line):
                        errors.append(f"{shown}:{number}: {description} — {line.strip()}")
                        break

            continue

        # 1. Frontmatter
        frontmatter = parse_frontmatter(contents)

        if not frontmatter:
            errors.append(f"{shown}: нет frontmatter")
        else:
            for required in ("kind", "title", "owner", "verified"):
                if not frontmatter.get(required):
                    errors.append(f"{shown}: во frontmatter нет поля `{required}`")

            kind = frontmatter.get("kind")
            if isinstance(kind, str) and kind not in KINDS:
                errors.append(f"{shown}: неизвестный kind `{kind}`")

            verified = frontmatter.get("verified")
            if isinstance(verified, str) and not DATE_RE.match(verified):
                errors.append(f"{shown}: `verified` не дата: `{verified}`")
            elif isinstance(verified, str) and kind in ("guide", "runbook"):
                # research не стареет: его ценность в том, что он показывает состояние
                # на дату.
                age = (today - datetime.strptime(verified, "%Y-%m-%d").date()).days
                if age > STALE_DAYS:
                    owner = frontmatter.get("owner", "?")
                    notices.append(
                        f"{shown}: не проверялась {age} дней (владелец: {owner})"
                    )

        # 2. Ручные правки в сгенерированном
        if is_generated and "Сгенерировано." not in contents:
            errors.append(f"{shown}: лежит в index/, но не помечен как сгенерированный")

        # 3. Секреты
        for number, line in enumerate(lines, start=1):
            if looks_intentional(line):
                continue
            for pattern, description in SECRET_PATTERNS:
                if pattern.search(line):
                    errors.append(f"{shown}:{number}: {description} — {line.strip()}")
                    break

        # 4. Ссылки
        for match in LINK_RE.finditer(contents):
            raw_target = match.group(1)
            if EXTERNAL_RE.match(raw_target):
                continue

            # Якорь отбрасываем: проверяем существование файла, не раздела в нём.
            target = raw_target.split("#")[0]
            if not target:
                continue

            resolved = (file.parent / target).resolve()
            if not resolved.exists():
                line_number = contents.count("\n", 0, match.start()) + 1
                errors.append(f"{shown}:{line_number}: битая ссылка `{target}`")
                continue

            if not resolved.is_relative_to(WIKI):
                continue

            # Ссылка на папку делает достижимым всё, что в ней лежит: читатель, пришедший
            # в раздел, видит его содержимое.
            if resolved.is_dir():
                link_graph.setdefault(file, []).extend(sorted(resolved.glob("*.md")))
                continue

            link_graph.setdefault(file, []).append(resolved)

    # 5. Достижимость из README
    entry = WIKI / "README.md"
    if not entry.is_file():
        errors.append("wiki/README.md: нет точки входа")
    else:
        reached: set[Path] = set()
        queue = [entry]
        while queue:
            current = queue.pop()
            if current in reached:
                continue
            reached.add(current)
            queue.extend(link_graph.get(current, []))

        for file in files:
            # Записи в raw/ не должны быть в оглавлении: это сырьё до разбора, а не страницы.
            relative_to_wiki = file.relative_to(WIKI).as_posix()
            if (
                relative_to_wiki.startswith("raw/")
                and relative_to_wiki != "raw/README.md"
            ):
                continue

            if file not in reached:
                notices.append(f"{file.relative_to(ROOT)}: не достижима из README.md")

    # 6. Роль без страницы
    #
    # У krot нет openspec/specs/: он описывает не поведение приложения, а машину. Роль —
    # его единица знания, и она играет ту же роль, что capability в проектах-приложениях:
    # по ней строится обратная связь «какая страница это объясняет».
    covered: set[str] = set()
    for file in files:
        declared = parse_frontmatter(read_page(file)[0]).get("roles", [])
        if isinstance(declared, list):
            covered.update(declared)

    existing_roles = directories_in(ROOT / "roles")

    # Роль, объявленная страницей, но отсутствующая в roles/ — это та же битая ссылка:
    # читатель пойдёт за ролью и не найдёт её.
    for declared_role in sorted(covered):
        if declared_role not in existing_roles:
            errors.append(f"объявлена несуществующая роль `{declared_role}`")

    uncovered = [role for role in existing_roles if role not in covered]
    if uncovered:
        notices.append(
            f"не объяснены ни одной страницей: {len(uncovered)} из "
            f"{len(existing_roles)} ролей ({', '.join(uncovered)})"
        )

    # --- вывод ---------------------------------------------------------------

    if notices:
        print("Замечания (не валят сборку):")
        for notice in notices:
            print(f"  {notice}")
        print()

    if errors:
        print("Ошибки:")
        for error in errors:
            print(f"  {error}")
        print(f"\nОшибок: {len(errors)}")

        return 1

    print(f"Вики в порядке: {len(files)} страниц, ошибок нет.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
