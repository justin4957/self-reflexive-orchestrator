"""Breaking change detection using multi-agent analysis."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core.logger import AuditLogger
from ..integrations.multi_agent_coder_client import (
    MultiAgentCoderClient,
    MultiAgentStrategy,
)


@dataclass
class BreakingChange:
    """Represents a detected breaking change."""

    severity: str  # MINOR, MAJOR, CRITICAL
    description: str
    impact: str  # Who/what is affected
    migration_path: str  # How to fix consumers
    file: Optional[str] = None
    line: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "severity": self.severity,
            "description": self.description,
            "impact": self.impact,
            "migration_path": self.migration_path,
            "file": self.file,
            "line": self.line,
        }


@dataclass
class BreakingChangeAnalysis:
    """Result of breaking change analysis."""

    changes: List[BreakingChange]
    overall_severity: str  # NONE, MINOR, MAJOR, CRITICAL
    consensus_reached: bool
    provider_assessments: Dict[str, str]  # provider -> severity
    recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "changes": [c.to_dict() for c in self.changes],
            "overall_severity": self.overall_severity,
            "consensus_reached": self.consensus_reached,
            "provider_assessments": self.provider_assessments,
            "recommendation": self.recommendation,
        }


class BreakingChangeDetector:
    """Detects breaking changes using multi-agent analysis."""

    def __init__(
        self,
        multi_agent_client: MultiAgentCoderClient,
        logger: AuditLogger,
    ):
        """Initialize detector."""
        self.multi_agent_client = multi_agent_client
        self.logger = logger

    def detect_breaking_changes(
        self,
        diff: str,
        files_changed: List[str],
        api_definition: Optional[str] = None,
    ) -> BreakingChangeAnalysis:
        """Detect breaking changes in diff."""
        prompt = f"""Identify breaking changes in this diff:

**Files Changed**: {', '.join(files_changed[:10])}
{"..." if len(files_changed) > 10 else ""}

**Diff**:
```diff
{diff[:5000]}
{"..." if len(diff) > 5000 else ""}
```

Identify:
1. **API signature changes** (parameters, return types, removed methods)
2. **Database schema modifications**
3. **Configuration changes** affecting behavior
4. **Behavioral changes** affecting consumers

For each breaking change:
- **Severity**: MINOR / MAJOR / CRITICAL
- **Description**: What changed
- **Impact**: Who/what is affected
- **Migration**: How to fix consumers

Then provide:
- **Overall Severity**: NONE / MINOR / MAJOR / CRITICAL
- **Recommendation**: APPROVE / REVIEW / REJECT

Be specific and thorough."""

        response = self.multi_agent_client.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.DIALECTICAL,
            timeout=240,
        )

        return self._parse_analysis(response, files_changed)

    def _parse_analysis(self, response, files_changed) -> BreakingChangeAnalysis:
        """Parse multi-agent response into analysis."""
        changes: List[BreakingChange] = []
        severities = {"NONE": 0, "MINOR": 0, "MAJOR": 0, "CRITICAL": 0}
        provider_assessments = {}

        # Parse each provider response
        for provider, text in response.responses.items():
            severity = self._extract_severity(text)
            provider_assessments[provider] = severity
            severities[severity] += 1

        # Determine overall severity (most conservative)
        if severities["CRITICAL"] > 0:
            overall = "CRITICAL"
        elif severities["MAJOR"] > 0:
            overall = "MAJOR"
        elif severities["MINOR"] > 0:
            overall = "MINOR"
        else:
            overall = "NONE"

        consensus = len(set(provider_assessments.values())) == 1

        # Build recommendation
        if overall == "CRITICAL":
            recommendation = "REJECT - Critical breaking changes detected"
        elif overall == "MAJOR":
            recommendation = "REVIEW - Major breaking changes require careful review"
        elif overall == "MINOR":
            recommendation = "APPROVE WITH CAUTION - Minor breaking changes detected"
        else:
            recommendation = "APPROVE - No breaking changes detected"

        return BreakingChangeAnalysis(
            changes=changes,
            overall_severity=overall,
            consensus_reached=consensus,
            provider_assessments=provider_assessments,
            recommendation=recommendation,
        )

    def _extract_severity(self, text: str) -> str:
        """Extract severity from response text."""
        text_upper = text.upper()
        if "CRITICAL" in text_upper:
            return "CRITICAL"
        elif "MAJOR" in text_upper:
            return "MAJOR"
        elif "MINOR" in text_upper:
            return "MINOR"
        return "NONE"
