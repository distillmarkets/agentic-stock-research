"""Tests for distill_toolkit.names.

Every company name below is synthetic and invented; no real company, filer or
outside dataset appears here. The cases are not arbitrary: each one
encodes a false positive that was found by reading pairs by hand, so a change
that makes one of these pass differently is a change that costs precision in
the field. The module docstring names the counts.
"""

import pytest

from distill_toolkit import names


# ---------------------------------------------------------------------------
# core
# ---------------------------------------------------------------------------
def test_core_strips_corporate_forms_but_not_industry_words():
    assert names.core("Invented Alpha Therapeutics, Inc.") == "invented alpha therapeutics"
    assert names.core("INVENTED ALPHA THERAPEUTICS INC") == "invented alpha therapeutics"


def test_core_strips_sec_registrant_artifacts():
    assert names.core("INVENTED BETA CORP /DE/") == "invented beta"
    assert names.core("INVENTED BETA CORP ET AL") == "invented beta"


def test_core_folds_ampersand_and_punctuation():
    # "&" becomes "and", which is itself a corporate-form token and goes.
    assert names.core("Invented Gamma & Delta Co.") == "invented gamma delta"
    assert names.core("Invented-Gamma/Delta") == "invented gamma delta"


@pytest.mark.parametrize("bad", ["", "care", "bio", "1234", "abcd"])
def test_usable_refuses_a_single_token_that_identifies_nothing(bad):
    assert names.usable(names.core(bad)) is False


def test_usable_accepts_a_distinctive_single_token_and_any_pair():
    assert names.usable(names.core("Zorbix")) is True
    assert names.usable(names.core("Care Holdings Corp")) is False  # "care" alone
    assert names.usable(names.core("Zorbix Care")) is True


def test_extra_stopwords_narrows_what_a_lone_token_may_be():
    assert names.usable("zorbix") is True
    assert names.usable("zorbix", extra_stopwords={"zorbix"}) is False


# ---------------------------------------------------------------------------
# rules
# ---------------------------------------------------------------------------
def test_r1_is_equality_after_normalisation():
    assert names.rule(names.core("Invented Alpha Inc"), names.core("INVENTED ALPHA")) == "R1"


def test_r2_allows_a_two_character_corporate_tag():
    assert names.rule("zorbixon", "zorbixonpq") == "R2"


def test_r2_refuses_a_longer_extension_that_makes_another_word():
    # Invented Immunogen against Invented Immunogenics: three characters, and
    # in the field these were two different companies.
    assert names.rule("zorbigen", "zorbigenics") is None


def test_r3_allows_a_place_or_division_suffix():
    assert names.rule("zorbix", "zorbix biosciences japan") == "R3"


def test_r3_refuses_more_than_two_extra_tokens():
    assert names.rule("zorbix", "zorbix biosciences japan holdings unit alpha") is None


def test_r3b_drops_descriptors_only():
    assert names.rule("zorbix pharma", "zorbix") == "R3b"
    # "delta" is not a descriptor, so dropping it is not allowed.
    assert names.rule("zorbix delta", "zorbix") is None


def test_the_head_token_gate_blocks_a_shared_tail():
    # "Praxis Precision Medicines" against "The Medicines Company" was the
    # shape of nine of the first ten false positives.
    assert names.rule(names.core("Zorbix Precision Medicines"),
                      names.core("The Medicines Company")) is None


def test_the_industry_word_is_half_the_identity():
    # Stripping industry words would collapse these. They are different firms.
    a, b = names.core("Precision Zorbiciences"), names.core("Precision Zorbilogics")
    assert a != b
    assert names.rule(a, b) is None


# ---------------------------------------------------------------------------
# match
# ---------------------------------------------------------------------------
def test_match_finds_the_pair_and_records_the_rule():
    pairs, diag = names.match({"111": ["Invented Alpha Corp"]}, ["Invented Alpha"])
    assert len(pairs) == 1
    assert pairs[0]["key"] == "111"
    assert pairs[0]["candidate"] == "Invented Alpha"
    assert pairs[0]["rule"] == "R1"
    assert diag["keysMatched"] == 1
    assert diag["byRule"]["R1"] == 1


