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

### fix_jobstats_mig_utilization.py

**Purpose**: Fix for jobstats GPU utilization queries to support both regular GPUs and MIG (Multi-Instance GPU) instances.

**Problem**: 
- Regular GPUs expose `nvidia_gpu_duty_cycle` metric for utilization
- MIG instances do NOT expose `duty_cycle` (nvidia-smi reports N/A)
- MIG instances expose `nvidia_gpu_sm_util_percent` instead
- Original jobstats only queries `duty_cycle`, causing empty results for MIG jobs

**Solution**: 
- Adds fallback logic to try `duty_cycle` first (regular GPUs)
- Falls back to `sm_util_percent` if no data returned (MIG GPUs)
- Maintains backward compatibility with non-MIG nodes

**Use Case**:
- Fix "Value is unknown" errors for GPU utilization on MIG nodes
- Enable GPU utilization reporting for both MIG and non-MIG jobs
- Support hybrid clusters with both regular GPUs and MIG instances

**Usage**:
```bash
# Run the fix (must be run on login node where jobstats is installed)
python3 fix_jobstats_mig_utilization.py

# The script will:
# - Create a backup of the original file
# - Add a new method with fallback logic for GPU utilization
# - Replace the single metric query with smart fallback
# - Test the fix with a recent job
# - Restore from backup if something goes wrong
```

**Features**:
- Automatic metric fallback (duty_cycle → sm_util_percent)
- Maintains compatibility with regular GPU nodes
- Automatic backup creation with rollback
- Built-in testing to verify fix works
- Debug logging to show which metric was used

**Technical Details**:
- Adds `get_gpu_utilization_with_fallback()` method to jobstats.py
- Tries `nvidia_gpu_duty_cycle` first (backward compatible)
- If empty, tries `nvidia_gpu_sm_util_percent` (MIG support)
- Works for both MIG-enabled B200 nodes and regular H100/A100 nodes

**Alternative Approach**:
- See [alternate_mig_fix.md](alternate_mig_fix.md) for Prometheus-based solution
- No code changes required - uses Prometheus recording rules
- Both approaches can coexist

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
