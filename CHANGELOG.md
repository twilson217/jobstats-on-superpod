# Changelog

## MIG Support Update - 2025-11-01

### Overview
Added comprehensive Multi-Instance GPU (MIG) support to the jobstats deployment automation.

### Files Modified

#### 1. Prolog/Epilog Scripts (MIG-Aware)
**Files Created:**
- `automation/scripts/prolog-jobstats.sh`
- `automation/scripts/epilog-jobstats.sh`
- `automation/scripts/README.md`

**Note:** These are custom scripts maintained in this repository, not in the upstream jobstats repo.

**Changes:**
- Added detection for MIG UUIDs (starting with `MIG-` or `GPU-`)
- Use UUIDs directly when provided in `CUDA_VISIBLE_DEVICES`
- Only query nvidia-smi for numeric indices
- Added error handling with `2>/dev/null`
- Skip empty values in device list
- Added comprehensive comments explaining MIG handling

**Impact:**
- Fixes "Nodeviceswerefound" errors on MIG nodes
- Enables proper GPU job tracking for MIG instances
- Maintains backward compatibility with regular GPUs

#### 2. GPU Utilization Fix Script
**File:**
- `automation/tools/fix_jobstats_mig_utilization.py` (NEW)

**Changes:**
- Created automated fix script for GPU utilization queries
- Adds fallback logic: `nvidia_gpu_duty_cycle` → `nvidia_gpu_sm_util_percent`
- Includes automatic backup and rollback
- Built-in testing functionality
- Debug logging support

**Impact:**
- Fixes "Value is unknown" errors for GPU utilization on MIG jobs
- Enables GPU utilization reporting for MIG instances
- Maintains compatibility with non-MIG nodes

#### 3. Documentation

**New Files:**
- `automation/MIG_SUPPORT.md` - Comprehensive MIG support documentation
  - Problem description and solutions
  - Architecture-specific behavior
  - Troubleshooting guide
  - Verification procedures
  - Alternative Prometheus-side fix

**Updated Files:**
- `README.md` - Added MIG support mention in overview
- `automation/README.md` - Added MIG Support section with quick deployment guide
- `automation/tools/README.md` - Added documentation for fix_jobstats_mig_utilization.py

### Technical Details

#### MIG UUID Handling
```bash
# Before (broken):
for i in $CUDA_VISIBLE_DEVICES; do
  UUID=$(/usr/bin/nvidia-smi --query-gpu=uuid -i $i)  # Fails for MIG-*
done

# After (fixed):
for i in $CUDA_VISIBLE_DEVICES; do
  if [[ $i =~ ^(GPU|MIG)- ]]; then
    # Already a UUID, use directly
    echo $SLURM_JOB_ID > "$DEST/$i"
  else
    # Numeric index, query nvidia-smi
    UUID=$(/usr/bin/nvidia-smi --query-gpu=uuid -i $i 2>/dev/null)
    echo $SLURM_JOB_ID > "$DEST/$UUID"
  fi
done
```

#### GPU Utilization Metric Fallback
```python
# Before (broken for MIG):
self.get_data('gpu_utilization', 
              "avg_over_time((nvidia_gpu_duty_cycle{...})[%ds:])")

# After (works for both):
def get_gpu_utilization_with_fallback(self):
    # Try duty_cycle first (regular GPUs)
    self.get_data('gpu_utilization', "...nvidia_gpu_duty_cycle...")
    
    # Check if we got data
    if not got_data:
        # Fall back to sm_util_percent (MIG GPUs)
        self.get_data('gpu_utilization', "...nvidia_gpu_sm_util_percent...")
```

### Deployment

#### For New Installations
The guided setup automatically deploys MIG-compatible scripts:
```bash
uv run python automation/guided_setup.py --config automation/configs/config.json
```

#### For Existing Installations
Apply the GPU utilization fix:
```bash
python3 automation/tools/fix_jobstats_mig_utilization.py
```

Update prolog/epilog scripts on all nodes:
```bash
# On head node - deploy our custom MIG-optimized scripts
cp automation/scripts/prolog-jobstats.sh /cm/shared/apps/slurm/var/cm/prolog-jobstats.sh
cp automation/scripts/epilog-jobstats.sh /cm/shared/apps/slurm/var/cm/epilog-jobstats.sh
chmod +x /cm/shared/apps/slurm/var/cm/*-jobstats.sh

# Verify on compute nodes
pdsh -w dgx[001-100] "ls -la /cm/local/apps/slurm/var/prologs/60-prolog-jobstats.sh"
```

### Testing

#### Verify MIG Support
```bash
# 1. Check MIG instances
ssh dgx018 "nvidia-smi mig -lgi"

# 2. Submit MIG test job
srun --partition=dgx-b200-mig90 --gpus=1 --time=5:00 sleep 300 &

# 3. Verify /run/gpustat/ during job
ssh dgx018 "ls -la /run/gpustat/"

# 4. Check jobstats output
jobstats <jobid>  # Should show GPU utilization
```

### Architecture Support

| GPU Type | Architecture | duty_cycle | sm_util_percent | Status |
|----------|-------------|------------|-----------------|--------|
| Regular GPUs | A100, H100 | ✅ Yes | ✅ Yes | Fully Supported |
| MIG Instances | B200, H100-MIG, A100-MIG | ❌ No | ✅ Yes | Fully Supported (with fallback) |

### Known Issues Fixed
1. ✅ "Nodeviceswerefound" files in `/run/gpustat/` on MIG nodes
2. ✅ "Value is unknown" for GPU utilization on MIG jobs
3. ✅ Missing `jobid` labels on MIG GPU metrics in Prometheus
4. ✅ Prolog script failures when CUDA_VISIBLE_DEVICES contains MIG UUIDs

### Migration Notes

**No Breaking Changes:**
- All changes are backward compatible
- Regular GPU nodes continue to work as before
- MIG and non-MIG nodes can coexist in the same cluster
- No Slurm configuration changes required

**Recommended Actions:**
1. Deploy updated prolog/epilog scripts to all GPU nodes
2. Run `fix_jobstats_mig_utilization.py` on login nodes
3. Test with both MIG and non-MIG jobs
4. Review [MIG_SUPPORT.md](automation/MIG_SUPPORT.md) for detailed information

### Future Considerations

**Alternative Prometheus Fix:**
Instead of modifying jobstats code, MIG support can be added entirely in Prometheus using metric relabeling:

```yaml
metric_relabel_configs:
  - source_labels: [__name__, uuid]
    regex: ^nvidia_gpu_sm_util_percent;(MIG-.+)
    target_label: __name__
    replacement: nvidia_gpu_duty_cycle
```

This approach:
- ✅ No code changes to jobstats
- ✅ Centralized configuration
- ❌ Requires Prometheus access
- ❌ Less transparent than code-based fix

Both approaches are documented and supported.

### References
- [MIG Support Documentation](automation/MIG_SUPPORT.md)
- [Tools README](automation/tools/README.md)
- [NVIDIA MIG User Guide](https://docs.nvidia.com/datacenter/tesla/mig-user-guide/)
- [Princeton Jobstats](https://github.com/PrincetonUniversity/jobstats)

---

## Previous Updates

### Initial Deployment - 2025-10-28
- Initial fork and customization of Princeton jobstats
- BCM integration and automation scripts
- Guided setup implementation
- Role monitor service for dynamic Prometheus targets

