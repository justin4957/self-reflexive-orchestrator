# Phase 6: Performance Dashboard & Reporting

The orchestrator provides comprehensive performance monitoring through an interactive dashboard and exportable reports.

## Dashboard

Access real-time performance metrics via the CLI dashboard.

### Usage

```bash
# Display dashboard once
orchestrator dashboard

# Auto-refresh every 10 seconds
orchestrator dashboard --refresh 10
```

### Dashboard Sections

#### 1. Status & Uptime
- Current orchestrator status
- Operating mode (manual/supervised/autonomous)
- Uptime since start

#### 2. Today's Activity
- Issues processed (success/failed)
- PRs merged
- API costs (with budget tracking)

#### 3. Performance Metrics (7 days)
- Success rate
- Average operation duration
- Cache hit rate
- Error rate

#### 4. Cost Analysis
- Last 7 days cost
- Last 30 days cost
- Monthly projection
- Cost per operation

#### 5. Current Work
- Active operations
- Recent completions

#### 6. Health Status
- Overall system health
- Warning indicators

### Example Output

```
┌─ Self-Reflexive Orchestrator Dashboard ────────────────────────┐
│ Status: Running              Mode: autonomous                   │
│ Uptime: 2d 4h 15m                                              │
│                                                                 │
│ Today:                                                          │
│  • Issues processed: 12 (10 success, 2 failed)                 │
│  • PRs merged: 8                                               │
│  • API cost: $ 2.45 / $50.00                                   │
│                                                                 │
│ Performance (7 days):                                           │
│  • Success rate:  82.5%                                        │
│  • Avg operation time:  45.3s                                  │
│  • Cache hit rate:  67.2%                                      │
│  • Error rate:   2.1%                                          │
│                                                                 │
│ Costs:                                                          │
│  • Last 7 days: $ 15.80                                        │
│  • Last 30 days: $ 58.40                                       │
│  • Monthly projection: $ 67.71                                 │
│                                                                 │
│ Current Work:                                                   │
│  • process_issue: issue-145                                    │
│  • analyze_pr: pr-92                                           │
│                                                                 │
│ Health: ✅ All systems operational                             │
└─────────────────────────────────────────────────────────────────┘
```

## Reports

Generate comprehensive performance reports in multiple formats.

### Usage

```bash
# Generate summary report (markdown)
orchestrator report

# Generate detailed report
orchestrator report --detailed

# Specify time period
orchestrator report --days 30

# Export to file
orchestrator report --output report.md --format markdown
orchestrator report --output report.json --format json
```

### Report Types

#### 1. Summary Report
High-level overview of key metrics:
- Overall success rate
- Total operations by type
- Cost summary
- Issue processing stats
- PR management stats
- Top insights and recommendations

#### 2. Detailed Report
In-depth analysis including:
- Operations by day (trend analysis)
- Costs by day (spending patterns)
- Errors by type (failure analysis)
- Slowest operations (performance bottlenecks)
- Most expensive operations (cost optimization)

### Export Formats

#### Markdown
Human-readable reports with tables and formatting:

```bash
orchestrator report --output report.md --format markdown
```

**Example:**
```markdown
# Orchestrator Report - 7 Days

Generated: 2025-11-10T14:30:00Z

## Overall Metrics

- Success Rate: 82.5%
- Total Operations: 124

## Operations

| Operation | Count | Success Rate | Avg Duration |
|-----------|-------|--------------|--------------|
| process_issue | 45 | 84.4% | 52.3s |
| create_pr | 38 | 94.7% | 28.1s |
| run_tests | 41 | 73.2% | 145.7s |

## Costs

- Total Cost: $15.80
- Average per Operation: $0.13
- Total Tokens: 1,580,000

## Recommendations

- Consider increasing test timeout for complex issues
- Cache hit rate could be improved (currently 67%)
- 3 recurring error patterns identified
```

#### JSON
Machine-readable format for automation:

```bash
orchestrator report --output report.json --format json
```

