#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import sys
import unicodedata
from typing import Iterable, List, Sequence


SCHEMAS = {
    "vless": [
        {"name": "NAME",  "min":  8, "ideal": 15, "max": 32, "align": "left",  "weight": 10},
        {"name": "STATE", "min":  6, "ideal":  6, "max":  8, "align": "left",  "weight":  1},
        {"name": "PORT",  "min":  5, "ideal":  5, "max":  5, "align": "right", "weight":  1},
        {"name": "LISN",  "min":  4, "ideal":  4, "max":  4, "align": "left",  "weight":  1},
        {"name": "QUOTA", "min":  6, "ideal":  6, "max":  6, "align": "left",  "weight":  1},
        {"name": "LIMIT", "min":  7, "ideal":  8, "max": 12, "align": "right", "weight":  1},
        {"name": "USED",  "min":  7, "ideal":  8, "max": 12, "align": "right", "weight":  1},
        {"name": "LEFT",  "min":  7, "ideal":  8, "max": 12, "align": "right", "weight":  1},
        {"name": "USE%",  "min":  6, "ideal":  6, "max":  6, "align": "right", "weight":  1},
        {"name": "TTL",   "min":  6, "ideal":  8, "max": 12, "align": "left",  "weight":  2},
        {"name": "EXPBJ", "min":  8, "ideal": 12, "max": 19, "align": "left",  "weight":  3},
        {"name": "IPLM",  "min":  4, "ideal":  4, "max":  4, "align": "right", "weight":  1},
        {"name": "IPACT", "min":  5, "ideal":  5, "max":  5, "align": "right", "weight":  1},
        {"name": "STKY",  "min":  4, "ideal":  4, "max":  4, "align": "right", "weight":  1},
    ],
    "pq": [
        {"name": "PORT",   "min":  5, "ideal":  5, "max":  5, "align": "right", "weight":  1},
        {"name": "OWNER",  "min": 10, "ideal": 20, "max": 40, "align": "left",  "weight": 10},
        {"name": "STATE",  "min":  6, "ideal":  6, "max":  8, "align": "left",  "weight":  1},
        {"name": "LIMIT",  "min":  7, "ideal":  8, "max": 12, "align": "right", "weight":  1},
        {"name": "USED",   "min":  7, "ideal":  8, "max": 12, "align": "right", "weight":  1},
        {"name": "LEFT",   "min":  7, "ideal":  8, "max": 12, "align": "right", "weight":  1},
        {"name": "USE%",   "min":  6, "ideal":  6, "max":  6, "align": "right", "weight":  1},
        {"name": "RESET",  "min":  5, "ideal":  5, "max":  8, "align": "left",  "weight":  1},
        {"name": "NEXTBJ", "min":  8, "ideal": 12, "max": 19, "align": "left",  "weight":  3},
    ],
}


def char_width(ch: str) -> int:
    if not ch or ch in "\n\r" or unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def text_width(text: str) -> int:
    return sum(char_width(ch) for ch in text)


def take_prefix(text: str, width: int):
    out: List[str] = []
    used = 0
    idx = 0
    while idx < len(text):
        ch = text[idx]
        if ch == "\n":
            idx += 1
            break
        w = char_width(ch)
        if used + w > width:
            break
        out.append(ch)
        used += w
        idx += 1
    return "".join(out), text[idx:]


def split_point(text: str, width: int) -> int:
    prefix, _ = take_prefix(text, width)
    if len(prefix) == len(text):
        return len(text)
    for i in range(len(prefix) - 1, -1, -1):
        ch = prefix[i]
        prev = prefix[i - 1] if i > 0 else ""
        if ch.isspace():
            return i + 1
        if ch in "/_-:@":
            return i + 1
        if i > 0 and prev.isdigit() and ch.isalpha():
            return i
    return len(prefix)


