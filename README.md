# Self-Reflexive Coding Orchestrator

An autonomous coding agent that manages the entire development lifecycle for simple projects with minimal oversight. The orchestrator can work on GitHub issues, create pull requests, use multi-agent-coder for code reviews, merge approved changes, propose future development, and create new issues based on validated roadmaps.

## 🎯 Vision

Create an automated development workflow where an AI agent can:
- ✅ Monitor and claim GitHub issues
- ✅ Implement solutions autonomously
- ✅ Create pull requests with comprehensive descriptions
- ✅ Use multi-agent-coder for code reviews
- ✅ Merge approved changes automatically
- ✅ Propose future development directions
- ✅ Create new issues from validated roadmaps

## 🚀 Features

### Current (Phase 1 - Foundation)
- ✅ **Configuration System**: YAML-based configuration with validation
- ✅ **Audit Logging**: Comprehensive structured logging for all operations
- ✅ **GitHub Integration**: Full API integration for issues, PRs, and CI/CD
- ✅ **State Machine**: Track orchestrator state and work items
- ✅ **CLI Interface**: Command-line tools for manual triggers and monitoring
- ✅ **Safety Mechanisms**: Multiple validation gates and approval flows

### Coming Soon
- 🔄 **Phase 2**: Issue processing and implementation cycle
- 🔄 **Phase 3**: PR management and review integration
- 🔄 **Phase 4**: Roadmap generation and validation
- 🔄 **Phase 5**: Advanced safety and monitoring
- 🔄 **Phase 6**: Learning and optimization

## 📋 Prerequisites

- Python 3.9 or higher
- GitHub account with personal access token
- Anthropic API key (for Claude)
- `../multi-agent-coder` set up for code reviews (Phase 3+)
- Git configured with bot credentials

## 🔧 Installation

### 1. Clone the Repository

```bash
cd ec2-test-apps/self-reflexive-orchestrator
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
# Or for development:
pip install -e ".[dev]"
```

### 4. Configure Environment

Copy the example configuration and customize it:

```bash
cp config/orchestrator-config.yaml.example config/orchestrator-config.yaml
```

Edit `config/orchestrator-config.yaml` with your settings, or set environment variables:

```bash
# Create .env file
cat > .env << EOF
GITHUB_TOKEN=your_github_token_here
ANTHROPIC_API_KEY=your_anthropic_key_here
EOF
```

### 5. Validate Configuration

```bash
python -m src.cli validate-config
```

## 🎮 Usage

### Starting the Orchestrator

```bash
# Start in supervised mode (requires approval for merges)
python -m src.cli start --mode supervised

# Start in manual mode (wait for explicit commands)
python -m src.cli start --mode manual

# Start in autonomous mode (fully automated - use with caution)
python -m src.cli start --mode autonomous
```

### Manual Operations

```bash
# Check status
python -m src.cli status

# List open issues
python -m src.cli list-issues

# List issues with specific labels
python -m src.cli list-issues --labels "bug,priority-high"

# Manually process a specific issue
python -m src.cli process-issue 123

# Export current state
python -m src.cli export-state

# Show version
python -m src.cli version
```

## ⚙️ Configuration

The orchestrator is configured via `config/orchestrator-config.yaml`. Key settings:

### Orchestrator Mode

- **`manual`**: Wait for explicit CLI commands
- **`supervised`**: Auto-process but require approval for merges
- **`autonomous`**: Fully automated (use with caution)

### Issue Processing

```yaml
issue_processing:
  auto_claim_labels:
    - bot-approved        # Issues with these labels are processed
  ignore_labels:
    - wontfix            # Issues with these labels are skipped
  max_complexity: 7      # Skip issues above this complexity (0-10)
  max_concurrent: 2      # Maximum concurrent issues to process
```

### PR Management

```yaml
pr_management:
  auto_fix_attempts: 2   # Times to retry fixing failed tests
  require_reviews: 1     # Minimum reviews required
  auto_merge: true       # Auto-merge when checks pass
  merge_strategy: squash # merge, squash, or rebase
```

### Safety Settings

```yaml
safety:
  human_approval_required:
    - merge_to_main
    - breaking_changes
    - security_related
  max_api_cost_per_day: 50.0
  rollback_on_test_failure: true
```

## 🛡️ Safety & Monitoring

The orchestrator includes comprehensive safety mechanisms for reliable, secure autonomous operation:

### Multi-Layer Safety

1. **Rate Limiting**: Prevents runaway API usage with token bucket algorithm
2. **Cost Tracking**: Enforces daily budget limits and tracks spending per provider
3. **Complexity Guards**: Blocks overly complex or risky code changes
4. **File Protection**: Prevents modification of critical files (`.env`, configs, etc.)
5. **Breaking Change Detection**: Identifies and gates changes that could break functionality
6. **Rollback Capability**: Git-based rollback points for quick recovery
7. **Human Approval Gates**: Multi-agent risk assessment with automatic escalation
8. **Health Monitoring**: Continuous monitoring of CPU, memory, disk, and API health
9. **Notifications**: Real-time alerts via Slack, email, or webhooks

### Production-Ready Features

- ✅ **Defense in Depth**: Multiple independent safety layers
- ✅ **Fail-Safe Defaults**: Safe behavior on errors
- ✅ **Observable**: Statistics and metrics for all safety components
- ✅ **Configurable**: Adjust thresholds to your needs
- ✅ **Auditable**: Complete audit trail of all decisions and violations
- ✅ **Tested**: Comprehensive integration tests for safety features

