"""Deterministic scene planning from validated and reviewed evidence only."""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import uuid4

from demoforge_api.catalog.matcher import SupportStatus
from demoforge_api.storyboard.models import Brief, Evidence, Gap, Scene, SceneCopy

SUPPORT_WARNING: dict[SupportStatus, str | None] = {
    "supported": None,
    "partial": (
        "Partial support. Discuss the documented boundary and verify prerequisites "
        "before demonstrating any supported subset."
    ),
    "unsupported": (
        "Unsupported in this release. Use this scene for discussion only. "
        "Do not demonstrate or promise the feature."
    ),
    "unknown": (
        "Product support is unverified. Use this scene to confirm coverage. "
        "Do not demonstrate or promise the feature."
    ),
}
PRIORITY = {"high": 0, "medium": 1, "low": 2}


@dataclass(frozen=True)
class SceneInput:
    evidence: Evidence
    gaps: list[Gap]


class StoryboardPlanner:
    def plan(self, brief: Brief, inputs: Sequence[SceneInput]) -> list[Scene]:
        if not inputs or len(inputs) > brief.target_minutes:
            raise ValueError("Allow at least one minute per approved requirement.")
        ordered = sorted(
            inputs,
            key=lambda item: (PRIORITY[item.evidence.priority], item.evidence.requirement_id),
        )
        minutes, remainder = divmod(brief.target_minutes, len(ordered))
        return [
            self.scene(brief, item, minutes + int(index < remainder))
            for index, item in enumerate(ordered)
        ]

    def scene(self, brief: Brief, item: SceneInput, minutes: int) -> Scene:
        evidence, gaps = item.evidence, item.gaps
        capability = evidence.capability
        if evidence.support_status == "supported" and capability:
            actions = [
                f"Open the documented workflow in {capability.name} using fictional records.",
                f"Walk through the steps at {capability.source_locator} and verify the result.",
            ]
            synthetic_data = [
                "Prepare fictional inputs and an expected result for the documented workflow."
            ]
            expected_outcome = (
                "The audience can compare the workflow result with its success criteria."
            )
        else:
            actions = [
                "Review the documented support status and agree on what needs product validation."
            ]
            synthetic_data = [
                "Use fictional examples to discuss the requirement and its acceptance criteria."
            ]
            expected_outcome = (
                "The audience agrees on a validation next step and any limits to communicate."
            )
        if capability and capability.dependencies:
            synthetic_data.append("Prepare fictional test inputs for any documented integrations.")
        outcomes = ", ".join(f"“{outcome}”" for outcome in brief.business_outcomes)
        risks = ["Check that demo inputs are completely synthetic."]
        if gaps:
            risks.append(
                "Resolve the discovery questions before making commitments about this scenario."
            )
        return Scene(
            id=uuid4(),
            minutes=minutes,
            content=SceneCopy(
                title=capability.name if capability else "Validate product coverage",
                actions=actions,
                talk_track=(
                    f"Frame the requirement for {brief.audience}. Discuss how this requirement "
                    f"relates to {outcomes}. Ask how the audience would measure success."
                ),
                expected_outcome=expected_outcome,
                synthetic_data=synthetic_data,
                risks=risks,
            ),
            evidence=evidence,
            gaps=gaps,
            edited_fields=[],
            stale_evidence=False,
            support_warning=SUPPORT_WARNING[evidence.support_status],
        )
