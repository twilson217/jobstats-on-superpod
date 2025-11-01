#!/bin/bash
# Slurm prolog script for GPU job tracking (MIG-optimized)
# Creates files in /run/gpustat/ to associate GPUs with job IDs
# 
# This script handles both regular GPUs and MIG (Multi-Instance GPU) instances.
# MIG instances are identified by UUIDs starting with "MIG-" in CUDA_VISIBLE_DEVICES.
#
# Version: 1.1 (MIG Support)
# Date: 2025-11-01

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