### Quick Safety Check

```bash
# Check system health
python -m src.cli health-check

# View pending approvals
python -m src.cli approvals list

# Check cost usage
python -m src.cli metrics cost

# View safety statistics
python -m src.cli metrics safety
```

### Documentation

- **[Safety Features Guide](docs/safety.md)**: Complete safety documentation
- **[Operations Runbook](docs/operations.md)**: How to run and maintain the orchestrator
- **[Troubleshooting Guide](docs/troubleshooting.md)**: Common issues and solutions

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Orchestrator Core                      │
│  (State Machine, Event Loop, Configuration Manager)    │
└─────────────────────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼────────┐ ┌──────▼──────┐ ┌────────▼────────┐
│  Issue Cycle   │ │  PR Cycle   │ │ Roadmap Cycle   │
│   Component    │ │  Component  │ │   Component     │
└───────┬────────┘ └──────┬──────┘ └────────┬────────┘
        │                  │                  │
┌───────▼──────────────────▼──────────────────▼────────┐
│              Integration Layer                        │
│  (GitHub API, multi-agent-coder, Git, CI/CD)         │
└──────────────────────────────────────────────────────┘
```

### Core Components

- **`src/core/orchestrator.py`**: Main orchestrator coordination
- **`src/core/config.py`**: Configuration management
- **`src/core/state.py`**: State machine and work tracking
- **`src/core/logger.py`**: Audit logging system
- **`src/integrations/github_client.py`**: GitHub API wrapper
- **`src/cli.py`**: Command-line interface

## 🧪 Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_config.py

# Run with verbose output
pytest -v
```

## 🔒 Safety Mechanisms

The orchestrator includes multiple safety features:

1. **Complexity Ceiling**: Refuses issues above configured complexity
2. **Test Coverage**: Requires tests to pass before merging
3. **Code Review**: Always uses multi-agent-coder for review (Phase 3+)
4. **Rollback Ready**: Tags before merge for easy revert
5. **Rate Limiting**: Prevents runaway API usage
6. **Human Escalation**: Automatic escalation for:
   - Security-sensitive changes
   - Breaking API changes
   - Test failures after N attempts
   - High complexity issues

## 📊 Audit Trail

All actions are logged with:
- Timestamp
- Event type
- Actor (orchestrator/human)
- Resource affected
- Reasoning and metadata

Logs are stored in:
- `logs/orchestrator.log` - Main application log
- `logs/audit.log` - Audit trail (JSON format)

## 🗺️ Development Roadmap

### ✅ Phase 1: Foundation (Completed)
- Project structure
- Configuration system
- Audit logging
- GitHub API integration
- State machine
- CLI interface

### 🔄 Phase 2: Issue Cycle (Next)
- Issue monitoring
- Issue analysis with LLM
- Implementation planning
- Code execution engine
- Test runner integration

### 🔄 Phase 3: PR Cycle
- CI monitoring
- Test failure analysis
- Multi-agent-coder integration
- Review feedback processor
- Merge automation

### 🔄 Phase 4: Roadmap Cycle
- Codebase analyzer
- Roadmap generation
- Multi-agent-coder validation
- Issue generation

### 🔄 Phase 5: Safety & Monitoring
- Rate limiting
- Complexity guards
- Rollback mechanism
- Notification system
- Health checks

### 🔄 Phase 6: Optimization
- Success/failure tracking
- Learning from mistakes
- Context-aware prompting
- Performance dashboard

## 🤝 Contributing

This is an experimental project in active development. Contributions welcome!

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📝 License

MIT License - See LICENSE file for details

## ⚠️ Warnings

- **Phase 1 Status**: This is currently Phase 1 (Foundation). Issue processing, PR management, and roadmap features are not yet implemented.
- **Use Supervised Mode**: Always start with supervised mode to review actions before they're executed.
- **API Costs**: Monitor your Anthropic API usage to avoid unexpected costs.
- **Test on Non-Critical Repos**: Test thoroughly on non-critical repositories before using on production code.

## 🆘 Troubleshooting

### Configuration Errors

```bash
# Validate your configuration
python -m src.cli validate-config
```

### GitHub API Issues

- Ensure your token has required permissions: `repo`, `issues`, `pull_requests`
- Check rate limits: https://api.github.com/rate_limit

### Import Errors

```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

## 📚 Documentation

- [Architecture Details](docs/architecture.md) (Coming soon)
- [Configuration Guide](docs/configuration.md) (Coming soon)
- [Safety Guide](docs/safety.md) (Coming soon)

## 💬 Support

For issues and questions:
- Open an issue on GitHub
- Check existing documentation
- Review audit logs for debugging

## 🙏 Acknowledgments

Built with:
- [Anthropic Claude](https://www.anthropic.com/) - AI capabilities
- [PyGithub](https://pygithub.readthedocs.io/) - GitHub API
- [Click](https://click.palletsprojects.com/) - CLI framework
- [Rich](https://rich.readthedocs.io/) - Terminal formatting
- [structlog](https://www.structlog.org/) - Structured logging

---

**Status**: Phase 1 Complete - Foundation established. Ready for Phase 2 development.
