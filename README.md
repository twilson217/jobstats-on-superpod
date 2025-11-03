# Jobstats on SuperPOD Deployment

This repository contains resources for deploying Princeton University's jobstats monitoring platform on NVIDIA DGX SuperPOD systems managed by Base Command Manager (BCM).

## Overview

Jobstats is a comprehensive job monitoring platform designed for CPU and GPU clusters using Slurm. It provides:
- Real-time job utilization metrics
- GPU and CPU performance monitoring (including MIG support)
- Automated efficiency reports
- Web-based dashboards via Grafana
- Command-line tools for job analysis

**MIG Support**: This deployment includes a fix for NVIDIA Multi-Instance GPU (MIG) technology that provides proper GPU utilization metrics for MIG instances. See [MIG Fix Documentation](automation/tools/README.md#fix_jobstats_mig_utilization_v3py) for details on both code-based and Prometheus-based fix options.

## Quickstart

### Getting Started with setup.sh

The `setup.sh` script is the recommended starting point for automated Jobstats on SuperPOD deployment. This interactive script:

- **Guides you through initial configuration** - Sets up `uv` package manager and generates `config.json`
- **Detects existing installations** - Checks for existing configurations and dependencies
- **Provides guided integration** - Optionally runs the guided setup script after configuration
- **Enables one-command deployment** - Complete setup from zero to deployed jobstats

**Usage:**
```bash
chmod +x setup.sh
./setup.sh
```

### Automated Deployment

For automated deployment with guided configuration, see the [Automation Guide](automation/README.md) for detailed information about running `automation/guided_setup.py` and other automated deployment options.

**Important Notes on Prometheus/Grafana Deployment:**

The `guided_setup.py` script can **deploy and configure NEW Prometheus and Grafana servers**, but it will **NOT automate configuration for existing Prometheus and Grafana servers**. 

- **For NEW servers**: The guided setup will handle installation and configuration automatically
- **For EXISTING servers**: Refer to the [How-To-Guide.md](How-To-Guide.md) for manual configuration steps

**SSH Key Requirements for New Server Deployment:**

For the guided setup to deploy to new Prometheus and Grafana servers, the BCM head node's SSH key must be configured:
- The BCM `/root/.ssh/id_ecdsa.pub` key must be added to `/root/.ssh/authorized_keys` on both the Prometheus and Grafana servers
- **If servers are BCM-managed**: SSH keys should be configured automatically by BCM
- **If servers are NOT BCM-managed**: You must set up SSH key access manually before running the guided setup

### Manual Deployment

For manual step-by-step deployment, see [How-To-Guide.md](How-To-Guide.md) for comprehensive instructions covering all aspects of the deployment process.

## Prerequisites

- DGX system with BCM management
- Slurm workload manager with cgroup support
- NVIDIA GPUs with nvidia-smi
- Go compiler (for building exporters)
- Python 3.6+ with requests and blessed libraries
- Git (for cloning repositories)
- Internet access (for downloading components)

## Dependencies

The following repositories are required for jobstats deployment:

### Required Repositories

| Component | Repository | Purpose | Used On |
|-----------|------------|---------|---------|
| **jobstats** | [PrincetonUniversity/jobstats](https://github.com/PrincetonUniversity/jobstats) | Main monitoring platform, prolog/epilog scripts, command-line tool | Slurm Controller, Login Nodes |
| **cgroup_exporter** | [plazonic/cgroup_exporter](https://github.com/plazonic/cgroup_exporter) | Collects CPU job metrics from cgroups | DGX Compute Nodes |
| **nvidia_gpu_prometheus_exporter** | [plazonic/nvidia_gpu_prometheus_exporter](https://github.com/plazonic/nvidia_gpu_prometheus_exporter) | Collects GPU metrics via nvidia-smi | DGX Compute Nodes |
| **node_exporter** | [prometheus/node_exporter](https://github.com/prometheus/node_exporter) | Collects system metrics | DGX Compute Nodes |

### Repository Distribution

**IMPORTANT**: The repositories need to be available on the systems where they will be used:

- **Slurm Controller Node**: Needs `jobstats` repository for prolog/epilog scripts
- **Login Nodes**: Needs `jobstats` repository for command-line tool
- **DGX Compute Nodes**: Needs all exporter repositories for building binaries
- **Prometheus Server**: No repositories needed (uses pre-built binaries)

**Repository Distribution**: Clone repositories on each system that needs them.

## Network Connectivity Requirements

### Required Network Connectivity

**Prometheus Server must be able to reach:**
- All DGX nodes on ports 9100, 9306, and 9445

**Login Nodes must be able to reach:**
- Prometheus server on port 9090

**Grafana Server must be able to reach:**
- Prometheus server on port 9090

**Users must be able to reach:**
- Grafana server on port 3000

### Port Configuration

| Service | Port | Description | Required On |
|---------|------|-------------|-------------|
| node_exporter | 9100 | System metrics | DGX nodes only |
| cgroup_exporter | 9306 | CPU job metrics | DGX nodes only |
| nvidia_gpu_prometheus_exporter | 9445 | GPU metrics | DGX nodes only |
| prometheus | 9090 | Metrics database | Prometheus server |
| grafana | 3000 | Web dashboard | Grafana server |

## Architecture

The jobstats platform consists of several components distributed across different systems in production:

### Production System Architecture

**BCM Head Node:**
- BCM cluster management (no jobstats components required)

**Slurm Controller Node:**
- Slurm controller and accounting database
- Slurm prolog/epilog scripts for job tracking

**Slurm Login Nodes:**
- jobstats command-line tool (where users run job analysis)
- Python dependencies for jobstats

**DGX Compute Nodes (workload nodes):**
- cgroup_exporter (collects CPU job metrics from /slurm cgroup filesystem)
- nvidia_gpu_prometheus_exporter (collects GPU metrics via nvidia-smi)
- prometheus node_exporter (collects system metrics)

**Prometheus Server:**
- Prometheus time-series database
- Scrapes metrics from all DGX nodes

**Grafana Server:**
- Web interface for visualization and dashboards

### Component Distribution

| Component | BCM Head | Slurm Controller | Login Nodes | DGX Nodes | Prometheus Server | Grafana Server |
|-----------|----------|------------------|-------------|-----------|-------------------|----------------|
| cgroup_exporter | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| nvidia_gpu_exporter | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| node_exporter | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| prometheus | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| grafana | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| jobstats command | 🔶 | 🔶 | ✅ | ❌ | ❌ | ❌ |
| slurm prolog/epilog | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ |
| slurmctld epilog | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| bcm role monitor | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |

**Legend:**
- ✅ Required
- 🔶 Optional
- ❌ Not needed

## Capacity Planning

Before deploying jobstats, use the **Prometheus Capacity Planner** to estimate storage requirements.

**Quick Start:**
```bash
# Copy the standalone script to your Slurm node
scp capacity-planning/prometheus_capacity_planner.py user@slurm-login:/tmp/

# Run analysis
ssh user@slurm-login
python3 /tmp/prometheus_capacity_planner.py --verbose
```

**Key Features:**
- Zero external dependencies (Python stdlib only)
- No Prometheus server required
- Analyzes cluster configuration and job history
- Provides storage estimates and hardware recommendations

**See**: [capacity-planning/README.md](capacity-planning/README.md) for complete documentation

## Troubleshooting

For troubleshooting information, see [Troubleshooting.md](Troubleshooting.md) which covers common issues and solutions for both basic deployment and visual features.

## Additional Resources

- [Princeton Jobstats Repository](https://github.com/PrincetonUniversity/jobstats)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Slurm Cgroup Configuration](https://slurm.schedmd.com/cgroups.html)

## License

This deployment guide and automation scripts are provided as-is for deploying Princeton University's jobstats platform. Please refer to the original jobstats repository for licensing information.
