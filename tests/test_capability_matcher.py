from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from demoforge_api.catalog.matcher import CapabilityMatcher, SupportStatus


@dataclass
class Evidence:
    id: UUID
    revision: int
    support_status: SupportStatus
    match_phrases: list[str]


@pytest.mark.parametrize("status", ["supported", "partial", "unsupported", "unknown"])
def test_exact_catalog_evidence_controls_the_mapping(status: SupportStatus) -> None:
    capability = Evidence(uuid4(), 3, status, ["Export a monthly audit report."])
    result = CapabilityMatcher([capability]).match("  EXPORT a monthly audit report! ")
    assert result.support_status == status
    assert (result.capability_id, result.capability_revision) == (capability.id, 3)


def test_missing_ambiguous_and_negated_requirements_are_unknown() -> None:
    first = Evidence(uuid4(), 1, "supported", ["Export a report"])
    second = Evidence(uuid4(), 4, "unsupported", ["Export a report"])
    for result in (
        CapabilityMatcher([]).match("Export a report"),
        CapabilityMatcher([first, second]).match("Export a report"),
        CapabilityMatcher([first]).match("Do not export a report"),
        CapabilityMatcher([first]).match("Export a report and email it to all customers"),
    ):
        assert result.support_status == "unknown"
        assert result.capability_id is None and result.capability_revision is None