def wrap_cell(text: str, width: int) -> List[str]:
    text = "-" if text in (None, "") else str(text)
    text = text.replace("\r", "")
    lines: List[str] = []
    for part in text.split("\n"):
        part = part.strip()
        if not part:
            lines.append("")
            continue
        while part:
            if text_width(part) <= width:
                lines.append(part)
                break
            cut = split_point(part, width)
            left = part[:cut].rstrip()
            part = part[cut:].lstrip()
            if not left:
                left, part = take_prefix(part, width)
            lines.append(left)
    return lines or ["-"]


def pad(text: str, width: int, align: str) -> str:
    text = "" if text is None else str(text)
    if text_width(text) > width:
        text = take_prefix(text, width)[0]
    spaces = " " * max(0, width - text_width(text))
    return spaces + text if align == "right" else text + spaces


def border(left: str, mid: str, right: str, widths: Sequence[int]) -> str:
    return left + mid.join("━" * w for w in widths) + right


def terminal_columns() -> int:
    env_cols = os.environ.get("COLUMNS", "").strip()
    if env_cols.isdigit() and int(env_cols) > 0:
        return int(env_cols)
    return shutil.get_terminal_size(fallback=(120, 24)).columns


def allocate_widths(schema: Sequence[dict]) -> List[int]:
    mins = [c["min"] for c in schema]
    ideals = [c["ideal"] for c in schema]
    maxs = [c["max"] for c in schema]
    weights = [max(1, int(c.get("weight", 1))) for c in schema]

    widths = ideals[:]
    available = max(sum(mins), terminal_columns() - (len(schema) + 1))
    current = sum(widths)

    if current > available:
        deficit = current - available
        order = sorted(range(len(schema)), key=lambda i: (weights[i], ideals[i] - mins[i]), reverse=True)
        changed = True
        while deficit > 0 and changed:
            changed = False
            for i in order:
                if deficit <= 0:
                    break
                if widths[i] > mins[i]:
                    widths[i] -= 1
                    deficit -= 1
                    changed = True
    elif current < available:
        extra = available - current
        order = sorted(range(len(schema)), key=lambda i: (weights[i], maxs[i] - ideals[i]), reverse=True)
        changed = True
        while extra > 0 and changed:
            changed = False
            for i in order:
                if extra <= 0:
                    break
                if widths[i] < maxs[i]:
                    widths[i] += 1
                    extra -= 1
                    changed = True
    return widths


def render_rows(schema_name: str, rows: Iterable[Sequence[str]]) -> str:
    if schema_name not in SCHEMAS:
        raise ValueError(f"unknown schema: {schema_name}")
    schema = SCHEMAS[schema_name]
    headers = [c["name"] for c in schema]
    aligns = [c["align"] for c in schema]
    widths = allocate_widths(schema)

    normalized = []
    for row in rows:
        cols = list(row[: len(schema)])
        if len(cols) < len(schema):
            cols.extend([""] * (len(schema) - len(cols)))
        normalized.append(cols)

    if not normalized:
        normalized = [["-"] * len(schema)]

    out = [border("┏", "┳", "┓", widths)]
    out.append("┃" + "│".join(pad(h, w, "left") for h, w in zip(headers, widths)) + "┃")
    out.append(border("┣", "╋", "┫", widths))

    for idx, row in enumerate(normalized):
        wrapped = [wrap_cell(col, width) for col, width in zip(row, widths)]
        height = max(len(parts) for parts in wrapped)
        for line_no in range(height):
            rendered = []
            for col_idx, parts in enumerate(wrapped):
                text = parts[line_no] if line_no < len(parts) else ""
                rendered.append(pad(text, widths[col_idx], aligns[col_idx]))
            out.append("┃" + "│".join(rendered) + "┃")
        if idx != len(normalized) - 1:
            out.append(border("┣", "╋", "┫", widths))
    out.append(border("┗", "┻", "┛", widths))
    return "\n".join(out)


def main(argv: Sequence[str]) -> int:
    if len(argv) != 2 or argv[1] not in SCHEMAS:
        print("usage: render_table.py <vless|pq>", file=sys.stderr)
        return 2
    rows = []
    for raw in sys.stdin:
        raw = raw.rstrip("\n")
        if not raw:
            continue
        rows.append(raw.split("\t"))
    print(render_rows(argv[1], rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

