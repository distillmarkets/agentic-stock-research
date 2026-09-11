"""Match a filer to a company name in an outside dataset, on the name alone.

Every dataset worth joining SEC filings to is keyed on a company name: a trial
registry, a patent assignee table, a layoff notice, a procurement award, a press
archive. None of them carries a CIK. ``docs/traps.md`` trap 19 measures what
that costs, and this module is the part that does the join once you have
accepted it has to be done on strings.

Nothing here touches the network and nothing here is specific to one source.
Give it ``{key: [names]}`` for the things you hold and a list of names from the
dataset you are joining to, and it returns the pairs plus the diagnostics a
study has to report.

The design, paid for by reading pairs by hand
---------------------------------------------
The obvious normalisation is to strip legal forms AND industry words and
compare what is left. It is a precision disaster. It collapses "Precision
Biosciences" into "Precision Biologics", "Voyager Therapeutics" into "Voyager
Pharmaceutical Corporation" and "Cornerstone Therapeutics" into "Cornerstone
Pharmaceuticals". Those are different companies. Reading 76 pairs from that
version by hand gave 54% precision. **The industry word is not noise, it is
half the identity**, so comparison happens on the name with only *corporate
forms* removed and the whole remaining phrase has to agree.

Every rule below exact equality also requires a shared **head token**. That is
the one thing about company names that carries: the identifying word comes
first and the descriptors follow. Without it "Praxis Precision Medicines"
matches "The Medicines Company". Adding the gate removed nine of the first ten
false positives.

What it scored where it was built
---------------------------------
On 684 filers against 16,062 ClinicalTrials.gov lead-sponsor names: **70.3%
matched (481 of 684) against 43.7% for an exact-token baseline**, at 98.5%
precision over 127 hand-read pairs. Ported unchanged to Texas layoff notices,
a completely different industry vocabulary, it reached 125 filers from 2,093
employer strings. Those rates belong to those datasets, not to this module; a
study using it reports its own, and reports them by hand-reading a sample.

``STOPWORDS`` is the vocabulary those numbers were measured on, and it is
deliberately shipped unchanged rather than generalised. Widening it is a
precision trade, not a free improvement. Adding "worldwide" and "partners" to
it while porting this module was tried and measured on layoff notices: it won
one true match, "Hilton Worldwide Holdings" to "Hilton", and lost one to a
false match, "Enterprise Products Partners LP", a pipeline operator, to
"Enterprise Holdings", a car rental firm. Pass ``extra_stopwords`` when your
domain needs a word treated as a descriptor, hand-read a sample afterwards, and
say in the study that you did.

    from distill_toolkit import names

    pairs, diag = names.match({"0000320193": ["APPLE INC"]}, ["Apple Inc."])
"""

from __future__ import annotations

import bisect
import re
from collections.abc import Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# vocabulary
# ---------------------------------------------------------------------------

#: Corporate-form tokens. These carry no identity: a company is the same
#: company whether it is an Inc, a Ltd or a GmbH.
LEGAL = frozenset({
    "inc", "incorporated", "corp", "corporation", "corporations",
    "co", "company", "companies", "ltd", "ltda", "limited", "llc", "lp", "llp",
    "plc", "the", "sa", "sas", "nv", "ag", "as", "ab", "oyj", "oy", "gmbh",
    "mbh", "kg", "kgaa", "kk", "aps", "spa", "srl", "bv", "pte", "pty", "pvt",
    "private", "holdings", "holding", "group", "groupe", "et", "al", "and",
    "of", "a",
})

#: Words too common to identify a company on their own. A one-token name made
#: only of these is refused, and a rule that drops tokens may only drop these.
#: This is the measured vocabulary; see the module docstring before widening it.
STOPWORDS = frozenset({
    "new", "first", "one", "two", "united", "general", "national", "advanced",
    "applied", "select", "premier", "prime", "next", "core", "pure", "true",
    "smart", "clear", "focus", "vision", "access", "summit", "capital", "north",
    "south", "east", "west", "central", "alliance", "network", "point", "path",
    "bridge", "spring", "phase", "trial", "study", "clinical", "cell", "cells",
    "gene", "genes", "protein", "molecular", "immune", "neuro", "cardio",
    "derma", "vascular", "surgical", "care", "life", "living", "human", "world",
    "health", "medical", "medicine", "pharma", "pharmaceutical",
    "pharmaceuticals", "therapeutics", "biosciences", "science", "sciences",
    "labs", "laboratories", "research", "global", "international", "america",
    "american", "usa", "technologies", "technology", "systems", "solutions",
    "products", "industries", "biotech", "biotechnology", "genomics", "genetics",
    "diagnostics", "devices", "oncology", "biologics", "bio", "medicines",
    "immunotherapeutics", "biopharma", "biopharmaceutical", "biopharmaceuticals",
    "biotherapeutics", "wellness", "nutrition", "immunotherapy", "vaccines",
})

