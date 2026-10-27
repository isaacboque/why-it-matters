import json

import pytest
from fastapi.testclient import TestClient

from whyitmatters.agents import Verifier
from whyitmatters.api import create_app

SEED = 7


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def _sse(client, url):
    """Parse an SSE response into (event, payload) pairs."""
    with client.stream("GET", url) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    out = []
    for block in body.strip().split("\n\n"):
        if block.startswith(":"):  # SSE comment (open / keep-alive)
            continue
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_cues_schema(client):
    r = client.get(f"/matches/{SEED}/cues")
    assert r.status_code == 200
    body = r.json()
    assert body["seed"] == SEED and body["cues"]
    assert body["trust"]["truth_score"] >= 0.95 and body["trust"]["on_air_accuracy"] == 1.0
    for cue in body["cues"]:
        assert {
            "cue_id",
            "kind",
            "t_in",
            "t_out",
            "priority",
            "headline",
            "body",
            "evidence_event_ids",
            "claims",
            "verified",
        } <= cue.keys()
        assert cue["t_out"] > cue["t_in"] and cue["priority"] in (1, 2, 3)


def test_cues_are_documented_in_openapi(client):
    spec = client.get("/openapi.json").json()
    assert "/matches/{seed}/cues" in spec["paths"] and "/matches/{seed}/stream" in spec["paths"]
    assert "Cue" in spec["components"]["schemas"]


def test_bad_seed_is_rejected(client):
    assert client.get("/matches/-1/cues").status_code == 422
    assert client.get("/matches/abc/cues").status_code == 422


def test_stream_yields_events_and_a_recap(client):
    msgs = _sse(client, f"/matches/{SEED}/stream?duration=0")
    kinds = [k for k, _ in msgs]
    assert kinds[0] == "meta" and kinds[-1] == "end"
    assert {"event", "pulse", "cue", "trust", "recap"} <= set(kinds)
    assert kinds.index("recap") > max(i for i, k in enumerate(kinds) if k == "cue")
    ts = [p["t"] for _, p in msgs]
    assert ts == sorted(ts), "the feed follows the match clock"
    recap = next(p for k, p in msgs if k == "recap")["data"]
    assert recap["moments"] and "score_home" in recap


def test_stream_cues_carry_their_proof(client):
    msgs = _sse(client, f"/matches/{SEED}/stream?duration=0")
    cues = [p["data"] for k, p in msgs if k == "cue"]
    assert cues
    for c in cues:
        why = c["why"]
        assert why["verified"] and why["claims"] and all(x["ok"] for x in why["claims"])
        assert why["evidence"] and why["history"][-1]["ok"]


def test_stream_with_an_unreliable_model_shows_rejections(client):
    msgs = _sse(client, f"/matches/{SEED}/stream?duration=0&faults=0.6")
    verdicts = [p["data"] for k, p in msgs if k == "verdict"]
    assert any(not v["ok"] for v in verdicts)
    assert all(c["data"]["why"]["verified"] for k, c in msgs if k == "cue")
    trust = [p["data"] for k, p in msgs if k == "trust"][-1]
    assert trust["claims_rejected"] > 0 and trust["on_air_accuracy"] == 1.0


def test_stream_is_paced_by_duration(client):
    import time

    started = time.perf_counter()
    _sse(client, f"/matches/{SEED}/stream?duration=1")
    assert 0.8 < time.perf_counter() - started < 5


def test_personal_view_in_each_language_is_verified(client):
    for lang in ("en", "es", "ca"):
        r = client.get(f"/matches/{SEED}/personal?mode=fan&lang={lang}&club=home")
        assert r.status_code == 200
        body = r.json()
        assert body["cues"] and body["recap"]["headline"]
        for c in body["cues"]:
            assert (
                Verifier.unsupported_numbers(
                    f"{c['headline']} {c['body']}", [_claim(x) for x in c["claims"]], lang
                )
                == []
            )


def _claim(d):
    from whyitmatters.agents import Claim

    return Claim(**d)


def test_personal_rejects_an_unknown_player(client):
    assert client.get(f"/matches/{SEED}/personal?player=nobody").status_code == 422


def test_match_info_lists_players_for_the_selectors(client):
    info = client.get(f"/matches/{SEED}").json()
    assert len(info["home"]["players"]) >= 11 and info["away"]["name"]


def test_eval_endpoint(client):
    r = client.get("/eval?seeds=2")
    assert r.status_code == 200 and r.json()["matches"] == 2


def test_web_ui_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "WhyItMatters" in r.text
    assert client.get("/app.js").status_code == 200
    assert client.get("/style.css").status_code == 200


def test_web_theme_palette_and_short_names(client):
    css = client.get("/style.css").text
    for colour in ("#37003c", "#00ff85", "#e90052", "#04f5ff"):
        assert colour in css
    assert "short_name" in client.get("/app.js").text
    info = client.get(f"/matches/{SEED}").json()
    assert info["home"]["short_name"] and info["away"]["short_name"]


def test_static_export_is_self_contained(tmp_path):
    import json

    from whyitmatters.api.export import SIZE_BUDGET, export_demo

    m = export_demo([7], tmp_path / "demo")
    assert m["bytes"] < SIZE_BUDGET
    for name in ("index.html", "app.js", "style.css"):
        assert (tmp_path / "demo" / name).is_file()
    for rel in m["files"]:
        assert json.loads((tmp_path / "demo" / rel).read_text(encoding="utf-8")) is not None
    focus = m["seeds"]["7"]["focus_players"]
    assert len(focus) == 3
    assert f"data/7/personal-player_focus-{focus[0]}-ca.json" in m["files"]
    assert "data/7/personal-fan-es.json" in m["files"] and "data/eval.json" in m["files"]
    assert "data/7/personal-coach-ca.json" in m["files"]
    feed = json.loads((tmp_path / "demo/data/7/stream-faults.json").read_text(encoding="utf-8"))
    assert any(r["type"] == "verdict" and not r["data"]["ok"] for r in feed)
    assert any(r["type"] == "recap" for r in feed)


def test_personal_coach_mode_and_my_metric(client):
    coach = client.get(f"/matches/{SEED}/personal?mode=coach&lang=ca")
    assert coach.status_code == 200 and coach.json()["cues"]
    assert all(c["tags"] is not None for c in coach.json()["cues"])
    for metric in ("pressing", "duels", "possession", "xg", "pass_quality", "speed"):
        r = client.get(f"/matches/{SEED}/personal?mode=fan&metric={metric}")
        assert r.status_code == 200
        assert all(c["kind"] == "goal" or metric in c["tags"] for c in r.json()["cues"])
    assert client.get(f"/matches/{SEED}/personal?metric=nonsense").status_code == 422


def test_stream_opens_with_a_comment_and_stays_proxy_friendly(client):
    with client.stream("GET", f"/matches/{SEED}/stream?duration=0") as r:
        assert r.headers["cache-control"] == "no-cache"
        assert r.headers["x-accel-buffering"] == "no"
        body = "".join(r.iter_text())
    assert body.startswith(": open\n\n")


def test_cold_match_is_simulated_once_under_concurrency():
    import importlib
    import threading
    from unittest import mock

    api = importlib.import_module("whyitmatters.api.app")  # the package re-exports `app`

    calls = []
    real = api.simulate

    def counting(seed):
        calls.append(seed)
        return real(seed)

    with mock.patch.object(api, "simulate", counting):
        c = TestClient(create_app())
        threads = [threading.Thread(target=lambda: c.get("/matches/4242")) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    assert calls == [4242]
