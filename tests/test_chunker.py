"""Chunker behaviour: sentence boundaries, limits, and no lost text."""

import pytest

from app.services import chunker


class TestBasicSplitting:
    def test_single_short_sentence(self):
        assert chunker.split("Hello there.") == ["Hello there."]

    def test_two_sentences_under_limit_stay_together(self):
        chunks = chunker.split("First one. Second one.")
        assert len(chunks) == 1
        assert "First one." in chunks[0]

    def test_empty_input(self):
        assert chunker.split("") == []

    def test_whitespace_only(self):
        assert chunker.split("   \n  ") == []

    def test_paragraph_break_splits(self):
        chunks = chunker.split("First paragraph here.\n\nSecond paragraph here.")
        assert len(chunks) == 2


class TestLimits:
    def test_respects_max_chars(self):
        text = " ".join(["This is a sentence that repeats itself."] * 20)
        chunks = chunker.split(text, max_chars=120)
        assert all(len(c) <= 120 for c in chunks)

    def test_rejects_tiny_max(self):
        with pytest.raises(ValueError):
            chunker.split("hello", max_chars=10)

    def test_long_sentence_split_on_clauses(self):
        text = (
            "The first clause is here, the second clause follows it, "
            "and the third clause closes the sentence out completely."
        )
        chunks = chunker.split(text, max_chars=60)
        assert len(chunks) > 1
        assert all(len(c) <= 60 for c in chunks)

    def test_very_long_word_run_hard_split(self):
        text = " ".join(["word"] * 200)
        chunks = chunker.split(text, max_chars=80)
        assert all(len(c) <= 80 for c in chunks)


class TestContentPreservation:
    def test_no_words_lost(self):
        text = "Alpha beta gamma. Delta epsilon zeta. Eta theta iota."
        chunks = chunker.split(text, max_chars=40)
        joined = " ".join(chunks)
        for word in ["Alpha", "gamma", "Delta", "zeta", "Eta", "iota"]:
            assert word in joined

    def test_short_tail_merged(self):
        # A two-word tail should not be sent to the synthesiser alone.
        text = "A reasonably long opening sentence that fills the space. Yes."
        chunks = chunker.split(text, max_chars=120, min_chars=40)
        assert chunks[-1] != "Yes."

    def test_merge_never_exceeds_limit(self):
        # Merging a short tail must not push a chunk past the limit.
        text = " ".join(["word"] * 200)
        chunks = chunker.split(text, max_chars=80)
        assert all(len(c) <= 80 for c in chunks)

    def test_order_preserved(self):
        text = "One. Two. Three. Four. Five."
        chunks = chunker.split(text, max_chars=45)
        assert chunks == sorted(chunks, key=lambda c: text.index(c))


class TestEstimate:
    def test_estimate_positive(self):
        assert chunker.estimate_seconds(["a" * 145]) == pytest.approx(10.0, abs=0.1)

    def test_estimate_empty(self):
        assert chunker.estimate_seconds([]) == 0.0