def test_a_former_name_is_the_cheapest_recall_there_is():
    aliases = {"111": ["Zorbix Holdings Inc", "Invented Alpha Corp"]}
    pairs, _ = names.match(aliases, ["Invented Alpha"])
    assert [p["alias"] for p in pairs] == ["Invented Alpha Corp"]


def test_a_candidate_claimed_by_two_keys_is_dropped_whole():
    aliases = {"111": ["Invented Alpha Corp"], "222": ["Invented Alpha Inc"]}
    pairs, diag = names.match(aliases, ["Invented Alpha"])
    assert pairs == []
    assert diag["ambiguousCandidateNames"] == 1
    assert diag["pairsDroppedForAmbiguity"] == 2
    assert diag["keysMatched"] == 0


def test_a_key_with_no_usable_name_is_counted_not_silently_lost():
    aliases = {"111": ["Care Inc"], "222": ["Invented Alpha Corp"]}
    pairs, diag = names.match(aliases, ["Invented Alpha"])
    assert diag["keysWithAliases"] == 2
    assert diag["keysUnmatchableByName"] == 1
    assert diag["unmatchableKeys"] == ["111"]
    assert diag["keysMatched"] == 1
    assert len(pairs) == 1


def test_the_strongest_rule_wins_when_several_apply():
    # One alias reaches the candidate under R1, another under R3.
    aliases = {"111": ["Invented Alpha", "Invented Alpha Japan"]}
    pairs, _ = names.match(aliases, ["Invented Alpha"])
    assert len(pairs) == 1
    assert pairs[0]["rule"] == "R1"


def test_every_spelling_of_one_candidate_core_comes_back():
    pairs, diag = names.match({"111": ["Invented Alpha Corp"]},
                              ["Invented Alpha", "INVENTED ALPHA INC", "Invented Alpha, Co."])
    assert {p["candidate"] for p in pairs} == {
        "Invented Alpha", "INVENTED ALPHA INC", "Invented Alpha, Co."}
    assert diag["candidateNamesIn"] == 3
    assert diag["candidateCoresUsable"] == 1


def test_no_match_returns_empty_with_the_counts_intact():
    pairs, diag = names.match({"111": ["Invented Alpha Corp"]}, ["Unrelated Zorbix Ltd"])
    assert pairs == []
    assert diag["keysMatched"] == 0
    assert diag["keysUnmatchableByName"] == 0
    assert diag["candidateCoresUsable"] == 1


def test_extra_stopwords_reaches_the_rules_through_match():
    # R3b may only drop a descriptor. "delta" is not one by default, so the
    # pair is refused; declaring it a descriptor for this domain admits it.
    # This is the knob a study turns when the vocabulary is not pharmaceutical.
    aliases = {"111": ["Zorbix Delta"]}
    assert names.match(aliases, ["Zorbix"])[0] == []
    pairs, _ = names.match(aliases, ["Zorbix"], extra_stopwords={"delta"})
    assert [p["rule"] for p in pairs] == ["R3b"]


# ---------------------------------------------------------------------------
# vocabulary regressions
#
# Both cases below were found by widening STOPWORDS while porting this module,
# and both are why it was reverted. They are kept as tests so the next person to
# widen it has to look at them.
# ---------------------------------------------------------------------------
def test_a_descriptor_that_is_part_of_the_name_is_not_a_corporate_form():
    # "Corps" here is half of "Job Corps" and is not a corporate form. Putting
    # it in LEGAL deleted it and left a different organisation behind.
    assert "corps" in names.core("Invented Connects (Zorbix Job Corps)")


def test_widening_the_descriptor_list_costs_precision():
    # Two unrelated companies that share only a head token and some
    # descriptors. They must not match on the shipped vocabulary.
    a = names.core("Zorbix Products Partners L.P.")
    b = names.core("Zorbix Holdings, LLC")
    assert names.rule(a, b) is None
    # Declaring "partners" a descriptor is what collapses them, which is the
    # trade a caller is making when they pass extra_stopwords.
    assert names.rule(a, b, extra_stopwords={"partners"}) == "R3b"
