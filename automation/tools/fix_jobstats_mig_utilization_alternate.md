# Alternative MIG Fix: Prometheus Recording Rules

This document describes how to fix MIG GPU utilization support entirely in Prometheus, without modifying the jobstats code.

## Overview

Instead of modifying `jobstats.py` to add fallback logic, you can configure Prometheus to create a `nvidia_gpu_duty_cycle` metric for MIG instances using their existing `nvidia_gpu_graphics_util_percent` metric (scaled by 100).

**Important:** The `nvidia_gpu_graphics_util_percent` metric from GPM is stored in 0-1 range, so it must be multiplied by 100 to match the 0-100 range of `duty_cycle`.

## Why Use This Approach?

**Pros:**
- ✅ No code changes to jobstats
- ✅ Centralized configuration in Prometheus
- ✅ Can be updated without redeploying jobstats
- ✅ Easy to verify and monitor
- ✅ Works for all consumers of Prometheus data (not just jobstats)

**Cons:**
- ❌ Requires access to Prometheus server
- ❌ Requires Prometheus reload/restart
- ❌ Less transparent than code-based fix
- ❌ Creates additional time series (small storage increase)

## Two Prometheus Approaches

There are two ways to fix this in Prometheus:

### Approach 1: Recording Rule (Recommended)

Creates a new `nvidia_gpu_duty_cycle` metric for MIG instances based on `nvidia_gpu_graphics_util_percent * 100`.

**Use When:**
- You want a persistent solution
- You want to keep original metrics unchanged
- You're okay with slight storage increase

### Approach 2: Metric Relabeling

Renames `nvidia_gpu_graphics_util_percent` to `nvidia_gpu_duty_cycle` for MIG instances at scrape time and scales by 100.

**Use When:**
- You want zero storage overhead
- You don't need to keep both metric names
- You want the fix to happen at ingestion time

## Approach 1: Recording Rule (Step-by-Step)

### Step 1: Create the Recording Rule File

On your Prometheus server, create a new rules file:

```bash
# SSH to Prometheus server
ssh prometheus-server

# Create rules directory if it doesn't exist
sudo mkdir -p /etc/prometheus/rules

# Create the recording rule file
sudo tee /etc/prometheus/rules/jobstats_mig_compat.yml > /dev/null << 'EOF'
groups:
  - name: jobstats_mig_compatibility
    interval: 30s
    rules:
      # Create duty_cycle metric for MIG instances using graphics_util_percent * 100
      # Note: GPM metrics are stored in 0-1 range, multiply by 100 to match duty_cycle scale (0-100)
      - record: nvidia_gpu_duty_cycle
        expr: nvidia_gpu_graphics_util_percent{uuid=~"MIG-.*"} * 100
        labels:
          source: "mig_compat_rule"
EOF
```

**What this does:**
- Creates a new `nvidia_gpu_duty_cycle` metric
- Only for devices where `uuid` starts with "MIG-"
- Uses the value from `nvidia_gpu_graphics_util_percent` multiplied by 100
- Scaling is necessary because GPM metrics are stored in 0-1 range, not 0-100
- Preserves all existing labels (jobid, instance, uuid, etc.)
- Adds a `source` label to identify it came from the rule

### Step 2: Configure Prometheus to Load the Rules

Edit your Prometheus configuration file:

```bash
# Edit prometheus.yml
sudo vim /etc/prometheus/prometheus.yml
```

Add or verify the `rule_files` section:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

