# MIG (Multi-Instance GPU) Support

This document describes the MIG support that has been added to the jobstats deployment automation.

## Overview

NVIDIA Multi-Instance GPU (MIG) allows a single GPU to be partitioned into multiple GPU instances, each appearing as a separate device to CUDA applications. This is particularly useful for B200 and newer GPU architectures.

## Changes Made for MIG Support

### 1. Prolog/Epilog Scripts

**Custom Scripts Created:**
- `automation/scripts/prolog-jobstats.sh`
- `automation/scripts/epilog-jobstats.sh`

**Note:** These are custom MIG-optimized scripts maintained in this repository. The automation deploys these instead of the upstream jobstats versions.

**Problem:**
- Regular GPUs expose numeric indices (0, 1, 2, etc.) in `CUDA_VISIBLE_DEVICES`
- MIG instances expose UUIDs directly (e.g., `MIG-1457e955-5461-5ddc-85aa-d5659b8d71f0`)
- The original scripts tried to query `nvidia-smi -i <MIG-UUID>`, which fails with "No devices were found"
- This created error files like `Nodeviceswerefound` in `/run/gpustat/`

**Solution:**
The updated scripts now:
1. Check if the device identifier is already a UUID (starts with `GPU-` or `MIG-`)
2. If it's a UUID, use it directly without querying nvidia-smi
3. If it's a numeric index, query nvidia-smi for the corresponding UUID
4. Skip empty values
5. Handle errors gracefully with `2>/dev/null`

**Example:**
```bash
# For regular GPU:
CUDA_VISIBLE_DEVICES=0,1
# Script creates: /run/gpustat/0, /run/gpustat/1, 
#                 /run/gpustat/GPU-<uuid-0>, /run/gpustat/GPU-<uuid-1>

# For MIG instance:
CUDA_VISIBLE_DEVICES=MIG-1457e955-5461-5ddc-85aa-d5659b8d71f0
# Script creates: /run/gpustat/MIG-1457e955-5461-5ddc-85aa-d5659b8d71f0
```

### 2. GPU Utilization Metrics Fix

**Tool Created:**
- `automation/tools/fix_jobstats_mig_utilization.py`

**Problem:**
- Regular GPUs expose `nvidia_gpu_duty_cycle` metric for utilization
- MIG instances do NOT expose `duty_cycle` (nvidia-smi reports N/A for utilization)
- MIG instances expose `nvidia_gpu_sm_util_percent` instead
- Original jobstats only queries `duty_cycle`, causing "Value is unknown" errors for MIG jobs

**Solution:**
The fix script adds intelligent fallback logic to `jobstats.py`:
1. Try `nvidia_gpu_duty_cycle` first (for regular GPUs)
2. If no data is returned, fall back to `nvidia_gpu_sm_util_percent` (for MIG GPUs)
3. Include debug logging to show which metric was used
4. Maintain full backward compatibility with non-MIG nodes

**Usage:**
```bash
# Run on the login node where jobstats is installed
python3 automation/tools/fix_jobstats_mig_utilization.py
```

The script will:
- Create automatic backup of original file
- Add the new fallback method
- Test with a recent job
- Roll back automatically if anything fails

## How MIG Works with jobstats

### Normal Job Flow (MIG-enabled node)

1. **Job Submission:**
   ```bash
   srun --partition=dgx-b200-mig90 --gpus=1 my_job.sh
   ```

2. **Prolog Script Execution:**
   - Slurm sets `CUDA_VISIBLE_DEVICES=MIG-1457e955-5461-5ddc-85aa-d5659b8d71f0`
   - Prolog script detects this is already a UUID
   - Creates `/run/gpustat/MIG-1457e955-5461-5ddc-85aa-d5659b8d71f0` with job ID and UID

3. **GPU Exporter:**
   - nvidia_gpu_prometheus_exporter reads `/run/gpustat/`
   - Associates the MIG UUID with the job ID
   - Exports metrics with `jobid` label

4. **Prometheus:**
   - Scrapes metrics from GPU exporter
   - Stores time-series data with `jobid` label

5. **Jobstats Query:**
   - User runs `jobstats <jobid>`
   - Queries Prometheus for GPU metrics with that job ID
   - Falls back to `sm_util_percent` if `duty_cycle` is not available
   - Displays GPU utilization correctly

6. **Epilog Script Execution:**
   - Job completes
   - Epilog script removes the MIG UUID file from `/run/gpustat/`

## Verification

### Check MIG Configuration

```bash
# List MIG instances on a node
ssh dgx018 "nvidia-smi mig -lgi"

# Check what metrics are available
ssh dgx018 "curl -s http://localhost:9445/metrics | grep nvidia_gpu"

# Verify prolog/epilog scripts exist
ls -la /cm/shared/apps/slurm/var/cm/*-jobstats.sh
ls -la /cm/local/apps/slurm/var/prologs/60-prolog-jobstats.sh
ls -la /cm/local/apps/slurm/var/epilogs/60-epilog-jobstats.sh
```

