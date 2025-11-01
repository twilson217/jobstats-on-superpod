#!/bin/bash
# Slurm epilog script for GPU job tracking cleanup (MIG-optimized)
# Removes files from /run/gpustat/ when jobs complete
# 
# This script handles both regular GPUs and MIG (Multi-Instance GPU) instances.
# MIG instances are identified by UUIDs starting with "MIG-" in CUDA_VISIBLE_DEVICES.
#
# Version: 1.1 (MIG Support)
# Date: 2025-11-01

DEST=/run/gpustat

for i in ${GPU_DEVICE_ORDINAL//,/ } ${CUDA_VISIBLE_DEVICES//,/ }; do
  # Skip empty values
  [ -z "$i" ] && continue
  
  # Remove ordinal-based file (for numeric indices or UUID strings)
  rm -f "$DEST/$i"
  
  # If it's already a UUID (GPU-* or MIG-*), we're done
  if [[ $i =~ ^(GPU|MIG)- ]]; then
    continue
  fi
  
  # Otherwise, it's a numeric index - query nvidia-smi for the UUID
  UUID=$(/usr/bin/nvidia-smi --query-gpu=uuid --format=noheader,csv -i $i 2>/dev/null | tr -d ' ')
  
  if [ -n "$UUID" ] && [[ $UUID =~ ^(GPU|MIG)- ]]; then
    rm -f "$DEST/$UUID"
  fi
done

exit 0

