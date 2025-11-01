# MIG Support Integration - Summary

## What Was Done

This document summarizes the integration of NVIDIA Multi-Instance GPU (MIG) support into the jobstats-on-superpod deployment automation.

## Problem Solved

**Issue:** The upstream Princeton jobstats prolog/epilog scripts fail with MIG instances because they attempt to query nvidia-smi using MIG UUIDs as device indices, which returns "No devices were found" errors.

**Impact:**
- `Nodeviceswerefound` error files created in `/run/gpustat/`
- GPU metrics missing `jobid` labels for MIG instances
- `jobstats` command showing "Value is unknown" for GPU utilization on MIG jobs

## Solution Overview

Created **custom MIG-optimized prolog/epilog scripts** that are maintained in this repository and automatically deployed by the guided setup instead of the upstream versions.

## Files Created/Modified

### New Custom Scripts (Permanent)

```
automation/scripts/
├── prolog-jobstats.sh          # MIG-optimized prolog script
├── epilog-jobstats.sh          # MIG-optimized epilog script
└── README.md                   # Documentation for custom scripts
```

### Automation Updates

**Modified:**
- `automation/guided_setup.py` - Updated to deploy custom scripts instead of upstream
  - Line 925: Changed from `jobstats/slurm/prolog.d/gpustats_helper.sh` to `automation/scripts/prolog-jobstats.sh`
  - Line 935: Changed from `jobstats/slurm/epilog.d/gpustats_helper.sh` to `automation/scripts/epilog-jobstats.sh`

### Fix Tool

**Created:**
- `automation/tools/fix_jobstats_mig_utilization.py` - Adds fallback for GPU utilization queries
  - Tries `nvidia_gpu_duty_cycle` first (regular GPUs)
  - Falls back to `nvidia_gpu_sm_util_percent` (MIG instances)

### Documentation

**Created:**
- `automation/MIG_SUPPORT.md` - Comprehensive MIG support guide
- `automation/scripts/README.md` - Custom scripts documentation
- `CHANGELOG.md` - Complete change history

**Updated:**
- `README.md` - Added MIG support mention
- `automation/README.md` - Added MIG Support section
- `automation/tools/README.md` - Documented fix script

## Key Technical Changes

### Prolog Script Logic

**Before (Upstream - Fails with MIG):**
```bash
for i in ${CUDA_VISIBLE_DEVICES//,/ }; do
  echo $SLURM_JOB_ID $SLURM_JOB_UID > $DEST/$i
  if [ "${i:0:3}" != "MIG" ]; then
    UUID=$(/usr/bin/nvidia-smi --query-gpu=uuid -i $i)  # FAILS if $i is MIG UUID
    echo $SLURM_JOB_ID $SLURM_JOB_UID > "$DEST/$UUID"
  fi
done
```

**After (Our Custom - Works with MIG):**
```bash
for i in ${CUDA_VISIBLE_DEVICES//,/ }; do
  [ -z "$i" ] && continue
  echo $SLURM_JOB_ID $SLURM_JOB_UID > "$DEST/$i"
  
  # If already a UUID, skip nvidia-smi query
  if [[ $i =~ ^(GPU|MIG)- ]]; then
    continue
  fi
  
  # Only query nvidia-smi for numeric indices
  UUID=$(/usr/bin/nvidia-smi --query-gpu=uuid -i $i 2>/dev/null | tr -d ' ')
  if [ -n "$UUID" ] && [[ $UUID =~ ^(GPU|MIG)- ]]; then
    echo $SLURM_JOB_ID $SLURM_JOB_UID > "$DEST/$UUID"
  fi
done
```

### Key Improvements

1. **UUID Detection:** Check if device ID is already a UUID using regex `^(GPU|MIG)-`
2. **Direct UUID Usage:** Use MIG UUIDs directly without nvidia-smi query
3. **Error Handling:** Add `2>/dev/null` to suppress errors
4. **Empty Value Handling:** Skip empty device IDs
5. **Validation:** Verify UUID format before creating files

## Deployment Flow

### Automated (Recommended)

```bash
# Guided setup automatically uses custom MIG-optimized scripts
uv run python automation/guided_setup.py --config automation/configs/config.json
```

**What happens:**
1. Copies `automation/scripts/prolog-jobstats.sh` → `/cm/shared/apps/slurm/var/cm/prolog-jobstats.sh`
2. Copies `automation/scripts/epilog-jobstats.sh` → `/cm/shared/apps/slurm/var/cm/epilog-jobstats.sh`
3. Creates symlinks on all GPU nodes
4. GPU jobs (MIG and non-MIG) automatically tracked

### Manual (Existing Installations)

```bash
# 1. Deploy custom scripts
cp automation/scripts/prolog-jobstats.sh /cm/shared/apps/slurm/var/cm/prolog-jobstats.sh
cp automation/scripts/epilog-jobstats.sh /cm/shared/apps/slurm/var/cm/epilog-jobstats.sh
chmod +x /cm/shared/apps/slurm/var/cm/*-jobstats.sh

# 2. Fix GPU utilization queries
python3 automation/tools/fix_jobstats_mig_utilization.py

# 3. Verify on nodes
pdsh -w dgx[001-100] "ls -la /cm/local/apps/slurm/var/prologs/60-prolog-jobstats.sh"
```

## Architecture Support Matrix

