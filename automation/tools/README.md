# Jobstats Automation Tools

This directory contains various tools for testing, validating, and managing the jobstats deployment on BCM (Bright Cluster Manager) systems. These tools are designed to work with the jobstats monitoring platform for Slurm clusters.

## Table of Contents

- [Deployment Testing](#deployment-testing)
- [Deployment Fixes/Patches](#deployment-fixespatches)
- [Workload Testing](#workload-testing)
- [Misc](#misc)

## Deployment Testing

### validate_jobstats_deployment.py

**Purpose**: Comprehensive validation script that tests all components of the jobstats deployment.

**Use Case**: 
- Verify that all services are running correctly
- Check that exporters are collecting metrics
- Validate Prometheus configuration
- Test Grafana connectivity
- Ensure BCM configuration is correct

**Usage**:
```bash
# Run with default config file
python3 validate_jobstats_deployment.py

# Run with specific config file
python3 validate_jobstats_deployment.py --config /path/to/config.json

# Run with verbose output
python3 validate_jobstats_deployment.py --verbose
```

**Note**: If the validation reports "No cgroup metrics found", the script will suggest running a test job to generate data for proper validation.

**Features**:
- 35+ comprehensive validation tests
- Tests all exporters (node, cgroup, GPU)
- Validates Prometheus and Grafana
- Checks BCM configuration
- **Data quality validation** - Tests for alloc/cores and timelimit issues
- **Smart suggestions** - Provides test job commands when no data is available
- Provides detailed pass/fail reporting

## Deployment Fixes/Patches

### fix_jobstats_timelimit.py

**Purpose**: Fix for jobstats timelimit parsing issues with UNLIMITED time limits.

**Use Case**:
- Fix TypeError when jobstats encounters UNLIMITED time limits
- Resolve string vs integer comparison errors
- Fix repeated "UNLIMITED" display in time limit field

**Usage**:
```bash
# Run the fix (must be run on login node where jobstats is installed)
python3 fix_jobstats_timelimit.py

# The script will:
# - Create a backup of the original file
# - Apply fixes to handle UNLIMITED time limits
# - Test the fix with a recent job
# - Restore from backup if something goes wrong
```

**Features**:
- Automatic backup creation
- Safe error handling with rollback
- Built-in testing to verify fix works
- Handles both string comparison and formatting issues

### fix_jobstats_alloc_cores.py

**Purpose**: Fix for jobstats alloc/cores division error where alloc is a string but cores is an integer.

**Use Case**:
- Fix TypeError in output_formatters.py where alloc/cores division fails
- Handle string vs integer type mismatches
- Resolve division errors in memory allocation calculations

**Usage**:
```bash
# Run the fix (must be run on login node where jobstats is installed)
python3 fix_jobstats_alloc_cores.py

# The script will:
# - Create a backup of the original file
# - Apply fixes to handle string alloc values
# - Test the fix with a recent job
# - Provide detailed error handling and recovery
```

**Features**:
- Comprehensive error handling (ValueError, TypeError, ZeroDivisionError)
- Pattern matching fallback if exact line not found
- Built-in testing functionality
- Automatic backup creation with rollback capability

### fix_jobstats_mig_utilization_v3.py

**Purpose**: Patches jobstats GPU utilization queries to support both regular GPUs and NVIDIA MIG (Multi-Instance GPU) instances with a three-tier metric fallback system.

**The Problem**: 
- **Regular GPUs** (H100, A100, V100): Expose `nvidia_gpu_duty_cycle` metric representing "% of time kernels were executing"
- **MIG instances** (B200 MIG, H100 MIG, A100 MIG): Do NOT expose `duty_cycle` metric (nvidia-smi reports N/A)
- **Original jobstats**: Only queries `duty_cycle`, causing "Value is unknown" errors for MIG jobs

**The Solution - Three-Tier Fallback**:

The fix implements an intelligent fallback system that tries metrics in order of preference:

1. **`nvidia_gpu_duty_cycle`** (0-100 range)
   - Primary metric for regular GPUs
   - Represents: "% of time one or more kernels were executing on the GPU"
   - Used by: H100, A100, V100, and other traditional GPUs

2. **`nvidia_gpu_graphics_util_percent * 100`** (stored as 0-1, multiplied to 0-100)
   - Fallback for Hopper+ architecture with GPM (GPU Performance Monitoring)
   - Represents: "% of time any compute/graphics application was active"
   - Used by: B200 MIG instances, H100 with GPM enabled
   - **Note:** This metric has very similar semantics to `duty_cycle` and provides intuitive utilization percentages

3. **`nvidia_gpu_sm_util_percent * 100`** (stored as 0-1, multiplied to 0-100)
   - Final fallback for older MIG implementations without GPM
   - Represents: "% of Streaming Multiprocessors that were busy"
   - More technically accurate but may show lower percentages for memory-bound workloads

**Why Different Metrics for MIG?**

NVIDIA's architecture changed how GPU metrics are exposed:
- **Regular GPUs**: Use NVML's `GetUtilizationRates()` API → returns `duty_cycle` (0-100 range)
- **MIG + GPM**: Use GPM (GPU Performance Monitoring) API → returns multiple utilization metrics in 0-1 range
- **Key difference**: The exporter stores GPM metrics as fractions (0-1) despite the "_percent" suffix, so we multiply by 100

**Metric Scaling**:
```python
# duty_cycle: Already in 0-100 range
nvidia_gpu_duty_cycle = 98.6  # → displays as 98.6%

# GPM metrics: In 0-1 range, must multiply by 100
nvidia_gpu_graphics_util_percent = 0.99  # → 0.99 * 100 = 99% (correct!)
nvidia_gpu_sm_util_percent = 0.94        # → 0.94 * 100 = 94% (correct!)
```

**Usage**:
```bash
# Copy to production server
scp automation/tools/fix_jobstats_mig_utilization_v3.py root@server:/tmp/

# Run the fix (creates automatic backup)
ssh root@server "python3 /tmp/fix_jobstats_mig_utilization_v3.py"

# Test with a job
jobstats --debug <jobid>
```

**What It Does**:
1. Creates timestamped backup of original `jobstats.py`
2. Replaces single GPU utilization query with three-tier fallback logic
3. Adds debug logging showing which metric was used
4. Preserves all original functionality for regular GPUs

**Expected Debug Output**:

For regular GPU jobs:
```
DEBUG: query=avg_over_time((nvidia_gpu_duty_cycle{...})[...]
DEBUG: Using duty_cycle (standard GPU utilization)
GPU utilization  [|||||||||||||||||||||||||||||||||||||||||||||||99%]
```

For MIG jobs (Hopper+ with GPM):
```
DEBUG: duty_cycle not available, trying graphics_util_percent
DEBUG: query=avg_over_time((nvidia_gpu_graphics_util_percent{...})[...]) * 100
DEBUG: Using graphics_util_percent (compute/graphics active time)
GPU utilization  [|||||||||||||||||||||||||||||||||||||||||||||||99%]
```

For MIG jobs (older or no GPM):
```
DEBUG: duty_cycle not available, trying graphics_util_percent
DEBUG: graphics_util_percent not available, trying sm_util_percent
DEBUG: query=avg_over_time((nvidia_gpu_sm_util_percent{...})[...]) * 100
DEBUG: Using sm_util_percent (SM hardware utilization)
GPU utilization  [|||||||||||||||||||||||||||||||||||||||||||||||94%]
```

**Architecture Support Matrix**:

| GPU Type | Primary Metric | Fallback Metric | Status |
|----------|---------------|-----------------|--------|
| H100, A100, V100 | `duty_cycle` | - | ✅ Fully Supported |
| B200 (non-MIG) | `duty_cycle` | `graphics_util * 100` | ✅ Fully Supported |
| B200 MIG | - | `graphics_util * 100` | ✅ Fully Supported |
| H100 MIG / A100 MIG | - | `graphics_util * 100` or `sm_util * 100` | ✅ Fully Supported |

**Technical Notes**:
- **Preserves `nvidia_gpu_jobId` casing**: The metric name uses capital 'I' - this is correct and must not be changed
- **No Prometheus changes required**: Fix is applied to jobstats.py only
- **Backward compatible**: Regular GPU functionality unchanged
- **Automatic backups**: Original file preserved with timestamp
- **Works with hybrid clusters**: MIG and non-MIG nodes coexist seamlessly

**Alternative Prometheus-Side Solution**:
If you prefer not to modify jobstats code, see [alternate_mig_fix.md](alternate_mig_fix.md) for Prometheus recording rule approach.

## Workload Testing

### GPU Test with GPU Burn (not in this repo)

```bash
# On DGX
apt install cuda-toolkit-12-8
git clone https://github.com/wilicc/gpu-burn 
cd gpu-burn && make 

# On Slurm Submit Node
srun --gpus=1 gpu_burn 600 --nodelist <dgx> # 600 seconds
```

### cpu_load_test.py

**Purpose**: CPU load test script for jobstats validation that generates sustained CPU load.

**Use Case**:
- Generate realistic CPU utilization patterns for testing
- Validate jobstats CPU metrics collection
- Create multi-process CPU workloads
- Test jobstats under various CPU loads

**Usage**:
```bash
# Run with default settings (4 processes, 60 seconds)
python3 cpu_load_test.py

# Run with custom parameters
python3 cpu_load_test.py --processes 8 --duration 120 --intensity 80

# Dry-run mode to see what would be executed
python3 cpu_load_test.py --dry-run
```

**Features**:
- Multi-process CPU intensive tasks
- Configurable duration and intensity
- Dry-run mode for testing
- Real-time progress reporting
- Automatic cleanup on completion

## Misc

### convert_pdfs.sh

**Purpose**: Utility script for converting PDF files (legacy tool).

**Use Case**:
- Convert PDF documentation
- Batch PDF processing
- Documentation management

**Usage**:
```bash
# Convert single PDF
./convert_pdfs.sh input.pdf

# Convert multiple PDFs
./convert_pdfs.sh *.pdf
```

## Prerequisites

### System Requirements
- BCM (Bright Cluster Manager) system
- Slurm workload manager
- Python 3.6+
- Access to jobstats deployment

### Required Modules
- `slurm` - Slurm commands
- `python` - Python environment

### Required Packages
- `requests` - HTTP library (for validation)
- `multiprocessing` - Built-in Python module (for CPU tests)

### Permissions
- Ability to submit Slurm jobs
- Access to target partitions and nodes
- Read access to jobstats configuration

## Related Documentation

- [Main README](../../README.md)
- [Automation README](../README.md)
- [Troubleshooting Guide](../../Troubleshooting.md)
