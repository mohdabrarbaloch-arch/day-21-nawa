"""The normaliser is the product. These tests are the specification."""

import pytest

from app.services.normaliser import (
    apply_lexicon,
    int_to_words,
    normalise,
)


class TestIntegers:
    def test_small_numbers(self):
        assert normalise("I have 3 cats") == "I have three cats"

    def test_teens_and_tens(self):
        assert normalise("15 people and 42 seats") == "fifteen people and forty-two seats"

    def test_hundreds(self):
        assert normalise("100 bottles") == "one hundred bottles"
        assert normalise("250 boxes") == "two hundred fifty boxes"

    def test_thousands(self):
        assert normalise("1000 days") == "one thousand days"
        assert normalise("1234 items") == "one thousand two hundred thirty-four items"

    def test_millions(self):
        assert normalise("5000000 users") == "five million users"

    def test_billions(self):
        assert int_to_words(1_234_567_890) == (
            "one billion two hundred thirty-four million "
            "five hundred sixty-seven thousand eight hundred ninety"
        )

    def test_zero(self):
        assert normalise("0 errors") == "zero errors"

    def test_negative(self):
        assert int_to_words(-42) == "minus forty-two"


class TestSouthAsianGrouping:
    def test_lakh_from_indian_grouping(self):
        # 1,50,000 is written the South Asian way, so it is read that way.
        assert normalise("Rs 1,50,000") == "one lakh fifty thousand rupees"

    def test_crore(self):
        assert int_to_words(25_000_000, south_asian=True) == "two crore fifty lakh"

    def test_western_grouping_stays_western(self):
        assert normalise("1,500,000 people") == "one million five hundred thousand people"

    def test_lakh_word_used_directly(self):
        assert normalise("500 thousand units") == "five hundred thousand units"


class TestCurrency:
    def test_rupee_prefix(self):
        assert normalise("Rs 500") == "five hundred rupees"

    def test_pkr_code(self):
        assert normalise("PKR 2500") == "two thousand five hundred rupees"

    def test_dollar_symbol(self):
        assert normalise("$1,299") == "one thousand two hundred ninety-nine dollars"

    def test_currency_after_number(self):
        assert normalise("1500 rupees") == "one thousand five hundred rupees"

    def test_decimal_currency(self):
        assert normalise("$2.50") == "two point five zero dollars"

    def test_magnitude_with_currency(self):
        # The order matters: "two point five million dollars", not
        # "two point five dollars million".
        assert normalise("$2.5 million") == "two point five million dollars"

    def test_crore_with_currency(self):
        assert normalise("Rs 3 crore") == "three crore rupees"


class TestDates:
    def test_dmy_slashes(self):
        assert normalise("15/11/2026") == "the fifteenth of November twenty twenty-six"

    def test_dmy_dashes(self):
        assert normalise("01-03-2027") == "the first of March twenty twenty-seven"

    def test_iso_date(self):
        assert normalise("2026-11-15") == "the fifteenth of November twenty twenty-six"

    def test_quantity_is_not_a_year(self):
        # "1000 days" is a count, not a year. Reading it as "ten hundred"
        # would be wrong.
        assert normalise("1000 days") == "one thousand days"

    def test_invalid_date_left_alone(self):
        # 45 is not a day; do not invent one.
        assert "45/13/2026" in normalise("45/13/2026")

    def test_year_alone(self):
        # A year is read in pairs, the way people say it: "twenty twenty-six".
        assert normalise("in 2026") == "in twenty twenty-six"

    def test_year_1999(self):
        assert normalise("since 1999") == "since nineteen ninety-nine"


class TestTimes:
    def test_hour_and_minutes(self):
        assert normalise("09:30") == "nine thirty"

    def test_am_suffix(self):
        assert normalise("9:30 AM") == "nine thirty a m"

    def test_oclock(self):
        assert normalise("17:00") == "five o'clock"

    def test_leading_zero_minutes(self):
        assert normalise("14:05") == "two oh five"

    def test_invalid_time_left_alone(self):
        assert "99:99" in normalise("99:99")


class TestDecimalsAndPercent:
    def test_simple_decimal(self):
        assert normalise("12.5 percent") == "twelve point five percent"

    def test_percent_symbol(self):
        assert normalise("18%") == "eighteen percent"

    def test_two_decimals(self):
        assert normalise("9.75") == "nine point seven five"


