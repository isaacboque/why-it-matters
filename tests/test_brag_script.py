from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "make_brag_video", Path(__file__).resolve().parents[1] / "scripts" / "make_brag_video.py"
)
brag = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(brag)


def test_caption_text_collapses_and_truncates():
    assert brag.caption_text("  a \n b  ") == "a b"
    long = brag.caption_text("word " * 50, limit=30)
    assert len(long) == 30 and long.endswith("…")


def test_parse_args():
    args = brag.parse_args(["--out", "x.webm", "--seed", "7"])
    assert args.out == Path("x.webm") and args.seed == 7 and args.stills is None
