from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e
LONG = 60_000  # ms: a cold match plus an instant replay


def _kick_off(page, seed=None, pace="0"):
    page.select_option("#pace", pace)
    if seed is not None:
        page.fill("#seed", str(seed))
    page.click("#start")


def _wait_full_time(page):
    page.wait_for_selector("#recap[open]", timeout=LONG)


def test_kick_off_runs_to_full_time_and_shows_the_recap(api_url, new_page):
    page = new_page()
    page.goto(api_url)
    _kick_off(page, 7)
    _wait_full_time(page)
    assert page.evaluate("S.seed") == 7 and page.evaluate("S.ended") is True
    assert "Full time" in page.inner_text("#recap")
    # the recap is non-modal: the header controls underneath it still work
    assert page.evaluate("document.querySelector('dialog#recap').matches(':modal')") is False
    box, bar = page.locator("#recap").bounding_box(), page.locator("header.top").bounding_box()
    assert box["y"] >= bar["y"] + bar["height"]


def test_new_seed_works_without_closing_the_recap(api_url, new_page):
    page = new_page()
    page.goto(api_url)
    _kick_off(page, 7)
    _wait_full_time(page)
    first = page.evaluate("S.info.match_id")
    page.fill("#seed", "42")
    page.click("#start")  # recap still open on purpose
    page.wait_for_function("S.seed === 42")
    _wait_full_time(page)
    assert page.evaluate("S.seed") == 42 and page.evaluate("S.info.match_id") != first
    # the scoreboard and the recap come from this match's own events
    score = page.evaluate("S.score")
    assert f"{score[0]} – {score[1]}" in page.inner_text("#recap .final")


def test_enter_key_restarts_mid_match(api_url, new_page):
    page = new_page()
    page.goto(api_url)
    _kick_off(page, 7, pace="45")
    page.wait_for_function("S.events.length > 5")
    page.fill("#seed", "11")
    page.press("#seed", "Enter")
    page.wait_for_function("S.seed === 11")
    page.wait_for_function("S.events.length > 5")
    # the match on screen is seed 11's, not the one we abandoned
    meta = page.evaluate("fetch('matches/11').then(r => r.json())")
    assert page.evaluate("S.info.match_id") == meta["match_id"]
    assert page.evaluate("S.ended") is False
    page.select_option("#pace", "0")
    page.click("#start")
    _wait_full_time(page)
    assert page.evaluate("S.seed") == 11


def test_bad_seed_is_clamped_with_a_visible_note(api_url, new_page):
    page = new_page()
    page.goto(api_url)
    for raw, expect in [("", 7), ("-5", 0), ("999999", 100000)]:
        page.select_option("#pace", "0")
        page.fill("#seed", raw)
        page.click("#start")
        page.wait_for_function(f"S.seed === {expect}")
        assert page.is_visible("#start-notice")
        assert page.input_value("#seed") == str(expect)


def test_unreliable_model_shows_rejected_drafts_in_trust(api_url, new_page):
    page = new_page()
    page.goto(api_url)
    page.check("#faults")
    _kick_off(page, 7)
    _wait_full_time(page)
    page.click("#tab-trust")
    assert page.locator("#verdicts .verdict").count() > 0


def test_static_demo_switches_between_recorded_matches(static_url, new_page):
    page = new_page()
    page.goto(static_url + "?static=1")
    page.wait_for_selector("select#seed")
    assert "Recorded matches" in page.inner_text("label:has(#seed)")
    recorded = [int(x) for x in page.evaluate("Object.keys(MANIFEST.seeds)")]
    assert len(recorded) >= 3
    for seed in (recorded[1], recorded[2], recorded[0]):
        page.select_option("#pace", "0")
        page.select_option("#seed", str(seed))
        page.wait_for_function(f"S.seed === {seed}")
        _wait_full_time(page)
    page.goto(static_url + "?static=1&seed=99")
    page.wait_for_selector("#start-notice:not([hidden])")
    assert "not in the recorded set" in page.inner_text("#start-notice")


def test_phone_recap_is_a_bottom_sheet_with_a_visible_close(api_url, new_page):
    page = new_page(viewport={"width": 390, "height": 844})
    page.goto(api_url)
    _kick_off(page, 7)
    _wait_full_time(page)
    sheet = page.locator("#recap").bounding_box()
    assert sheet["width"] >= 388 and sheet["y"] + sheet["height"] >= 843
    assert page.locator("#recap .close").is_visible()
    page.click("#recap .close")
    assert not page.evaluate("document.querySelector('#recap').open")
    page.click("#start")  # controls remain reachable
    page.press("body", "Escape")


def test_deep_link_opens_the_exact_match(api_url, new_page):
    page = new_page()
    page.goto(f"{api_url}?seed=11&pace=0&faults=1")
    _wait_full_time(page)
    assert page.evaluate("S.seed") == 11
    assert page.input_value("#pace") == "0" and page.is_checked("#faults")
    assert "seed=11" in page.url and "faults=1" in page.url


def test_random_match_kicks_off(api_url, new_page):
    page = new_page()
    page.goto(api_url)
    page.select_option("#pace", "0")
    page.click("#random")
    _wait_full_time(page)
    assert 0 <= page.evaluate("S.seed") < 1000


def test_featured_match_can_be_picked(api_url, new_page):
    page = new_page()
    page.goto(api_url + "?pace=0")
    try:
        page.wait_for_function(
            "document.querySelectorAll('#featured option').length > 1", timeout=5000
        )
    except Exception:  # noqa: BLE001
        pytest.skip("no featured matches generated yet")
    options = page.locator("#featured option:not([value=''])")
    seed = int(options.first.get_attribute("value"))
    page.select_option("#featured", str(seed))
    page.wait_for_function(f"S.seed === {seed}")
    _wait_full_time(page)
    assert page.input_value("#seed") == str(seed)
