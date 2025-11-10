# Troubleshooting Guide

Common issues, their causes, and solutions for the Self-Reflexive Orchestrator.

## Table of Contents

- [Startup Issues](#startup-issues)
- [Configuration Problems](#configuration-problems)
- [API and Network Issues](#api-and-network-issues)
- [Performance Problems](#performance-problems)
- [Safety and Security Issues](#safety-and-security-issues)
- [Git and Repository Issues](#git-and-repository-issues)
- [Testing and CI Problems](#testing-and-ci-problems)
- [Cost and Rate Limiting](#cost-and-rate-limiting)
- [Logging and Debugging](#logging-and-debugging)

## Startup Issues

### Orchestrator Won't Start

**Symptoms:**
- Command exits immediately
- Error: "Configuration file not found"
- Error: "Invalid configuration"

**Causes & Solutions:**

#### Missing Configuration File

```bash
# Check if config exists
ls config/orchestrator-config.yaml

# If missing, copy example
cp config/orchestrator-config.yaml.example config/orchestrator-config.yaml

# Edit configuration
vim config/orchestrator-config.yaml
```

#### Invalid Configuration

```bash
# Validate configuration
python -m src.cli validate-config

# Common issues:
# - Missing required fields (repository, token, api_key)
# - Invalid YAML syntax
# - Incorrect data types

# Fix and revalidate
vim config/orchestrator-config.yaml
python -m src.cli validate-config
```

#### Missing Environment Variables

```bash
# Check environment
echo $GITHUB_TOKEN
echo $ANTHROPIC_API_KEY

# If empty, create .env file
cp .env.example .env
vim .env

# Add:
# GITHUB_TOKEN=your_token_here
# ANTHROPIC_API_KEY=your_key_here

# Load environment
source .env  # or restart terminal
```

#### Dependency Issues

```bash
# Reinstall dependencies
pip install --upgrade pip
pip install -e ".[dev]"

# If specific package fails
pip install --upgrade anthropic
pip install --upgrade PyGithub

# Clear cache and reinstall
pip cache purge
pip install -e ".[dev]" --no-cache-dir
```

### Module Import Errors

**Error:** `ModuleNotFoundError: No module named 'src'`

**Solution:**
```bash
# Ensure installed in editable mode
pip install -e .

# Or set PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Verify installation
pip list | grep self-reflexive-orchestrator
```

### Permission Errors

**Error:** `PermissionError: [Errno 13] Permission denied`

**Solutions:**
```bash
# Check file permissions
ls -la config/
ls -la logs/

# Fix permissions
chmod 644 config/orchestrator-config.yaml
chmod 755 logs/

# If running as service, check user
sudo systemctl status orchestrator
# Ensure WorkingDirectory and files are owned by service user
sudo chown -R orchestrator:orchestrator /opt/orchestrator
```

## Configuration Problems

### Multi-Agent-Coder Path Not Found

**Error:** `multi-agent-coder path does not exist: ../multi_agent_coder/multi_agent_coder`

**Solutions:**

```bash
# Option 1: Install multi-agent-coder
cd ..
git clone https://github.com/yourusername/multi-agent-coder.git
cd multi-agent-coder
pip install -e .

# Verify installation
which multi_agent_coder

# Option 2: Update config path
vim config/orchestrator-config.yaml
# Update: code_review.multi_agent_coder_path

# Option 3: Disable if not needed
vim config/orchestrator-config.yaml
# Set: roadmap.enabled: false
```

### Invalid Mode Configuration

**Error:** `Invalid mode: 'auto'. Must be one of: manual, supervised, autonomous`

**Solution:**
```bash
vim config/orchestrator-config.yaml

# Fix mode value
orchestrator:
  mode: supervised  # Not 'auto'
```

### YAML Syntax Errors

**Error:** `yaml.scanner.ScannerError: while scanning...`

**Solutions:**
```bash
# Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('config/orchestrator-config.yaml'))"

# Common issues:
# - Tabs instead of spaces (use spaces only)
# - Inconsistent indentation
# - Missing quotes around special characters
# - Unclosed brackets or quotes

# Use YAML linter
yamllint config/orchestrator-config.yaml

# Or online validator
# https://www.yamllint.com/
```

## API and Network Issues

### GitHub API Rate Limit

**Error:** `github.GithubException.RateLimitExceededException`

**Solutions:**

```bash
# Check rate limit status
gh api rate_limit

# Wait for reset or use authenticated requests
# Ensure GITHUB_TOKEN is set
echo $GITHUB_TOKEN

# Increase authenticated rate limit
# - Use personal access token (5000 req/hour)
# - Use GitHub App (higher limits)

# Adjust polling interval
vim config/orchestrator-config.yaml
# Increase: orchestrator.poll_interval (seconds)
```

### GitHub API Authentication Failed

**Error:** `Bad credentials`

**Solutions:**

```bash
# Verify token
gh auth status

# Test token
curl -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/user

# Generate new token if expired
# https://github.com/settings/tokens
# Required scopes: repo, workflow, write:packages

# Update token
vim .env
# GITHUB_TOKEN=ghp_new_token_here

# Reload environment
source .env
```

### Anthropic API Errors

**Error:** `anthropic.APIError: Invalid API key`

**Solutions:**

```bash
# Verify API key
echo $ANTHROPIC_API_KEY

# Test API key
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-3-sonnet-20240229","max_tokens":10,"messages":[{"role":"user","content":"test"}]}'

# Get new API key
# https://console.anthropic.com/settings/keys

# Update key
vim .env
# ANTHROPIC_API_KEY=sk-ant-new_key_here
```

### Network Connectivity Issues

**Error:** `requests.exceptions.ConnectionError`

**Solutions:**

```bash
# Test internet connectivity
ping -c 3 api.github.com
ping -c 3 api.anthropic.com

# Check firewall
sudo iptables -L
sudo ufw status

# Check proxy settings
echo $HTTP_PROXY
echo $HTTPS_PROXY

# If behind proxy, configure:
export HTTP_PROXY=http://proxy.example.com:8080
export HTTPS_PROXY=http://proxy.example.com:8080

# Or in Python code
# See: https://requests.readthedocs.io/en/latest/user/advanced/#proxies
```

### SSL Certificate Errors

**Error:** `SSLError: [SSL: CERTIFICATE_VERIFY_FAILED]`

**Solutions:**

```bash
# Update CA certificates
sudo apt-get install ca-certificates  # Ubuntu/Debian
brew install ca-certificates          # macOS

# Update Python certificates
pip install --upgrade certifi

# As last resort (NOT RECOMMENDED for production):
# Disable SSL verification
export PYTHONHTTPSVERIFY=0
```

## Performance Problems

### High CPU Usage

**Symptoms:**
- System slow and unresponsive
- Health check shows CPU > 80%

**Solutions:**

```bash
# Check current operations
python -m src.cli status

# Identify CPU-intensive operations
ps aux | grep python | sort -k3 -r

# Reduce load:
# 1. Lower polling frequency
vim config/orchestrator-config.yaml
# Increase: orchestrator.poll_interval

# 2. Reduce concurrent operations
vim config/orchestrator-config.yaml
# Add: orchestrator.max_concurrent_operations: 1

# 3. Use less complex models
vim config/orchestrator-config.yaml
# Change: llm.model to a smaller model

# 4. Temporarily pause
python -m src.cli pause
```

### High Memory Usage

**Symptoms:**
- OOM errors
- System swapping
- Health check shows Memory > 85%

**Solutions:**

```bash
# Check memory usage
free -h
ps aux --sort=-%mem | head

# Reduce memory usage:
# 1. Reduce max_tokens
vim config/orchestrator-config.yaml
# Lower: llm.max_tokens

# 2. Clear caches
python -m src.cli cache clear

# 3. Restart orchestrator
sudo systemctl restart orchestrator

# 4. Increase system memory
# Or use swap file:
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### Slow Response Times

**Symptoms:**
- Operations take much longer than expected
- Timeouts occur frequently

**Solutions:**

```bash
# Check API latency
curl -w "@curl-format.txt" -o /dev/null -s https://api.anthropic.com

# Check network:
ping -c 10 api.anthropic.com
traceroute api.anthropic.com

# Optimize configuration:
# 1. Reduce token counts
vim config/orchestrator-config.yaml
# Lower: llm.max_tokens

# 2. Use faster model
vim config/orchestrator-config.yaml
# Change: llm.model: "claude-3-haiku-20240307"

# 3. Increase timeouts
vim config/orchestrator-config.yaml
# Increase: code_review.query_timeout

# 4. Enable caching
vim config/orchestrator-config.yaml
# Add: caching.enabled: true
```

## Safety and Security Issues

### Safety Violations Blocking Operations

**Symptoms:**
- Operations consistently blocked
- Logs show "safety_violation"

**Solutions:**

```bash
# View recent violations
grep "safety_violation" logs/orchestrator.log | tail -n 20

# Identify which guard is blocking
# Common guards: ComplexityGuard, FileProtectionGuard, CostTracker

# Option 1: Adjust thresholds
vim config/orchestrator-config.yaml
# Example: Increase complexity.max_complexity: 8

# Option 2: Disable specific guard temporarily
# (NOT RECOMMENDED for production)
vim config/orchestrator-config.yaml
# Comment out or modify guard configuration

# Option 3: Review if violations are legitimate
# If operations are genuinely too risky, violations are working correctly
```

### Unauthorized File Access

**Error:** `FileProtectionGuard blocked: .env is protected`

**Solutions:**

```bash
# This is INTENTIONAL security protection

# If you need to modify protected files:
# 1. Do it manually, not through orchestrator
git checkout -b manual-env-update
vim .env
git add .env
git commit -m "Update environment variables"
git push

# 2. Temporarily remove protection (NOT RECOMMENDED)
vim config/orchestrator-config.yaml
# Remove pattern from: safety.protected_files

# 3. Add file to whitelist
vim config/orchestrator-config.yaml
# Add: safety.protection_whitelist: [".env.example"]
```

### Cost Limit Exceeded

**Error:** `CostTracker: Daily limit exceeded`

**Solutions:**

```bash
# Check current usage
python -m src.cli metrics cost

# Option 1: Wait for daily reset (midnight UTC)

# Option 2: Increase limit
vim config/orchestrator-config.yaml
# Increase: safety.cost_limits.daily_limit: 200.0
sudo systemctl restart orchestrator

# Option 3: Reduce costs
# - Use cheaper models (haiku instead of sonnet)
# - Reduce max_tokens
# - Reduce operation frequency

# Option 4: Manual operations only
python -m src.cli pause
# Process critical issues manually
python -m src.cli process-issue 123
```

### Approval Timeout

**Symptoms:**
- Pending approvals expire
- Operations blocked waiting for approval

**Solutions:**

```bash
# Check pending approvals
python -m src.cli approvals list

# Option 1: Approve quickly
python -m src.cli approvals approve <id>

# Option 2: Increase timeout
vim config/orchestrator-config.yaml
# Increase: safety.approval_timeout_hours: 48

# Option 3: Enable auto-approval for low risk
vim config/orchestrator-config.yaml
# Set: safety.auto_approve_low_risk: true

# Option 4: Process manually to bypass approval
python -m src.cli process-issue 123 --skip-approval
```

## Git and Repository Issues

### Git Repository Dirty

**Error:** `Git repository has uncommitted changes`

**Solutions:**

```bash
# Check status
git status

# Option 1: Commit changes
git add .
git commit -m "Save working changes"

# Option 2: Stash changes
git stash

# Option 3: Reset to clean state (DESTRUCTIVE)
git reset --hard HEAD
git clean -fd

# Option 4: Allow dirty repo (NOT RECOMMENDED)
vim config/orchestrator-config.yaml
# Add: git.allow_dirty: true
```

### Merge Conflicts

**Error:** `Git merge conflict detected`

**Solutions:**

```bash
# View conflicts
git status
git diff

# Option 1: Auto-resolve (orchestrator will attempt)
python -m src.cli resolve-conflicts --pr 123

# Option 2: Manual resolution
git checkout <file>
vim <file>  # Resolve conflicts manually
git add <file>
git commit

# Option 3: Abort and retry
git merge --abort
python -m src.cli process-issue 123 --retry
```

### Detached HEAD State

**Error:** `Git repository in detached HEAD state`

**Solutions:**

```bash
# Check current state
git status

# Return to main branch
git checkout main

# Or create branch from current state
git checkout -b recovery-$(date +%Y%m%d)

# Restart orchestrator
sudo systemctl restart orchestrator
```

### Push Rejected

**Error:** `Push rejected: non-fast-forward`

**Solutions:**

```bash
# Fetch latest
git fetch origin

# Rebase onto latest
git rebase origin/main

# If conflicts, resolve them
git add .
git rebase --continue

# Force push (if necessary and safe)
git push --force-with-lease origin <branch>
```

## Testing and CI Problems

### Tests Failing Locally

**Symptoms:**
- `pytest` returns failures
- Tests pass in CI but fail locally

**Solutions:**

```bash
# Ensure dependencies up to date
pip install -e ".[dev]"

# Clear pytest cache
rm -rf .pytest_cache
pytest --cache-clear

# Run specific failing test
pytest tests/unit/test_specific.py::test_name -v

# Check environment differences
# - Python version
python --version
# - Package versions
pip list

# Reset test database/state
rm -f test.db .test-state.json

# Run with verbose output
pytest -vv --tb=long
```

### CI Pipeline Failing

**Symptoms:**
- GitHub Actions failing
- Tests pass locally but fail in CI

**Solutions:**

```bash
# View CI logs
gh run list --limit 5
gh run view <run-id>

# Common issues:

# 1. Missing dependencies in CI
#    Check .github/workflows/ci.yml
#    Ensure all dependencies in setup.py

# 2. Environment variables not set
#    Add to GitHub repository secrets
#    Settings > Secrets and variables > Actions

# 3. Python version mismatch
#    Check python-version in workflow
#    Should match your dev environment

# 4. Timeout issues
#    Increase timeout in workflow:
#    timeout-minutes: 30

# Test CI locally with act
act -j test
```

### Type Checking Errors

**Error:** `mypy` reports type errors

**Solutions:**

```bash
# Run mypy locally
mypy src/

# Common fixes:

# 1. Add type hints
def function(param: str) -> int:
    return int(param)

# 2. Use type: ignore for third-party issues
import untyped_library  # type: ignore

# 3. Update mypy config
vim setup.cfg or pyproject.toml
[mypy]
ignore_missing_imports = True

# 4. Install type stubs
pip install types-requests types-PyYAML
```

## Cost and Rate Limiting

### Rate Limit Exceeded

**Error:** `Rate limit exceeded. Wait 30 seconds.`

**Solutions:**

```bash
# Check rate limit stats
python -m src.cli metrics rate-limits

# Adjust rate limits
vim config/orchestrator-config.yaml
# Reduce: safety.rate_limits.requests_per_minute

# Increase burst capacity for spikes
vim config/orchestrator-config.yaml
# Increase: safety.rate_limits.burst_size

# Respect rate limits in code
# (orchestrator does this automatically)
```

### Unexpected High Costs

**Symptoms:**
- Costs higher than expected
- Daily limit reached quickly

**Solutions:**

```bash
# Analyze cost breakdown
python -m src.cli metrics cost --detailed

# Identify expensive operations
grep "track_request" logs/orchestrator.log | \
  awk '{print $NF}' | sort -nr | head -20

# Reduce costs:

# 1. Use cheaper models
vim config/orchestrator-config.yaml
# Change: llm.model: "claude-3-haiku-20240307"

# 2. Reduce token usage
vim config/orchestrator-config.yaml
# Lower: llm.max_tokens: 4000

# 3. Reduce operation frequency
vim config/orchestrator-config.yaml
# Increase: orchestrator.poll_interval

# 4. Enable caching
vim config/orchestrator-config.yaml
# Add: caching.enabled: true
# Add: caching.ttl: 3600

# 5. Limit multi-agent providers
vim config/orchestrator-config.yaml
# Limit: code_review.default_providers: ["anthropic"]
```

## Logging and Debugging

### Missing or Empty Logs

**Problem:** No logs being generated

**Solutions:**

```bash
# Check log directory exists
ls -la logs/

# Create if missing
mkdir -p logs
chmod 755 logs

# Check logging configuration
vim config/orchestrator-config.yaml
# Ensure:
logging:
  level: INFO
  file: logs/orchestrator.log

# Check file permissions
ls -la logs/orchestrator.log

# If running as service, check permissions
sudo systemctl status orchestrator
# Ensure service user can write to logs/
```

### Log File Too Large

**Problem:** Log file consuming disk space

**Solutions:**

```bash
# Check log size
du -h logs/orchestrator.log

# Rotate logs
python -m src.cli logs rotate

# Or manually
mv logs/orchestrator.log logs/orchestrator.log.$(date +%Y%m%d)
touch logs/orchestrator.log

# Set up log rotation
sudo vim /etc/logrotate.d/orchestrator

/opt/orchestrator/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
}
```

### Enable Debug Logging

```bash
# Temporary debug mode
python -m src.cli start --log-level DEBUG

# Permanent debug mode
vim config/orchestrator-config.yaml
# Set: logging.level: DEBUG

# Debug specific module
import logging
logging.getLogger('src.cycles').setLevel(logging.DEBUG)
```

## Getting More Help

If issues persist after trying these solutions:

1. **Check documentation:**
   - [Safety Features](safety.md)
   - [Operations Runbook](operations.md)
   - [README](../README.md)

2. **Search existing issues:**
   ```bash
   gh issue list --search "your error message"
   ```

3. **Enable debug logging and collect information:**
   ```bash
   python -m src.cli start --log-level DEBUG
   python -m src.cli status > status.txt
   python -m src.cli health-check > health.txt
   ```

4. **Create a new issue:**
   ```bash
   gh issue create --title "Problem: ..." --body "$(cat <<EOF
   ## Description
   [Describe the problem]

   ## Steps to Reproduce
   1. ...
   2. ...

   ## Expected Behavior
   [What should happen]

   ## Actual Behavior
   [What actually happens]

   ## Environment
   - OS: $(uname -a)
   - Python: $(python --version)
   - Version: $(git describe --tags)

   ## Logs
   \`\`\`
   $(tail -n 50 logs/orchestrator.log)
   \`\`\`
   EOF
   )"
   ```

5. **Join the community:**
   - GitHub Discussions
   - Slack channel (if available)
   - Stack Overflow tag: `self-reflexive-orchestrator`
