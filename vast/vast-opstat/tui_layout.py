#!/usr/bin/env python3
"""Terminal table layout helpers for vast-opstat TUI rendering."""

import re
import unicodedata

_ANSI_RE = re.compile(r"\033\[[^m]*m")


def strip_ansi(text):
    """Remove ANSI SGR escape sequences from *text*."""
    return _ANSI_RE.sub("", text or "")


def char_display_width(ch):
    """Return terminal column width for a single Unicode character."""
    o = ord(ch)
    if o < 32 or o == 0x7F:
        return 0
    cat = unicodedata.category(ch)
    if cat in ("Mn", "Me"):
        return 0
    eaw = unicodedata.east_asian_width(ch)
    if eaw in ("W", "F"):
        return 2
    return 1


def display_width(text):
    """Visual column width of *text*, ignoring ANSI escapes."""
    plain = strip_ansi(text)
    return sum(char_display_width(ch) for ch in plain)


def truncate_display(text, max_width, ellipsis="…"):
    """Truncate *text* to *max_width* display columns, appending *ellipsis* if needed."""
    if max_width <= 0:
        return ""
    if display_width(text) <= max_width:
        return text
    ell_w = display_width(ellipsis)
    if ell_w >= max_width:
        return ellipsis[:max_width]
    target = max_width - ell_w
    out = []
    width = 0
    for ch in text:
        cw = char_display_width(ch)
        if width + cw > target:
            break
        out.append(ch)
        width += cw
    return "".join(out) + ellipsis


def pad_display(text, width, align="<"):
    """Pad or truncate *text* to exactly *width* terminal columns."""
    text = "" if text is None else str(text)
    if display_width(text) > width:
        text = truncate_display(text, width)
    pad = max(0, width - display_width(text))
    if align == ">":
        return " " * pad + text
    if align == "^":
        left = pad // 2
        return " " * left + text + " " * (pad - left)
    return text + " " * pad


def join_columns(cells, sep=" "):
    """Join pre-sized table cells with a fixed separator."""
    return sep.join(cells)


def format_fixed_number(value, width, precision=2, empty="-"):
    """Right-align a numeric value (or placeholder) within *width* columns."""
    if value is None:
        return pad_display(empty, width, ">")
    try:
        text = f"{float(value):.{precision}f}"
    except (TypeError, ValueError):
        text = str(value)
    return pad_display(text, width, ">")


def format_scaled_metric(text, width, empty="-"):
    """Right-align a pre-formatted value+unit string within *width* columns."""
    if not text or text == empty:
        return pad_display(empty, width, ">")
    return pad_display(text, width, ">")
