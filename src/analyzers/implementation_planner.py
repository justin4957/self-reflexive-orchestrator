"""Implementation planning using multi-agent-coder for enhanced planning."""

import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict, field
from enum import Enum

from ..core.logger import AuditLogger, EventType
from ..integrations.multi_agent_coder_client import MultiAgentCoderClient, MultiAgentResponse, MultiAgentStrategy
from ..analyzers.issue_analyzer import IssueAnalysis
from github.Issue import Issue


class PlanConfidence(Enum):
    """Confidence level in implementation plan."""
    LOW = "low"  # < 0.60
    MEDIUM = "medium"  # 0.60 - 0.79
    HIGH = "high"  # 0.80 - 0.89
    VERY_HIGH = "very_high"  # >= 0.90


@dataclass
class ImplementationStep:
    """A single step in the implementation plan."""
    step_number: int
    description: str
    files_affected: List[str]
    estimated_complexity: int  # 1-10
    dependencies: List[int] = field(default_factory=list)  # Step numbers this depends on

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class TestStrategy:
    """Test strategy for implementation."""
    unit_tests_to_create: List[str]
    unit_tests_to_modify: List[str]
    integration_tests_to_create: List[str]
    test_fixtures_needed: List[str]
    coverage_requirements: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ImplementationPlan:
    """Complete implementation plan for a GitHub issue."""
    issue_number: int
    branch_name: str

    # Files
    files_to_modify: List[str]
    files_to_create: List[str]

    # Implementation steps
    implementation_steps: List[ImplementationStep]

    # Testing
    test_strategy: TestStrategy

    # PR information
    pr_title: str
    pr_description: str

    # Validation
    validation_criteria: List[str]
    estimated_total_complexity: int  # 0-10

    # Multi-agent consensus
    provider_plans: Dict[str, str]  # Provider -> raw plan text
    consensus_confidence: float  # 0.0-1.0
    confidence_level: PlanConfidence

    # Metadata
    total_tokens: int
    total_cost: float
    planning_success: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)
        result['confidence_level'] = self.confidence_level.value
        result['implementation_steps'] = [step.to_dict() for step in self.implementation_steps]
        result['test_strategy'] = self.test_strategy.to_dict()
        return result