#: Rules in the order they are tried. First hit wins, and a lower number is a
#: stronger claim of identity. A study reports its matches broken down by this.
ORDER = {"R1": 0, "R2": 1, "R3": 2, "R3b": 3}

_PUNCT = re.compile(r"[^a-z0-9]+")
# SEC registrant-name artifacts: "/DE/", "\DE", "/NEW/", "/FI", " ET AL".
_SEC_ARTIFACT = re.compile(r"[\\/][a-z]{2,4}[\\/]?\s*$|\bet\s+al\b", re.I)


# ---------------------------------------------------------------------------
# normalisation
# ---------------------------------------------------------------------------
def core(name: str) -> str:
    """The comparison unit: lowercased, punctuation-split, corporate forms out.

    Industry words survive on purpose. See the module docstring.
    """
    s = (name or "").lower().replace("&", " and ")
    s = _SEC_ARTIFACT.sub(" ", s)
    toks = [t for t in _PUNCT.split(s) if t]
    return " ".join(t for t in toks if t not in LEGAL)


def usable(c: str, *, extra_stopwords: Iterable[str] = ()) -> bool:
    """Is this core distinctive enough to match on at all?

    A single short token, a bare number, or a single stopword is not. Refusing
    them is what keeps "Care Inc" from matching every healthcare company in the
    other dataset.
    """
    if not c:
        return False
    toks = c.split()
    if len(toks) == 1:
        t = toks[0]
        stop = STOPWORDS | frozenset(extra_stopwords)
        if len(t) < 5 or t in stop or t.isdigit():
            return False
    return True


def _droppable(tok: str, stop: frozenset[str]) -> bool:
    """May this token be dropped without changing who the company is?

    Pure descriptors, plus one and two character fragments, which is what a
    state code or a registrant-name artifact looks like.
    """
    return len(tok) <= 2 or tok in stop


def _ok_alone(toks: set[str], stop: frozenset[str]) -> bool:
    """May this token set stand as evidence of identity by itself?"""
    if len(toks) >= 2:
        return True
    t = next(iter(toks))
    return len(t) >= 6 and t not in stop


def _flat(c: str) -> str:
    return c.replace(" ", "")


# ---------------------------------------------------------------------------
# the rules
# ---------------------------------------------------------------------------
def rule(a: str, b: str, *, extra_stopwords: Iterable[str] = ()) -> str | None:
    """Which rule matches two cores, or ``None``. First hit wins, in ``ORDER``.

    ``R1``  the cores are equal.
    ``R2``  a single-token name with a corporate tag glued on, at most two
            characters (Moderna to ModernaTX). A longer extension makes a
            different word and often a different company, so Immunogen does
            not match Immunogenics. This is the one rule that varies the head
            token, so it runs before the head gate rather than under it.
    ``R3``  the other name is this one plus a place or a division (Incyte to
            Incyte Biosciences Japan), at most two extra tokens.
    ``R3b`` the other name is this one with descriptors dropped (Albireo Pharma
            to Albireo). Everything dropped has to BE a descriptor.
    """
    if a == b:
        return "R1"

    stop = STOPWORDS | frozenset(extra_stopwords)
    at, bt = a.split(), b.split()

    if len(at) == 1 and len(bt) == 1:
        x, y = at[0], bt[0]
        short, long_ = (x, y) if len(x) <= len(y) else (y, x)
        if (long_.startswith(short) and len(short) >= 6
                and 1 <= len(long_) - len(short) <= 2
                and len(short) >= 0.70 * len(long_)):
            return "R2"

    if at[0] != bt[0]:
        return None
    ats, bts = set(at), set(bt)

    if ats < bts and _ok_alone(ats, stop) and len(bts - ats) <= 2:
        return "R3"
    if bts < ats and _ok_alone(bts, stop) and all(_droppable(t, stop) for t in ats - bts):
        return "R3b"
    return None


