# Custom Jobstats Scripts

This directory contains custom, MIG-optimized versions of jobstats prolog/epilog scripts that are deployed by the automation instead of the upstream versions from the Princeton jobstats repository.

## Why Custom Scripts?

The upstream jobstats repository (https://github.com/PrincetonUniversity/jobstats) contains generic prolog/epilog scripts that work well for traditional GPU configurations but fail with NVIDIA Multi-Instance GPU (MIG) instances.

Our custom scripts add MIG support while maintaining full backward compatibility with regular GPUs.

## Files

### prolog-jobstats.sh

**Purpose:** Creates job tracking files in `/run/gpustat/` when GPU jobs start.

**Deployed To:** `/cm/shared/apps/slurm/var/cm/prolog-jobstats.sh` (via guided setup)

**Symlinked On:** All GPU compute nodes at `/cm/local/apps/slurm/var/prologs/60-prolog-jobstats.sh`

**Key Features:**
- Automatically detects MIG UUIDs (starting with `MIG-` or `GPU-`)
- Uses UUIDs directly when already provided in `CUDA_VISIBLE_DEVICES`
- Only queries nvidia-smi for numeric GPU indices
- Handles errors gracefully with `2>/dev/null`
- Skips empty device values

### epilog-jobstats.sh

**Purpose:** Cleans up job tracking files from `/run/gpustat/` when GPU jobs complete.

**Deployed To:** `/cm/shared/apps/slurm/var/cm/epilog-jobstats.sh` (via guided setup)

**Symlinked On:** All GPU compute nodes at `/cm/local/apps/slurm/var/epilogs/60-epilog-jobstats.sh`

**Key Features:**
- Mirrors the prolog logic for cleanup
- Handles both MIG and regular GPU device identifiers
- Removes all tracking files for the job

## Differences from Upstream

### Upstream (jobstats/slurm/prolog.d/gpustats_helper.sh)

```bash
#!/bin/bash
DEST=/run/gpustat
[ -e $DEST ] || mkdir -m 755 $DEST
for i in ${GPU_DEVICE_ORDINAL//,/ } ${CUDA_VISIBLE_DEVICES//,/ }; do
  echo $SLURM_JOB_ID $SLURM_JOB_UID > $DEST/$i
  if [ "${i:0:3}" != "MIG" ]; then
    UUID="`/usr/bin/nvidia-smi --query-gpu=uuid --format=noheader,csv -i $i`"
    echo $SLURM_JOB_ID $SLURM_JOB_UID > "$DEST/$UUID"
  fi
done
exit 0
```

**Problem:** Attempts to query nvidia-smi with MIG UUID as index, which fails:
```bash
nvidia-smi -i MIG-1457e955-5461-5ddc-85aa-d5659b8d71f0
# Error: No devices were found
```

This creates error files like `Nodeviceswerefound` in `/run/gpustat/`.

### Our Version (automation/scripts/prolog-jobstats.sh)

```bash
#!/bin/bash
DEST=/run/gpustat
[ -e $DEST ] || mkdir -m 755 $DEST

for i in ${GPU_DEVICE_ORDINAL//,/ } ${CUDA_VISIBLE_DEVICES//,/ }; do
  # Skip empty values
  [ -z "$i" ] && continue
  
  # Create ordinal-based file (for numeric indices or UUID strings)
  echo $SLURM_JOB_ID $SLURM_JOB_UID > "$DEST/$i"
  
  # If it's already a UUID (GPU-* or MIG-*), we're done
  if [[ $i =~ ^(GPU|MIG)- ]]; then
    continue
  fi
  
  # Otherwise, it's a numeric index - query nvidia-smi for the UUID
  UUID=$(/usr/bin/nvidia-smi --query-gpu=uuid --format=noheader,csv -i $i 2>/dev/null | tr -d ' ')
  
  if [ -n "$UUID" ] && [[ $UUID =~ ^(GPU|MIG)- ]]; then
    echo $SLURM_JOB_ID $SLURM_JOB_UID > "$DEST/$UUID"
  fi
done

exit 0
```

**Fix:** 
1. Check if device identifier is already a UUID using regex `^(GPU|MIG)-`
2. If UUID, use directly without querying nvidia-smi
3. If numeric index, query nvidia-smi
4. Add error suppression (`2>/dev/null`) and validation
5. Skip empty values

## Deployment

### Automatic (via guided_setup.py)

The guided setup automatically deploys these custom scripts:

```bash
uv run python automation/guided_setup.py --config automation/configs/config.json
```

The script will:
1. Copy `automation/scripts/prolog-jobstats.sh` → `/cm/shared/apps/slurm/var/cm/prolog-jobstats.sh`
2. Copy `automation/scripts/epilog-jobstats.sh` → `/cm/shared/apps/slurm/var/cm/epilog-jobstats.sh`
3. Create symlinks on all GPU nodes

### Manual Deployment

If you need to deploy manually:

```bash
# On Slurm controller / head node
cp automation/scripts/prolog-jobstats.sh /cm/shared/apps/slurm/var/cm/prolog-jobstats.sh
cp automation/scripts/epilog-jobstats.sh /cm/shared/apps/slurm/var/cm/epilog-jobstats.sh
chmod +x /cm/shared/apps/slurm/var/cm/*-jobstats.sh

# On each GPU node (or via pdsh)
mkdir -p /cm/local/apps/slurm/var/prologs /cm/local/apps/slurm/var/epilogs
ln -sf /cm/shared/apps/slurm/var/cm/prolog-jobstats.sh /cm/local/apps/slurm/var/prologs/60-prolog-jobstats.sh
ln -sf /cm/shared/apps/slurm/var/cm/epilog-jobstats.sh /cm/local/apps/slurm/var/epilogs/60-epilog-jobstats.sh

# Or with pdsh for all nodes
pdsh -w dgx[001-100] "mkdir -p /cm/local/apps/slurm/var/prologs /cm/local/apps/slurm/var/epilogs"
pdsh -w dgx[001-100] "ln -sf /cm/shared/apps/slurm/var/cm/prolog-jobstats.sh /cm/local/apps/slurm/var/prologs/60-prolog-jobstats.sh"
pdsh -w dgx[001-100] "ln -sf /cm/shared/apps/slurm/var/cm/epilog-jobstats.sh /cm/local/apps/slurm/var/epilogs/60-epilog-jobstats.sh"
```

## Testing

### Test on Regular GPU Node

```bash
# Submit job on regular GPU node
srun --partition=dgx-h100 --gpus=1 --time=5:00 sleep 300 &
JOBID=$(squeue --me --noheader -o "%i" | head -1)
NODE=$(squeue -j $JOBID --noheader -o "%N")

# Check /run/gpustat/ on the node
ssh $NODE "ls -la /run/gpustat/"

# Should see:
# - Numeric index file (e.g., "0")
# - GPU UUID file (e.g., "GPU-...")
# - Both containing the job ID and UID
```

### Test on MIG Node

```bash
# Submit job on MIG node
srun --partition=dgx-b200-mig90 --gpus=1 --time=5:00 sleep 300 &
JOBID=$(squeue --me --noheader -o "%i" | head -1)
NODE=$(squeue -j $JOBID --noheader -o "%N")

# Check /run/gpustat/ on the node
ssh $NODE "ls -la /run/gpustat/"

# Should see:
# - MIG UUID file (e.g., "MIG-...")
# - File containing the job ID and UID
# - NO "Nodeviceswerefound" error files
```

### Verify nvidia_gpu_exporter Sees Job IDs

```bash
# While job is running
ssh $NODE "curl -s http://localhost:9445/metrics | grep 'jobId=\"$JOBID\"'"

# Should show GPU metrics labeled with the job ID
```

## Architecture Support

| GPU Type | CUDA_VISIBLE_DEVICES | Script Behavior |
|----------|---------------------|-----------------|
| Regular GPU | `0,1,2` | Creates numeric files + queries UUID |
| MIG Instance | `MIG-1457e955-...` | Uses UUID directly, no query |
| Mixed | `0,MIG-1457e955-...` | Handles each appropriately |

## Troubleshooting

### Issue: "Nodeviceswerefound" files in /run/gpustat/

**Cause:** Using upstream scripts that try to query nvidia-smi with MIG UUID

**Fix:** Deploy our custom scripts:
```bash
cp automation/scripts/*.sh /cm/shared/apps/slurm/var/cm/
chmod +x /cm/shared/apps/slurm/var/cm/*-jobstats.sh
```

### Issue: No files created in /run/gpustat/ during MIG job

**Checks:**
1. Verify scripts are symlinked: `ls -la /cm/local/apps/slurm/var/prologs/60-prolog-jobstats.sh`
2. Check script permissions: `ls -la /cm/shared/apps/slurm/var/cm/prolog-jobstats.sh`
3. Verify CUDA_VISIBLE_DEVICES: `scontrol show job <jobid> | grep GRES`
4. Check Slurm logs: `grep prolog /var/log/slurm/slurmd.log`

### Issue: Files created but nvidia_gpu_exporter doesn't see them

**Cause:** Exporter may need restart to detect new files

**Fix:**
```bash
systemctl restart nvidia_gpu_exporter
```

## Version History

- **v1.0** (2025-10-28): Initial upstream scripts
- **v1.1** (2025-11-01): Added MIG support with UUID detection and error handling

## Related Documentation

- [MIG Support Guide](../MIG_SUPPORT.md)
- [Tools README](../tools/README.md)
- [Main Automation README](../README.md)
- [NVIDIA MIG User Guide](https://docs.nvidia.com/datacenter/tesla/mig-user-guide/)

