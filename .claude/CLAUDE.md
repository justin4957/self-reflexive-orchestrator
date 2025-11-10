# Self-Reflexive Orchestrator - Claude Code Instructions

## Project Overview

This is a **self-reflexive coding orchestrator** - an autonomous AI agent that manages the entire development lifecycle for projects with minimal human oversight. The orchestrator coordinates multiple LLMs and providers to handle issues, pull requests, code reviews, and development planning.

## Core Principles

### 1. Multi-Agent Collaboration Strategy

This project uses a **dual-AI approach** combining:
- **Claude Code (you)**: Implementation, file operations, git workflows, tool orchestration
- **multi-agent-coder CLI**: Multi-perspective analysis, code review, consensus building

**Key Philosophy**: Different AI capabilities should be leveraged for different tasks. Claude Code excels at implementation and orchestration, while multi-agent-coder excels at analysis and validation through multiple AI perspectives.

See `AI_COLLABORATION_STRATEGY.md` for detailed task distribution patterns.

**IMPORTANT - Reporting Issues to multi_agent_coder**:

When you encounter bugs, unexpected behavior, or have feature requests related to the **multi-agent-coder CLI** (located at `../multi_agent_coder`), you MUST create GitHub issues in that repository:

```bash
# Navigate to multi_agent_coder repo and create issue
cd ../multi_agent_coder
gh issue create --title "Bug: [Brief description]" --body "$(cat <<'EOF'
## Description
[Detailed description of the bug or feature request]

## Steps to Reproduce (for bugs)
1. Step 1
2. Step 2
3. Expected vs actual behavior

## Context
- Encountered while working on: [self-reflexive-orchestrator issue #N]
- Use case: [What you were trying to accomplish]

## Suggested Solution (optional)
[Any ideas for fixing or implementing]
EOF
)"
cd -  # Return to orchestrator repo
```

**When to report**:
- Bugs in multi-agent-coder output parsing
- Unexpected response formats
- Missing features needed for orchestrator integration
- Performance issues with multi-agent-coder
- API changes or breaking changes
- Documentation gaps

This ensures the multi-agent-coder maintainers can track and address issues affecting the orchestrator.

### 2. Issue Processing Workflow

When working on issues, always follow this pattern:

1. **Analysis Phase** (Optional: Use multi-agent-coder for complex issues)
   - Analyze requirements and complexity
   - Generate implementation plan
   - Identify risks and test strategy

2. **Implementation Phase** (Claude Code - you)
   - Create feature branch
   - Implement changes following the plan
   - Write comprehensive tests
   - Run tests locally to ensure they pass

3. **Review Phase** (Optional: Use multi-agent-coder for critical features)
   - Multi-perspective code review
   - Validate against requirements
   - Apply feedback and refine

4. **PR Creation Phase** (Claude Code - you)
   - Run code formatter and linting
   - Create pull request with detailed description
   - Monitor CI/CD checks
   - Ensure all checks pass before considering complete

### 3. Pull Request Requirements

**CRITICAL**: Every pull request MUST:

1. **Format Code Properly**:
   - Run `black .` to format Python code
   - Run `isort .` to sort imports
   - Verify with `black --check .` before creating PR

2. **Pass All Tests**:
   - Run `pytest` locally before creating PR
   - Ensure 100% of tests pass
   - Add new tests for new functionality

3. **Include Comprehensive Description**:
   - Clear summary of changes
   - Link to related issue(s) with "Closes #N"
   - Test plan or verification steps
   - Any breaking changes or migration notes

4. **Verify CI Checks**:
   - After creating PR, use `gh pr checks <pr-number>` to monitor
   - Wait for all checks to pass: "Test", "Code Quality", "Build"
   - Fix any failures before marking task complete

### 4. Code Quality Standards

**Always prioritize**:
- Descriptive variable and function names
- Composability and reusability - aim for abstraction
- Type hints for all function signatures
- Comprehensive docstrings (Google style)
- Structured logging with context
- Error handling with specific exceptions
- Test coverage for new code

### 5. Git Workflow

**Branch Naming**:
- Feature: `feature/issue-N-brief-description`
- Bug fix: `fix/issue-N-brief-description`
- Phase work: `phase-N/feature-name`

