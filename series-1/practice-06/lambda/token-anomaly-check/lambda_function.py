"""
Stage 7: token-usage anomaly detection, scheduled rather than inline.

The assignment's TokenUsageMonitor keeps `self.token_history = {}` - an
in-memory dict on the class instance - and flags anything >2 standard
deviations from the running mean. That cannot work on Lambda: instances are
ephemeral and not shared across concurrent invocations, so the dict resets on
every cold start and never accumulates a real window. Implemented literally it
would either never fire or fire on noise from a two-sample "history".

The fix is to let CloudWatch be the history. Stage 6 already publishes
TokenCount to RagAssistant/Ops dimensioned by ModelId, so the trailing window
is queryable - durable, shared across invocations, and free to keep.

Scheduled rather than inline (practice-06 decision 3): an inline per-request
check would add a CloudWatch API round-trip to the user-facing `generate` path
to answer a question nobody is waiting on. This runs on an EventBridge
schedule instead, the same pattern practice-02 proved with
rag-assistant-doc-sync-schedule -> check-and-sync.

Emits TokenUsageAnomaly (dimensioned by ModelId only - same cardinality
constraint as Stage 6) when the latest period's mean sits more than
SIGMA_THRESHOLD standard deviations from the baseline mean.
"""
import datetime
import json
import statistics

import boto3

cloudwatch = boto3.client("cloudwatch")

NAMESPACE = "RagAssistant/Ops"
METRIC = "TokenCount"
MODELS = ["amazon.nova-lite-v1:0", "amazon.nova-pro-v1:0"]

BASELINE_HOURS = 24     # trailing window that defines "normal"
RECENT_MINUTES = 60     # the window being judged against it
PERIOD_SECONDS = 300    # 5-minute buckets
SIGMA_THRESHOLD = 2.0
MIN_BASELINE_POINTS = 5  # below this, stdev is meaningless - stay silent


def _datapoints(model_id, start, end):
    resp = cloudwatch.get_metric_statistics(
        Namespace=NAMESPACE,
        MetricName=METRIC,
        Dimensions=[{"Name": "ModelId", "Value": model_id}],
        StartTime=start,
        EndTime=end,
        Period=PERIOD_SECONDS,
        Statistics=["Average"],
    )
    return sorted(resp["Datapoints"], key=lambda d: d["Timestamp"])


def check_model(model_id, now, baseline_hours=BASELINE_HOURS,
                recent_minutes=RECENT_MINUTES, min_baseline=MIN_BASELINE_POINTS):
    baseline_start = now - datetime.timedelta(hours=baseline_hours)
    recent_start = now - datetime.timedelta(minutes=recent_minutes)

    baseline = [d["Average"] for d in _datapoints(model_id, baseline_start, recent_start)]
    recent = [d["Average"] for d in _datapoints(model_id, recent_start, now)]

    if not recent:
        return {"model": model_id, "status": "no_recent_data"}
    # A "2 sigma" call on 2 datapoints is exactly the single-sample trap
    # practice-05 had to retract a finding over. Refuse to judge instead.
    if len(baseline) < min_baseline:
        return {"model": model_id, "status": "insufficient_baseline",
                "baseline_points": len(baseline), "required": min_baseline}

    mean = statistics.mean(baseline)
    stdev = statistics.stdev(baseline)
    recent_mean = statistics.mean(recent)

    # Zero variance is real (a fixed prompt shape gives near-identical token
    # counts). Dividing by it would make every tiny drift infinitely anomalous.
    if stdev == 0:
        z = 0.0
        anomalous = False
    else:
        z = (recent_mean - mean) / stdev
        anomalous = abs(z) > SIGMA_THRESHOLD

    result = {
        "model": model_id,
        "status": "anomaly" if anomalous else "normal",
        "baseline_mean": round(mean, 1),
        "baseline_stdev": round(stdev, 1),
        "baseline_points": len(baseline),
        "recent_mean": round(recent_mean, 1),
        "recent_points": len(recent),
        "z_score": round(z, 2),
    }

    if anomalous:
        cloudwatch.put_metric_data(
            Namespace=NAMESPACE,
            MetricData=[{
                "MetricName": "TokenUsageAnomaly",
                "Dimensions": [{"Name": "ModelId", "Value": model_id}],
                "Value": 1,
                "Unit": "Count",
            }],
        )
    return result


def lambda_handler(event, context):
    now = datetime.datetime.now(datetime.UTC)
    # Window overrides exist so the detector can actually be tested - waiting a
    # real 24h to find out whether it fires is not verification.
    event = event or {}
    kwargs = {
        "baseline_hours": event.get("baseline_hours", BASELINE_HOURS),
        "recent_minutes": event.get("recent_minutes", RECENT_MINUTES),
        "min_baseline": event.get("min_baseline", MIN_BASELINE_POINTS),
    }
    results = [check_model(m, now, **kwargs) for m in MODELS]
    print(json.dumps({"checked_at": now.isoformat(), "results": results}))
    return {
        "checked": len(results),
        "anomalies": [r["model"] for r in results if r["status"] == "anomaly"],
        "results": results,
    }
