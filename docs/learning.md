# Phase 6: Learning from Mistakes

The orchestrator implements a learning system that continuously improves performance by analyzing failures and applying insights.

## Overview

The learning system tracks all operations, identifies failure patterns, and generates actionable recommendations to prevent recurring issues.

## Components

### 1. Analytics Collection

The `AnalyticsCollector` aggregates operational data:

```python
from src.core.analytics import AnalyticsCollector

collector = AnalyticsCollector(database, logger)

# Get success rates
success_rate_7d = collector.get_success_rate(days=7)
success_rate_30d = collector.get_success_rate(days=30)

# Analyze by operation type
type_rates = collector.get_success_rate_by_type(days=7)
```

### 2. Operation Tracking

Every operation is tracked with full context:

```python
from src.core.analytics import OperationTracker

tracker = OperationTracker(database, logger)

# Start tracking
op_id = tracker.start_operation("process_issue", "issue-123")

# Complete with success
tracker.complete_operation(op_id, success=True)

# Or complete with failure
tracker.complete_operation(
    op_id,
    success=False,
    error_type="TestFailure",
    error_message="Unit tests failed"
)
```

### 3. Insights Generation

The `InsightsGenerator` identifies patterns and creates recommendations:

```python
from src.core.analytics import InsightsGenerator

insights = InsightsGenerator(analytics_collector, logger)

# Generate insights summary
summary = insights.generate_summary(days=7)

print(f"Success rate: {summary['success_rate']:.1%}")
print(f"Failure patterns: {summary['failure_patterns']}")
print(f"Recommendations: {summary['recommendations']}")
```

## Learning Mechanisms

### 1. Failure Pattern Recognition

The system identifies recurring failure patterns:

- **Error type clustering**: Groups similar errors
- **Temporal analysis**: Identifies time-based patterns
- **Context correlation**: Links failures to specific conditions

Example:
```python
# System detects pattern
# Pattern: 80% of test failures occur when complexity > 7
# Recommendation: "Reduce complexity threshold to 6"
```

### 2. Success Rate Trending

Track success rates over time to measure improvement:

```python
# Weekly trend
for week in range(4):
    rate = collector.get_success_rate(days=7, offset=week*7)
    print(f"Week {week+1}: {rate:.1%}")

# Expected output after learning:
# Week 1: 65.0%
# Week 2: 72.0%  (+7%)
# Week 3: 78.0%  (+6%)
# Week 4: 82.0%  (+4%)
```

### 3. Adaptive Thresholds

Automatically adjust operational thresholds based on performance:

```python
# Initial: max_complexity = 8, success_rate = 70%
# After learning: max_complexity = 6, success_rate = 85%

if insights.recommend_threshold_adjustment("max_complexity"):
    new_threshold = insights.get_recommended_threshold("max_complexity")
    config.update(max_complexity=new_threshold)
```

## Learning Loop

The orchestrator implements a continuous learning loop:

```
1. Execute Operation
2. Track Outcome (success/failure)
3. Store in Database
4. Analyze Patterns (periodically)
5. Generate Insights
6. Apply Recommendations
7. Measure Improvement
8. Repeat
```

## Measurable Improvements

Expected improvements from learning system:

| Period | Success Rate | Improvement |
|--------|--------------|-------------|
| Week 1 | 65-70% | Baseline |
| Week 2 | 72-77% | +7-10% |
| Week 3 | 78-82% | +13-17% |
| Week 4 | 82-87% | +17-25% |

## Configuration

Enable learning features in config:

```yaml
learning:
  enabled: true
  analysis_interval: 86400  # Daily analysis
  min_samples: 10  # Minimum operations before generating insights
  confidence_threshold: 0.7  # Minimum confidence for recommendations
```

## Accessing Insights

### Via Dashboard

```bash
orchestrator dashboard
```

Shows current success rates, trends, and recommendations.

### Via Reports

```bash
orchestrator report --days 30 --detailed --output report.md
```

Includes failure patterns and improvement recommendations.

### Programmatically

```python
insights = orchestrator.insights_generator
summary = insights.generate_summary(days=30)

for recommendation in summary["recommendations"]:
    print(f"📋 {recommendation}")
```

## Best Practices

### 1. Regular Analysis

Run insights generation regularly:

```python
# In main loop
if time_since_last_analysis > 24 * 3600:
    summary = insights.generate_summary(days=7)
    apply_recommendations(summary["recommendations"])
```

### 2. Track All Operations

Ensure every operation is tracked:

```python
def process_issue(issue):
    op_id = tracker.start_operation("process_issue", f"issue-{issue.number}")
    try:
        result = do_work(issue)
        tracker.complete_operation(op_id, success=True)
        return result
    except Exception as e:
        tracker.complete_operation(
            op_id,
            success=False,
            error_type=type(e).__name__,
            error_message=str(e)
        )
        raise
```

### 3. Act on Recommendations

Implement a feedback loop:

```python
summary = insights.generate_summary(days=7)

if "reduce_complexity_threshold" in summary["actions"]:
    new_threshold = summary["recommended_complexity"]
    update_config(max_complexity=new_threshold)
    logger.info("Applied learning: reduced complexity threshold")
```

## See Also

- [Optimization Features](optimization.md)
- [Performance Dashboard](performance.md)
- [Analytics Database Schema](../src/core/database.py)