### Test MIG Job

```bash
# Submit a test job to MIG partition
srun --partition=dgx-b200-mig90 --gpus=1 --time=5:00 sleep 300 &
JOBID=$(squeue --me --noheader -o "%i" | head -1)

# While running, check /run/gpustat/
ssh dgx018 "ls -la /run/gpustat/"

# Should see MIG UUID files with job ID

# Check jobstats (after job starts)
jobstats $JOBID

# Should see GPU utilization data
```

## Architecture Support

### Regular GPUs (Non-MIG)
- **Architectures:** A100, H100 (non-MIG mode), V100, etc.
- **Metrics Available:** `nvidia_gpu_duty_cycle`, `nvidia_gpu_sm_util_percent`
- **Prolog/Epilog:** Creates numeric index files + UUID files
- **Jobstats Query:** Uses `duty_cycle` (primary)

### MIG GPUs
- **Architectures:** B200, H100 (MIG mode), A100 (MIG mode)
- **Metrics Available:** `nvidia_gpu_sm_util_percent` (duty_cycle N/A)
- **Prolog/Epilog:** Creates UUID files directly
- **Jobstats Query:** Falls back to `sm_util_percent`

## Troubleshooting

### Issue: "Value is unknown" for GPU utilization on MIG jobs

**Cause:** jobstats not using fallback to `sm_util_percent`

**Fix:**
```bash
python3 automation/tools/fix_jobstats_mig_utilization.py
```

### Issue: No `jobid` label on MIG GPU metrics in Prometheus

**Causes:**
1. Prolog/epilog scripts not installed on GPU nodes
2. Files not being created in `/run/gpustat/`
3. GPU exporter not reading `/run/gpustat/` correctly

**Checks:**
```bash
# 1. Verify scripts are symlinked
pdsh -w dgx[001-100] "ls -la /cm/local/apps/slurm/var/prologs/60-prolog-jobstats.sh"

# 2. Run a job and check /run/gpustat/ during execution
srun --gpus=1 sleep 300 &
ssh <node> "ls -la /run/gpustat/"

# 3. Check GPU exporter metrics
ssh <node> "curl -s http://localhost:9445/metrics | grep jobId"
```

### Issue: "Nodeviceswerefound" files in /run/gpustat/

**Cause:** Old prolog script trying to query nvidia-smi with MIG UUID

**Fix:** Deploy updated prolog/epilog scripts from this repo

```bash
# Copy updated custom scripts
cp automation/scripts/prolog-jobstats.sh /cm/shared/apps/slurm/var/cm/prolog-jobstats.sh
cp automation/scripts/epilog-jobstats.sh /cm/shared/apps/slurm/var/cm/epilog-jobstats.sh
chmod +x /cm/shared/apps/slurm/var/cm/*-jobstats.sh

# Clean up old error files
pdsh -w dgx[001-100] "rm -f /run/gpustat/Nodeviceswerefound"
```

## Alternative Fix: Prometheus-Side

If you prefer not to modify jobstats code, you can fix this entirely in Prometheus configuration.

**See detailed guide:** [automation/tools/alternate_mig_fix.md](tools/alternate_mig_fix.md)

### Quick Overview

**Option 1: Recording Rule (Recommended)**
```yaml
groups:
  - name: jobstats_mig_compatibility
    rules:
      - record: nvidia_gpu_duty_cycle
        expr: nvidia_gpu_sm_util_percent{uuid=~"MIG-.*"}
```

**Option 2: Metric Relabeling**
```yaml
# In prometheus.yml under nvidia_gpu_exporter job:
metric_relabel_configs:
  - source_labels: [__name__, uuid]
    separator: ;
    regex: ^nvidia_gpu_sm_util_percent;(MIG-.+)
    target_label: __name__
    replacement: nvidia_gpu_duty_cycle
    action: replace
```

Both approaches make MIG instances expose `duty_cycle` in Prometheus, so jobstats' existing query works unchanged.

**Full instructions:** See [alternate_mig_fix.md](tools/alternate_mig_fix.md) for complete step-by-step guide.

## References

- [NVIDIA MIG Documentation](https://docs.nvidia.com/datacenter/tesla/mig-user-guide/)
- [Princeton Jobstats](https://github.com/PrincetonUniversity/jobstats)
- [nvidia_gpu_prometheus_exporter](https://github.com/plazonic/nvidia_gpu_prometheus_exporter)

## Summary

The MIG support changes ensure that jobstats works seamlessly with both:
- Traditional GPU nodes (A100, H100 in non-MIG mode)
- MIG-enabled nodes (B200, H100/A100 in MIG mode)

The deployment automation now includes these fixes by default, making MIG support transparent to users.

