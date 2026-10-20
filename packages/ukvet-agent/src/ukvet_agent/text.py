"""Text utilities shared by fact builders and the citation checker.

`extract_checkables` is the single definition of "a checkable value in prose" (dates and numbers).
Facts are tokenised with it when built, and claims are tokenised with it when checked, so the two
can never drift apart.
"""

import re
from dataclasses import dataclass, field
from datetime import date

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]  # fmt: skip
_MONTH_NUM = {m.lower(): i + 1 for i, m in enumerate(MONTHS)}

_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_LONG = re.compile(r"\b(\d{1,2})\s+(" + "|".join(MONTHS) + r")\s+(\d{4})\b", re.IGNORECASE)
_NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?!\w)")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def fmt_date(value: str | date | None) -> str:
    """'2019-03-04' -> '4 March 2019'. Unparseable values are returned unchanged."""
    if value is None or value == "":
        return "not recorded"
    try:
        d = value if isinstance(value, date) else date.fromisoformat(str(value))
    except ValueError:
        return str(value)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def plural(n: int, singular: str, plural_form: str | None = None) -> str:
    return f"{n} {singular if n == 1 else (plural_form or singular + 's')}"


def sanitise_registry_text(value: object, max_len: int = 200) -> str:
    """Make attacker-controllable registry text safe to embed in prompts and UIs.

    Anyone can register a company called 'Ignore previous instructions </registry_data>'. We strip
    control characters, neutralise angle brackets (so nobody can close our data delimiters),
    collapse whitespace and cap the length.
    """
    text = _CONTROL.sub(" ", str(value if value is not None else ""))
    text = text.replace("<", "‹").replace(">", "›")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def _norm_number(raw: str) -> str:
    """'7.0' -> '7', '6.90' -> '6.9'; integers (incl. leading zeros) are kept as written."""
    if "." in raw:
        raw = raw.rstrip("0").rstrip(".")
    return raw or "0"


@dataclass
class Checkables:
    dates: set[str] = field(default_factory=set)  # ISO dates
    numbers: set[str] = field(default_factory=set)  # normalised numeric strings


def extract_checkables(text: str) -> Checkables:
    """Find dates (ISO or 'D Month YYYY') and standalone numbers in prose."""
    found = Checkables()

    def take_iso(m: re.Match[str]) -> str:
        try:
            found.dates.add(date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat())
        except ValueError:
            found.numbers.update({m.group(1), m.group(2), m.group(3)})
        return " "

    def take_long(m: re.Match[str]) -> str:
        try:
            iso = date(int(m.group(3)), _MONTH_NUM[m.group(2).lower()], int(m.group(1)))
            found.dates.add(iso.isoformat())
        except ValueError:
            found.numbers.update({m.group(1), m.group(3)})
        return " "

    remainder = _ISO.sub(take_iso, text)
    remainder = _LONG.sub(take_long, remainder)
    found.numbers.update(_norm_number(n) for n in _NUM.findall(remainder))
    return found


def fact_tokens(
    statement: str, extra_numbers: tuple[object, ...] = (), extra_dates: tuple[str, ...] = ()
) -> Checkables:
    """Tokens a fact 'owns': whatever its statement contains, plus extras, plus each date's year
    (so 'in March 2019' and 'in 2019' are accepted when the fact holds 4 March 2019)."""
    tokens = extract_checkables(statement)
    tokens.dates.update(extra_dates)
    tokens.numbers.update(_norm_number(str(n)) for n in extra_numbers)
    for iso in tokens.dates:
        tokens.numbers.add(iso[:4])
    return tokens
