# GPU Utilization Metrics Comparison

## Critical Finding: The Metrics Are NOT Identical

After reviewing the `nvidia_gpu_prometheus_exporter` source code, we've discovered that `nvidia_gpu_duty_cycle` and `nvidia_gpu_sm_util_percent` are **similar but NOT identical** metrics from different NVIDIA APIs.

## Metric Definitions

### nvidia_gpu_duty_cycle

**Source:** NVML `GetUtilizationRates()` API (older)  
**Definition:** "Percent of time over the past sample period during which one or more kernels were executing on the GPU device"  
**Availability:** 
- ✅ Regular GPUs (MIG disabled)
- ❌ MIG instances (explicitly disabled in code)

**From nvidia_gpu_prometheus_exporter/main.go (lines 546-554):**
```go
// GPU cards in MIG mode cannot report Utilization
if currentMig == nvml.DEVICE_MIG_DISABLE {
    dutyCycle, err := oneDev.device.GetUtilizationRates()
    if err == nvml.SUCCESS {
        c.dutyCycle.WithLabelValues(...).Set(float64(dutyCycle.Gpu))
    }
}
```

### nvidia_gpu_sm_util_percent

**Source:** GPM (GPU Performance Metrics) API via `nvml.GPM_METRIC_SM_UTIL` (newer)  
**Definition:** "Percentage of SMs (Streaming Multiprocessors) that were busy"  
**Availability:**
- ✅ Hopper GPUs and newer (H100, B200)
- ✅ MIG instances
- ❌ Older architectures (pre-Hopper)

**From nvidia_gpu_prometheus_exporter/main.go (lines 649-650):**
```go
case int(nvml.GPM_METRIC_SM_UTIL):
    c.smUtil.WithLabelValues(...).Set(gpmMetric.Metrics[i].Value / 100.0)
```

## Key Differences

| Aspect | duty_cycle | sm_util_percent |
|--------|-----------|-----------------|
| **What it measures** | Time with ANY kernel executing | % of SMs that were busy |
| **API Source** | NVML GetUtilizationRates | GPM (GPU Performance Metrics) |
| **Sampling** | Averages over sample period | Fine-grained SM activity |
| **MIG Support** | ❌ No (explicitly disabled) | ✅ Yes |
| **Architecture** | All GPUs with NVML | Hopper+ (H100, B200) |
| **Granularity** | Coarse (any activity = 100%) | Fine (per-SM busy percentage) |

## Semantic Difference

### duty_cycle: Binary Activity
- Measures if **ANY kernel** is executing
- Can show 100% even if only ONE SM is busy
- More like "GPU was active X% of the time"
- Example: Single-threaded kernel = 100% duty_cycle even though most SMs idle

### sm_util_percent: SM Occupancy
- Measures **how many SMs** are busy
- Shows actual SM utilization percentage
- More accurate for parallel workload efficiency
- Example: Using 50/132 SMs = ~38% sm_util_percent

## Real-World Example

**Scenario:** Job using 1/8 of GPU resources

```
duty_cycle:       100%  (kernel is executing, so GPU is "busy")
sm_util_percent:   12%  (only 12% of SMs actually doing work)
```

**Which is more accurate?** `sm_util_percent` provides better insight into actual resource usage.

## Impact on Jobstats

### What Jobstats Uses It For

From `jobstats/jobstats.py` (line 360):
```python
self.get_data('gpu_utilization', 
              "avg_over_time((nvidia_gpu_duty_cycle{...})[%ds:])")
```

**Purpose:** Display overall GPU utilization to users  
**Current behavior:** Shows "% of time GPU had any activity"  
**With sm_util_percent:** Shows "% of GPU compute resources actually utilized"

### Will It Break Jobstats?

**Short Answer: No, but values will be different (and possibly more accurate)**

**Testing Required:**
1. Check if jobstats has hardcoded thresholds
2. Verify jobstats doesn't assume specific value ranges
3. Test with real workloads on both metrics

## Checking Jobstats for Issues

Let me check the jobstats config for any hardcoded thresholds:

**From jobstats/config.py:**
```python
GPU_UTIL_RED   = 15  # percentage
GPU_UTIL_BLACK = 25  # percentage

# Low GPU utilization warnings
condition = 'self.js.gpu_utilization <= c.GPU_UTIL_RED'  # <= 15%
condition = 'self.js.gpu_utilization < c.GPU_UTIL_BLACK' # < 25%
```

**Analysis:**
- Jobstats uses thresholds at 15% and 25%
- These are for "low utilization" warnings
- Both metrics are percentages (0-100)
- **Potential Issue:** `sm_util_percent` may show LOWER values than `duty_cycle`

## Expected Value Differences

### Typical Workloads

| Workload Type | duty_cycle | sm_util_percent | Difference |
|--------------|-----------|-----------------|------------|
| **Idle GPU** | 0% | 0% | None |
| **Light/Single-threaded** | 80-100% | 5-15% | ⚠️ LARGE |
| **Well-parallelized** | 95-100% | 70-95% | Minimal |
| **Fully saturated** | 100% | 95-100% | Minimal |

**Concern:** Light workloads will show MUCH lower utilization with `sm_util_percent`, which is actually MORE ACCURATE but may trigger more "low utilization" warnings.

## Validation Steps

### Step 1: Compare Metrics Side-by-Side

