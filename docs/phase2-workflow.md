# Phase 2: Issue Processing Workflow

## Overview

Phase 2 implements the complete autonomous issue-to-PR workflow, integrating all components into a cohesive system that can claim issues, analyze them, generate implementation plans, execute code changes, run tests, and create pull requests.

## Architecture

### Component Integration

```
┌─────────────────────────────────────────────────────────────────┐
│                         Orchestrator                              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Phase 2 Integration Layer                    │   │
│  │  ┌────────────────────────────────────────────────────┐  │   │
│  │  │             IssueProcessor                          │  │   │
│  │  │  (Coordinates full workflow)                       │  │   │
│  │  └────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
    ┌──────────┐         ┌──────────┐        ┌──────────┐
    │  Issue   │         │  Code    │        │    PR    │
    │ Analysis │         │Execution │        │ Creation │
    └──────────┘         └──────────┘        └──────────┘
          │                    │                    │
          ▼                    ▼                    ▼
    Multi-Agent           GitOps +             GitHub API
     Analysis            Test Runner
```

### Workflow Sequence

1. **Issue Monitor** - Claims issues with configured labels
2. **Issue Analyzer** - Multi-agent analysis for actionability
3. **Implementation Planner** - Generates detailed implementation plan
4. **Code Executor** - Executes plan step-by-step
5. **Test Runner** - Runs project tests
6. **Test Failure Analyzer** - (If needed) Analyzes and fixes failures
7. **PR Creator** - Creates pull request with comprehensive description

## Components

### IssueProcessor

**Location**: `src/cycles/issue_processor.py`

**Responsibility**: Orchestrates the complete workflow for a single work item.

**Key Methods**:
- `process_work_item(work_item)` - Main entry point for processing
- `_analyze_issue(work_item)` - Runs multi-agent analysis
- `_generate_plan(work_item, analysis)` - Creates implementation plan
- `_execute_implementation(work_item, plan)` - Applies code changes
- `_test_and_fix_loop(work_item, plan)` - Test/fix iteration
- `_create_pr(work_item, plan, test_result)` - Creates pull request

**Configuration**: `ProcessingConfig` dataclass with:
- Complexity thresholds
- Confidence minimums
- Auto-fix settings
- Timeouts for each stage

### IssueMonitor

**Location**: `src/cycles/issue_cycle.py`

**Responsibility**: Monitors GitHub for new issues and claims them.

**Features**:
- Rate limit tracking
- Concurrent limit enforcement
- Label-based filtering
- Statistics collection

### Orchestrator Integration

**Location**: `src/core/orchestrator.py`

**New Methods**:
- `_initialize_phase2_components()` - Sets up all Phase 2 components
- `_check_work_progress()` - Processes pending work items
- `get_status()` - Enhanced with Phase 2 statistics

**Main Loop**:
```python
while running:
    transition_to(MONITORING)
    _check_for_issues()       # Claim new issues
    _check_work_progress()    # Process pending items
    transition_to(IDLE)
    sleep(poll_interval)
```

## State Management

### Work Item States

- `pending` - Newly claimed issue
- `analyzing` - Running issue analysis
- `rejected` - Not actionable or too complex
- `planning` - Generating implementation plan
- `implementing` - Executing code changes
- `testing` - Running test suite
- `analyzing_failures` - Analyzing test failures
- `fixing` - Applying fixes for failures
- `creating_pr` - Creating pull request
- `pr_created` - PR successfully created
- `completed` - Fully complete
- `failed` - Unrecoverable failure

### State Transitions

```
pending
  ├─> analyzing
  │   ├─> rejected (not actionable)
  │   └─> planning
  │       ├─> rejected (low confidence)
  │       └─> implementing
  │           ├─> failed (execution error)
  │           └─> testing
  │               ├─> analyzing_failures
  │               │   └─> fixing
  │               │       └─> testing (retry)
  │               ├─> creating_pr
  │               │   └─> pr_created
  │               │       └─> completed
  │               └─> failed (tests failed, max retries)
  └─> failed (unexpected error)
```

## Configuration

### Phase 2 Settings

In `orchestrator-config.yaml`:

