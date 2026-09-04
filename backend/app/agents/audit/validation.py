"""Validate audit findings against the evidence catalog — drop unsupported claims."""

from __future__ import annotations

from app.agents.audit.schemas import AuditAIEnrichment, AuditEvidenceItem, AuditFinding
from app.exceptions import ValidationAppError


def validate_findings(
    findings: list[AuditFinding],
    catalog: list[AuditEvidenceItem],
) -> list[AuditFinding]:
    allowed = {item.evidence_id for item in catalog}
    valid: list[AuditFinding] = []
    for finding in findings:
        if not finding.evidence_ids:
            continue
        if any(eid not in allowed for eid in finding.evidence_ids):
            continue
        valid.append(finding)
    return valid


def validate_ai_enrichment(
    enrichment: AuditAIEnrichment,
    catalog: list[AuditEvidenceItem],
) -> AuditAIEnrichment:
    """Ensure AI output only references known evidence; raise if entirely invalid."""
    if not enrichment.summary.strip():
        raise ValidationAppError("AI audit enrichment missing summary")
    validated = validate_findings(enrichment.findings, catalog)
    if enrichment.findings and not validated:
        raise ValidationAppError(
            "AI audit enrichment findings lacked valid evidence references",
            details={"finding_count": len(enrichment.findings)},
        )
    return enrichment.model_copy(update={"findings": validated})