**Commit Messages**:
- Use conventional commits: `type(scope): description`
- Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`
- Include issue reference: `feat(notifications): implement Slack integration (#25)`
- Be descriptive about the "why", not just the "what"

### 6. Testing Requirements

**For every new feature**:
- Unit tests in `tests/unit/test_<module>.py`
- Integration tests if interacting with external services
- Mock external dependencies appropriately
- Test both success and failure cases
- Test edge cases and error handling

**Test Structure**:
```python
"""Tests for <module> functionality."""

import pytest
from unittest.mock import Mock, patch

class Test<ClassName>:
    """Tests for <ClassName>."""

    def test_<specific_behavior>(self):
        """Test that <specific behavior> works correctly."""
        # Arrange
        # Act
        # Assert
```

### 7. Multi-Agent Coordination

**When to use multi-agent-coder**:
- Complex architectural decisions
- Ambiguous requirements needing multiple perspectives
- Code review for critical features
- Risk assessment
- Design pattern recommendations

**How to invoke** (from your implementation):
```python
from src.integrations.multi_agent_coder_client import MultiAgentCoderClient

client = MultiAgentCoderClient(config)

# For analysis
analysis = client.query(
    prompt="Analyze this issue...",
    strategy="all"  # or "sequential", "dialectical"
)

# For code review
review = client.review_code(
    code=generated_code,
    context="Implementation of notification system"
)
```

### 8. Safety and Approval Gates

**Automatic approval gates** (configured in `config/orchestrator-config.yaml`):
- Complexity ceiling: Escalate issues above threshold
- Test requirements: Must pass before PR creation
- Human approval: Required for merges, breaking changes, security
- Rollback: Automatic on test failures

**Always**:
- Tag before merge for easy rollback
- Run full test suite before PR
- Monitor CI/CD status
- Log all significant operations to audit trail

### 9. Configuration Management

**Configuration lives in**: `config/orchestrator-config.yaml`

**Key settings to respect**:
- `orchestrator.mode`: manual/supervised/autonomous
- `issue_processing.auto_claim_labels`: Only process labeled issues
- `safety.human_approval_required`: Events requiring approval
- `notifications.on_events`: Events to notify about

**Environment variables**:
- `GITHUB_TOKEN`: GitHub API authentication
- `ANTHROPIC_API_KEY`: Claude API authentication
- Load from `.env` file using python-dotenv

### 10. Logging and Audit Trail

**Use structured logging**:
```python
from src.core.logger import get_logger

logger = get_logger(__name__)

logger.info(
    "notification_sent",
    channel="slack",
    event_type="pr_merged",
    pr_number=123,
    success=True
)
```

**Audit important events**:
- All PR creations and merges
- Test failures and fixes
- Configuration changes
- API calls and costs
- Human approval requests

### 11. Project Structure

```
src/
├── core/           # Core orchestrator logic
│   ├── orchestrator.py
│   ├── config.py
│   ├── state.py
│   └── logger.py
├── cycles/         # Workflow cycles
│   ├── issue_cycle.py
│   ├── pr_cycle.py
│   └── code_executor.py
├── analyzers/      # Analysis components
│   ├── issue_analyzer.py
│   └── implementation_planner.py
├── integrations/   # External integrations
│   ├── github_client.py
│   ├── multi_agent_coder_client.py
│   └── git_ops.py
└── safety/         # Safety mechanisms
```

### 12. Development Phases

**Current Status**: Phase 1 Complete, working on Phase 2-6

- Phase 1: Foundation (✅ Complete)
- Phase 2: Issue Cycle (In Progress)
- Phase 3: PR Cycle (In Progress)
- Phase 4: Roadmap Cycle (Planned)
- Phase 5: Safety & Monitoring (In Progress)
- Phase 6: Optimization (Planned)

**When implementing new features**:
- Check which phase it belongs to
- Follow the acceptance criteria in the GitHub issue
- Update phase status documentation when complete

### 13. Common Commands

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Code Quality
black .
isort .
pytest
pytest --cov=src --cov-report=html

# Validation
black --check .
isort --check .
pytest -v

# Running
python -m src.cli validate-config
python -m src.cli status
python -m src.cli process-issue <N>

# Git & PR
git checkout -b feature/issue-N-description
gh pr create --title "..." --body "..."
gh pr checks <pr-number>
```

### 14. Issue and PR Interaction Rules

**Issue Management**:
- Only process issues with `bot-approved` label (or configured labels)
- Skip issues with `wontfix`, `manual-only` labels
- Check complexity before claiming
- Update issue with progress comments
- Link PR to issue with "Closes #N"

**PR Management**:
- Create PR only after local tests pass
- Include comprehensive description with:
  - Summary of changes
  - Test plan
  - Related issue(s)
  - Breaking changes (if any)
- Monitor CI checks until all pass
- Request review from multi-agent-coder for critical features
- Auto-merge only if configured and checks pass

**Code Review Coordination**:
- Use multi-agent-coder for multi-perspective review
- Apply feedback systematically
- Re-review after significant changes
- Document review decisions

### 15. Error Handling Patterns

**Always**:
- Use specific exception types
- Log errors with full context
- Retry transient failures (with exponential backoff)
- Escalate to human for persistent failures
- Update issue with error details

```python
from src.core.logger import get_logger

logger = get_logger(__name__)

try:
    result = risky_operation()
except SpecificError as e:
    logger.error(
        "operation_failed",
        operation="risky_operation",
        error=str(e),
        retry_count=retry
    )
    if retry < max_retries:
        # Retry logic
    else:
        # Escalate to human
```

### 16. Success Criteria

**A task is complete when**:
1. ✅ All code is implemented and tested
2. ✅ All tests pass locally (`pytest`)
3. ✅ Code is formatted (`black .` and `isort .`)
4. ✅ PR is created with comprehensive description
5. ✅ All CI checks pass (`gh pr checks <pr-number>`)
6. ✅ Code review completed (if required)
7. ✅ Issue is updated with completion status

**Never consider a task complete if**:
- ❌ Tests are failing
- ❌ CI checks are failing
- ❌ Code is not formatted
- ❌ PR description is incomplete
- ❌ Required reviews are missing

---

## Quick Reference

**Before starting any task**:
1. Read the GitHub issue carefully
2. Understand which phase it belongs to
3. Check if multi-agent analysis is recommended
4. Plan the implementation approach

**During implementation**:
1. Create feature branch
2. Implement with tests
3. Run formatters and tests locally
4. Commit with clear messages

**Before creating PR**:
1. `black .` and `isort .`
2. `pytest` - ensure 100% pass
3. Review changes yourself
4. Prepare comprehensive PR description

**After creating PR**:
1. `gh pr checks <pr-number>` - monitor until all pass
2. Address any CI failures immediately
3. Update issue with PR link
4. Only mark complete when all checks pass

---

**This project is about autonomous, high-quality, multi-agent coordinated development. Follow these guidelines to maintain consistency and quality.**