```yaml
issue_processing:
  # Existing settings
  auto_claim_labels: ["bot-approved"]
  max_complexity: 7
  max_concurrent: 2

  # Phase 2 workflow settings
  enable_auto_analysis: true
  min_actionability_confidence: 0.6
  enable_auto_implementation: true
  min_plan_confidence: 0.6
  enable_auto_fix: true
  max_auto_fix_attempts: 2
  min_fix_confidence: 0.6
  require_tests_passing: true

  # Timeouts (seconds)
  analysis_timeout: 300      # 5 minutes
  planning_timeout: 600      # 10 minutes
  execution_timeout: 1200    # 20 minutes
  test_timeout: 300          # 5 minutes
```

## Usage

### Autonomous Mode

Start the orchestrator in autonomous mode:

```bash
python -m src.cli start
```

The orchestrator will:
1. Poll for issues every `poll_interval` seconds
2. Claim issues with configured labels
3. Process them through the Phase 2 workflow
4. Create PRs automatically

### Manual Mode

Process a specific issue manually:

```bash
python -m src.cli process-issue 42
```

### Status Monitoring

View orchestrator status and Phase 2 statistics:

```bash
python -m src.cli status
```

Output includes:
- Orchestrator state
- Work item summary
- Issue Monitor statistics
- Issue Processor statistics

## Error Handling

### Retry Logic

- **Test Failures**: Up to `max_auto_fix_attempts` (default: 2)
- **Code Execution**: Up to 3 retries per step
- **API Failures**: Exponential backoff

### Rejection Criteria

Issues are rejected (not implemented) if:
- Not actionable (confidence < `min_actionability_confidence`)
- Too complex (complexity > `max_complexity`)
- Low plan confidence (< `min_plan_confidence`)

### Failure States

Work items transition to `failed` state if:
- Analysis fails unexpectedly
- Planning fails unexpectedly
- Execution fails after all retries
- Tests fail after max fix attempts
- PR creation fails

## Monitoring & Metrics

### Issue Monitor Metrics

- Total issues found
- Issues claimed
- Issues skipped (concurrent limit)
- Issues skipped (already claimed)
- Rate limit hits
- Errors encountered

### Issue Processor Metrics

- Total work items processed
- Successful completions
- Failures
- Success rate
- Stage completion statistics

### Audit Logging

All workflow events are logged to the audit log:
- Issue claimed
- Analysis started/completed
- Plan generated
- Implementation started/completed
- Tests run
- Fix attempts
- PR created

## Integration Points

### Multi-Agent-Coder

Used for:
- Issue analysis (multiple providers for consensus)
- Implementation planning (dialectical approach)
- Test failure analysis (root cause identification)

### GitHub API

Used for:
- Fetching issues
- Creating pull requests
- Adding labels
- Requesting reviews

### Git Operations

Used for:
- Branch creation
- Code changes
- Committing with signatures
- Pushing to remote

### Test Runner

Supports:
- pytest (Python)
- jest (JavaScript)
- go test (Go)
- Auto-detection of framework

## Performance

### Typical Processing Times

- Issue Analysis: 1-2 minutes
- Implementation Planning: 3-5 minutes
- Code Execution: 5-10 minutes (depends on complexity)
- Test Running: 1-5 minutes (depends on test suite)
- PR Creation: < 30 seconds

Total: **15-30 minutes per issue** (varies by complexity)

### Resource Usage

- Multi-agent queries: 3-5 per issue
- GitHub API calls: 10-15 per issue
- Token usage: ~10K-20K tokens per issue
- Cost: ~$0.10-$0.30 per issue (varies by provider)

## Future Enhancements

### Phase 3 Integration

- PR monitoring and CI waiting
- Review feedback processing
- Auto-merge capabilities

### Advanced Features

- Parallel issue processing
- Priority queues
- Cost optimization
- Caching of analysis results
- Learning from past successes/failures

## Troubleshooting

### Issue not being processed

Check:
1. Issue has correct labels (`auto_claim_labels`)
2. Doesn't have ignore labels
3. Not at concurrent limit
4. Auto-implementation is enabled
5. Check logs for errors

### Work item stuck in state

- View state with `python -m src.cli export-state`
- Check error message in work item
- Review audit log for details
- May need manual intervention

### Tests failing repeatedly

- Check `max_auto_fix_attempts` setting
- Review test failure analysis in logs
- May need to increase `min_fix_confidence`
- Consider manual fixes for complex failures

## References

- Issue #7: Phase 2 Integration
- [Multi-Agent-Coder Documentation](../multi_agent_coder/)
- [Configuration Guide](../config/)
- [Development Roadmap](../ROADMAP.md)
