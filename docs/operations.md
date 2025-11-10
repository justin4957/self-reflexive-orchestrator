# Operations Runbook

Complete operational guide for running and maintaining the Self-Reflexive Orchestrator in production.

## Table of Contents

- [Quick Start](#quick-start)
- [Starting the Orchestrator](#starting-the-orchestrator)
- [Stopping the Orchestrator](#stopping-the-orchestrator)
- [Monitoring Health](#monitoring-health)
- [Responding to Alerts](#responding-to-alerts)
- [Approving Operations](#approving-operations)
- [Rolling Back Changes](#rolling-back-changes)
- [Debugging Issues](#debugging-issues)
- [Recovering from Failures](#recovering-from-failures)
- [Maintenance Tasks](#maintenance-tasks)
- [Emergency Procedures](#emergency-procedures)

## Quick Start

### Prerequisites

- Python 3.9+
- Git repository access
- GitHub Personal Access Token
- Anthropic API key
- Multi-agent-coder CLI installed

### Initial Setup

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/self-reflexive-orchestrator.git
cd self-reflexive-orchestrator

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Copy and configure
cp config/orchestrator-config.yaml.example config/orchestrator-config.yaml
cp .env.example .env

# 5. Edit configuration
vim config/orchestrator-config.yaml
vim .env

# 6. Validate configuration
python -m src.cli validate-config

# 7. Check health
python -m src.cli health-check
```

## Starting the Orchestrator

### Manual Mode

For testing and development:

```bash
# Process a specific issue
python -m src.cli process-issue 123

# Generate a roadmap
python -m src.cli generate-roadmap

# Review a PR
python -m src.cli review-pr 456
```

### Supervised Mode

Orchestrator processes issues but requires approval for critical operations:

```bash
# Start in supervised mode
python -m src.cli start --mode supervised

# Or configure in config file
orchestrator:
  mode: supervised
  poll_interval: 300  # Check every 5 minutes
```

### Autonomous Mode

**WARNING**: Only use in production after thorough testing.

```bash
# Start in autonomous mode
python -m src.cli start --mode autonomous

# Monitor logs
tail -f logs/orchestrator.log
```

### Running as a Service

#### Using systemd (Linux)

Create `/etc/systemd/system/orchestrator.service`:

```ini
[Unit]
Description=Self-Reflexive Orchestrator
After=network.target

[Service]
Type=simple
User=orchestrator
WorkingDirectory=/opt/orchestrator
Environment="PATH=/opt/orchestrator/venv/bin"
ExecStart=/opt/orchestrator/venv/bin/python -m src.cli start --mode supervised
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

Commands:

```bash
# Enable and start
sudo systemctl enable orchestrator
sudo systemctl start orchestrator

# Check status
sudo systemctl status orchestrator

# View logs
sudo journalctl -u orchestrator -f

# Stop
sudo systemctl stop orchestrator
```

#### Using Docker

```bash
# Build image
docker build -t orchestrator:latest .

# Run container
docker run -d \
  --name orchestrator \
  --env-file .env \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/logs:/app/logs \
  orchestrator:latest

# View logs
docker logs -f orchestrator

# Stop
docker stop orchestrator
```

## Stopping the Orchestrator

### Graceful Shutdown

```bash
# If running in terminal
Ctrl+C  # Sends SIGINT

# If running as service
sudo systemctl stop orchestrator

# If running in Docker
docker stop orchestrator
```

The orchestrator will:
1. Stop accepting new issues
2. Complete current operations
3. Save state
4. Exit cleanly

### Force Stop

**Only use if graceful shutdown fails:**

```bash
# Find process
ps aux | grep "src.cli"

# Kill process
kill -9 <PID>

# Or with systemd
sudo systemctl kill -s SIGKILL orchestrator
```

## Monitoring Health

### Health Check Command

```bash
# Run health check
python -m src.cli health-check

# Output example:
# Overall Status: HEALTHY
#
# Components:
# ✓ CPU Usage: 45% (HEALTHY)
# ✓ Memory: 60% (HEALTHY)
# ✓ Disk Space: 70% (HEALTHY)
# ✓ Git Repository: Clean (HEALTHY)
# ✓ GitHub API: Connected (HEALTHY)
# ✓ Multi-Agent Coder: Available (HEALTHY)
```

### Status Dashboard

```bash
# View orchestrator status
python -m src.cli status

# Output:
# Orchestrator Status
# ------------------
# Mode: supervised
# State: running
# Issues processed: 45
# PRs created: 40
# Current cost: $12.50 / $100.00 daily
# Rate limit: 45 / 60 rpm
# Pending approvals: 2
```

### Metrics

```bash
# View cost usage
python -m src.cli metrics cost

# View rate limit stats
python -m src.cli metrics rate-limits

# View safety violations
python -m src.cli metrics safety
```

### Log Monitoring

```bash
# Follow main log
tail -f logs/orchestrator.log

# Search for errors
grep ERROR logs/orchestrator.log

# Search for safety violations
grep "safety_violation" logs/orchestrator.log

# View recent activity
tail -n 100 logs/orchestrator.log
```

## Responding to Alerts

### Alert Types

#### 1. Health Degraded

**Alert**: "System health degraded: High CPU usage"

**Response**:
```bash
# 1. Check health details
python -m src.cli health-check

# 2. Check current operations
python -m src.cli status

# 3. Review logs for heavy operations
grep "started" logs/orchestrator.log | tail -n 20

# 4. If necessary, temporarily pause
python -m src.cli pause
```

#### 2. Cost Limit Approaching

**Alert**: "Daily cost at 90% of limit"

**Response**:
```bash
# 1. Check cost breakdown
python -m src.cli metrics cost

# 2. Review recent expensive operations
grep "track_request" logs/orchestrator.log | tail -n 50

# 3. Options:
#    a) Increase daily limit (config change)
#    b) Pause until tomorrow
#    c) Continue with caution

# To pause:
python -m src.cli pause

# To increase limit (requires config update and restart):
vim config/orchestrator-config.yaml
# Edit: safety.cost_limits.daily_limit
sudo systemctl restart orchestrator
```

#### 3. Safety Violation

**Alert**: "Safety violation: Complexity guard blocked operation"

**Response**:
```bash
# 1. View violation details
grep "safety_violation" logs/orchestrator.log | tail -n 1

# 2. Review the blocked operation context
# Look for issue number or PR number in log

# 3. Assess if violation was correct:
#    - If correct: No action needed, safety working as intended
#    - If incorrect: Adjust guard thresholds

# 4. To adjust thresholds:
vim config/orchestrator-config.yaml
# Edit: safety.complexity.max_complexity
sudo systemctl restart orchestrator
```

#### 4. CI Failure

**Alert**: "CI failed on PR #123"

**Response**:
```bash
# 1. View PR details
gh pr view 123

# 2. Check CI logs
gh pr checks 123

# 3. Check if auto-fix is enabled
#    (Orchestrator will attempt to fix automatically)

# 4. Monitor for fix attempt
tail -f logs/orchestrator.log | grep "pr_123"

# 5. If auto-fix fails, manual intervention may be needed
```

#### 5. Approval Request

**Alert**: "Approval required for PR #456"

**Response**: See [Approving Operations](#approving-operations) section.

## Approving Operations

### View Pending Approvals

```bash
# List pending approvals
python -m src.cli approvals list

# Output:
# Pending Approvals
# ----------------
# ID: apr_1234
# Operation: merge_pr_456
# Risk Level: MEDIUM
# Requested: 2 hours ago
# Expires: 22 hours
#
# ID: apr_1235
# Operation: security_change
# Risk Level: HIGH
# Requested: 30 minutes ago
# Expires: 23.5 hours
```

### Review Approval Request

```bash
# View details
python -m src.cli approvals view apr_1234

# Output shows:
# - Operation description
# - Risk assessment
# - Changed files
# - Test results
# - Multi-agent risk analysis
```

### Approve Operation

```bash
# Approve with comment
python -m src.cli approvals approve apr_1234 \
  --comment "Reviewed and approved. Tests passing."

# Approve multiple
python -m src.cli approvals approve apr_1234 apr_1235
```

### Deny Operation

```bash
# Deny with reason
python -m src.cli approvals deny apr_1234 \
  --reason "Security concerns. Need additional review."
```

### Auto-Approval

Low-risk operations are auto-approved if configured:

```yaml
safety:
  auto_approve_low_risk: true
```

To disable auto-approval temporarily:

```bash
python -m src.cli config set safety.auto_approve_low_risk false
```

## Rolling Back Changes

### List Rollback Points

```bash
# List recent rollback points
python -m src.cli rollback list

# Output:
# Rollback Points
# ---------------
# ID: rb_1234
# PR: #456
# Description: Add authentication feature
# Created: 2 hours ago
# Commit: abc123def
#
# ID: rb_1235
# PR: #457
# Description: Update dependencies
# Created: 1 hour ago
# Commit: def456abc
```

### Perform Rollback

```bash
# Rollback by ID
python -m src.cli rollback rb_1234

# Rollback by PR number
python -m src.cli rollback --pr 456

# Rollback to specific commit
python -m src.cli rollback --commit abc123def
```

### Verify Rollback

```bash
# Check git status
git log -1

# Run tests
pytest

# Check health
python -m src.cli health-check
```

### Manual Rollback

If CLI rollback fails:

```bash
# 1. Find the commit to rollback to
git log --oneline -20

# 2. Reset to that commit
git reset --hard <commit-hash>

# 3. Force push (if already pushed)
git push --force origin main

# 4. Restart orchestrator
sudo systemctl restart orchestrator
```

## Debugging Issues

### Enable Debug Logging

```bash
# Set log level to DEBUG
python -m src.cli start --log-level DEBUG

# Or in config:
logging:
  level: DEBUG
```

### Common Issues

#### Issue: Orchestrator won't start

**Debug steps:**
```bash
# 1. Validate configuration
python -m src.cli validate-config

# 2. Check dependencies
pip list | grep anthropic
pip list | grep github

# 3. Test API connections
python -m src.cli test-connections

# 4. Check logs
cat logs/orchestrator.log
```

#### Issue: Issues not being processed

**Debug steps:**
```bash
# 1. Check status
python -m src.cli status

# 2. Verify label configuration
grep "auto_claim_labels" config/orchestrator-config.yaml

# 3. Check GitHub API
python -m src.cli test-github

# 4. Review recent logs
tail -n 100 logs/orchestrator.log
```

#### Issue: High API costs

**Debug steps:**
```bash
# 1. Check cost breakdown
python -m src.cli metrics cost

# 2. Find expensive operations
grep "track_request" logs/orchestrator.log | \
  awk '{print $NF}' | sort -nr | head -10

# 3. Review model usage
grep "model=" logs/orchestrator.log | cut -d= -f2 | sort | uniq -c

# 4. Consider:
#    - Using cheaper models
#    - Reducing max_tokens
#    - Adjusting temperature
```

See [troubleshooting.md](troubleshooting.md) for more issues and solutions.

## Recovering from Failures

### Git Repository Corruption

```bash
# 1. Backup current state
cp -r .git .git.backup

# 2. Verify corruption
git fsck

# 3. If corrupted, re-clone
cd ..
git clone <repo-url> orchestrator-new
cd orchestrator-new

# 4. Restore configuration
cp ../orchestrator/config/orchestrator-config.yaml config/
cp ../orchestrator/.env .env

# 5. Restart
python -m src.cli start
```

### State File Corruption

```bash
# 1. Stop orchestrator
sudo systemctl stop orchestrator

# 2. Backup state
cp .orchestrator-state.json .orchestrator-state.json.backup

# 3. Reset state
rm .orchestrator-state.json

# 4. Restart (will rebuild state)
sudo systemctl start orchestrator
```

### Database Issues (Redis)

```bash
# 1. Check Redis status
redis-cli ping

# 2. If down, restart Redis
sudo systemctl restart redis

# 3. Clear Redis cache if corrupted
redis-cli FLUSHALL

# 4. Restart orchestrator
sudo systemctl restart orchestrator
```

## Maintenance Tasks

### Daily

- [ ] Check health status
- [ ] Review pending approvals
- [ ] Monitor cost usage
- [ ] Check for safety violations

```bash
# Daily check script
#!/bin/bash
python -m src.cli health-check
python -m src.cli approvals list
python -m src.cli metrics cost
grep "safety_violation" logs/orchestrator.log | tail -n 10
```

### Weekly

- [ ] Review processed issues
- [ ] Analyze cost trends
- [ ] Update dependencies
- [ ] Review and clean old rollback points
- [ ] Rotate logs

```bash
# Weekly maintenance script
#!/bin/bash
python -m src.cli metrics summary --period week
python -m src.cli rollback cleanup --older-than 30d
python -m src.cli logs rotate
pip list --outdated
```

### Monthly

- [ ] Review safety thresholds
- [ ] Update configuration
- [ ] Test rollback procedures
- [ ] Review and update documentation
- [ ] Backup configuration

```bash
# Monthly backup
tar -czf backup-$(date +%Y%m%d).tar.gz \
  config/ .env .orchestrator-state.json
```

## Emergency Procedures

### Complete System Failure

```bash
# 1. Stop everything
sudo systemctl stop orchestrator
docker stop orchestrator

# 2. Assess damage
git status
python -m src.cli health-check

# 3. Rollback to last known good state
python -m src.cli rollback --latest

# 4. If rollback fails, manual recovery:
git log --oneline -50  # Find last good commit
git reset --hard <commit>
git push --force origin main

# 5. Restart in manual mode
python -m src.cli start --mode manual

# 6. Verify health
python -m src.cli health-check

# 7. Gradually restore to supervised mode
python -m src.cli start --mode supervised
```

### Security Incident

```bash
# 1. IMMEDIATELY STOP ORCHESTRATOR
sudo systemctl stop orchestrator

# 2. Rotate all credentials
#    - Generate new GitHub token
#    - Generate new Anthropic API key
#    - Update .env file

# 3. Review recent activity
grep "security" logs/orchestrator.log
git log --since="24 hours ago"

# 4. Audit all recent PRs
gh pr list --state merged --limit 50

# 5. If necessary, revert suspicious PRs
gh pr view <pr-number>
git revert <commit-hash>

# 6. Update security configuration
vim config/orchestrator-config.yaml
# Add to protected_files, increase approval requirements

# 7. Restart with enhanced monitoring
python -m src.cli start --mode supervised --log-level DEBUG
```

### Data Loss

```bash
# 1. Stop orchestrator
sudo systemctl stop orchestrator

# 2. Restore from backup
tar -xzf backup-YYYYMMDD.tar.gz

# 3. Verify integrity
python -m src.cli validate-config
git fsck

# 4. Rebuild state if needed
rm .orchestrator-state.json

# 5. Restart
sudo systemctl start orchestrator
```

## Support and Escalation

### Getting Help

1. Check [troubleshooting.md](troubleshooting.md)
2. Review logs: `logs/orchestrator.log`
3. Search issues: `gh issue list`
4. File new issue: `gh issue create`

### Escalation Criteria

Escalate to engineering if:
- System repeatedly fails to start
- Data corruption detected
- Security incident suspected
- Unknown safety violations
- Rollback fails repeatedly

### Emergency Contacts

Maintain an emergency contact list:

```yaml
# config/emergency-contacts.yaml
contacts:
  engineering_lead:
    name: "Engineering Lead"
    slack: "@eng-lead"
    phone: "+1-555-0100"

  devops:
    name: "DevOps Team"
    slack: "#devops-urgent"
    pagerduty: "devops-escalation"

  security:
    name: "Security Team"
    slack: "#security-incidents"
    email: "security@company.com"
```

## Related Documentation

- [Safety Features](safety.md)
- [Troubleshooting Guide](troubleshooting.md)
- [Architecture Overview](../README.md)
