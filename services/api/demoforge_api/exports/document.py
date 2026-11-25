"""Document content shared by the Markdown and PDF renderers."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from demoforge_api.exports.readiness import Readiness
from demoforge_api.opportunities import Opportunity
from demoforge_api.storyboard.models import Scene, Storyboard

BlockKind = Literal[
    "title", "subtitle", "section", "subheading", "text", "bullet", "check", "warning"
]


@dataclass(frozen=True)
class Block:
    kind: BlockKind
    text: str
    href: str | None = None
    checked: bool = False


def discovery_link(base: str, session: UUID, item: UUID, revision: int) -> str:
    return f"{base}/discovery/{session}/plan?history={item}#plan-{item}-r{revision}"


def scenario_blocks(scene: Scene, number: int, base: str) -> list[Block]:
    content, evidence = scene.content, scene.evidence
    blocks = [Block("section", f"{number:02d} / {content.title} · {scene.minutes} min")]
    if scene.stale_evidence:
        blocks.append(
            Block(
                "warning",
                "Stale evidence. Refresh the requirement and mapping before using this scene.",
            )
        )
    if scene.support_warning:
        blocks.append(Block("warning", scene.support_warning))
    blocks += [
        Block("subheading", "Approved requirement"),
        Block("text", f"{evidence.requirement} (requirement r{evidence.requirement_revision})"),
        Block(
            "text",
            f"Open requirement revision {evidence.requirement_revision}",
            discovery_link(
                base,
                evidence.session_id,
                evidence.requirement_id,
                evidence.requirement_revision,
            ),
        ),
        Block("subheading", "Product evidence and limitations"),
        Block(
            "text", f"{evidence.support_status.capitalize()} · Mapping r{evidence.mapping_revision}"
        ),
        Block("text", evidence.mapping_rationale),
    ]
    capability = evidence.capability
    if capability:
        blocks += [
            Block("text", f"{capability.name} · Catalog r{capability.revision} · {capability.id}"),
            Block(
                "text", f"Documentation: {capability.source_title} · {capability.source_locator}"
            ),
        ]
        if capability.limitations:
            blocks.append(Block("text", f"Limitations: {capability.limitations}"))
        if capability.dependencies:
            blocks.append(
                Block("text", "Integration dependencies: " + ", ".join(capability.dependencies))
            )
    else:
        blocks.append(Block("text", "Product documentation is unverified for this requirement."))
    discussion = scene.stale_evidence or scene.support_warning is not None
    blocks += [Block("subheading", "Discussion actions" if discussion else "Demo actions")]
    blocks += [Block("bullet", action) for action in content.actions]
    blocks += [
        Block("subheading", "Talk track"),
        Block("text", content.talk_track),
        Block("subheading", "Expected outcome"),
        Block("text", content.expected_outcome),
    ]
    if content.synthetic_data:
        blocks += [Block("subheading", "Synthetic data needs")]
        blocks += [Block("bullet", need) for need in content.synthetic_data]
    if scene.gaps:
        blocks += [Block("subheading", "Discovery gaps at planning")]
        for gap in scene.gaps:
            blocks.append(
                Block(
                    "bullet",
                    f"{gap.question} ({gap.priority} priority)",
                    discovery_link(
                        base,
                        evidence.session_id,
                        gap.id,
                        gap.revision,
                    ),
                )
            )
    if content.risks:
        blocks += [Block("subheading", "Demo risks")]
        blocks += [Block("bullet", risk) for risk in content.risks]
    return blocks


def storyboard_document(
    opportunity: Opportunity, board: Storyboard, readiness: Readiness, origin: str
) -> list[Block]:
    base = f"{origin}/workspaces/{opportunity.workspace_id}/opportunities/{opportunity.id}"
    approval = f"Approved {board.approved_at:%Y-%m-%d}" if board.approved_at else "Draft"
    blocks = [
        Block("title", "Demo storyboard"),
        Block("subtitle", opportunity.name),
        Block(
            "text", f"Revision {board.revision} · {approval} · {board.brief.target_minutes} minutes"
        ),
        Block(
            "subtitle" if readiness.ready else "warning",
            "Demo-ready" if readiness.ready else "Not demo-ready",
        ),
        Block("text", f"Readiness checked {datetime.now(UTC):%Y-%m-%d %H:%M} UTC"),
        Block(
            "text",
            f"Open storyboard revision {board.revision}",
            f"{base}/demo-studio?storyboard={board.id}&revision={board.revision}",
        ),
        Block("section", "Opportunity and demo brief"),
        Block("text", f"Company: {opportunity.company}"),
        Block("text", f"Product interest: {opportunity.product}"),
        Block("text", f"Opportunity stage: {opportunity.stage.replace('_', ' ').capitalize()}"),
        Block("text", f"Product release: {board.release.product} · {board.release.version}"),
        Block("text", f"Audience: {board.brief.audience}"),
    ]
    if opportunity.demo_date:
        blocks.append(Block("text", f"Target demo date: {opportunity.demo_date.isoformat()}"))
    if opportunity.use_case:
        blocks.append(Block("text", f"Use case: {opportunity.use_case}"))
    blocks += [Block("subheading", "Business outcomes")]
    blocks += [Block("bullet", outcome) for outcome in board.brief.business_outcomes]
    blocks += [Block("section", "Agenda")]
    blocks += [
        Block("bullet", f"{number:02d} · {scene.minutes} min · {scene.content.title}")
        for number, scene in enumerate(board.scenes, 1)
    ]
    blocks += [Block("section", "Demo prep checklist")]
    blocks += [Block("check", check.label, checked=check.complete) for check in readiness.checks]
    blockers = [check.blocker for check in readiness.checks if check.blocker]
    if blockers:
        blocks += [Block("subheading", "Readiness blockers")]
        blocks += [Block("bullet", blocker) for blocker in blockers]
    for number, scene in enumerate(board.scenes, 1):
        blocks.extend(scenario_blocks(scene, number, base))
    return blocks