**Example:**
```json
{
  "report_type": "summary",
  "period_days": 7,
  "generated_at": "2025-11-10T14:30:00Z",
  "overall": {
    "success_rate": 0.825,
    "total_operations": 124
  },
  "operations": {
    "process_issue": {
      "count": 45,
      "success_count": 38,
      "avg_duration": 52.3
    }
  },
  "costs": {
    "total_cost": 15.80,
    "total_tokens": 1580000,
    "avg_cost_per_operation": 0.13
  }
}
```

## Metrics Explained

### Success Rate
Percentage of operations that completed successfully without errors.

**Good**: > 80%
**Acceptable**: 60-80%
**Needs Attention**: < 60%

### Cache Hit Rate
Percentage of requests served from cache vs. fetching from API.

**Excellent**: > 70%
**Good**: 50-70%
**Poor**: < 50%

### Error Rate
Percentage of operations that failed.

**Excellent**: < 5%
**Good**: 5-15%
**Concerning**: > 15%

### Cost per Operation
Average API cost per operation.

**Varies by operation type:**
- Simple analysis: $0.01-$0.05
- Code generation: $0.10-$0.30
- Complex planning: $0.20-$0.50

## Performance Monitoring

### Continuous Monitoring

Set up auto-refresh dashboard for continuous monitoring:

```bash
# Monitor in real-time
orchestrator dashboard --refresh 10 &

# Or use tmux/screen for persistent monitoring
tmux new -s orchestrator-monitor
orchestrator dashboard --refresh 10
```

### Automated Reporting

Schedule daily reports via cron:

```bash
# Add to crontab
0 8 * * * cd /path/to/orchestrator && orchestrator report --days 1 --output daily-$(date +\%Y\%m\%d).md
0 8 * * 1 cd /path/to/orchestrator && orchestrator report --days 7 --detailed --output weekly-$(date +\%Y\%m\%d).md
```

### Alerting

Monitor key metrics and alert on thresholds:

```python
from src.core.dashboard import Dashboard

dashboard = Dashboard(...)
metrics = dashboard.get_metrics()

# Alert on low success rate
if metrics.success_rate_7d < 0.7:
    send_alert("Success rate dropped below 70%")

# Alert on high costs
if metrics.api_cost_today > 50.0:
    send_alert("Daily API cost exceeded $50")

# Alert on high error rate
if metrics.error_rate > 0.15:
    send_alert("Error rate above 15%")
```

## Performance Tuning

### Identifying Bottlenecks

Use detailed reports to find performance bottlenecks:

```bash
orchestrator report --detailed --days 30 | grep "Slowest"
```

**Common bottlenecks:**
- Test execution (increase parallelism)
- Code analysis (enable caching)
- File operations (optimize I/O)

### Optimizing Costs

Analyze cost patterns:

```bash
orchestrator report --detailed --days 30 | grep "expensive"
```

**Cost reduction strategies:**
- Increase cache TTL for stable data
- Batch similar operations
- Use cheaper models for simple tasks
- Implement request deduplication

### Improving Success Rates

Review failure patterns:

```bash
orchestrator report --detailed --days 30 | grep "Error"
```

**Common improvements:**
- Adjust complexity thresholds
- Increase timeout values
- Improve error handling
- Add retry logic

## Integration

### Programmatic Access

Access dashboard and reports programmatically:

```python
from src.core.orchestrator import Orchestrator

orchestrator = Orchestrator("config.yaml")

# Get dashboard metrics
metrics = orchestrator.dashboard.get_metrics()
print(f"Success rate: {metrics.success_rate_7d:.1%}")
print(f"Cache hit rate: {metrics.cache_hit_rate:.1%}")

# Generate report
report = orchestrator.report_generator.generate_summary_report(days=7)

# Export
orchestrator.report_generator.export_json(report, "report.json")
orchestrator.report_generator.export_markdown(report, "report.md")
```

### Metrics API

Expose metrics via web API for monitoring tools:

```python
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/metrics")
def metrics():
    metrics = orchestrator.dashboard.get_metrics()
    return jsonify({
        "success_rate": metrics.success_rate_7d,
        "cache_hit_rate": metrics.cache_hit_rate,
        "error_rate": metrics.error_rate,
        "cost_today": metrics.api_cost_today
    })
```

## See Also

- [Optimization Features](optimization.md)
- [Learning System](learning.md)
- [Analytics Configuration](../README.md#configuration)