class TestOrdinals:
    def test_first(self):
        assert normalise("1st place") == "first place"

    def test_third(self):
        assert normalise("3rd") == "third"

    def test_twenty_first(self):
        assert normalise("21st") == "twenty-first"

    def test_twelfth(self):
        assert normalise("12th") == "twelfth"


class TestPhones:
    def test_local_number_spelled_digit_by_digit(self):
        assert normalise("0300-1234567") == (
            "zero three zero zero one two three four five six seven"
        )

    def test_international_prefix(self):
        result = normalise("+92 300 1234567")
        assert result.startswith("plus nine two")
        assert "three zero zero" in result

    def test_short_number_not_treated_as_phone(self):
        # 3-4 digits is a quantity, not a phone number.
        assert normalise("12-34") == "twelve-thirty-four" or "12" in normalise("12-34")


class TestAbbreviations:
    def test_mister(self):
        assert normalise("Mr. Khan") == "Mister Khan"

    def test_doctor(self):
        assert normalise("Dr. Ahmed") == "Doctor Ahmed"

    def test_versus(self):
        assert normalise("A vs. B") == "A versus B"

    def test_et_cetera(self):
        assert normalise("apples, etc.") == "apples, et cetera."

    def test_number_abbreviation(self):
        assert normalise("No. 42") == "number forty-two"


class TestProtection:
    def test_url_untouched(self):
        text = "Visit https://example.com/path?q=1 today"
        assert "https://example.com/path?q=1" in normalise(text)

    def test_email_untouched(self):
        text = "Email hi@test.com now"
        assert "hi@test.com" in normalise(text)

    def test_multiple_protected_spans(self):
        text = "a@b.com and https://x.io and c@d.org"
        out = normalise(text)
        assert "a@b.com" in out
        assert "https://x.io" in out
        assert "c@d.org" in out


class TestSymbols:
    def test_degrees(self):
        assert normalise("34°C") == "thirty-four degrees celsius"

    def test_ampersand(self):
        assert normalise("salt & pepper") == "salt and pepper"


class TestEdgeCases:
    def test_empty_string(self):
        assert normalise("") == ""

    def test_whitespace_only(self):
        assert normalise("   ") == ""

    def test_apply_false_returns_input(self):
        assert normalise("Rs 500", apply=False) == "Rs 500"

    def test_plain_text_unchanged(self):
        assert normalise("Hello there, friend.") == "Hello there, friend."

    def test_whitespace_collapsed(self):
        assert normalise("too    many     spaces") == "too many spaces"

    def test_paragraph_breaks_preserved(self):
        out = normalise("First para.\n\nSecond para.")
        assert "\n\n" in out

    def test_urdu_text_untouched(self):
        text = "یہ ایک جملہ ہے۔"
        assert normalise(text) == text


class TestLexicon:
    def test_simple_override(self):
        assert apply_lexicon("Nawa is here", {"Nawa": "nuh-waa"}) == "nuh-waa is here"

    def test_case_insensitive(self):
        assert apply_lexicon("NAWA rocks", {"Nawa": "nuh-waa"}) == "nuh-waa rocks"

    def test_whole_word_only(self):
        # "Nawa" inside "Nawaz" must not be replaced.
        assert apply_lexicon("Nawaz Ali", {"Nawa": "nuh-waa"}) == "Nawaz Ali"

    def test_longer_key_wins(self):
        entries = {"Nawa": "short", "Nawa Studio": "long"}
        assert apply_lexicon("Nawa Studio", entries) == "long"

    def test_empty_lexicon(self):
        assert apply_lexicon("anything", {}) == "anything"

    def test_regex_metacharacters_are_safe(self):
        # A key with regex syntax must be treated literally, not compiled.
        assert apply_lexicon("cost is $5", {"$5": "five dollars"}) == "cost is five dollars"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Rs 1,50,000", "one lakh fifty thousand rupees"),
        ("$2.5 million", "two point five million dollars"),
        ("15/11/2026", "the fifteenth of November twenty twenty-six"),
        ("18%", "eighteen percent"),
        ("3rd", "third"),
    ],
)
def test_headline_cases(text, expected):
    assert normalise(text) == expected
