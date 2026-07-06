#!/usr/bin/env python3
"""Terminal table layout helpers for vast-opstat TUI rendering."""

import re
import unicodedata

_ANSI_RE = re.compile(r"\033\[[^m]*m")

# ---------------------------------------------------------------------------
# ANSI colors (shared by every protocol engine)
# ---------------------------------------------------------------------------
_RST = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_MAGENTA = "\033[35m"
_CYAN = "\033[36m"
_BRED = "\033[1;31m"
_BGREEN = "\033[1;32m"
_BYELLOW = "\033[1;33m"
_BBLUE = "\033[1;34m"
_BMAGENTA = "\033[1;35m"
_BCYAN = "\033[1;36m"
_BWHITE = "\033[1;37m"

COLOR_ENABLED = False


def set_color(enabled):
    """Enable/disable ANSI colorization for :func:`c`."""
    global COLOR_ENABLED
    COLOR_ENABLED = bool(enabled)


def c(text, code):
    """Wrap *text* in ANSI *code* when color is enabled, else return it plain."""
    return f"{code}{text}{_RST}" if COLOR_ENABLED else text


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
