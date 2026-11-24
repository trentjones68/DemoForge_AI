"""Deterministic drafts derived from current, approved discovery findings."""

import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from demoforge_api.analysis.schema import EvidenceClass, FindingKind

Category = Literal["buyer", "kpi", "workflow", "integration", "general"]
Priority = Literal["high", "medium", "low"]
Kind = Literal["requirement", "gap"]
GapStatus = Literal["open", "in_progress", "resolved"]

REQUIREMENT_CATEGORIES: dict[FindingKind, Category] = {
    "requirement": "workflow",
    "goal": "kpi",
    "integration": "integration",
    "constraint": "workflow",
    "success_criterion": "kpi",
}
BUYER = re.compile(r"\b(economic buyer|budget owner|decision[- ]maker|final approver)\b", re.I)
BUYER_MISSING = re.compile(
    r"\b(no|without) (an? |the )?(economic buyer|budget owner|decision[- ]maker|final approver)\b",
    re.I,
)
KPI = re.compile(r"\b(kpi|target|threshold|baseline|benchmark|success)\b", re.I)
WORKFLOW = re.compile(r"\b(workflow|process|handoff|routing|step|queue)s?\b", re.I)
UNCERTAIN = re.compile(
    r"\b(unknown|unclear|unconfirmed|not (yet )?(known|identified|confirmed|defined)|"
    r"to be (determined|confirmed)|tbd)\b",
    re.I,
)


@dataclass(frozen=True)
class ApprovedInsight:
    job_id: UUID
    id: UUID
    revision: int
    kind: FindingKind
    classification: EvidenceClass
    statement: str

    @property
    def key(self) -> str:
        return f"{self.job_id}:{self.id}:{self.revision}"


@dataclass(frozen=True)
class Draft:
    key: str
    kind: Kind
    statement: str
    rationale: str
    category: Category
    priority: Priority
    source: ApprovedInsight | None = None


class RequirementsNormalizer:
    """Turn approved evidence into reviewable drafts without another provider call."""

    def normalize(self, insights: list[ApprovedInsight]) -> list[Draft]:
        if not insights:
            return []
        direct = [
            insight
            for insight in insights
            if insight.classification == "direct" and not UNCERTAIN.search(insight.statement)
        ]
        drafts: list[Draft] = []
        for insight in direct:
            category = REQUIREMENT_CATEGORIES.get(insight.kind)
            if category is not None:
                drafts.append(
                    Draft(
                        f"requirement:{insight.key}",
                        "requirement",
                        insight.statement,
                        "Review the approved discovery finding as a proposed requirement.",
                        category,
                        "high" if insight.kind == "constraint" else "medium",
                        insight,
                    )
                )

        coverage: list[tuple[Category, Priority, bool, str, str]] = [
            (
                "buyer",
                "high",
                any(
                    i.kind == "persona"
                    and BUYER.search(i.statement)
                    and not BUYER_MISSING.search(i.statement)
                    for i in direct
                ),
                "Who is the economic buyer and who can give final approval?",
                "No approved direct buyer finding identifies the decision authority.",
            ),
            (
                "kpi",
                "high",
                any(
                    i.kind == "success_criterion"
                    or (i.kind == "metric" and KPI.search(i.statement))
                    for i in direct
                ),
                "Which KPI, baseline, and target will define success?",
                "No approved direct metric or success criterion establishes a measure of success.",
            ),
            (
                "workflow",
                "medium",
                any(
                    i.kind in ("requirement", "pain_point") and WORKFLOW.search(i.statement)
                    for i in direct
                ),
                "What are the current workflow steps, handoffs, and exceptions?",
                "No approved direct workflow finding describes the operating process.",
            ),
            (
                "integration",
                "medium",
                any(i.kind == "integration" for i in direct),
                "Which systems need to integrate, and what data must move between them?",
                "No approved direct integration finding identifies a required connection.",
            ),
        ]
        for category, priority, covered, question, rationale in coverage:
            if not covered:
                drafts.append(
                    Draft(
                        f"coverage:{category}",
                        "gap",
                        question,
                        rationale,
                        category,
                        priority,
                    )
                )

        for insight in insights:
            if insight.classification in ("unknown", "contradictory", "inference"):
                contradictory = insight.classification == "contradictory"
                drafts.append(
                    Draft(
                        f"evidence:{insight.key}",
                        "gap",
                        "What resolves the conflicting finding below?"
                        if contradictory
                        else "What evidence would clarify the finding below?",
                        insight.statement,
                        REQUIREMENT_CATEGORIES.get(insight.kind, "general"),
                        "high" if contradictory else "medium",
                        insight,
                    )
                )
        return drafts
