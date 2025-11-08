# Quick Start Guide

Get the Self-Reflexive Coding Orchestrator up and running in 5 minutes.

## Prerequisites

- Python 3.9+
- GitHub account with personal access token
- Anthropic API key

## 5-Minute Setup

### 1. Run Setup Script

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

This will:
- Create virtual environment
- Install dependencies
- Create configuration files
- Run tests

### 2. Get API Keys

#### GitHub Token
1. Go to https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Select scopes: `repo`, `workflow`, `admin:org` (if using org repos)
4. Copy the token

#### Anthropic API Key
1. Go to https://console.anthropic.com/
2. Navigate to API Keys
3. Create a new key
4. Copy the key

### 3. Configure

Edit `.env` file:

```bash
GITHUB_TOKEN=ghp_your_token_here
ANTHROPIC_API_KEY=sk-ant-your_key_here
```

Edit `config/orchestrator-config.yaml`:

```yaml
github:
  repository: "your-username/your-repo"  # Change this!
  base_branch: main

orchestrator:
  mode: supervised  # Start with supervised mode
```

### 4. Validate

```bash
source venv/bin/activate
python -m src.cli validate-config
```

You should see:
```
✓ Configuration is valid!
```

### 5. Start!

```bash
python -m src.cli start --mode supervised
```

## First Steps

### Label an Issue for Processing

1. Go to your GitHub repository
2. Create or open an issue
3. Add the label `bot-approved`
4. The orchestrator will detect it on the next poll cycle

### Manually Trigger Processing

```bash
# Process issue #123
python -m src.cli process-issue 123

# Check status
python -m src.cli status

# List issues
python -m src.cli list-issues
```

## Modes Explained

### Manual Mode
```bash
python -m src.cli start --mode manual
```
- Orchestrator waits for explicit CLI commands
- Use `process-issue` to trigger processing
- Safest mode for testing

### Supervised Mode (Recommended)
```bash
python -m src.cli start --mode supervised
```
- Auto-processes labeled issues
- Requires human approval for merges
- Good balance of automation and control

### Autonomous Mode
```bash
python -m src.cli start --mode autonomous
```
- Fully automated
- Auto-merges passing PRs
- Use only after thorough testing!

## Common Tasks

### List Open Issues
```bash
python -m src.cli list-issues
```

### List Issues with Specific Labels
```bash
python -m src.cli list-issues --labels "bug,priority-high"
```

### Check Status
```bash
python -m src.cli status
```

### Export State
```bash
python -m src.cli export-state
```

## Configuration Tips

### Start Small
Begin with simple issues:
```yaml
issue_processing:
  max_complexity: 3  # Only simple issues
  max_concurrent: 1  # One at a time
```

### Test on Non-Critical Repo
Use a test repository first:
```yaml
github:
  repository: "your-username/test-repo"
```

### Enable Notifications
Get notified of key events:
```yaml
notifications:
  slack_webhook: "https://hooks.slack.com/..."
  on_events:
    - error
    - merge
    - human_approval_required
```

## Troubleshooting

### "Configuration file not found"
```bash
cp config/orchestrator-config.yaml.example config/orchestrator-config.yaml
```

### "GitHub token is required"
Add token to `.env`:
```bash
echo "GITHUB_TOKEN=your_token" >> .env
```

### "Failed to fetch issues"
Check token permissions - needs `repo` scope.

### Import errors
```bash
pip install -r requirements.txt --force-reinstall
```

## What's Next?

After Phase 1 (current):
- **Phase 2**: Actual issue processing will be implemented
- **Phase 3**: PR management and code review integration
- **Phase 4**: Roadmap generation

Currently, the orchestrator will:
- ✅ Monitor for labeled issues
- ✅ Track work items in state
- ✅ Log all operations
- ⏳ Full implementation coming in Phase 2+

## Getting Help

- Check `logs/orchestrator.log` for detailed logs
- Check `logs/audit.log` for audit trail
- Review README.md for full documentation
- Open an issue on GitHub

## Safety Reminders

1. ✅ Always start in supervised mode
2. ✅ Test on non-critical repositories first
3. ✅ Monitor API costs
4. ✅ Review audit logs regularly
5. ✅ Keep backups of important code

---

Happy automating! 🤖✨