# ---------------------------------------------------------------------------
# the join
# ---------------------------------------------------------------------------
def match(aliases: Mapping[str, Sequence[str]], candidates: Iterable[str], *,
          extra_stopwords: Iterable[str] = ()) -> tuple[list[dict], dict]:
    """Join ``{key: [names]}`` to ``candidates`` on the name alone.

    ``aliases`` is what you hold: one key, usually a CIK, and every name you
    know that key by. Former names belong here, and adding them is the cheapest
    recall a caller has. ``candidates`` is the name column of the other dataset.

    Returns ``(pairs, diag)``. Each pair is
    ``{key, alias, aliasCore, candidate, candidateCore, rule}``.

    **A candidate name claimed by more than one key is dropped whole**, both
    ways, rather than assigned to a guess. That trades recall for precision on
    purpose: an ambiguous match is a wrong row in a study, and a dropped one is
    a number in ``diag`` that the study reports.

    ``diag`` carries what a study has to state: how many names went in, how
    many keys had nothing usable to match on, how many pairs were dropped for
    ambiguity, and the breakdown by rule. Report it. The match rate on its own
    is not a coverage claim, because the keys that carry no usable name never
    had a chance to match and belong in the denominator.
    """
    aliases = dict(aliases)
    cand_core: dict[str, list[str]] = {}
    n_in = 0
    for n in candidates:
        n_in += 1
        c = core(n)
        if usable(c, extra_stopwords=extra_stopwords):
            cand_core.setdefault(c, []).append(n)

    # Blocking: a candidate is only compared when it shares a token, or a
    # six-character prefix once spaces are removed. Every rule requires one or
    # the other, so this changes speed and not results.
    by_token: dict[str, set[str]] = {}
    flat_to_core: dict[str, list[str]] = {}
    for c in cand_core:
        for t in c.split():
            by_token.setdefault(t, set()).add(c)
        flat_to_core.setdefault(_flat(c), []).append(c)
    flats = sorted(flat_to_core)

    raw: list[dict] = []
    unmatchable: list[str] = []
    for key, names in aliases.items():
        hits: dict[str, tuple[str, str, str]] = {}
        any_usable = False
        for alias in names:
            ac = core(alias)
            if not usable(ac, extra_stopwords=extra_stopwords):
                continue
            any_usable = True
            cands: set[str] = set()
            for t in ac.split():
                cands |= by_token.get(t, set())
            fa = _flat(ac)[:6]
            i = bisect.bisect_left(flats, fa)
            while i < len(flats) and flats[i][:6] == fa:
                cands |= set(flat_to_core[flats[i]])
                i += 1
            for cc in cands:
                r = rule(ac, cc, extra_stopwords=extra_stopwords)
                if r is None:
                    continue
                prev = hits.get(cc)
                if prev is None or ORDER[r] < ORDER[prev[2]]:
                    hits[cc] = (alias, ac, r)
        if not any_usable:
            unmatchable.append(key)
            continue
        for cc, (alias, ac, r) in hits.items():
            for name in cand_core[cc]:
                raw.append({"key": key, "alias": alias, "aliasCore": ac,
                            "candidate": name, "candidateCore": cc, "rule": r})

    owners: dict[str, set[str]] = {}
    for p in raw:
        owners.setdefault(p["candidate"], set()).add(p["key"])
    ambiguous = {c for c, ks in owners.items() if len(ks) > 1}
    pairs = [p for p in raw if p["candidate"] not in ambiguous]

    diag = {
        "candidateNamesIn": n_in,
        "candidateCoresUsable": len(cand_core),
        "keysWithAliases": len(aliases),
        "keysUnmatchableByName": len(unmatchable),
        "rawPairs": len(raw),
        "ambiguousCandidateNames": len(ambiguous),
        "pairsDroppedForAmbiguity": len(raw) - len(pairs),
        "keysMatched": len({p["key"] for p in pairs}),
        "byRule": {r: sum(1 for p in pairs if p["rule"] == r) for r in ORDER},
        "unmatchableKeys": unmatchable,
        "ambiguousNames": sorted(ambiguous),
    }
    return pairs, diag
