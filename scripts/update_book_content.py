"""Update knowledge entries in the 构建之法 shelf with actual chapter content from txt files.

Reads chapter text files from the source directory, splits content by section headings,
and updates the corresponding knowledge entries in the DuckDB database.

Usage:
    python scripts/update_book_content.py [--dry-run]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import duckdb

SHELF_DIR = Path.home() / ".hypatia" / "构建之法"
SOURCE_DIR = Path("/Users/mars/jobs/euclid/构建之法")
DB_PATH = SHELF_DIR / "data.duckdb"

# Pattern to match section headings like "6.1    敏捷的流程简介" or "6.2.1 实际项目的燃尽图"
SECTION_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(.+)$")


def parse_chapter(chapter_num: int, text: str) -> dict[str, str]:
    """Parse a chapter text file into a mapping of entry_name -> content.

    Returns:
        A dict with keys like "SE.06" (full chapter), "SE.06.section.6.1" (section).
    """
    prefix = f"SE.{chapter_num:02d}"
    lines = text.split("\n")
    entries: dict[str, str] = {}

    # Full chapter content (everything after the title)
    # Skip leading blank lines after chapter title
    content_start = 0
    for i, line in enumerate(lines):
        if line.strip() and not line.strip().startswith("第") and "章" not in line:
            content_start = i
            break
    entries[prefix] = "\n".join(lines[content_start:]).strip()

    # Split by section headings
    current_section: str | None = None
    current_lines: list[str] = []

    for line in lines:
        match = SECTION_RE.match(line.strip())
        if match:
            # Save previous section
            if current_section is not None:
                section_text = "\n".join(current_lines).strip()
                if section_text:
                    entries[current_section] = section_text

            section_num = match.group(1)
            section_title = match.group(2).strip()
            current_section = f"{prefix}.section.{section_num}"
            current_lines = []
        elif current_section is not None:
            current_lines.append(line)

    # Save last section
    if current_section is not None:
        section_text = "\n".join(current_lines).strip()
        if section_text:
            entries[current_section] = section_text

    return entries


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    conn = duckdb.connect(str(DB_PATH))

    # Get all existing SE.* entry names
    existing = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM knowledge WHERE name LIKE 'SE.%'"
        ).fetchall()
    }

    total_updated = 0
    total_skipped = 0

    for chapter_num in range(1, 18):
        txt_file = SOURCE_DIR / f"{chapter_num:02d}.txt"
        if not txt_file.exists():
            print(f"  SKIP: {txt_file.name} not found")
            continue

        text = txt_file.read_text(encoding="utf-8")
        entries = parse_chapter(chapter_num, text)

        prefix = f"SE.{chapter_num:02d}"
        print(f"\nCh {chapter_num:02d}: parsed {len(entries)} entries from {txt_file.name}")

        for entry_name, content in entries.items():
            if entry_name not in existing:
                total_skipped += 1
                print(f"  SKIP (not in DB): {entry_name}")
                continue

            # Truncate display
            preview = content[:60].replace("\n", " ") + ("..." if len(content) > 60 else "")

            if dry_run:
                print(f"  WOULD UPDATE: {entry_name} ({len(content)} chars)")
                print(f"    -> {preview}")
                total_updated += 1
            else:
                try:
                    # Read existing content JSON, update .data field, write back
                    row = conn.execute(
                        "SELECT content FROM knowledge WHERE name = ?",
                        [entry_name],
                    ).fetchone()
                    if row is None:
                        print(f"  ERROR: {entry_name} not found")
                        continue
                    obj = json.loads(row[0])
                    obj["data"] = content
                    new_json = json.dumps(obj, ensure_ascii=False)
                    conn.execute(
                        "UPDATE knowledge SET content = ? WHERE name = ?",
                        [new_json, entry_name],
                    )
                    total_updated += 1
                    print(f"  UPDATED: {entry_name} ({len(content)} chars)")
                    print(f"    -> {preview}")
                except Exception as e:
                    print(f"  ERROR: {entry_name}: {e}")

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Done: {total_updated} updated, {total_skipped} skipped")

    conn.close()


if __name__ == "__main__":
    main()
