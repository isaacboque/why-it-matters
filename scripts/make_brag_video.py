"""Record a ~30 s showcase video of the static demo (no backend, fully offline).

    python scripts/make_brag_video.py --out ../_handoff/brag/why-it-matters-brag.webm

Serves dist/demo, drives Chromium through a short storyboard with Playwright's video
recorder, and overlays a caption bar. Numbers in captions are read from the page.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import shutil
import socket
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "dist" / "demo"
REPO_URL = "github.com/isaacboque/why-it-matters"
LIVE_URL = "whyitmatters.nicerock-0b92f5eb.swedencentral.azurecontainerapps.io"
SIZE = {"width": 1920, "height": 1080}

_CAPTION_JS = """
(text) => {
  let el = document.getElementById('brag-caption');
  if (!el) {
    el = document.createElement('div');
    el.id = 'brag-caption';
    el.style.cssText = 'position:fixed;left:32px;bottom:32px;z-index:99999;max-width:70vw;'
      + 'padding:12px 22px;border-radius:999px;background:rgba(10,10,20,.78);color:#fff;'
      + 'font:600 26px/1.3 system-ui,sans-serif;white-space:nowrap;overflow:hidden;'
      + 'text-overflow:ellipsis;transition:opacity .3s;pointer-events:none';
    document.body.appendChild(el);
  }
  el.textContent = text;
  el.style.opacity = text ? '1' : '0';
}
"""

_CARD_HTML = """<body style="margin:0;height:100vh;display:grid;place-items:center;
background:#37003c;color:#fff;font-family:system-ui,sans-serif;text-align:center">
<div><h1 style="font-size:96px;margin:0">{title}</h1>
<p style="font-size:36px;margin:24px 0 0;color:#00ff85">{line1}</p>
<p style="font-size:28px;margin:16px 0 0;opacity:.85">{line2}</p></div></body>"""


def caption_text(text: str, limit: int = 90) -> str:
    """One-line caption: collapse whitespace, truncate with an ellipsis."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True, help="output .webm path")
    ap.add_argument(
        "--seed", type=int, default=None, help="recorded seed (default: first with faults)"
    )
    ap.add_argument(
        "--stills", type=Path, default=None, help="folder for PNG stills (default: next to --out)"
    )
    return ap.parse_args(argv)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve() -> tuple[http.server.ThreadingHTTPServer, str]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DEMO))
    handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", _free_port()), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"


def _pick_seed(wanted: int | None) -> int:
    seeds = json.loads((DEMO / "data" / "index.json").read_text(encoding="utf-8"))["seeds"]
    if wanted is not None and str(wanted) in seeds:
        return wanted
    for s, meta in seeds.items():
        if meta.get("faults") is not False:
            return int(s)
    return int(next(iter(seeds)))


def record(out: Path, seed: int | None, stills: Path | None) -> None:
    from playwright.sync_api import sync_playwright

    out.parent.mkdir(parents=True, exist_ok=True)
    stills = stills or out.parent
    seed = _pick_seed(seed)
    srv, base = _serve()
    tmp = Path(tempfile.mkdtemp(prefix="brag-"))
    errors: list[str] = []
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception:  # noqa: BLE001  (no bundled Chromium: use an installed Chrome)
                browser = p.chromium.launch(channel="chrome")
            ctx = browser.new_context(
                viewport=SIZE, record_video_dir=str(tmp), record_video_size=SIZE
            )
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))

            def say(text: str, pause: float = 0.0) -> None:
                page.evaluate(_CAPTION_JS, caption_text(text))
                if pause:
                    page.wait_for_timeout(int(pause * 1000))

            def glide(selector: str) -> None:
                box = page.locator(selector).first.bounding_box()
                if box:
                    page.mouse.move(
                        box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=20
                    )

            def shot(name: str) -> None:
                page.screenshot(path=str(stills / name))

            # 0-3 s title card
            page.set_content(
                _CARD_HTML.format(
                    title="Why It Matters",
                    line1="An AI that explains football, and proves every number.",
                    line2="Synthetic data · every insight verified",
                )
            )
            page.wait_for_timeout(3000)

            # 3-10 s Match Centre while the match replays
            page.goto(f"{base}?static=1&seed={seed}&pace=45&faults=1")
            page.wait_for_selector("#rail .card, #rail [data-why]", timeout=60_000)
            say("A synthetic match replays live: pitch layers, momentum, insights", 3.5)
            shot("brag-match-centre.png")
            glide("#pulse")
            page.wait_for_timeout(3000)

            # 10-16 s Broadcast overlay
            page.click("#tab-broadcast")
            glide("#bc-pitch")
            say("Broadcast view: on-air overlay cards, ready for a TV graphic", 4.5)
            shot("brag-broadcast.png")
            page.wait_for_timeout(1500)

            # 16-21 s Why? drawer
            page.click("#tab-studio")
            page.wait_for_selector("#rail [data-why]", timeout=30_000)
            glide("#rail [data-why]")
            page.click("#rail [data-why]")
            page.wait_for_selector("#why[open]", timeout=10_000)
            say("Every insight is checked against the raw event log", 4.5)

            # 21-27 s Trust tab
            page.keyboard.press("Escape")
            page.wait_for_selector("#recap[open]", timeout=60_000)
            page.click("#tab-trust")
            page.wait_for_selector("#trust-grid *", timeout=10_000)
            score = page.inner_text("#badge-score").strip()
            rejected = page.locator("#verdicts .verdict").count()
            say(f"Truth Score {score} · {rejected} model drafts checked and rejected", 5.0)
            shot("brag-trust.png")
            page.wait_for_timeout(1000)

            # 27-30 s end card
            page.set_content(
                _CARD_HTML.format(
                    title="Why It Matters",
                    line1=REPO_URL,
                    line2=f"Live demo: {LIVE_URL}",
                )
            )
            page.wait_for_timeout(3000)

            video = page.video
            ctx.close()
            browser.close()
            shutil.move(video.path(), out)
    finally:
        srv.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    if errors:
        raise SystemExit(f"page errors while recording: {errors}")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    record(args.out, args.seed, args.stills)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
