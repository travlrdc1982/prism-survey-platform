"""
Tests for page flow engine — get_next_page(), build_page_sequence(),
evaluate_condition(), should_show_page().

Covers the AL study sequence, critics rotation, conditional display logic,
and post-test ordering rules per the PRISM build brief §1.1.
"""

import json
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add platform/ to path so we can import the page flow functions directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "platform"))

from page_flow import (
    build_page_sequence,
    evaluate_condition,
    should_show_page,
    get_next_page,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def al_config():
    """Load the real AL study config."""
    config_path = Path(__file__).resolve().parent.parent / "configs" / "AL.json"
    with open(config_path) as f:
        return json.load(f)


def _make_session(splits=None, responses=None):
    """Create a mock session with configurable splits and responses."""
    session = MagicMock()
    session.get_splits.return_value = splits or {}
    session.get_all_responses.return_value = responses or {}
    return session


# ── build_page_sequence tests ───────────────────────────────────────────────

class TestBuildPageSequence:
    """Test that build_page_sequence produces the correct ordered page list."""

    def test_al_sequence_starts_with_pre_test(self, al_config):
        session = _make_session()
        seq = build_page_sequence(al_config, session)
        assert seq[0] == "pre_test.SECTORFAV"

    def test_al_sequence_contains_all_pre_test_questions(self, al_config):
        session = _make_session()
        seq = build_page_sequence(al_config, session)
        pre_test_pages = [p for p in seq if p.startswith("pre_test.")]
        expected_vars = [
            "SECTORFAV", "CORPFAV", "INVEST_AWARE", "INVEST_AWARE_OE",
            "INVEST_AWARE_CO", "JOBALIGNA", "JOBALIGNB", "FUTUREJOB",
            "JOBMOST", "JOBLEAST", "AL_PRE_RANK", "AL_PRE",
        ]
        assert pre_test_pages == [f"pre_test.{v}" for v in expected_vars]

    def test_al_sequence_inf360_after_pre_test(self, al_config):
        session = _make_session()
        seq = build_page_sequence(al_config, session)
        last_pre = max(i for i, p in enumerate(seq) if p.startswith("pre_test."))
        assert seq[last_pre + 1] == "inf360"

    def test_al_sequence_investment_before_maxdiff(self, al_config):
        session = _make_session()
        seq = build_page_sequence(al_config, session)
        inv_idx = seq.index("investment")
        md_idx = seq.index("msg_maxdiff")
        assert inv_idx < md_idx

    def test_al_sequence_post_test_after_maxdiff(self, al_config):
        session = _make_session()
        seq = build_page_sequence(al_config, session)
        md_idx = seq.index("msg_maxdiff")
        first_post = next(i for i, p in enumerate(seq) if p.startswith("post_test."))
        assert first_post > md_idx

    def test_al_sequence_post_test_order_locked(self, al_config):
        """Post-test variables must appear in exactly the same order as config."""
        session = _make_session()
        seq = build_page_sequence(al_config, session)
        post_test_pages = [p for p in seq if p.startswith("post_test.")]
        assert post_test_pages == [
            "post_test.AL_POST",
            "post_test.AL_POST_RANK",
            "post_test.CORPFAV_POST",
        ]

    def test_al_sequence_mob_after_post_test(self, al_config):
        session = _make_session()
        seq = build_page_sequence(al_config, session)
        last_post = max(i for i, p in enumerate(seq) if p.startswith("post_test."))
        assert seq[last_post + 1] == "mob_battery"

    def test_al_sequence_adv_after_mob(self, al_config):
        session = _make_session()
        seq = build_page_sequence(al_config, session)
        mob_idx = seq.index("mob_battery")
        adv_pages = [p for p in seq if p.startswith("adv_battery.")]
        first_adv_idx = seq.index(adv_pages[0])
        assert first_adv_idx > mob_idx

    def test_al_sequence_adv_questions(self, al_config):
        session = _make_session()
        seq = build_page_sequence(al_config, session)
        adv_pages = [p for p in seq if p.startswith("adv_battery.")]
        assert adv_pages == [
            "adv_battery.AL_ADV_P1",
            "adv_battery.AL_ADV_P2",
            "adv_battery.AL_ADV_P2n",
        ]

    def test_al_sequence_bespoke_after_adv(self, al_config):
        session = _make_session()
        seq = build_page_sequence(al_config, session)
        last_adv = max(i for i, p in enumerate(seq) if p.startswith("adv_battery."))
        bespoke_pages = [p for p in seq if p.startswith("bespoke.")]
        assert seq.index(bespoke_pages[0]) > last_adv

    def test_al_sequence_bespoke_questions(self, al_config):
        session = _make_session()
        seq = build_page_sequence(al_config, session)
        bespoke_pages = [p for p in seq if p.startswith("bespoke.")]
        assert bespoke_pages == [
            "bespoke.PHRMA01",
            "bespoke.PHRMA02",
            "bespoke.PHRMA03",
            "bespoke.PHRMA04",
        ]

    def test_al_sequence_ends_with_demographics_then_optin(self, al_config):
        session = _make_session()
        seq = build_page_sequence(al_config, session)
        assert seq[-2] == "demographics"
        assert seq[-1] == "opt_in"

    def test_al_no_critics_blocks_when_disabled(self, al_config):
        """AL config has critics_enabled=false, so no critics blocks."""
        session = _make_session()
        seq = build_page_sequence(al_config, session)
        assert "critics_block_a" not in seq
        assert "critics_block_b" not in seq

    def test_critics_blocks_present_when_enabled(self, al_config):
        """When critics_enabled=true, both blocks appear in correct positions."""
        config = dict(al_config)
        config["critics_enabled"] = True
        config["critics_battery"] = {"questions": [{"var": "CRITIC_1"}]}
        session = _make_session()
        seq = build_page_sequence(config, session)
        assert "critics_block_a" in seq
        assert "critics_block_b" in seq
        # Block A before MaxDiff, Block B after
        a_idx = seq.index("critics_block_a")
        md_idx = seq.index("msg_maxdiff")
        b_idx = seq.index("critics_block_b")
        assert a_idx < md_idx < b_idx

    def test_no_awareness_info_issues_for_al(self, al_config):
        """AL config has no awareness/info_channels/issue_views sections."""
        session = _make_session()
        seq = build_page_sequence(al_config, session)
        assert not any(p.startswith("awareness.") for p in seq)
        assert not any(p.startswith("info_channels.") for p in seq)
        assert not any(p.startswith("issue_views.") for p in seq)


# ── evaluate_condition tests ────────────────────────────────────────────────

class TestEvaluateCondition:

    def test_empty_condition_returns_true(self):
        session = _make_session()
        assert evaluate_condition("", session) is True

    def test_none_condition_returns_true(self):
        session = _make_session()
        assert evaluate_condition(None, session) is True

    def test_split_condition_matches(self):
        session = _make_session(splits={"Xrandom2": "r1"})
        assert evaluate_condition("Xrandom2.r1", session) is True

    def test_split_condition_no_match(self):
        session = _make_session(splits={"Xrandom2": "r2"})
        assert evaluate_condition("Xrandom2.r1", session) is False

    def test_split_condition_missing_split(self):
        session = _make_session(splits={})
        assert evaluate_condition("Xrandom2.r1", session) is False

    def test_if_condition_matches(self):
        session = _make_session(responses={"MAHA_AWARE": 2})
        assert evaluate_condition("IF MAHA_AWARE=1,2,3 THEN show MAHA_PERCEP", session) is True

    def test_if_condition_no_match(self):
        session = _make_session(responses={"MAHA_AWARE": 5})
        assert evaluate_condition("IF MAHA_AWARE=1,2,3 THEN show MAHA_PERCEP", session) is False

    def test_if_condition_missing_var(self):
        session = _make_session(responses={})
        assert evaluate_condition("IF MAHA_AWARE=1,2,3 THEN show MAHA_PERCEP", session) is False

    def test_cond_prefix_format(self):
        session = _make_session(responses={"MAHA_AWARE": 1})
        assert evaluate_condition("COND: IF MAHA_AWARE=1,2,3 THEN show MAHA_PERCEP", session) is True


# ── should_show_page tests (critics rotation) ──────────────────────────────

class TestShouldShowPage:

    def test_critics_block_a_shows_for_r1(self, al_config):
        session = _make_session(splits={"xrandom4": "r1"})
        assert should_show_page("critics_block_a", al_config, session) is True

    def test_critics_block_a_hidden_for_r2(self, al_config):
        session = _make_session(splits={"xrandom4": "r2"})
        assert should_show_page("critics_block_a", al_config, session) is False

    def test_critics_block_b_shows_for_r2(self, al_config):
        session = _make_session(splits={"xrandom4": "r2"})
        assert should_show_page("critics_block_b", al_config, session) is True

    def test_critics_block_b_hidden_for_r1(self, al_config):
        session = _make_session(splits={"xrandom4": "r1"})
        assert should_show_page("critics_block_b", al_config, session) is False

    def test_layer1_pages_always_show(self, al_config):
        session = _make_session()
        for page in ("inf360", "demographics", "opt_in", "msg_maxdiff",
                      "investment", "mob_battery"):
            assert should_show_page(page, al_config, session) is True

    def test_conditional_pre_test_question_shown(self, al_config):
        """JOBALIGNA requires Xrandom2.r1 — should show when condition met."""
        session = _make_session(splits={"Xrandom2": "r1"})
        assert should_show_page("pre_test.JOBALIGNA", al_config, session) is True

    def test_conditional_pre_test_question_hidden(self, al_config):
        """JOBALIGNA requires Xrandom2.r1 — should hide when r2."""
        session = _make_session(splits={"Xrandom2": "r2"})
        assert should_show_page("pre_test.JOBALIGNA", al_config, session) is False

    def test_unconditional_question_always_shown(self, al_config):
        """SECTORFAV has no condition — should always show."""
        session = _make_session()
        assert should_show_page("pre_test.SECTORFAV", al_config, session) is True


# ── get_next_page tests ─────────────────────────────────────────────────────

class TestGetNextPage:

    def test_first_page_to_second(self, al_config):
        session = _make_session(splits={"Xrandom2": "r1", "xrandom4": "r1"})
        nxt = get_next_page("pre_test.SECTORFAV", al_config, session)
        assert nxt == "pre_test.CORPFAV"

    def test_last_pre_test_to_inf360(self, al_config):
        session = _make_session(splits={"Xrandom2": "r1", "xrandom4": "r1"})
        nxt = get_next_page("pre_test.AL_PRE", al_config, session)
        assert nxt == "inf360"

    def test_inf360_to_investment(self, al_config):
        """AL has no awareness/info/issues/critics, so inf360 → investment."""
        session = _make_session(splits={"xrandom4": "r1"})
        nxt = get_next_page("inf360", al_config, session)
        assert nxt == "investment"

    def test_investment_to_maxdiff(self, al_config):
        session = _make_session(splits={"xrandom4": "r1"})
        nxt = get_next_page("investment", al_config, session)
        assert nxt == "msg_maxdiff"

    def test_maxdiff_to_post_test(self, al_config):
        """After MaxDiff, should go to first post-test question."""
        session = _make_session(splits={"xrandom4": "r1"})
        nxt = get_next_page("msg_maxdiff", al_config, session)
        assert nxt == "post_test.AL_POST"

    def test_last_post_test_to_mob(self, al_config):
        session = _make_session(splits={"xrandom4": "r1"})
        nxt = get_next_page("post_test.CORPFAV_POST", al_config, session)
        assert nxt == "mob_battery"

    def test_mob_to_adv(self, al_config):
        session = _make_session(splits={"xrandom4": "r1"})
        nxt = get_next_page("mob_battery", al_config, session)
        assert nxt == "adv_battery.AL_ADV_P1"

    def test_last_adv_to_bespoke(self, al_config):
        session = _make_session(splits={"xrandom4": "r1"})
        nxt = get_next_page("adv_battery.AL_ADV_P2n", al_config, session)
        assert nxt == "bespoke.PHRMA01"

    def test_last_bespoke_to_demographics(self, al_config):
        session = _make_session(splits={"xrandom4": "r1"})
        nxt = get_next_page("bespoke.PHRMA04", al_config, session)
        assert nxt == "demographics"

    def test_demographics_to_optin(self, al_config):
        session = _make_session(splits={"xrandom4": "r1"})
        nxt = get_next_page("demographics", al_config, session)
        assert nxt == "opt_in"

    def test_optin_returns_none(self, al_config):
        """After opt_in, instrument is complete — returns None."""
        session = _make_session(splits={"xrandom4": "r1"})
        nxt = get_next_page("opt_in", al_config, session)
        assert nxt is None

    def test_skips_conditional_question_jobaligna_for_r2(self, al_config):
        """When Xrandom2=r2, JOBALIGNA should be skipped → goes to JOBALIGNB."""
        session = _make_session(splits={"Xrandom2": "r2", "xrandom4": "r1"})
        nxt = get_next_page("pre_test.INVEST_AWARE_CO", al_config, session)
        assert nxt == "pre_test.JOBALIGNB"

    def test_skips_conditional_question_jobalignb_for_r1(self, al_config):
        """When Xrandom2=r1, JOBALIGNB should be skipped → goes to FUTUREJOB."""
        session = _make_session(splits={"Xrandom2": "r1", "xrandom4": "r1"})
        nxt = get_next_page("pre_test.JOBALIGNA", al_config, session)
        assert nxt == "pre_test.FUTUREJOB"

    def test_unknown_page_returns_first_page(self, al_config):
        """If current page isn't in the sequence, return the first valid page."""
        session = _make_session(splits={"xrandom4": "r1"})
        nxt = get_next_page("nonexistent_page", al_config, session)
        assert nxt == "pre_test.SECTORFAV"

    def test_full_walk_through_al_no_conditions(self, al_config):
        """Walk through the entire AL sequence with both splits as r1.
        Verify no page appears twice and we end at None."""
        session = _make_session(splits={"Xrandom2": "r1", "xrandom4": "r1"})
        visited = []
        page = get_next_page("__start__", al_config, session)
        while page is not None:
            assert page not in visited, f"Duplicate page: {page}"
            visited.append(page)
            page = get_next_page(page, al_config, session)

        # Should have visited all non-conditional pages
        # JOBALIGNB is conditional on Xrandom2.r2, so it's skipped
        assert "pre_test.JOBALIGNA" in visited
        assert "pre_test.JOBALIGNB" not in visited
        assert visited[-1] == "opt_in"
        assert "inf360" in visited
        assert "msg_maxdiff" in visited
        assert "demographics" in visited

    def test_full_walk_through_al_r2_split(self, al_config):
        """Walk through with Xrandom2=r2 — JOBALIGNB shown, JOBALIGNA skipped."""
        session = _make_session(splits={"Xrandom2": "r2", "xrandom4": "r2"})
        visited = []
        page = get_next_page("__start__", al_config, session)
        while page is not None:
            assert page not in visited, f"Duplicate page: {page}"
            visited.append(page)
            page = get_next_page(page, al_config, session)

        assert "pre_test.JOBALIGNB" in visited
        assert "pre_test.JOBALIGNA" not in visited
        assert visited[-1] == "opt_in"


# ── Critics rotation integration tests ───────────────────────────────────────

class TestCriticsRotation:
    """Test that critics blocks appear in correct positions for studies with critics."""

    def _config_with_critics(self, al_config):
        config = dict(al_config)
        config["critics_enabled"] = True
        config["critics_battery"] = {
            "questions": [
                {"var": "CRITIC_1"},
                {"var": "CRITIC_2"},
            ]
        }
        return config

    def test_block_a_before_maxdiff_for_r1(self, al_config):
        config = self._config_with_critics(al_config)
        session = _make_session(splits={"xrandom4": "r1"})
        seq = build_page_sequence(config, session)
        a_idx = seq.index("critics_block_a")
        md_idx = seq.index("msg_maxdiff")
        assert a_idx < md_idx

        # Block A should be shown
        assert should_show_page("critics_block_a", config, session) is True
        # Block B should be hidden
        assert should_show_page("critics_block_b", config, session) is False

    def test_block_b_after_maxdiff_for_r2(self, al_config):
        config = self._config_with_critics(al_config)
        session = _make_session(splits={"xrandom4": "r2"})
        seq = build_page_sequence(config, session)
        md_idx = seq.index("msg_maxdiff")
        b_idx = seq.index("critics_block_b")
        assert md_idx < b_idx

        # Block B should be shown
        assert should_show_page("critics_block_b", config, session) is True
        # Block A should be hidden
        assert should_show_page("critics_block_a", config, session) is False

    def test_critics_navigation_r1(self, al_config):
        """For xrandom4=r1, critics_block_a appears before investment."""
        config = self._config_with_critics(al_config)
        session = _make_session(splits={"xrandom4": "r1"})

        # After inf360, should go to critics_block_a (before investment)
        nxt = get_next_page("inf360", config, session)
        assert nxt == "critics_block_a"

        # After critics_block_a, should go to investment
        nxt = get_next_page("critics_block_a", config, session)
        assert nxt == "investment"

        # After maxdiff, should skip critics_block_b → post_test
        nxt = get_next_page("msg_maxdiff", config, session)
        assert nxt == "post_test.AL_POST"

    def test_critics_navigation_r2(self, al_config):
        """For xrandom4=r2, critics_block_b appears after maxdiff."""
        config = self._config_with_critics(al_config)
        session = _make_session(splits={"xrandom4": "r2"})

        # After inf360, should skip critics_block_a → investment
        nxt = get_next_page("inf360", config, session)
        assert nxt == "investment"

        # After maxdiff, should go to critics_block_b
        nxt = get_next_page("msg_maxdiff", config, session)
        assert nxt == "critics_block_b"

        # After critics_block_b, should go to post_test
        nxt = get_next_page("critics_block_b", config, session)
        assert nxt == "post_test.AL_POST"


# ── Empty / minimal config edge cases ────────────────────────────────────────

class TestEdgeCases:

    def test_empty_config(self):
        session = _make_session()
        seq = build_page_sequence({}, session)
        # Should still have Layer 1 pages
        assert "inf360" in seq
        assert "demographics" in seq
        assert "opt_in" in seq

    def test_config_without_investment(self):
        session = _make_session()
        config = {"msg_maxdiff": {"var": "TEST"}}
        seq = build_page_sequence(config, session)
        assert "investment" not in seq
        assert "msg_maxdiff" in seq

    def test_config_without_maxdiff(self):
        session = _make_session()
        config = {"investment_variable": {"variants": []}}
        seq = build_page_sequence(config, session)
        assert "msg_maxdiff" not in seq
        assert "investment" in seq

    def test_mob_battery_disabled(self, al_config):
        config = dict(al_config)
        config["mob_battery"] = {"enabled": False, "items": []}
        session = _make_session(splits={"xrandom4": "r1"})
        seq = build_page_sequence(config, session)
        assert "mob_battery" not in seq