class ImplementationPlanner:
    """Generates implementation plans using multi-agent-coder for enhanced planning.

    Uses multiple AI providers (Anthropic, OpenAI, DeepSeek) to:
    - Generate multiple implementation approaches
    - Build consensus on best approach
    - Identify files to modify/create
    - Create ordered implementation steps
    - Design test strategy
    - Generate PR templates
    - Assess plan confidence
    """

    # Complexity thresholds
    MAX_TOTAL_COMPLEXITY = 10
    MAX_STEP_COMPLEXITY = 10

    # Confidence thresholds
    CONFIDENCE_VERY_HIGH = 0.90
    CONFIDENCE_HIGH = 0.80
    CONFIDENCE_MEDIUM = 0.60

    def __init__(
        self,
        multi_agent_client: MultiAgentCoderClient,
        logger: AuditLogger,
    ):
        """Initialize implementation planner.

        Args:
            multi_agent_client: Multi-agent-coder client instance
            logger: Audit logger instance
        """
        self.multi_agent = multi_agent_client
        self.logger = logger

        # Statistics
        self.plans_generated = 0
        self.high_confidence_plans = 0
        self.low_confidence_plans = 0

    def generate_plan(
        self,
        issue: Issue,
        issue_analysis: IssueAnalysis,
    ) -> ImplementationPlan:
        """Generate implementation plan for a GitHub issue.

        Args:
            issue: GitHub Issue object
            issue_analysis: Analysis from IssueAnalyzer

        Returns:
            ImplementationPlan with multi-agent consensus
        """
        self.logger.info(
            "Generating implementation plan",
            issue_number=issue.number,
            issue_type=issue_analysis.issue_type.value,
            complexity=issue_analysis.complexity_score,
        )

        try:
            # Step 1: Get multiple implementation approaches from multi-agent-coder
            approaches = self._get_implementation_approaches(issue, issue_analysis)

            if not approaches.success:
                self.logger.error(
                    "Failed to get implementation approaches",
                    issue_number=issue.number,
                    error=approaches.error,
                )
                return self._create_fallback_plan(issue, issue_analysis, approaches)

            # Step 2: Synthesize consensus plan
            plan = self._synthesize_plan(issue, issue_analysis, approaches)

            # Step 3: Update statistics
            self.plans_generated += 1
            if plan.confidence_level in [PlanConfidence.HIGH, PlanConfidence.VERY_HIGH]:
                self.high_confidence_plans += 1
            elif plan.confidence_level == PlanConfidence.LOW:
                self.low_confidence_plans += 1

            self.logger.info(
                "Implementation plan generated",
                issue_number=issue.number,
                steps=len(plan.implementation_steps),
                files_to_create=len(plan.files_to_create),
                files_to_modify=len(plan.files_to_modify),
                confidence=plan.consensus_confidence,
                confidence_level=plan.confidence_level.value,
                cost=plan.total_cost,
            )

            return plan

        except Exception as e:
            self.logger.error(
                "Unexpected error generating implementation plan",
                issue_number=issue.number,
                error=str(e),
                exc_info=True,
            )
            # Return minimal fallback plan
            return self._create_error_plan(issue, issue_analysis, str(e))

    def _get_implementation_approaches(
        self,
        issue: Issue,
        analysis: IssueAnalysis,
    ) -> MultiAgentResponse:
        """Get multiple implementation approaches from multi-agent-coder.

        Args:
            issue: GitHub Issue object
            analysis: Issue analysis

        Returns:
            MultiAgentResponse with approaches from multiple providers
        """
        prompt = f"""Generate a detailed implementation plan for this GitHub issue:

**Issue #{issue.number}: {issue.title}**

**Analysis:**
- Type: {analysis.issue_type.value}
- Complexity: {analysis.complexity_score}/10
- Actionable: {analysis.is_actionable}

**Requirements:**
{self._format_list(analysis.key_requirements)}

**Affected Files (predicted):**
{self._format_list(analysis.affected_files) if analysis.affected_files else "Unknown"}

**Recommended Approach:**
{analysis.recommended_approach}

**Risks:**
{self._format_list(analysis.risks)}

---

Please provide a detailed implementation plan with:

1. **Files to Modify**: List existing files that need changes
2. **Files to Create**: List new files to create with brief description
3. **Implementation Steps**: Ordered list (5-10 steps) with:
   - Step description
   - Files affected by this step
   - Estimated complexity (1-10)
   - Dependencies on previous steps
4. **Test Strategy**:
   - Unit tests to create
   - Unit tests to modify
   - Integration tests needed
   - Test fixtures required
   - Coverage requirements
5. **Validation Criteria**: How to verify implementation works
6. **Overall Complexity**: Total complexity estimate (0-10)

Format your response with clear sections and bullet points.
"""

        return self.multi_agent.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.ALL,
            timeout=120,
        )

    def _synthesize_plan(
        self,
        issue: Issue,
        analysis: IssueAnalysis,
        approaches: MultiAgentResponse,
    ) -> ImplementationPlan:
        """Synthesize implementation plan from multiple AI approaches.

        Args:
            issue: GitHub Issue object
            analysis: Issue analysis
            approaches: Multi-agent responses

        Returns:
            Synthesized ImplementationPlan
        """
        # Extract files from all providers
        files_to_modify = self._extract_files_to_modify(approaches)
        files_to_create = self._extract_files_to_create(approaches)

        # Extract implementation steps
        implementation_steps = self._extract_implementation_steps(approaches)

        # Extract test strategy
        test_strategy = self._extract_test_strategy(approaches)

        # Generate branch name
        branch_name = self._generate_branch_name(issue)

        # Generate PR title and description
        pr_title, pr_description = self._generate_pr_template(issue, analysis, implementation_steps)

        # Extract validation criteria
        validation_criteria = self._extract_validation_criteria(approaches)

        # Calculate complexity
        total_complexity = self._calculate_total_complexity(approaches, implementation_steps)

        # Calculate confidence
        consensus_confidence = self._calculate_confidence(approaches, len(files_to_modify), len(files_to_create), len(implementation_steps))
        confidence_level = self._get_confidence_level(consensus_confidence)

        return ImplementationPlan(
            issue_number=issue.number,
            branch_name=branch_name,
            files_to_modify=files_to_modify,
            files_to_create=files_to_create,
            implementation_steps=implementation_steps,
            test_strategy=test_strategy,
            pr_title=pr_title,
            pr_description=pr_description,
            validation_criteria=validation_criteria,
            estimated_total_complexity=total_complexity,
            provider_plans=approaches.responses,
            consensus_confidence=consensus_confidence,
            confidence_level=confidence_level,
            total_tokens=approaches.total_tokens,
            total_cost=approaches.total_cost,
            planning_success=True,
        )

    def _extract_files_to_modify(self, approaches: MultiAgentResponse) -> List[str]:
        """Extract files to modify from multi-agent responses."""
        files = set()

        for provider, response in approaches.responses.items():
            # Look for "Files to Modify" section
            matches = re.findall(r'(?:files? to modify|modify:?)[:\s]+([^\n]+)', response, re.IGNORECASE)
            for match in matches:
                # Extract file paths (look for Python files, config files, etc.)
                file_paths = re.findall(r'`?([a-zA-Z0-9_/]+\.(?:py|yaml|yml|json|md|txt))`?', match)
                files.update(file_paths)

            # Also look for inline file mentions
            file_paths = re.findall(r'(?:^|\s)-\s*`?([a-zA-Z0-9_/]+\.(?:py|yaml|yml|json|md|txt))`?', response, re.MULTILINE)
            files.update(file_paths)

        return sorted(list(files))

    def _extract_files_to_create(self, approaches: MultiAgentResponse) -> List[str]:
        """Extract files to create from multi-agent responses."""
        files = set()

        for provider, response in approaches.responses.items():
            # Look for "Files to Create" section
            matches = re.findall(r'(?:files? to create|create:?)[:\s]+([^\n]+)', response, re.IGNORECASE)
            for match in matches:
                file_paths = re.findall(r'`?([a-zA-Z0-9_/]+\.(?:py|yaml|yml|json|md|txt))`?', match)
                files.update(file_paths)

            # Look for "Create:" or "New:" prefixes
            new_files = re.findall(r'(?:Create|New):\s*`?([a-zA-Z0-9_/]+\.(?:py|yaml|yml|json|md|txt))`?', response, re.MULTILINE)
            files.update(new_files)

        return sorted(list(files))

    def _extract_implementation_steps(self, approaches: MultiAgentResponse) -> List[ImplementationStep]:
        """Extract implementation steps from multi-agent responses."""
        all_steps = []

        for provider, response in approaches.responses.items():
            # Look for numbered steps
            step_matches = re.findall(r'(?:^|\n)\s*(\d+)\.\s*\*?\*?(.+?)(?:\n|$)', response, re.MULTILINE)

            for step_num_str, description in step_matches:
                try:
                    step_num = int(step_num_str)
                    if step_num <= 20:  # Reasonable limit
                        # Extract complexity if mentioned
                        complexity_match = re.search(r'complexity[:\s]+(\d+)', description, re.IGNORECASE)
                        complexity = int(complexity_match.group(1)) if complexity_match else 5
                        complexity = min(complexity, self.MAX_STEP_COMPLEXITY)

                        # Extract file mentions in this step
                        files_in_step = re.findall(r'`([a-zA-Z0-9_/]+\.(?:py|yaml|yml|json|md|txt))`', description)

                        all_steps.append({
                            'step_number': step_num,
                            'description': description.strip(),
                            'files_affected': files_in_step,
                            'complexity': complexity,
                            'provider': provider,
                        })
                except ValueError:
                    continue

        # Deduplicate and merge similar steps
        merged_steps = self._merge_similar_steps(all_steps)

        return merged_steps

    def _merge_similar_steps(self, all_steps: List[Dict[str, Any]]) -> List[ImplementationStep]:
        """Merge similar steps from different providers."""
        if not all_steps:
            return []

        # Group by step number
        steps_by_number = {}
        for step in all_steps:
            num = step['step_number']
            if num not in steps_by_number:
                steps_by_number[num] = []
            steps_by_number[num].append(step)

        # Merge steps with same number
        merged = []
        for step_num in sorted(steps_by_number.keys()):
            steps = steps_by_number[step_num]

            # Use the most detailed description
            description = max(steps, key=lambda s: len(s['description']))['description']

            # Combine all files mentioned
            all_files = set()
            for step in steps:
                all_files.update(step['files_affected'])

            # Average complexity
            avg_complexity = sum(s['complexity'] for s in steps) // len(steps)

            merged.append(ImplementationStep(
                step_number=step_num,
                description=description,
                files_affected=sorted(list(all_files)),
                estimated_complexity=avg_complexity,
                dependencies=[],  # TODO: Extract dependencies from descriptions
            ))

        return merged

    def _extract_test_strategy(self, approaches: MultiAgentResponse) -> TestStrategy:
        """Extract test strategy from multi-agent responses."""
        unit_tests_create = set()
        unit_tests_modify = set()
        integration_tests = set()
        fixtures = set()
        coverage = "Maintain or improve existing coverage"

        for provider, response in approaches.responses.items():
            # Look for test file mentions
            test_files = re.findall(r'test_([a-zA-Z0-9_]+)\.py', response)
            unit_tests_create.update([f"tests/unit/test_{name}.py" for name in test_files])

            # Look for integration tests
            integration_matches = re.findall(r'integration[:\s]+test_([a-zA-Z0-9_]+)', response, re.IGNORECASE)
            integration_tests.update([f"tests/integration/test_{name}.py" for name in integration_matches])

            # Look for fixtures
            fixture_matches = re.findall(r'fixture[s]?:?\s*([a-zA-Z0-9_/]+)', response, re.IGNORECASE)
            fixtures.update(fixture_matches)

            # Look for coverage mentions
            coverage_match = re.search(r'coverage[:\s]+([^\n]+)', response, re.IGNORECASE)
            if coverage_match:
                coverage = coverage_match.group(1).strip()

        return TestStrategy(
            unit_tests_to_create=sorted(list(unit_tests_create)),
            unit_tests_to_modify=sorted(list(unit_tests_modify)),
            integration_tests_to_create=sorted(list(integration_tests)),
            test_fixtures_needed=sorted(list(fixtures)),
            coverage_requirements=coverage,
        )

    def _generate_branch_name(self, issue: Issue) -> str:
        """Generate branch name from issue number and title.

        Args:
            issue: GitHub Issue object

        Returns:
            Branch name in format: orchestrator/issue-{number}-{slug}
        """
        # Create slug from title
        slug = issue.title.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)  # Remove special chars
        slug = re.sub(r'[-\s]+', '-', slug)  # Replace spaces/dashes with single dash
        slug = slug[:50]  # Limit length
        slug = slug.strip('-')  # Remove trailing dashes

        return f"orchestrator/issue-{issue.number}-{slug}"

    def _generate_pr_template(
        self,
        issue: Issue,
        analysis: IssueAnalysis,
        steps: List[ImplementationStep],
    ) -> tuple[str, str]:
        """Generate PR title and description template.

        Args:
            issue: GitHub Issue object
            analysis: Issue analysis
            steps: Implementation steps

        Returns:
            Tuple of (pr_title, pr_description)
        """
        # Title: "[Phase X] Issue Title"
        pr_title = issue.title

        # Description template
        pr_description = f"""## Summary

Implements #{issue.number}: {issue.title}

**Issue Type:** {analysis.issue_type.value}
**Complexity:** {analysis.complexity_score}/10

## Changes

### Files Modified
{self._format_list([step.files_affected for step in steps if step.files_affected]) if steps else "None"}

### Implementation Steps
{chr(10).join([f"{step.step_number}. {step.description}" for step in steps])}

## Testing

- Unit tests added/modified
- Integration tests where applicable
- All existing tests pass

## Validation

{self._format_list(analysis.key_requirements)}

---

Fixes #{issue.number}

🤖 Generated by Self-Reflexive Orchestrator
"""

        return pr_title, pr_description

    def _extract_validation_criteria(self, approaches: MultiAgentResponse) -> List[str]:
        """Extract validation criteria from multi-agent responses."""
        criteria = set()

        for provider, response in approaches.responses.items():
            # Look for validation section
            validation_match = re.search(r'validation[:\s]+(.+?)(?:\n\n|\Z)', response, re.IGNORECASE | re.DOTALL)
            if validation_match:
                validation_text = validation_match.group(1)
                # Extract bullet points
                bullets = re.findall(r'(?:^|\n)\s*[-*]\s*(.+?)(?:\n|$)', validation_text)
                criteria.update([b.strip() for b in bullets if b.strip()])

        if not criteria:
            criteria = {"All tests pass", "Code follows project style", "No regressions"}

        return sorted(list(criteria))

    def _calculate_total_complexity(
        self,
        approaches: MultiAgentResponse,
        steps: List[ImplementationStep],
    ) -> int:
        """Calculate total complexity estimate."""
        # Average complexity from all providers
        complexity_values = []

        for provider, response in approaches.responses.items():
            complexity_match = re.search(r'(?:overall|total)\s+complexity[:\s]+(\d+)', response, re.IGNORECASE)
            if complexity_match:
                try:
                    complexity_values.append(int(complexity_match.group(1)))
                except ValueError:
                    pass

        if complexity_values:
            avg_complexity = sum(complexity_values) // len(complexity_values)
        elif steps:
            # Average of step complexities
            avg_complexity = sum(step.estimated_complexity for step in steps) // max(len(steps), 1)
        else:
            avg_complexity = 5  # Default moderate

        return min(avg_complexity, self.MAX_TOTAL_COMPLEXITY)

    def _calculate_confidence(
        self,
        approaches: MultiAgentResponse,
        num_files_modify: int,
        num_files_create: int,
        num_steps: int,
    ) -> float:
        """Calculate confidence in implementation plan.

        Higher confidence when:
        - More providers responded successfully
        - Plans are more consistent (similar files/steps)
        - Responses are detailed and specific
        """
        total_providers = len(approaches.providers)
        if total_providers == 0:
            return 0.0

        # Base confidence from response rate
        response_rate = len(approaches.responses) / max(total_providers, 1)

        # Boost for having specific files and steps
        specificity_score = 0.0
        if num_files_modify > 0 or num_files_create > 0:
            specificity_score += 0.2
        if num_steps >= 3:
            specificity_score += 0.2

        # Boost for detailed responses (longer is generally more detailed)
        avg_response_length = sum(len(r) for r in approaches.responses.values()) / max(len(approaches.responses), 1)
        detail_score = min(avg_response_length / 5000, 0.2)  # Cap at 0.2

        confidence = (response_rate * 0.6) + specificity_score + detail_score

        return min(confidence, 1.0)

    def _get_confidence_level(self, confidence: float) -> PlanConfidence:
        """Get confidence level enum from confidence score."""
        if confidence >= self.CONFIDENCE_VERY_HIGH:
            return PlanConfidence.VERY_HIGH
        elif confidence >= self.CONFIDENCE_HIGH:
            return PlanConfidence.HIGH
        elif confidence >= self.CONFIDENCE_MEDIUM:
            return PlanConfidence.MEDIUM
        else:
            return PlanConfidence.LOW

    def _format_list(self, items: List[Any]) -> str:
        """Format list of items as bullet points."""
        if not items:
            return "- None"

        # Flatten if list of lists
        flat_items = []
        for item in items:
            if isinstance(item, list):
                flat_items.extend(item)
            else:
                flat_items.append(item)

        return "\n".join([f"- {item}" for item in flat_items if item])

    def _create_fallback_plan(
        self,
        issue: Issue,
        analysis: IssueAnalysis,
        approaches: MultiAgentResponse,
    ) -> ImplementationPlan:
        """Create fallback plan when multi-agent-coder fails."""
        return ImplementationPlan(
            issue_number=issue.number,
            branch_name=self._generate_branch_name(issue),
            files_to_modify=analysis.affected_files if analysis.affected_files else [],
            files_to_create=[],
            implementation_steps=[
                ImplementationStep(
                    step_number=1,
                    description="Implement solution based on issue requirements",
                    files_affected=analysis.affected_files if analysis.affected_files else [],
                    estimated_complexity=analysis.complexity_score,
                )
            ],
            test_strategy=TestStrategy(
                unit_tests_to_create=[f"tests/unit/test_issue_{issue.number}.py"],
                unit_tests_to_modify=[],
                integration_tests_to_create=[],
                test_fixtures_needed=[],
                coverage_requirements="Maintain existing coverage",
            ),
            pr_title=issue.title,
            pr_description=f"Fixes #{issue.number}\n\n{analysis.recommended_approach}",
            validation_criteria=["All tests pass", "Code review approved"],
            estimated_total_complexity=analysis.complexity_score,
            provider_plans=approaches.responses,
            consensus_confidence=0.3,  # Low confidence for fallback
            confidence_level=PlanConfidence.LOW,
            total_tokens=approaches.total_tokens,
            total_cost=approaches.total_cost,
            planning_success=False,
        )

    def _create_error_plan(
        self,
        issue: Issue,
        analysis: IssueAnalysis,
        error: str,
    ) -> ImplementationPlan:
        """Create minimal error plan when planning completely fails."""
        return ImplementationPlan(
            issue_number=issue.number,
            branch_name=self._generate_branch_name(issue),
            files_to_modify=[],
            files_to_create=[],
            implementation_steps=[],
            test_strategy=TestStrategy(
                unit_tests_to_create=[],
                unit_tests_to_modify=[],
                integration_tests_to_create=[],
                test_fixtures_needed=[],
                coverage_requirements="Unknown",
            ),
            pr_title=issue.title,
            pr_description=f"Error planning #{issue.number}: {error}",
            validation_criteria=[],
            estimated_total_complexity=10,  # Max complexity for error
            provider_plans={},
            consensus_confidence=0.0,
            confidence_level=PlanConfidence.LOW,
            total_tokens=0,
            total_cost=0.0,
            planning_success=False,
        )

    def get_statistics(self) -> Dict[str, Any]:
        """Get planning statistics.

        Returns:
            Dictionary with planning statistics
        """
        return {
            "plans_generated": self.plans_generated,
            "high_confidence_plans": self.high_confidence_plans,
            "low_confidence_plans": self.low_confidence_plans,
            "high_confidence_percentage": (
                (self.high_confidence_plans / self.plans_generated * 100)
                if self.plans_generated > 0
                else 0.0
            ),
            "multi_agent_stats": self.multi_agent.get_statistics(),
        }

    def reset_statistics(self):
        """Reset planning statistics."""
        self.plans_generated = 0
        self.high_confidence_plans = 0
        self.low_confidence_plans = 0
        self.multi_agent.reset_statistics()