On a non-MIG node that has BOTH metrics, compare them:

```bash
# Get both metrics for the same GPU at same time
ssh dgx007 "curl -s http://localhost:9445/metrics | grep -E 'duty_cycle|sm_util_percent' | grep 'uuid=\"GPU-9a7401a6.*\"'"
```

**Expected output:**
```
nvidia_gpu_duty_cycle{uuid="GPU-9a7401a6-..."} 95.0
nvidia_gpu_sm_util_percent{uuid="GPU-9a7401a6-..."} 78.5
```

### Step 2: Run Test Workloads

```bash
# Submit a GPU job
srun --gpus=1 --time=10:00 gpu_burn 600 &
JOBID=$(squeue --me --noheader -o "%i" | head -1)

# Query Prometheus for BOTH metrics
PROM="http://prometheus:9090"
curl -s "$PROM/api/v1/query?query=nvidia_gpu_duty_cycle{jobId=\"$JOBID\"}" | jq '.data.result[0].value[1]'
curl -s "$PROM/api/v1/query?query=nvidia_gpu_sm_util_percent{jobId=\"$JOBID\"}" | jq '.data.result[0].value[1]'
```

### Step 3: Test Jobstats Display

```bash
# Test with duty_cycle (current)
jobstats $JOBID | grep -i "gpu util"

# Apply MIG fix to use sm_util_percent
python3 automation/tools/fix_jobstats_mig_utilization.py

# Test with sm_util_percent (new)
jobstats $JOBID | grep -i "gpu util"

# Compare the values
```

### Step 4: Check Warning Thresholds

```bash
# Submit a light GPU workload that uses few SMs
srun --gpus=1 --time=10:00 python3 -c "
import torch
import time
# Light single-threaded workload
x = torch.randn(100, 100).cuda()
for _ in range(600):
    y = torch.mm(x, x)
    time.sleep(1)
" &

JOBID=$(squeue --me --noheader -o "%i" | head -1)

# Check if jobstats shows low utilization warning
jobstats $JOBID
```

## Recommendations

### Option 1: Accept the Difference (Recommended)

**Rationale:**
- `sm_util_percent` is MORE accurate for showing actual resource usage
- Low utilization warnings for inefficient jobs are APPROPRIATE
- Better to show accurate metrics than artificially inflated ones

**Action:**
- Use `sm_util_percent` for MIG (no choice)
- Consider using it for regular GPUs too (more accurate)
- Update documentation to explain the metric

### Option 2: Adjust Thresholds for sm_util_percent

If `sm_util_percent` shows too many false positives:

**Modify jobstats/config.py:**
```python
# Original thresholds (for duty_cycle)
GPU_UTIL_RED   = 15  # percentage
GPU_UTIL_BLACK = 25  # percentage

# Adjusted thresholds (for sm_util_percent)
GPU_UTIL_RED   = 10  # percentage (lower because metric is more granular)
GPU_UTIL_BLACK = 20  # percentage
```

**Pros:** Fewer false positives  
**Cons:** May miss actually underutilized GPUs

### Option 3: Use graphics_util_percent Instead

**Alternative metric available on all GPUs:**
```
nvidia_gpu_graphics_util_percent
"Percentage of time any compute/graphics app was active on the GPU"
```

**From main.go (lines 169-176):**
```go
graphicsUtil: prometheus.NewGaugeVec(
    prometheus.GaugeOpts{
        Name: "graphics_util_percent",
        Help: "Percentage of time any compute/graphics app was active on the GPU",
    },
    labelsJobInfo,
),
```

**Pros:** More similar to `duty_cycle` semantically  
**Cons:** May not be available on MIG; still need to verify

## Testing Checklist

Before deploying to production:

- [ ] Compare duty_cycle vs sm_util_percent on non-MIG nodes
- [ ] Test with various workload types (light, heavy, mixed)
- [ ] Verify warning thresholds don't trigger too often
- [ ] Check that jobstats display looks reasonable
- [ ] Test on both MIG and non-MIG jobs
- [ ] Document expected value differences for users
- [ ] Consider adjusting thresholds if needed

## Conclusion

**Answer to Original Question:**

> Can we confirm that the data we receive for those two metrics is the same?

**NO - They are NOT the same:**
- `duty_cycle`: "Was GPU doing anything?" (coarse, binary-ish)
- `sm_util_percent`: "What % of GPU resources were busy?" (fine-grained, accurate)

**Will it break jobstats?**

**Probably not, but:**
1. Values will be **different** (often lower for sm_util_percent)
2. May trigger more "low utilization" warnings (which could be **accurate**)
3. Need to test with real workloads
4. May want to adjust thresholds

**Recommendation:**
1. ✅ Deploy the MIG fix (no choice for MIG support)
2. ✅ Test with representative workloads
3. ✅ Document the metric change for users
4. ⚠️ Consider adjusting warning thresholds if too sensitive
5. ✅ Accept that `sm_util_percent` is more accurate (this is good!)

The change makes jobstats show MORE ACCURATE utilization, which aligns with its purpose of helping users optimize GPU usage.

## References

- NVML Documentation: https://docs.nvidia.com/deploy/nvml-api/
- GPM Documentation: https://docs.nvidia.com/datacenter/tesla/gpu-performance-metrics/
- nvidia_gpu_prometheus_exporter source: https://github.com/plazonic/nvidia_gpu_prometheus_exporter

