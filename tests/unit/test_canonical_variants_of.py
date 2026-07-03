# SPDX-License-Identifier: Apache-2.0
"""Unit tests for canonical_variants_of() — the DRY helper (#242) that consolidates
the canonical reverse-lookup + NFC normalization shared by classify_query,
_relation_match_count, and ask_router.

These tests are engine-free and read-only — the aliases dict (raw -> canonical) is
built directly, so no policy file / accepted.dl is required.
"""
from __future__ import annotations

import unicodedata

import factlog.common as fcommon


class TestCanonicalVariantsOf:
    """Reverse lookup of surface variants for a declared canonical relation."""

    def test_declared_canonical_returns_variant_set(self):
        """A canonical returns exactly the raw predicates that map to it."""
        aliases = {
            "게재연도": "published_year",
            "publication_year": "published_year",
            "저자": "author",
        }
        assert fcommon.canonical_variants_of("published_year", aliases) == {
            "게재연도",
            "publication_year",
        }

    def test_nfd_input_relation_matches_nfc_alias_value(self):
        """An NFD-composed relation arg still matches an NFC canonical alias value.

        relation_aliases() NFC-normalizes on load, so both alias keys and values are
        NFC. A query may arrive NFD-composed; the helper NFC-normalizes the relation
        arg so the reverse lookup against the NFC canonical value succeeds.
        """
        canonical_nfc = unicodedata.normalize("NFC", "게재연도")  # NFC canonical value
        aliases = {"publication_year": canonical_nfc, "pub_yr": canonical_nfc}
        query_nfd = unicodedata.normalize("NFD", "게재연도")  # NFD-composed query name
        assert query_nfd != canonical_nfc  # precondition: forms genuinely differ
        # Without normalization an NFD arg would miss the NFC value; the helper fixes it.
        assert fcommon.canonical_variants_of(query_nfd, aliases) == {
            "publication_year",
            "pub_yr",
        }

    def test_unknown_relation_returns_empty_set(self):
        """A relation that is not a declared canonical yields an empty (falsy) set."""
        aliases = {"게재연도": "published_year"}
        result = fcommon.canonical_variants_of("not_a_canonical", aliases)
        assert result == set()
        assert not result  # the boolean "not a declared canonical" use

    def test_empty_aliases_returns_empty_set(self):
        """No aliases -> empty set regardless of the relation name."""
        assert fcommon.canonical_variants_of("published_year", {}) == set()


class TestRelationMatchCountAliasThreading:
    """_relation_match_count reuses a caller-supplied aliases dict (#242).

    classify_query already reads relation_aliases() for the canonical-acceptance
    check; threading that single read into _relation_match_count removes the
    per-relation-query double read while keeping the count byte-identical. When no
    aliases is passed the original lazy per-call fetch is preserved.
    """

    def _facts(self):
        # 게재연도 is a surface variant of the canonical published_year; a
        # canonical query must count this variant row.
        return [
            {"subject": "책", "relation": "게재연도", "object": "2020"},
            {"subject": "책", "relation": "저자", "object": "김작가"},
        ]

    def test_passed_aliases_matches_lazy_fetch(self, monkeypatch):
        """A supplied aliases dict yields the identical count to the lazy path."""
        aliases = {"게재연도": "published_year"}
        query = 'relation("책", "published_year", "2020")?'
        monkeypatch.setattr(fcommon, "relation_aliases", lambda *a, **k: aliases)
        lazy = fcommon._relation_match_count(query, self._facts())
        threaded = fcommon._relation_match_count(query, self._facts(), aliases)
        assert lazy == threaded == 1

    def test_passed_aliases_skips_relation_aliases_read(self, monkeypatch):
        """Supplying aliases avoids re-reading the policy file (re-fetch removed)."""
        def _boom(*a, **k):
            raise AssertionError("relation_aliases() must not be re-read when aliases is supplied")

        monkeypatch.setattr(fcommon, "relation_aliases", _boom)
        query = 'relation("책", "published_year", "2020")?'
        assert fcommon._relation_match_count(query, self._facts(), {"게재연도": "published_year"}) == 1

    def test_lazy_path_still_reads_relation_aliases(self, monkeypatch):
        """Complement: the aliases=None path still fetches once for a quoted relation."""
        calls: list[int] = []

        def _tracked(*a, **k):
            calls.append(1)
            return {"게재연도": "published_year"}

        monkeypatch.setattr(fcommon, "relation_aliases", _tracked)
        query = 'relation("책", "published_year", "2020")?'
        assert fcommon._relation_match_count(query, self._facts()) == 1
        assert calls == [1]