| GPU Type | Arch | CUDA_VISIBLE_DEVICES | duty_cycle | sm_util_percent | Status |
|----------|------|---------------------|------------|-----------------|--------|
| Regular | H100, A100, V100 | `0,1,2` | ✅ Yes | ✅ Yes | Fully Supported |
| MIG | B200, H100-MIG, A100-MIG | `MIG-xxx...` | ❌ No | ✅ Yes | Fully Supported |

## Testing

### Test Regular GPU

```bash
srun --partition=dgx-h100 --gpus=1 --time=5:00 sleep 300 &
JOBID=$(squeue --me --noheader -o "%i" | head -1)
NODE=$(squeue -j $JOBID --noheader -o "%N")

# Should see numeric and UUID files
ssh $NODE "ls -la /run/gpustat/"
```

### Test MIG GPU

```bash
srun --partition=dgx-b200-mig90 --gpus=1 --time=5:00 sleep 300 &
JOBID=$(squeue --me --noheader -o "%i" | head -1)
NODE=$(squeue -j $JOBID --noheader -o "%N")

# Should see MIG UUID file, NO error files
ssh $NODE "ls -la /run/gpustat/"

# Check jobstats
jobstats $JOBID  # Should show GPU utilization
```

## Version Information

- **Initial Version:** 1.0 (2025-10-28) - Upstream scripts only
- **MIG Support:** 1.1 (2025-11-01) - Custom MIG-optimized scripts

## Important Notes

### Why Custom Scripts?

The `jobstats/` directory in this repo is **temporary** - it's cloned fresh from upstream during deployment. Any changes made there would be lost.

**Solution:** Maintain custom scripts in `automation/scripts/` and update `guided_setup.py` to deploy them instead of upstream versions.

### Upstream Compatibility

Our custom scripts are **fully backward compatible** with the upstream behavior for regular GPUs, while adding MIG support. If upstream adds official MIG support in the future, we can evaluate switching back.

### No Breaking Changes

- Regular GPU nodes work exactly as before
- MIG and non-MIG nodes can coexist in same cluster
- No Slurm configuration changes required
- Existing jobs not affected

## Directory Structure

```
jobstats-on-superpod/
├── automation/
│   ├── scripts/                    # ← NEW: Custom MIG-optimized scripts
│   │   ├── prolog-jobstats.sh      # ← Deployed to /cm/shared/.../prolog-jobstats.sh
│   │   ├── epilog-jobstats.sh      # ← Deployed to /cm/shared/.../epilog-jobstats.sh
│   │   └── README.md               # ← Documentation
│   ├── tools/
│   │   ├── fix_jobstats_mig_utilization.py  # ← NEW: GPU util fix
│   │   └── README.md               # ← Updated with new tool
│   ├── guided_setup.py             # ← Modified to use custom scripts
│   ├── MIG_SUPPORT.md              # ← NEW: Complete MIG guide
│   └── README.md                   # ← Updated with MIG section
├── CHANGELOG.md                    # ← NEW: Complete history
└── README.md                       # ← Updated with MIG mention
```

## Next Steps

### For New Deployments

Just run the guided setup - MIG support is automatic:
```bash
uv run python automation/guided_setup.py --config automation/configs/config.json
```

### For Existing Deployments

1. **Update scripts on all nodes:**
   ```bash
   cp automation/scripts/*.sh /cm/shared/apps/slurm/var/cm/
   chmod +x /cm/shared/apps/slurm/var/cm/*-jobstats.sh
   ```

2. **Fix GPU utilization queries:**
   ```bash
   python3 automation/tools/fix_jobstats_mig_utilization.py
   ```

3. **Test with MIG job:**
   ```bash
   srun --partition=dgx-b200-mig90 --gpus=1 --time=5:00 sleep 300 &
   jobstats <jobid>
   ```

## Troubleshooting

See [automation/MIG_SUPPORT.md](automation/MIG_SUPPORT.md) for:
- Detailed troubleshooting steps
- Verification procedures
- Common issues and fixes
- Alternative Prometheus-side solutions

## References

- **MIG Support Guide:** [automation/MIG_SUPPORT.md](automation/MIG_SUPPORT.md)
- **Custom Scripts:** [automation/scripts/README.md](automation/scripts/README.md)
- **Tools Documentation:** [automation/tools/README.md](automation/tools/README.md)
- **Changelog:** [CHANGELOG.md](CHANGELOG.md)
- **NVIDIA MIG Guide:** https://docs.nvidia.com/datacenter/tesla/mig-user-guide/

## Success Criteria

✅ **Scripts Work on Both GPU Types:**
- Regular GPUs: Creates numeric + UUID files
- MIG GPUs: Creates MIG UUID files directly
- No "Nodeviceswerefound" errors

✅ **GPU Metrics Have Job IDs:**
- nvidia_gpu_prometheus_exporter correctly labels metrics
- Prometheus ingests metrics with jobid labels

✅ **Jobstats Shows Utilization:**
- `jobstats <jobid>` displays GPU utilization
- Works for both MIG and non-MIG jobs
- No "Value is unknown" errors

✅ **Deployment is Automatic:**
- Guided setup deploys custom scripts
- No manual intervention needed
- Works for fresh and existing installations

---

**Date:** 2025-11-01  
**Status:** Complete ✅  
**Tested:** Yes (MIG B200 and non-MIG H100)

