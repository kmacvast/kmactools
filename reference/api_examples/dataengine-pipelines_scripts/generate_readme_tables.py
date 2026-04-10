#!/usr/bin/env python3
"""Generate pipeline tables in README.md from registry.json."""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
REGISTRY_PATH = REPO_ROOT / "registry.json"
README_PATH = REPO_ROOT / "README.md"

SCRIPT_NAME = Path(__file__).stem

SECTION_MARKERS = {
    "in-repo": (
        f"<!-- {SCRIPT_NAME}:in-repo:start -->",
        f"<!-- {SCRIPT_NAME}:in-repo:end -->",
    ),
    "vast-org": (
        f"<!-- {SCRIPT_NAME}:vast-org:start -->",
        f"<!-- {SCRIPT_NAME}:vast-org:end -->",
    ),
    "community": (
        f"<!-- {SCRIPT_NAME}:community:start -->",
        f"<!-- {SCRIPT_NAME}:community:end -->",
    ),
}


def sanitize(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").replace("\r", "")


def make_table(headers: list[str], rows: list[list[str]]) -> str:
    header_row = "| " + " | ".join(headers) + " |"
    separator = "|" + "|".join("---" for _ in headers) + "|"
    data_rows = ["| " + " | ".join(sanitize(cell) for cell in row) + " |" for row in rows]
    return "\n".join([header_row, separator] + data_rows)


def build_tables(entries: list[dict]) -> dict[str, str]:
    in_repo, vast_org, community = [], [], []

    for e in entries:
        section = e.get("section", "")
        name = e.get("name", "")
        runtime = e.get("runtime", "")
        description = e.get("description", "")

        if section == "in-repo":
            link = e.get("link", "")
            link_cell = f"[link]({link})" if link and link != "<link>" else ""
            if e.get("status") == "planned":
                description = f"**Coming soon:** {description}"
            in_repo.append([name, e.get("trigger", ""), runtime, link_cell, description])
        elif section == "vast-org":
            repo = e.get("repo", "")
            repo_link = f"[link]({repo})" if repo else ""
            vast_org.append([name, runtime, repo_link, description])
        elif section == "community":
            repo = e.get("repo", "")
            repo_link = f"[link]({repo})" if repo else ""
            community.append([name, runtime, repo_link, e.get("author", ""), description])

    return {
        "in-repo": make_table(["Pipeline", "Trigger", "Runtime", "Link", "Description"], in_repo),
        "vast-org": make_table(["Pipeline", "Runtime", "Repo", "Description"], vast_org),
        "community": make_table(["Pipeline", "Runtime", "Repo", "Author", "Description"], community),
    }


def inject_tables(readme: str, tables: dict[str, str]) -> str:
    for section, (start_marker, end_marker) in SECTION_MARKERS.items():
        table = tables[section]
        pattern = re.compile(
            rf"{re.escape(start_marker)}.*?{re.escape(end_marker)}",
            re.DOTALL,
        )
        replacement = f"{start_marker}\n{table}\n{end_marker}"
        if pattern.search(readme):
            readme = pattern.sub(replacement, readme)
        else:
            print(f"Warning: markers not found for section '{section}' — skipping.")
    return readme


def main() -> None:
    entries = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    tables = build_tables(entries)

    readme = README_PATH.read_text(encoding="utf-8")
    updated = inject_tables(readme, tables)

    if updated == readme:
        print("README.md is already up to date.")
        return

    README_PATH.write_text(updated, encoding="utf-8")
    print("README.md updated.")


if __name__ == "__main__":
    sys.exit(main())
