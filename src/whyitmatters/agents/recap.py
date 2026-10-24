"""Recap: the full-time story. Final score, the verdict, and the moments that changed it."""

from __future__ import annotations

from whyitmatters.agents.blackboard import Blackboard
from whyitmatters.agents.generator import TemplateGenerator, TextGenerator
from whyitmatters.agents.models import Claim, Cue, Lang, Mode, Recap, RecapMoment
from whyitmatters.agents.verifier import Verifier

RECAP_MOMENTS = 3


class RecapWriter:
    name = "recap"

    def __init__(self, generator: TextGenerator | None = None, verifier: Verifier | None = None):
        self.generator = generator or TemplateGenerator()
        self.verifier = verifier or Verifier()

    def run(
        self,
        state: Blackboard,
        aired: list[Cue],
        mode: Mode = "analyst",
        lang: Lang = "en",
        personalize=None,
    ) -> Recap:
        last = state.last_event
        assert last is not None, "recap needs a finished match"
        sh, sa = state.score["home"], state.score["away"]
        full = (0, last.minute)
        w = state.pulse.counter.window(last.minute, last.minute + 1)
        xg_h, xg_a = round(state.team_xg["home"], 2), round(state.team_xg["away"], 2)

        claims = [
            Claim(key="sh", metric="score_home", unit="count", value=sh, event_id=last.id),
            Claim(key="sa", metric="score_away", unit="count", value=sa, event_id=last.id),
            Claim(
                key="poss_h",
                metric="possession_share",
                unit="share",
                side="home",
                value=w.home.possession_share,
                window=full,
                tolerance=0.006,
            ),
            Claim(
                key="poss_a",
                metric="possession_share",
                unit="share",
                side="away",
                value=w.away.possession_share,
                window=full,
                tolerance=0.006,
            ),
            Claim(
                key="xg_h", metric="team_xg", unit="xg", side="home", value=xg_h, tolerance=0.006
            ),
            Claim(
                key="xg_a", metric="team_xg", unit="xg", side="away", value=xg_a, tolerance=0.006
            ),
        ]
        names = {"home": state.team_name("home"), "away": state.team_name("away")}
        if sh == sa:
            verdict, winner, loser = "verdict_draw", "", ""
        else:
            win_side = "home" if sh > sa else "away"
            lose_side = "away" if win_side == "home" else "home"
            winner, loser = names[win_side], names[lose_side]
            created_more = state.team_xg[win_side] >= state.team_xg[lose_side]
            verdict = "verdict_deserved" if created_more else "verdict_robbery"
        slots = {**names, "verdict": verdict, "winner": winner, "loser": loser}
        headline, summary = self.generator.render("recap", mode, lang, slots, claims)

        ranked = sorted(aired, key=lambda c: (-_weight(c), c.t_in))[:RECAP_MOMENTS]
        moments = []
        for cue in sorted(ranked, key=lambda c: c.t_in):
            if personalize is not None:
                pc = personalize(cue)
                if pc is None:
                    continue
                h, b = pc.headline, pc.body
            else:
                h, b = cue.headline, cue.body
            moments.append(
                RecapMoment(
                    minute=cue.minute, headline=h, body=b, evidence_event_ids=cue.evidence_event_ids
                )
            )
        return Recap(
            headline=headline,
            score_home=sh,
            score_away=sa,
            summary=summary,
            moments=moments,
            claims=claims,
        )


def _weight(cue: Cue) -> float:
    """How much a moment changed the match: goals first, then control shifts, then chances."""
    base = {"goal": 3.0, "state_shift": 2.0, "big_chance": 1.5}.get(cue.kind, 0.5)
    if cue.kind == "state_shift" and cue.slots.get("template") == "shift_balanced":
        base = 1.0
    return base
