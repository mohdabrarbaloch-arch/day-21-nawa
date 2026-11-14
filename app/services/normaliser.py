"""Turn written text into what a person would actually say out loud.

This is the part of a speech product that people notice only when it is
missing. Ask a synthesiser to read "Rs 1,50,000" and you get letter soup.
Ask it to read "15/11/2026" and you get fifteen slash eleven slash two
thousand and twenty six.

The module works by protecting what must not be touched, then applying
rewrite rules in a deliberate order. Order matters: dates and times have to
run before bare integers, or "09:30" becomes "nine colon thirty".
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Word tables
# ---------------------------------------------------------------------------

_ONES = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)

_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")

_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

_ORDINAL_WORDS = {
    1: "first",
    2: "second",
    3: "third",
    4: "fourth",
    5: "fifth",
    6: "sixth",
    7: "seventh",
    8: "eighth",
    9: "ninth",
    10: "tenth",
    11: "eleventh",
    12: "twelfth",
    13: "thirteenth",
    14: "fourteenth",
    15: "fifteenth",
    16: "sixteenth",
    17: "seventeenth",
    18: "eighteenth",
    19: "nineteenth",
    20: "twentieth",
    30: "thirtieth",
    40: "fortieth",
    50: "fiftieth",
    60: "sixtieth",
    70: "seventieth",
    80: "eightieth",
    90: "ninetieth",
}

# Spoken forms for things that are written as symbols.
_SYMBOLS = (
    ("&", " and "),
    (" @ ", " at "),
    (" + ", " plus "),
    (" = ", " equals "),
    (" %", " percent"),
    ("%", " percent"),
    ("°C", " degrees celsius"),
    ("°F", " degrees fahrenheit"),
    ("km/h", " kilometres per hour"),
    ("mpg", " miles per gallon"),
)

# Abbreviations that must be expanded before the letters get read one by one.
_ABBREVIATIONS = (
    (r"\bMr\.", "Mister"),
    (r"\bMrs\.", "Missus"),
    (r"\bMs\.", "Miss"),
    (r"\bDr\.(?=\s+[A-Z])", "Doctor"),
    (r"\bProf\.", "Professor"),
    (r"\bSr\.", "Senior"),
    (r"\bJr\.", "Junior"),
    (r"\bvs\.", "versus"),
    (r"\bvs\b", "versus"),
    (r"\betc\.", "et cetera."),
    (r"\be\.g\.", "for example"),
    (r"\bi\.e\.", "that is"),
    (r"\bapprox\.", "approximately"),
    (r"\bNo\.(?=\s*\d)", "number"),
    (r"\bSt\.(?=\s+[A-Z])", "Saint"),
    (r"\bAve\b", "Avenue"),
    (r"\bRd\b", "Road"),
)

_CURRENCY = {
    "rs": "rupees",
    "rs.": "rupees",
    "pkr": "rupees",
    "inr": "rupees",
    "₨": "rupees",
    "$": "dollars",
    "usd": "dollars",
    "£": "pounds",
    "gbp": "pounds",
    "€": "euros",
    "eur": "euros",
    "aed": "dirhams",
    "sar": "riyals",
}

# Placeholders must contain no ASCII digits, or the integer rule would eat
# the index. Private-use code points are outside every pattern we run.
_GUARD_OPEN = "\ue000"
_GUARD_CLOSE = "\ue001"


def _guard_for(index: int) -> str:
    return (
        _GUARD_OPEN + chr(0xE010 + index) + _GUARD_CLOSE
        if index < 10
        else (_GUARD_OPEN + "".join(chr(0xE010 + int(d)) for d in str(index)) + _GUARD_CLOSE)
    )


_PROTECTED = re.compile(
    r"(?:https?://[^\s]+|www\.[^\s]+|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)


# ---------------------------------------------------------------------------
# Integer to words
# ---------------------------------------------------------------------------


def _below_hundred(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] if ones == 0 else f"{_TENS[tens]}-{_ONES[ones]}"


def _below_thousand(n: int) -> str:
    if n < 100:
        return _below_hundred(n)
    hundreds, rest = divmod(n, 100)
    head = f"{_ONES[hundreds]} hundred"
    return head if rest == 0 else f"{head} {_below_hundred(rest)}"


def _western(n: int) -> str:
    """Group in thousands: million / billion, the way most of the world reads."""
    if n < 1000:
        return _below_thousand(n)

    parts: list[str] = []
    for divisor, label in ((1_000_000_000, "billion"), (1_000_000, "million"), (1_000, "thousand")):
        if n >= divisor:
            count, n = divmod(n, divisor)
            parts.append(f"{_below_thousand(count)} {label}")
    if n:
        parts.append(_below_thousand(n))
    return " ".join(parts)


def _south_asian(n: int) -> str:
    """Group in lakhs and crores: 1,50,000 is one lakh fifty thousand."""
    if n < 100_000:
        return _western(n)

    parts: list[str] = []
    crore, n = divmod(n, 10_000_000)
    lakh, n = divmod(n, 100_000)
    thousand, rest = divmod(n, 1000)

    if crore:
        parts.append(f"{_western(crore)} crore")
    if lakh:
        parts.append(f"{_below_thousand(lakh)} lakh")
    if thousand:
        parts.append(f"{_below_thousand(thousand)} thousand")
    if rest:
        parts.append(_below_thousand(rest))
    return " ".join(parts)


def int_to_words(n: int, *, south_asian: bool = False) -> str:
    if n < 0:
        return f"minus {int_to_words(-n, south_asian=south_asian)}"
    return _south_asian(n) if south_asian else _western(n)


def _ordinal_to_words(n: int) -> str:
    if n in _ORDINAL_WORDS:
        return _ORDINAL_WORDS[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return f"{_TENS[tens]}-{_ORDINAL_WORDS[ones]}"
    return str(n)


def _year_to_words(n: int) -> str:
    """Read a four digit year the way people say it aloud."""
    if 2000 <= n <= 2009:
        return "two thousand" if n == 2000 else f"two thousand and {_ONES[n - 2000]}"
    if 2010 <= n <= 2099:
        return f"twenty {_below_hundred(n - 2000)}"
    if 1000 <= n <= 1999:
        head, tail = divmod(n, 100)
        return (
            f"{_below_thousand(head)} {_below_hundred(tail)}"
            if tail
            else f"{_below_thousand(head)} hundred"
        )
    return int_to_words(n)


def _decimal_to_words(raw: str) -> str:
    """3.50 -> three point five zero. Digits after the point are read singly."""
    whole, frac = raw.split(".", 1)
    whole_words = int_to_words(int(whole)) if whole else "zero"
    frac_words = " ".join(_ONES[int(d)] for d in frac)
    return f"{whole_words} point {frac_words}"


# ---------------------------------------------------------------------------
# Grouping detection
# ---------------------------------------------------------------------------

# 1,50,000 style: first group of 1-2 digits, then pairs, then a final three.
_INDIAN_GROUPING = re.compile(r"^\d{1,2}(?:,\d{2})*,\d{3}$")
_WESTERN_GROUPING = re.compile(r"^\d{1,3}(?:,\d{3})+$")

# Boundaries that mean "this integer is not part of a larger word".
# Lookbehinds must be fixed width in Python's re, so currency is handled by
# running the currency rules first and leaving this to guard the residue.
#
# The guard characters are listed explicitly: they are private-use code points
# and Python's \w does not treat them as word characters, so without this a
# protected fragment like "45/13/2026" would still be reached by the integer
# rule and turned into "forty-five/thirteen/...".
_G = "\ue000\ue001"
_LEFT = rf"(?<![\w.,{_G}])"
_RIGHT = rf"(?![\w{_G}]|\.\d)"


def _replace_number(
    raw: str,
    *,
    currency: str | None,
    as_year: bool = False,
    force_south_asian: bool = False,
) -> str:
    digits = raw.replace(",", "")
    if not digits.isdigit():
        return raw

    n = int(digits)
    south_asian = force_south_asian or bool(_INDIAN_GROUPING.match(raw))

    if as_year:
        words = _year_to_words(n)
    elif south_asian or (currency in {"rupees"} and n >= 100_000):
        words = _south_asian(n)
    else:
        words = _western(n)

    return f"{words} {currency}" if currency else words


# ---------------------------------------------------------------------------
# Individual rewriting rules
# ---------------------------------------------------------------------------


def _normalise_dates(text: str, protected: list[str]) -> str:
    def dmy(m: re.Match[str]) -> str:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= d <= 31 and 1 <= mo <= 12):
            return m.group(0)
        month = _MONTHS[mo - 1]
        day = _ordinal_to_words(d)
        return f"the {day} of {month} {_year_to_words(y)}"

    # A date-shaped string that is not a real date must be left exactly as
    # written. Otherwise "45/13/2026" becomes "forty-five/thirteen/...".
    def dmy_guard(m: re.Match[str]) -> str:
        d, mo = int(m.group(1)), int(m.group(2))
        if 1 <= d <= 31 and 1 <= mo <= 12:
            return dmy(m)
        # Not a real date. Hand it to the registry so no later rule sees it.
        protected.append(m.group(0))
        return _guard_for(len(protected) - 1)

    # 15/11/2026 or 15-11-2026
    text = re.sub(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", dmy_guard, text)

    def ymd(m: re.Match[str]) -> str:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= d <= 31 and 1 <= mo <= 12):
            return m.group(0)
        return f"the {_ordinal_to_words(d)} of {_MONTHS[mo - 1]} {_year_to_words(y)}"

    # 2026-11-15
    return re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", ymd, text)


def _normalise_times(text: str, protected: list[str]) -> str:
    def hm(m: re.Match[str]) -> str:
        h, mi = int(m.group(1)), int(m.group(2))
        if h > 23 or mi > 59:
            return m.group(0)
        suffix = m.group(3) or ""
        hour = h % 12 or 12
        hour_words = _below_hundred(hour)
        if mi == 0:
            spoken = f"{hour_words} o'clock"
        else:
            spoken = f"{hour_words} {_below_hundred(mi) if mi >= 10 else 'oh ' + _ONES[mi]}"
        if suffix:
            spoken = f"{spoken} {suffix.strip().lower().replace('.', ' ').replace(' ', '')}"
            spoken = spoken.replace("am", "a m").replace("pm", "p m")
            if suffix.rstrip().endswith("."):
                spoken += "."
        return spoken

    def hm_guard(m: re.Match[str]) -> str:
        h, mi = int(m.group(1)), int(m.group(2))
        if h > 23 or mi > 59:
            protected.append(m.group(0))
            return _guard_for(len(protected) - 1)
        return hm(m)

    return re.sub(r"\b(\d{1,2}):(\d{2})(\s*[ap]\.?m\.?)?", hm_guard, text, flags=re.IGNORECASE)


def _normalise_currency(text: str) -> str:
    keys = "|".join(re.escape(k) for k in sorted(_CURRENCY, key=len, reverse=True))

    # Rs 1,50,000 / PKR 5000 / $1,299
    # \d+ first, then optional grouping: "2500" must not be read as "250".
    pattern = re.compile(
        rf"(?P<cur>{keys})\s*(?P<num>\d+(?:,\d{{2,3}})*(?:\.\d+)?)",
        flags=re.IGNORECASE,
    )

    def repl(m: re.Match[str]) -> str:
        raw_cur = m.group("cur").lower().strip()
        unit = _CURRENCY.get(raw_cur) or _CURRENCY.get(raw_cur.rstrip("."), "")
        if not unit:
            return m.group(0)
        num = m.group("num")
        if "." in num:
            return f"{_decimal_to_words(num)} {unit}"
        return _replace_number(num, currency=unit)

    text = pattern.sub(repl, text)

    # Number first: 1,50,000 rupees
    suffix_pattern = re.compile(
        r"(?<![A-Za-z0-9])(?P<num>\d{1,3}(?:,\d{2,3})+|\d+)\s+"
        r"(?P<cur>rupees|dollars|pounds|euros|dirhams|riyals)\b",
        flags=re.IGNORECASE,
    )

    def suffix_repl(m: re.Match[str]) -> str:
        return _replace_number(m.group("num"), currency=m.group("cur").lower())

    return suffix_pattern.sub(suffix_repl, text)


def _normalise_ordinals(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        n = int(m.group(1))
        return _ordinal_to_words(n)

    return re.sub(r"\b(\d{1,3})(?:st|nd|rd|th)\b", repl, text, flags=re.IGNORECASE)


def _normalise_magnitudes(text: str) -> str:
    """Handle "2.5 million", "Rs 3 crore", "500 thousand".

    Runs before the currency rule so a magnitude and its unit are spoken in
    the right order. Without this, "$2.5 million" becomes "two point five
    dollars million".
    """
    magnitude_words = (
        "trillion",
        "billion",
        "million",
        "crore",
        "crores",
        "lakh",
        "lakhs",
        "thousand",
    )
    keys = "|".join(re.escape(k) for k in sorted(_CURRENCY, key=len, reverse=True))
    # The currency prefix swallows its own trailing space. Keeping the space
    # outside that group stops "for 500 thousand" becoming "forfive hundred".
    pattern = re.compile(
        rf"(?<!\w)(?:(?P<pre>{keys})\s*)?(?P<num>\d[\d,]*(?:\.\d+)?)\s*"
        rf"(?P<mag>{'|'.join(magnitude_words)})(?![\w])",
        flags=re.IGNORECASE,
    )

    def repl(m: re.Match[str]) -> str:
        num = m.group("num")
        mag = m.group("mag").lower().rstrip("s")
        if "." in num:
            spoken = _decimal_to_words(num.replace(",", ""))
        else:
            spoken = _western(int(num.replace(",", "")))
        out = f"{spoken} {mag}"
        pre = (m.group("pre") or "").lower().strip()
        unit = _CURRENCY.get(pre) or _CURRENCY.get(pre.rstrip("."), "")
        return f"{out} {unit}" if unit else out

    return pattern.sub(repl, text)


def _normalise_phones(text: str) -> str:
    """Spell phone numbers out digit by digit.

    Only fires on shapes that look like a phone number: a leading plus, a
    leading zero, or an internal separator with enough digits to rule out a
    reformatted quantity.
    """
    pattern = re.compile(r"(?<![\w])(\+?\d[\d\s\-().]{6,}\d)(?![\w])")

    def repl(m: re.Match[str]) -> str:
        raw = m.group(1)
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 7:
            return raw
        looks_like_phone = raw.startswith("+") or digits.startswith("0") or "-" in raw
        if not looks_like_phone:
            return raw
        spoken = " ".join(_ONES[int(d)] for d in digits)
        return f"plus {spoken}" if raw.startswith("+") else spoken

    return pattern.sub(repl, text)


def _normalise_decimals(text: str) -> str:
    return re.sub(
        rf"{_LEFT}(\d{{1,3}}(?:,\d{{3}})*)\.(\d+)",
        lambda m: _decimal_to_words(f"{m.group(1).replace(',', '')}.{m.group(2)}"),
        text,
    )


# Words that introduce a year: "in 2026", "since 1999".
_YEAR_LEAD = re.compile(
    r"(?:\b(?:in|since|by|from|until|till|during|year|of|early|late|mid)\s+)$",
    re.IGNORECASE,
)


def _normalise_integers(text: str) -> str:
    pattern = re.compile(rf"{_LEFT}(\d{{1,3}}(?:,\d{{2,3}})*|\d+){_RIGHT}")

    def repl(m: re.Match[str]) -> str:
        raw = m.group(1)
        digits = raw.replace(",", "")

        # A four digit number is read as a year only when the surrounding
        # words say so. "in 2026" is a year; "1000 days" is a quantity, and
        # reading it as "ten hundred" would be wrong.
        as_year = False
        if len(digits) == 4 and 1000 <= int(digits) <= 2099:
            before = text[: m.start()]
            after = text[m.end() :]
            followed_by_end = not after or after[0] in ".,;:!?)\n"
            as_year = bool(_YEAR_LEAD.search(before)) or followed_by_end

        return _replace_number(raw, currency=None, as_year=as_year)

    return pattern.sub(repl, text)


def _normalise_abbreviations(text: str) -> str:
    for pattern, replacement in _ABBREVIATIONS:
        text = re.sub(pattern, replacement, text)
    return text


def _normalise_symbols(text: str) -> str:
    for symbol, spoken in _SYMBOLS:
        text = text.replace(symbol, spoken)
    return text


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def normalise(text: str, *, apply: bool = True) -> str:
    """Return text ready to hand to a synthesiser.

    ``apply=False`` returns the input unchanged so callers can offer a
    raw mode for text that is already spelled the way it should sound.
    """
    if not apply or not text:
        return text or ""

    # 1. Protect things that would be destroyed by later rules. URLs, emails
    #    and invalid dates/times all share one registry.
    guarded: list[str] = []

    def guard(m: re.Match[str]) -> str:
        guarded.append(m.group(0))
        return _guard_for(len(guarded) - 1)

    out = _PROTECTED.sub(guard, text)

    # 2. Rules, most specific first. Dates and times must precede integers.
    out = _normalise_abbreviations(out)
    out = _normalise_dates(out, guarded)
    out = _normalise_times(out, guarded)
    out = _normalise_magnitudes(out)
    out = _normalise_currency(out)
    out = _normalise_ordinals(out)
    out = _normalise_phones(out)
    out = _normalise_decimals(out)
    out = _normalise_integers(out)
    out = _normalise_symbols(out)

    # 3. Restore protected spans.
    for index, original in enumerate(guarded):
        out = out.replace(_guard_for(index), original)

    # 4. Tidy whitespace without touching intentional paragraph breaks.
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r" *\n *", "\n", out)
    return out.strip()


def apply_lexicon(text: str, entries: dict[str, str]) -> str:
    """Apply user pronunciation overrides.

    Longer keys win, and matching is whole-word so "Nawa" inside "Nawaz"
    is left alone. Entries are escaped, so a key containing regex
    metacharacters is safe.
    """
    if not entries:
        return text

    for written in sorted(entries, key=len, reverse=True):
        spoken = entries[written]
        if not written or not spoken:
            continue
        pattern = re.compile(rf"(?<![\w'-]){re.escape(written)}(?![\w'-])", re.IGNORECASE)
        text = pattern.sub(spoken, text)
    return text
