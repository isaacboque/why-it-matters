"""Personalizer: one verified intelligence, many viewers.

Re-renders a cue for a viewer's mode, language, club and player, then re-verifies the
result: the words may change, the numbers may not. Any number in the personalized text
that no verified claim supports means the cue is withheld for that viewer.
"""

from __future__ import annotations

from whyitmatters.agents.blackboard import Blackboard
from whyitmatters.agents.generator import TemplateGenerator, TextGenerator, render_with_source
from whyitmatters.agents.models import Cue, PersonalCue, TrustStats, Viewer
from whyitmatters.agents.verifier import Verifier

# What each mode shows. Player focus keeps the match-defining moments plus the player's own.
TACTICAL = {
    "press_surge",
    "midfield_battle",
    "danger_turnovers",
    "direct_switch",
    "line_breakers",
    "zone_damage",
    "momentum_swing",
    "shape_change",
    "lines_stretched",
    "block_drop",
    "hub_player",
    "press_escape",
    "physical_drop",
}
MODE_KINDS = {
    "analyst": {"goal", "state_shift", "big_chance", "top_speed", "pass_master"}
    | TACTICAL
    | {"pass_difficulty", "shot_speed", "most_dangerous_pass"},
    "fan": {"goal", "state_shift", "big_chance", "top_speed"}
    | TACTICAL
    | {"pass_difficulty", "shot_speed", "most_dangerous_pass"},
    "player_focus": {"goal", "state_shift"},
    # the coach sees what is happening on the pitch, not individual records
    "coach": {"goal", "state_shift", "big_chance"} | TACTICAL,
}


class Personalizer:
    name = "personalizer"

    def __init__(
        self,
        generator: TextGenerator | None = None,
        verifier: Verifier | None = None,
        stats: TrustStats | None = None,
    ):
        self.generator = generator or TemplateGenerator()
        self.verifier = verifier or Verifier()
        self.stats = stats or TrustStats()

    def run(self, state: Blackboard, cue: Cue, viewer: Viewer) -> PersonalCue | None:
        involves_player = viewer.player_id is not None and cue.player_id == viewer.player_id
        if cue.kind not in MODE_KINDS[viewer.mode] and not involves_player:
            return None
        if viewer.metric and cue.kind != "goal" and viewer.metric not in cue.tags:
            return None  # "My metric": one thread only (a goal always shows)
        if viewer.mode == "player_focus" and not involves_player and cue.kind != "goal":
            # in player focus, state shifts only matter when the player's team is involved
            if viewer.player_id and cue.side and cue.side != state.side_of(viewer.player_id):
                return None

        template = cue.slots.get("template", "")
        out = render_with_source(
            self.generator, template, viewer.mode, viewer.lang, cue.slots, cue.claims
        )
        headline, body = out.headline, out.body
        self.stats.personalized_checked += 1
        checks = self.verifier.check_claims(state, cue.claims)
        # English standing in for a language without a writer is checked as English
        check_lang = "en" if out.translation_unavailable else viewer.lang
        text = f"{headline} {body}"
        unsupported = self.verifier.unsupported_numbers(text, cue.claims, check_lang)
        names = self.verifier.unsupported_names(state, text, cue.slots)
        if unsupported or names or not all(c.ok for c in checks):
            self.stats.personalized_rejected += 1
            return None

        for_you = involves_player or (viewer.club is not None and cue.side == viewer.club)
        return PersonalCue(
            cue_id=cue.cue_id,
            kind=cue.kind,
            t_in=cue.t_in,
            t_out=cue.t_out,
            minute=cue.minute,
            priority=cue.priority,
            headline=headline,
            body=body,
            for_you=for_you,
            evidence_event_ids=cue.evidence_event_ids,
            claims=cue.claims,
            verified=True,
            tags=cue.tags,
            written_by=out.source,
            translation_unavailable=out.translation_unavailable,
        )
