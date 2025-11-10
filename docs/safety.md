# Safety & Monitoring Features

The Self-Reflexive Orchestrator includes comprehensive safety mechanisms to ensure reliable, secure, and cost-effective autonomous operation.

## Table of Contents

- [Safety Philosophy](#safety-philosophy)
- [Safety Layers](#safety-layers)
- [Rate Limiting](#rate-limiting)
- [Cost Tracking](#cost-tracking)
- [Complexity Guards](#complexity-guards)
- [File Protection](#file-protection)
- [Breaking Change Detection](#breaking-change-detection)
- [Rollback Capability](#rollback-capability)
- [Human Approval Gates](#human-approval-gates)
- [Health Monitoring](#health-monitoring)
- [Notifications](#notifications)
- [Configuration](#configuration)

## Safety Philosophy

The orchestrator follows a **defense-in-depth** approach with multiple independent safety layers:

1. **Prevention**: Stop dangerous operations before they start
2. **Detection**: Monitor for issues during execution
3. **Recovery**: Rollback and restore when problems occur
4. **Escalation**: Involve humans for critical decisions

All safety mechanisms are:
- **Configurable**: Adjust thresholds to your needs
- **Observable**: Track statistics and violations
- **Fail-safe**: Default to safe behavior on errors

## Safety Layers

### Layer 1: Rate Limiting

Prevents runaway API usage and excessive resource consumption.

**Features:**
- Token bucket algorithm with burst capacity
- Per-operation and global limits
- Automatic backoff on rate limit violations
- Statistics tracking for monitoring

**When it activates:**
- Too many API calls in short time period
- Burst capacity exceeded
- Sustained high request rate

**Configuration:**
```yaml
safety:
  rate_limits:
    requests_per_minute: 60  # Base rate limit
    burst_size: 10           # Burst capacity
    window_size: 60          # Rolling window (seconds)
```

**Example:**
```python
from src.safety.rate_limiter import RateLimiter

limiter = RateLimiter(
    requests_per_minute=60,
    burst_size=10
)

allowed, wait_time = limiter.check_rate_limit("anthropic_api")
if not allowed:
    print(f"Rate limited. Wait {wait_time} seconds")
```

### Layer 2: Cost Tracking

Ensures API usage stays within budget limits.

**Features:**
- Real-time cost tracking per provider
- Daily budget enforcement
- Cost estimation before operations
- Detailed usage reporting

**When it activates:**
- Daily cost limit approaching (90%)
- Daily cost limit exceeded
- Single operation too expensive

**Configuration:**
```yaml
safety:
  cost_limits:
    daily_limit: 100.0       # USD per day
    warning_threshold: 0.9   # 90% warning
```

**Example:**
```python
from src.safety.cost_tracker import CostTracker

tracker = CostTracker(daily_limit=100.0)

# Check before expensive operation
if tracker.can_afford_operation(estimated_cost=5.0):
    # Proceed with operation
    result = call_api()
    tracker.track_request(
        provider="anthropic",
        model="claude-3-sonnet",
        tokens=10000,
        cost=5.0
    )
```

### Layer 3: Complexity Guards

Prevents overly complex or risky changes.

**Features:**
- Complexity estimation for code changes
- File count and line change limits
- Risk scoring based on change scope
- Automatic escalation for complex changes

**When it activates:**
- Too many files modified (>20)
- Too many lines changed (>1000)
- High complexity score (>8/10)
- Multiple high-risk factors combined

**Configuration:**
```yaml
safety:
  complexity:
    max_complexity: 7
    max_files: 20
    max_lines: 1000
```

**Example:**
```python
from src.safety.guards import ComplexityGuard

guard = ComplexityGuard(max_complexity=7)

context = {
    "files_changed": 5,
    "lines_added": 200,
    "complexity_estimate": 6
}

result = guard.check(context)
if not result.allowed:
    print(f"Blocked: {result.reason}")
```

### Layer 4: File Protection

Protects critical files from accidental modification.

**Features:**
- Pattern-based file protection
- Automatic detection of sensitive files
- Whitelist for authorized changes
- Audit logging of protection violations

**Protected by default:**
- Configuration files (`.env`, `*.yaml`)
- Credentials and secrets
- Git internals (`.git/*`)
- CI/CD configuration
- Database schemas

**Configuration:**
```yaml
safety:
  protected_files:
    - "*.env*"
    - "config/*.yaml"
    - ".git/*"
    - "credentials.json"
    - "database/schema.sql"
```

**Example:**
```python
from src.safety.guards import FileProtectionGuard

guard = FileProtectionGuard(
    protected_patterns=["*.env", "config/*"]
)

result = guard.check({"file_path": ".env.production"})
if not result.allowed:
    print(f"File protected: {result.reason}")
```

### Layer 5: Breaking Change Detection

Identifies changes that could break existing functionality.

**Features:**
- API signature analysis
- Public interface detection
- Semantic versioning checks
- Impact assessment

**What it detects:**
- Removed public functions/classes
- Changed function signatures
- Modified API contracts
- Deleted configuration options

**Configuration:**
```yaml
safety:
  breaking_changes:
    check_enabled: true
    require_major_version: true
    block_unannounced: true
```

### Layer 6: Rollback Capability

Enables quick recovery from failed changes.

**Features:**
- Git-based rollback points
- Tagged releases for easy restore
- Automatic rollback on test failures
- Manual rollback by ID or PR number

**When it triggers:**
- Test failures after merge
- CI/CD pipeline failures
- Manual rollback request
- Health check failures

**Example:**
```python
from src.safety.rollback import RollbackManager

manager = RollbackManager(repo_path=Path("/repo"))

# Create rollback point before risky change
rollback_id = manager.create_rollback_point(
    pr_number=123,
    description="Feature X implementation"
)

try:
    # Make changes
    deploy_feature()
except Exception:
    # Rollback on failure
    manager.rollback(rollback_id)
```

### Layer 7: Human Approval Gates

Requires human approval for critical operations.

**Features:**
- Multi-agent risk assessment
- Automatic approval for low-risk changes
- Configurable approval criteria
- Timeout and escalation handling
- Audit trail of all decisions

**Requires approval:**
- Merges to main branch
- Breaking changes
- Security-related changes
- High-risk/complexity changes
- Production deployments

**Configuration:**
```yaml
safety:
  human_approval_required:
    - merge_to_main
    - breaking_changes
    - security_related
    - high_complexity
  approval_timeout_hours: 24
  auto_approve_low_risk: true
```

**Example:**
```python
from src.safety.approval import ApprovalSystem

system = ApprovalSystem(
    multi_agent_client=client,
    timeout_hours=24,
    auto_approve_low_risk=True
)

request = ApprovalRequest(
    operation="merge_pr",
    description="Merge feature X to main",
    risk_factors={
        "breaking_changes": False,
        "complexity": 5
    }
)

decision = await system.request_approval(request)
if decision.approved:
    # Proceed with merge
    merge_pr()
```

### Layer 8: Health Monitoring

Continuously monitors system health and resource usage.

**Monitors:**
- CPU usage (threshold: 80%)
- Memory usage (threshold: 85%)
- Disk space (threshold: 90%)
- Git repository status
- GitHub API connectivity
- Multi-agent-coder availability

**Health States:**
- `HEALTHY`: All systems normal
- `DEGRADED`: Issues detected, still operational
- `UNHEALTHY`: Critical issues, limited functionality

**Configuration:**
```yaml
safety:
  health_monitoring:
    check_interval: 300  # 5 minutes
    cpu_threshold: 0.8
    memory_threshold: 0.85
    disk_threshold: 0.9
```

**Example:**
```python
from src.core.health import HealthChecker

checker = HealthChecker(repo_path=Path("/repo"))

report = checker.check_health()
if report.overall_status != HealthStatus.HEALTHY:
    print(f"Health issues detected:")
    for check in report.checks:
        if check.status != HealthStatus.HEALTHY:
            print(f"  - {check.component}: {check.message}")
```

### Layer 9: Notifications

Alerts operators of important events and issues.

**Notification Channels:**
- Slack
- Email
- Webhooks
- Logs

**Events:**
- PR created/merged
- CI failures
- Safety violations
- Health degradation
- Approval requests
- Rollbacks performed

**Configuration:**
```yaml
notifications:
  slack:
    enabled: true
    webhook_url: "https://hooks.slack.com/..."
    on_events:
      - pr_created
      - pr_merged
      - ci_failure
      - safety_violation
```

## Configuration

### Complete Safety Configuration Example

```yaml
# config/orchestrator-config.yaml

safety:
  # Rate limiting
  rate_limits:
    requests_per_minute: 60
    burst_size: 10
    window_size: 60

  # Cost tracking
  cost_limits:
    daily_limit: 100.0
    warning_threshold: 0.9

  # Complexity guards
  complexity:
    max_complexity: 7
    max_files: 20
    max_lines: 1000

  # File protection
  protected_files:
    - "*.env*"
    - "config/*.yaml"
    - ".git/*"
    - "credentials.json"

  # Breaking changes
  breaking_changes:
    check_enabled: true
    require_major_version: true

  # Human approval
  human_approval_required:
    - merge_to_main
    - breaking_changes
    - security_related
  approval_timeout_hours: 24
  auto_approve_low_risk: true

  # Health monitoring
  health_monitoring:
    check_interval: 300
    cpu_threshold: 0.8
    memory_threshold: 0.85
    disk_threshold: 0.9

# Notifications
notifications:
  slack:
    enabled: true
    webhook_url: "${SLACK_WEBHOOK_URL}"
    on_events:
      - pr_created
      - pr_merged
      - ci_failure
      - safety_violation
      - approval_request
      - health_degraded
```

## Monitoring & Observability

### Safety Statistics

All safety components provide real-time statistics:

```python
# Rate limiter stats
stats = rate_limiter.get_statistics()
# {
#     "total_requests": 1000,
#     "allowed": 950,
#     "rejected": 50,
#     "current_rate": 45.2
# }

# Cost tracker report
report = cost_tracker.get_usage_report()
# {
#     "total_cost": 42.50,
#     "daily_limit": 100.0,
#     "remaining_budget": 57.50,
#     "by_provider": {
#         "anthropic": {"cost": 30.0, "requests": 150},
#         "deepseek": {"cost": 12.5, "requests": 80}
#     }
# }

# Health check report
health = health_checker.check_health()
# HealthReport(
#     overall_status=HealthStatus.HEALTHY,
#     checks=[...],
#     timestamp=datetime.now()
# )
```

### Audit Logging

All safety events are logged with full context:

```python
logger.warning(
    "safety_violation",
    guard="ComplexityGuard",
    operation="process_issue",
    issue_number=123,
    complexity=9,
    threshold=7,
    action="blocked"
)
```

### Metrics Collection

Safety metrics are tracked for analysis:

- Safety violation counts by type
- Approval request statistics
- Rollback frequency and causes
- Health check failures
- Cost trends over time

## Best Practices

### 1. Start Conservative

Begin with strict safety limits and relax them based on observed behavior:

```yaml
safety:
  complexity:
    max_complexity: 5  # Start strict
  cost_limits:
    daily_limit: 10.0  # Start low
```

### 2. Monitor Continuously

Set up monitoring dashboards for:
- Safety violation trends
- Cost usage patterns
- Health check results
- Approval request frequency

### 3. Review Violations

Regularly review safety violations to:
- Identify patterns
- Adjust thresholds
- Improve guards
- Update documentation

### 4. Test Safety Mechanisms

Include safety testing in your test suite:

```python
def test_safety_prevents_runaway_costs():
    """Verify cost limits prevent expensive operations."""
    tracker = CostTracker(daily_limit=1.0)
    tracker.track_request("provider", "model", 1000, 0.95)

    assert not tracker.can_afford_operation(0.10)
```

### 5. Document Overrides

When you override safety checks, document why:

```python
# Override: Emergency hotfix for production incident #456
# Approved by: Engineering Lead
# Date: 2025-01-15
with safety_override("complexity_check"):
    apply_emergency_fix()
```

## Troubleshooting

See [troubleshooting.md](troubleshooting.md) for common issues and solutions.

## Related Documentation

- [Operations Runbook](operations.md)
- [Troubleshooting Guide](troubleshooting.md)
- [Architecture Overview](../README.md)