# Load recording rules
rule_files:
  - /etc/prometheus/rules/*.yml

scrape_configs:
  # ... your existing scrape configs ...
```

**Important:** Make sure the `rule_files` section is at the **top level** of the config, not inside any other section.

### Step 3: Validate the Configuration

Before reloading, validate the configuration:

```bash
# Validate prometheus.yml syntax
promtool check config /etc/prometheus/prometheus.yml

# Validate the rules file
promtool check rules /etc/prometheus/rules/jobstats_mig_compat.yml
```

**Expected output:**
```
Checking /etc/prometheus/prometheus.yml
  SUCCESS: 1 rule files found

Checking /etc/prometheus/rules/jobstats_mig_compat.yml
  SUCCESS: 1 rules found
```

If you see errors, fix them before proceeding.

### Step 4: Reload Prometheus

Reload Prometheus to apply the new rules:

```bash
# Method 1: Using systemctl (if Prometheus is a systemd service)
sudo systemctl reload prometheus

# Method 2: Using the HTTP API (if web.enable-lifecycle is enabled)
curl -X POST http://localhost:9090/-/reload

# Method 3: Send SIGHUP signal
sudo pkill -HUP prometheus
```

**Verify reload succeeded:**
```bash
# Check Prometheus logs
sudo journalctl -u prometheus -n 50 --no-pager

# Look for:
# "Loading configuration file" and "Completed loading of configuration file"
```

### Step 5: Verify the Recording Rule is Active

Check that Prometheus loaded the rule:

```bash
# Query Prometheus rules endpoint
curl -s http://localhost:9090/api/v1/rules | jq '.data.groups[] | select(.name=="jobstats_mig_compatibility")'
```

**Expected output:**
```json
{
  "name": "jobstats_mig_compatibility",
  "file": "/etc/prometheus/rules/jobstats_mig_compat.yml",
  "interval": 30,
  "rules": [
    {
      "name": "nvidia_gpu_duty_cycle",
      "query": "nvidia_gpu_graphics_util_percent{uuid=~\"MIG-.*\"} * 100",
      "type": "recording",
      ...
    }
  ]
}
```

### Step 6: Wait for Data to Populate

Recording rules evaluate at the `interval` specified (30s in our case). Wait at least 1-2 minutes for data to populate.

### Step 7: Verify the New Metric Exists

Query Prometheus to verify the new `nvidia_gpu_duty_cycle` metric exists for MIG devices:

```bash
# Check if metric exists
curl -s 'http://localhost:9090/api/v1/query?query=nvidia_gpu_duty_cycle{uuid=~"MIG-.*"}' | jq '.data.result[] | {uuid: .metric.uuid, value: .value[1], jobid: .metric.jobid}'
```

**Example output:**
```json
{
  "uuid": "MIG-1457e955-5461-5ddc-85aa-d5659b8d71f0",
  "value": "99.2",
  "jobid": "167890"
}
```

**Note:** The value will be in 0-100 range (after multiplication) matching `duty_cycle` scale.

### Step 8: Test with jobstats

Submit a MIG job and test jobstats:

```bash
# Submit a MIG test job
srun --partition=dgx-b200-mig90 --gpus=1 --time=10:00 sleep 600 &
JOBID=$(squeue --me --noheader -o "%i" | head -1)

# Wait for job to start and metrics to be scraped (1-2 minutes)
sleep 120

# Test jobstats
jobstats $JOBID

# Should now show GPU utilization instead of "Value is unknown"
```

## Approach 2: Metric Relabeling (Alternative)

If you prefer to rename the metric at scrape time instead of creating a recording rule:

### Step 1: Edit Prometheus Scrape Config

```bash
sudo vim /etc/prometheus/prometheus.yml
```

Find the `nvidia_gpu_exporter` scrape job and add `metric_relabel_configs`:

```yaml
scrape_configs:
  - job_name: 'nvidia_gpu_exporter'
    # ... your existing settings ...
    
    metric_relabel_configs:
      # Keep your existing relabel configs (e.g., cluster label)
      - source_labels: []
        target_label: cluster
        replacement: slurm
      
      # NEW: Rename graphics_util_percent to duty_cycle for MIG devices
      # Note: This approach has a limitation - it cannot multiply by 100 at scrape time
      # For proper scaling, use Recording Rule (Approach 1) instead
      - source_labels: [__name__, uuid]
        separator: ;
        regex: ^nvidia_gpu_graphics_util_percent;(MIG-.+)
        target_label: __name__
        replacement: nvidia_gpu_duty_cycle
        action: replace
```

**⚠️ Important Limitation:**

Metric relabeling **cannot perform arithmetic operations** like multiplying by 100. This means:
- The metric will be renamed to `nvidia_gpu_duty_cycle`
- But values will still be in 0-1 range (e.g., 0.99 instead of 99)
- Jobstats will display 1% instead of 99%

**For this reason, Approach 1 (Recording Rule) is strongly recommended**, as it can both rename AND scale the metric properly.

### Step 2: Validate and Reload

```bash
# Validate configuration
promtool check config /etc/prometheus/prometheus.yml

# Reload Prometheus
sudo systemctl reload prometheus
```

### Step 3: Verify the Relabeling

Wait 1-2 scrape intervals, then query:

```bash
# Should now see duty_cycle for MIG devices
curl -s 'http://localhost:9090/api/v1/query?query=nvidia_gpu_duty_cycle{uuid=~"MIG-.*"}' | jq '.data.result[0]'

# Should NOT see graphics_util_percent for MIG devices anymore
curl -s 'http://localhost:9090/api/v1/query?query=nvidia_gpu_graphics_util_percent{uuid=~"MIG-.*"}' | jq '.data.result'
# (should be empty or show only non-MIG devices)
```

**Note:** Due to the scaling limitation mentioned above, this approach is **not recommended**. Use Approach 1 (Recording Rule) instead.

## Comparison: Recording Rule vs Metric Relabeling

| Feature | Recording Rule | Metric Relabeling |
|---------|---------------|-------------------|
| **Storage Impact** | Creates new time series (+storage) | No additional storage |
| **Original Metric** | Preserved (both exist) | Replaced (only new name exists) |
| **Evaluation Timing** | After scrape (rule evaluation) | During scrape (immediate) |
| **Flexibility** | Can add logic/transformations | Limited to relabeling only |
| **Arithmetic Operations** | ✅ Yes (can multiply by 100) | ❌ No (cannot scale values) |
| **Visibility** | Easy to debug (shows in rules) | Harder to debug (transparent) |
| **Best For** | Complex transformations, keeping both | Simple renames without math |
| **MIG Fix Recommendation** | ✅ **Recommended** (includes * 100) | ❌ Not recommended (missing scale) |

## Troubleshooting

### Issue: Rule file not loading

**Check:**
```bash
# Verify rule_files path is correct
grep -A 2 "rule_files" /etc/prometheus/prometheus.yml

# Check file permissions
ls -la /etc/prometheus/rules/jobstats_mig_compat.yml

# Should be readable by prometheus user
```

**Fix:**
```bash
sudo chown prometheus:prometheus /etc/prometheus/rules/jobstats_mig_compat.yml
sudo chmod 644 /etc/prometheus/rules/jobstats_mig_compat.yml
sudo systemctl reload prometheus
```

### Issue: Recording rule not evaluating

**Check rule evaluation:**
```bash
# View evaluation stats
curl -s http://localhost:9090/api/v1/rules | jq '.data.groups[] | select(.name=="jobstats_mig_compatibility") | .rules[0] | {evaluationTime, health, lastError}'
```

**Common causes:**
- Source metric `nvidia_gpu_graphics_util_percent` doesn't exist yet
- No MIG devices currently allocated to jobs (or GPM not enabled)
- Recording rule interval too long

### Issue: Metric exists but jobstats still shows errors

**Verify jobstats is querying the right Prometheus:**
```bash
# Check jobstats config
grep -i prometheus /cm/shared/apps/jobstats/config.py

# Test query manually
PROM_URL="http://prometheus-server:9090"
JOBID="167890"
curl -s "$PROM_URL/api/v1/query?query=nvidia_gpu_duty_cycle{jobId==\"$JOBID\"}" | jq .
```

### Issue: Both duty_cycle and graphics_util_percent exist for MIG

This is **expected behavior** with recording rules - both metrics exist:
- `nvidia_gpu_graphics_util_percent{uuid="MIG-..."}` - Original from exporter (0-1 range)
- `nvidia_gpu_duty_cycle{uuid="MIG-..."}` - Created by recording rule (0-100 range)

This is fine! Jobstats will use `duty_cycle` which now exists with proper scaling.

**Note:** Do NOT use metric relabeling to get only one metric, as it cannot perform the * 100 scaling needed.

## Testing Checklist

- [ ] Recording rule file created and readable
- [ ] prometheus.yml includes rule_files path
- [ ] Configuration validated with promtool
- [ ] Prometheus reloaded successfully
- [ ] Rule appears in `/api/v1/rules` endpoint
- [ ] New metric appears in Prometheus queries
- [ ] MIG job submitted and running
- [ ] Metric has correct labels (jobid, uuid, cluster)
- [ ] jobstats shows GPU utilization (not "unknown")
- [ ] Both MIG and non-MIG jobs work correctly

## Rollback

If you need to remove this fix:

```bash
# Remove the recording rule file
sudo rm /etc/prometheus/rules/jobstats_mig_compat.yml

# Reload Prometheus
sudo systemctl reload prometheus

# Verify removal
curl -s http://localhost:9090/api/v1/rules | jq '.data.groups[] | select(.name=="jobstats_mig_compatibility")'
# (should return nothing)
```

The created `nvidia_gpu_duty_cycle` metrics will stop being generated, but historical data remains until retention period expires.

## When to Use This vs Code Fix

**Use Prometheus fix when:**
- ✅ You have Prometheus server access
- ✅ You want centralized configuration
- ✅ You prefer not to modify application code
- ✅ You want the fix to benefit all Prometheus consumers

**Use jobstats code fix when:**
- ✅ You don't have Prometheus access
- ✅ You want the fix to be self-contained in jobstats
- ✅ You prefer transparent, documented behavior
- ✅ You're already planning to modify jobstats

**Use both when:**
- ✅ You want defense in depth
- ✅ You're in a transition period
- ✅ You have mixed environments (some with Prometheus fix, some without)

## Related Documentation

- [Code-based Fix (Python Script)](fix_jobstats_mig_utilization_v3.py)
- [Tools Documentation](README.md)
- [Custom Prolog/Epilog Scripts](../scripts/README.md)
- [Prometheus Recording Rules Documentation](https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/)
- [Prometheus Relabeling Documentation](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#relabel_config)

## Summary

The Prometheus recording rule approach:
1. Creates `nvidia_gpu_duty_cycle` for MIG devices using `nvidia_gpu_graphics_util_percent * 100`
2. Properly scales GPM metrics from 0-1 range to 0-100 range
3. Preserves all labels including `jobid`
4. Requires no code changes to jobstats
5. Works immediately once Prometheus is reloaded
6. Can coexist with code-based fix (no conflicts)

**Recommendation:** Use Recording Rule (Approach 1) for MIG fixes, as metric relabeling cannot perform the necessary * 100 scaling.

Both the Prometheus recording rule and the code-based fix can be used together for maximum compatibility!

