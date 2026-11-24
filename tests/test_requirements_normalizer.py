from uuid import uuid4

from demoforge_api.analysis.schema import EvidenceClass, FindingKind
from demoforge_api.planning.normalizer import ApprovedInsight, RequirementsNormalizer


def insight(
    kind: FindingKind, statement: str, evidence: EvidenceClass = "direct"
) -> ApprovedInsight:
    return ApprovedInsight(uuid4(), uuid4(), 1, kind, evidence, statement)


def test_only_direct_actionable_findings_become_requirement_drafts() -> None:
    requirement = insight("requirement", "Export a monthly audit report.")
    contradiction = insight(
        "constraint", "Two different retention periods were stated.", "contradictory"
    )
    unknown = insight("unknown", "The decision authority is missing.", "unknown")
    inference = insight("integration", "They may need a connection to the warehouse.", "inference")
    drafts = RequirementsNormalizer().normalize([requirement, contradiction, unknown, inference])
    assert RequirementsNormalizer().normalize([]) == []
    requirements = [item for item in drafts if item.kind == "requirement"]
    assert [item.source for item in requirements] == [requirement]
    gaps = [item for item in drafts if item.kind == "gap"]
    assert {item.category for item in gaps if item.source is None} == {
        "buyer",
        "kpi",
        "workflow",
        "integration",
    }
    assert next(item for item in gaps if item.source == contradiction).priority == "high"
    assert {item.source for item in gaps if item.source} == {contradiction, unknown, inference}


def test_coverage_uses_explicit_direct_signals() -> None:
    normalizer = RequirementsNormalizer()
    drafts = normalizer.normalize(
        [
            insight("persona", "The CFO is the economic buyer."),
            insight("success_criterion", "Reduce audit review time to two days."),
            insight("pain_point", "The review workflow requires three manual handoffs."),
            insight("integration", "Send audit events to the reporting system."),
        ]
    )
    assert all(item.kind == "requirement" for item in drafts)
    drafts = normalizer.normalize(
        [
            insight("persona", "No economic buyer was named."),
            insight("metric", "The customer processes 30 files a month."),
            insight("integration", "The integration is unconfirmed."),
        ]
    )
    assert {item.category for item in drafts if item.kind == "gap"} == {
        "buyer",
        "kpi",
        "workflow",
        "integration",
    }
