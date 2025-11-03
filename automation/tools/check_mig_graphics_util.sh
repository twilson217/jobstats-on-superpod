#!/bin/bash
# Check if nvidia_gpu_graphics_util_percent is available for MIG instances
# This metric is potentially better than sm_util_percent for user-facing utilization

echo "=========================================="
echo "Checking MIG GPU Utilization Metrics"
echo "=========================================="
echo

# Check if arguments provided
if [ $# -eq 0 ]; then
    echo "Usage: $0 <dgx-hostname> [exporter-port]"
    echo "Example: $0 dgx001 9445"
    exit 1
fi

DGX_HOST=$1
EXPORTER_PORT=${2:-9445}

echo "Target: http://${DGX_HOST}:${EXPORTER_PORT}/metrics"
echo

# Check if exporter is responding
echo "1. Testing exporter connectivity..."
if ! curl -s -m 5 "http://${DGX_HOST}:${EXPORTER_PORT}/metrics" > /dev/null; then
    echo "   ❌ Cannot reach exporter on ${DGX_HOST}:${EXPORTER_PORT}"
    exit 1
fi
echo "   ✅ Exporter is responding"
echo

# Check for MIG UUIDs
echo "2. Checking for MIG instances..."
MIG_COUNT=$(curl -s "http://${DGX_HOST}:${EXPORTER_PORT}/metrics" | grep -c 'uuid="MIG-')
if [ $MIG_COUNT -eq 0 ]; then
    echo "   ⚠️  No MIG instances found on this node"
    echo "   This node may not have MIG enabled or no MIG instances are configured"
else
    echo "   ✅ Found $MIG_COUNT MIG-related metrics"
fi
echo

# Check for duty_cycle on MIG
echo "3. Checking nvidia_gpu_duty_cycle for MIG..."
DUTY_CYCLE_MIG=$(curl -s "http://${DGX_HOST}:${EXPORTER_PORT}/metrics" | grep 'nvidia_gpu_duty_cycle{' | grep 'uuid="MIG-')
if [ -z "$DUTY_CYCLE_MIG" ]; then
    echo "   ❌ nvidia_gpu_duty_cycle NOT available for MIG (expected)"
else
    echo "   ✅ nvidia_gpu_duty_cycle IS available for MIG (unexpected but good!)"
    echo "   Sample:"
    echo "$DUTY_CYCLE_MIG" | head -3
fi
echo

# Check for graphics_util_percent on MIG
echo "4. Checking nvidia_gpu_graphics_util_percent for MIG..."
GRAPHICS_UTIL_MIG=$(curl -s "http://${DGX_HOST}:${EXPORTER_PORT}/metrics" | grep 'nvidia_gpu_graphics_util_percent{' | grep 'uuid="MIG-')
if [ -z "$GRAPHICS_UTIL_MIG" ]; then
    echo "   ❌ nvidia_gpu_graphics_util_percent NOT available for MIG"
    echo "   This means GPM is not enabled or not supported for MIG on this GPU"
else
    echo "   ✅ nvidia_gpu_graphics_util_percent IS available for MIG!"
    echo "   Sample:"
    echo "$GRAPHICS_UTIL_MIG" | head -3
    echo
    echo "   🎉 This is great news! We can use this metric instead of sm_util_percent"
fi
echo

# Check for sm_util_percent on MIG
echo "5. Checking nvidia_gpu_sm_util_percent for MIG..."
SM_UTIL_MIG=$(curl -s "http://${DGX_HOST}:${EXPORTER_PORT}/metrics" | grep 'nvidia_gpu_sm_util_percent{' | grep 'uuid="MIG-')
if [ -z "$SM_UTIL_MIG" ]; then
    echo "   ❌ nvidia_gpu_sm_util_percent NOT available for MIG"
else
    echo "   ✅ nvidia_gpu_sm_util_percent IS available for MIG"
    echo "   Sample:"
    echo "$SM_UTIL_MIG" | head -3
fi
echo

# Summary and recommendations
echo "=========================================="
echo "SUMMARY & RECOMMENDATIONS"
echo "=========================================="
echo

if [ -n "$GRAPHICS_UTIL_MIG" ]; then
    echo "✅ BEST OPTION: Use nvidia_gpu_graphics_util_percent"
    echo "   This metric represents 'time any compute app was active'"
    echo "   Very similar semantics to duty_cycle that users expect"
    echo
    echo "   Recommended fallback hierarchy:"
    echo "   1. nvidia_gpu_duty_cycle (regular GPUs, 0-100 range)"
    echo "   2. nvidia_gpu_graphics_util_percent * 100 (MIG with GPM support, stored as 0-1)"
    echo "   3. nvidia_gpu_sm_util_percent * 100 (fallback, stored as 0-1)"
    echo
    echo "   IMPORTANT: GPM metrics are stored in 0-1 range and must be multiplied by 100!"
    echo
    echo "   Next step: Run fix_jobstats_mig_utilization_v3.py to apply this fix"
elif [ -n "$SM_UTIL_MIG" ]; then
    echo "⚠️  CURRENT OPTION: nvidia_gpu_sm_util_percent"
    echo "   This works but shows SM hardware utilization (often lower than expected)"
    echo
    echo "   Options to consider:"
    echo "   1. Check if GPM can be enabled (may require exporter restart with different flags)"
    echo "   2. Consider DCGM exporter for better MIG metrics"
    echo "   3. Continue with current solution and document the behavior"
else
    echo "❌ NO UTILIZATION METRICS FOUND FOR MIG"
    echo "   This is unexpected. Please check:"
    echo "   1. Is MIG actually enabled? (nvidia-smi -i 0 --query-gpu=mig.mode.current --format=csv)"
    echo "   2. Is the exporter version recent enough?"
    echo "   3. Are there any errors in exporter logs?"
fi
echo

# Check for regular GPU (non-MIG) metrics for comparison
echo "=========================================="
echo "REFERENCE: Non-MIG GPU Metrics"
echo "=========================================="
echo

DUTY_CYCLE_REGULAR=$(curl -s "http://${DGX_HOST}:${EXPORTER_PORT}/metrics" | grep 'nvidia_gpu_duty_cycle{' | grep -v 'uuid="MIG-' | head -1)
GRAPHICS_UTIL_REGULAR=$(curl -s "http://${DGX_HOST}:${EXPORTER_PORT}/metrics" | grep 'nvidia_gpu_graphics_util_percent{' | grep -v 'uuid="MIG-' | head -1)

if [ -n "$DUTY_CYCLE_REGULAR" ]; then
    echo "duty_cycle (regular GPU): Available"
    echo "  $DUTY_CYCLE_REGULAR"
else
    echo "duty_cycle (regular GPU): Not available"
fi

if [ -n "$GRAPHICS_UTIL_REGULAR" ]; then
    echo "graphics_util_percent (regular GPU): Available"
    echo "  $GRAPHICS_UTIL_REGULAR"
else
    echo "graphics_util_percent (regular GPU): Not available"
fi
echo

echo "=========================================="
echo "Done!"
echo "=========================================="

