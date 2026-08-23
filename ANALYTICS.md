# Local health analytics

The service should compute derived metrics locally before exposing them to an LLM. This keeps context small and makes results reproducible.

Implemented analysis primitives include:

- mean/median/min/max/standard deviation
- 7/14/30-day rolling averages
- linear trend and R-squared
- Pearson correlation with sample size and strength
- IQR outlier detection
- personal baselines
- period-to-period comparison
- sleep debt
- bedtime/waketime regularity

Recommended MCP tools/resources:

- `health://today`
- `health://7-day-summary`
- `health://30-day-summary`
- `health://90-day-summary`
- `health://baseline`
- `health://current-trends`
- `health://current-anomalies`
- `get_health_snapshot`
- `get_health_history`
- `compare_periods`
- `find_correlations`
- `find_anomalies`
- `find_best_conditions`
- `compare_tagged_days`
- `calculate_sleep_debt`
- `calculate_sleep_regularity`

### Interpretation rule

Correlation is not causation. Results should include sample size and should not be presented as proof that one behavior caused another. Avoid declaring a medical diagnosis from wearable data alone.
