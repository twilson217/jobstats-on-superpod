#!/usr/bin/env python3
"""
BCM Jobstats Guided Setup Script

This script provides an interactive, step-by-step guided deployment process
that follows the Princeton University jobstats documentation flow.

Usage:
    python guided_setup.py [--resume] [--config CONFIG_FILE]

Requirements:
    - Run from BCM head node with passwordless SSH access to all target systems
    - uv package manager for Python dependency management
    - cmsh access for BCM configuration verification
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Colors for output
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    PURPLE = '\033[0;35m'
    CYAN = '\033[0;36m'
    WHITE = '\033[1;37m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

class GuidedJobstatsSetup:
    """Interactive guided setup for BCM jobstats deployment."""
    
    def __init__(self, resume: bool = False, config_file: Optional[str] = None, dry_run: bool = False, non_interactive: bool = False):
        self.resume = resume
        self.config_file = config_file
        self.dry_run = dry_run
        self.non_interactive = non_interactive
        self.config = self._load_config()
        self.progress_file = Path("automation/logs/guided_setup_progress.json")
        self.progress = self._load_progress()
        self.working_dir = Path("/opt/jobstats-deployment")
        self.document_file = Path("automation/logs/guided_setup_document.md")
        self.document_content = []
        
        # Repository URLs
        self.repositories = {
            'jobstats': 'https://github.com/PrincetonUniversity/jobstats.git',
            'cgroup_exporter': 'https://github.com/plazonic/cgroup_exporter.git',
            'nvidia_gpu_prometheus_exporter': 'https://github.com/plazonic/nvidia_gpu_prometheus_exporter.git',
            'node_exporter': 'https://github.com/prometheus/node_exporter.git'
        }
        
        # Setup sections following Princeton documentation
        self.setup_sections = [
            {
                'id': 'overview',
                'title': 'Setup Overview',
                'description': 'Introduction to the jobstats platform setup process',
                'completed': False
            },
            {
                'id': 'cpu_job_stats',
                'title': 'CPU Job Statistics',
                'description': 'Configure Slurm for cgroup-based job accounting and install cgroup exporter',
                'completed': False
            },
            {
                'id': 'gpu_job_stats',
                'title': 'GPU Job Statistics',
                'description': 'Setup GPU monitoring and prolog/epilog scripts',
                'completed': False
            },
            {
                'id': 'node_stats',
                'title': 'Node Statistics',
                'description': 'Setup node_exporter on compute nodes',
                'completed': False
            },
            {
                'id': 'job_summaries',
                'title': 'Job Summaries',
                'description': 'Setup slurmctld epilog for job summary retention',
                'completed': False
            },
            {
                'id': 'prometheus',
                'title': 'Prometheus',
                'description': 'Setup Prometheus server and configuration',
                'completed': False
            },
            {
                'id': 'grafana',
                'title': 'Grafana',
                'description': 'Setup Grafana visualization interface',
                'completed': False
            },
            {
                'id': 'ood',
                'title': 'Open OnDemand Integration (Not Covered)',
                'description': 'Open OnDemand integration is not included in this setup',
                'completed': False
            },
            {
                'id': 'jobstats_command',
                'title': 'The jobstats Command',
                'description': 'Install and configure the jobstats command-line tool',
                'completed': False
            },
            {
                'id': 'bcm_role_monitor',
                'title': 'BCM Role Monitor',
                'description': 'Deploy BCM role monitoring service to DGX nodes',
                'completed': False
            },
            {
                'id': 'bcm_configurations',
                'title': 'Additional BCM Configurations',
                'description': 'BCM imaging workflow instructions',
                'completed': False
            }
        ]

    def _load_config(self) -> Dict:
        """Load configuration from file or use defaults."""
        default_config = {
            'cluster_name': 'slurm',
            'prometheus_server': 'prometheus-server',
            'grafana_server': 'grafana-server',
            'prometheus_port': 9090,
            'grafana_port': 3000,
            'node_exporter_port': 9100,
            'cgroup_exporter_port': 9306,
            'nvidia_gpu_exporter_port': 9445,
            'prometheus_retention_days': 365,
            'use_existing_prometheus': False,
            'use_existing_grafana': False,
            'deploy_bcm_role_monitor': True,
            'systems': {
                'slurm_controller': [],
                'login_nodes': [],
                'dgx_nodes': [],
                'prometheus_server': [],
                'grafana_server': []
            }
        }
        
        if self.config_file and Path(self.config_file).exists():
            with open(self.config_file, 'r') as f:
                user_config = json.load(f)
                default_config.update(user_config)
        
        return default_config

    def _load_progress(self) -> Dict:
        """Load progress tracking from file."""
        if self.progress_file.exists():
            with open(self.progress_file, 'r') as f:
                return json.load(f)
        return {
            'current_section': 0,
            'completed_sections': [],
            'setup_commands': []
        }

    def _save_progress(self):
        """Save current progress to file."""
        self.progress_file.parent.mkdir(exist_ok=True)
        with open(self.progress_file, 'w') as f:
            json.dump(self.progress, f, indent=2)

    def _add_to_document(self, content: str):
        """Add content to the document (only in dry-run mode)."""
        if self.dry_run:
            self.document_content.append(content)

    def _save_document(self):
        """Save the complete document to file."""
        self.document_file.parent.mkdir(exist_ok=True)
        with open(self.document_file, 'w') as f:
            f.write('\n'.join(self.document_content))

    def _init_document(self):
        """Initialize the document with header and metadata."""
        timestamp = subprocess.run(['date'], capture_output=True, text=True).stdout.strip()
        
        self._add_to_document("# BCM Jobstats Guided Setup Document")
        self._add_to_document("")
        self._add_to_document(f"**Generated on:** {timestamp}")
        self._add_to_document(f"**Mode:** {'Dry Run' if self.dry_run else 'Live Execution'}")
        self._add_to_document(f"**Configuration:** {self.config_file or 'Default'}")
        self._add_to_document("")
        self._add_to_document("This document provides a complete record of the jobstats deployment process.")
        self._add_to_document("It can be used as a reference for what was done or as a manual implementation guide.")
        self._add_to_document("")
        self._add_to_document("## Table of Contents")
        self._add_to_document("")
        
        for i, section in enumerate(self.setup_sections, 1):
            section_id = section['id'].replace('_', '-')
            self._add_to_document(f"{i}. [{section['title']}](#{section_id})")
        
        self._add_to_document("")
        self._add_to_document("---")
        self._add_to_document("")

    def _print_header(self, title: str, description: str = ""):
        """Print a formatted section header."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.WHITE}{title}{Colors.END}")
        print(f"{Colors.CYAN}{'='*80}{Colors.END}")
        if description:
            print(f"\n{Colors.BLUE}{description}{Colors.END}\n")

    def _print_command_summary(self, commands: List[Dict]):
        """Print a summary of commands that will be executed."""
        print(f"\n{Colors.BOLD}{Colors.YELLOW}Commands to be executed:{Colors.END}")
        print(f"{Colors.YELLOW}{'-'*50}{Colors.END}")
        
        for i, cmd in enumerate(commands, 1):
            host = cmd.get('host', 'localhost')
            command = cmd['command']
            description = cmd.get('description', '')
            
            print(f"\n{Colors.BOLD}{i}. {Colors.GREEN}{host}{Colors.END}")
            if description:
                print(f"   {Colors.BLUE}{description}{Colors.END}")
            else:
                print(f"   {Colors.WHITE}{command}{Colors.END}")

    def _confirm_execution(self, commands: List[Dict]) -> bool:
        """Ask user to confirm command execution."""
        print(f"\n{Colors.BOLD}{Colors.YELLOW}Ready to execute {len(commands)} command(s).{Colors.END}")
        return self._safe_input(f"{Colors.YELLOW}Do you want to proceed? (y/N): {Colors.END}")

    def _safe_input(self, prompt: str) -> bool:
        """Safely handle input, returning True if user confirms or in non-interactive mode."""
        try:
            if self.dry_run or self.non_interactive:
                print(f"{prompt} (auto-confirmed)")
                return True
            response = input(prompt).strip().lower()
            return response in ['y', 'yes']
        except EOFError:
            print(f"\n{Colors.BLUE}[NON-INTERACTIVE] Auto-proceeding...{Colors.END}")
            return True

    def _safe_continue(self, message: str = "Press Enter to continue to the next section..."):
        """Safely handle continue prompts."""
        try:
            if self.dry_run or self.non_interactive:
                print(f"\n{Colors.BLUE}[NON-INTERACTIVE] {message.replace('Press Enter to ', 'Auto-').replace('...', '')}{Colors.END}")
                return
            input(f"\n{Colors.YELLOW}{message}{Colors.END}")
        except EOFError:
            print(f"\n{Colors.BLUE}[NON-INTERACTIVE] Continuing to next section...{Colors.END}")

    def _run_command(self, command: str, host: Optional[str] = None, 
                    capture_output: bool = True) -> Tuple[int, str, str]:
        """Run a command locally or on a remote host."""
        try:
            if host:
                # Remote execution via SSH
                ssh_command = ['ssh', host, command]
                result = subprocess.run(ssh_command, capture_output=capture_output, 
                                      text=True, check=False)
            else:
                # Local execution using bash to support source command
                result = subprocess.run(['bash', '-c', command], capture_output=capture_output,
                                      text=True, check=False)
            
            return result.returncode, result.stdout or "", result.stderr or ""
        except Exception as e:
            logger.error(f"Error executing command '{command}' on {host or 'localhost'}: {e}")
            return 1, "", str(e)

    def _execute_commands(self, commands: List[Dict], section_title: str = "") -> bool:
        """Execute a list of commands with user confirmation."""
        if not commands:
            return True
        
        # Add commands to document
        if section_title:
            self._add_to_document(f"### Commands for {section_title}")
            self._add_to_document("")
        
        # Group commands by host
        commands_by_host = {}
        for cmd in commands:
            host = cmd.get('host', 'localhost')
            if host is None:
                host = 'localhost'  # Convert None to 'localhost' for display
            if host not in commands_by_host:
                commands_by_host[host] = []
            commands_by_host[host].append(cmd)
        
        # Add commands to document grouped by host
        for host, host_commands in commands_by_host.items():
            display_host = host if host != 'localhost' else 'BCM Headnode'
            self._add_to_document(f"#### Host: {display_host}")
            self._add_to_document("")
            self._add_to_document("```bash")
            for i, cmd in enumerate(host_commands, 1):
                description = cmd.get('description', '')
                command = cmd['command']
                if description:
                    # Remove hostname from description since it's already shown above
                    if host and host != 'localhost':
                        clean_description = description.replace(f" on {host}", "").replace(f" on {host.split('.')[0]}", "")
                    else:
                        clean_description = description
                    self._add_to_document(f"# Step {i} - {clean_description}")
                else:
                    self._add_to_document(f"# Step {i}")
                self._add_to_document("")
                self._add_to_document(command)
                self._add_to_document("")
            self._add_to_document("```")
            self._add_to_document("")
            self._add_to_document("---")
            self._add_to_document("")
        
        if self.dry_run:
            print(f"\n{Colors.BOLD}{Colors.YELLOW}[DRY RUN] Commands would be executed:{Colors.END}")
            self._print_command_summary(commands)
            print(f"\n{Colors.BLUE}Commands have been added to the document.{Colors.END}")
            return True
            
        self._print_command_summary(commands)
        
        if not self._confirm_execution(commands):
            print(f"{Colors.YELLOW}Commands skipped by user.{Colors.END}")
            return False
        
        print(f"\n{Colors.BOLD}{Colors.GREEN}Executing commands...{Colors.END}")
        
        success = True
        for cmd in commands:
            host = cmd.get('host')
            command = cmd['command']
            description = cmd.get('description', '')
            
            print(f"\n{Colors.BLUE}Executing: {description or command}{Colors.END}")
            if host:
                print(f"{Colors.CYAN}Host: {host}{Colors.END}")
            else:
                print(f"{Colors.CYAN}Host: BCM Headnode{Colors.END}")
            
            returncode, stdout, stderr = self._run_command(command, host)
            
            if returncode == 0:
                print(f"{Colors.GREEN}✓ Success{Colors.END}")
                if stdout.strip():
                    print(f"{Colors.WHITE}Output: {stdout.strip()}{Colors.END}")
            else:
                print(f"{Colors.RED}✗ Failed (exit code: {returncode}){Colors.END}")
                if stderr.strip():
                    print(f"{Colors.RED}Error: {stderr.strip()}{Colors.END}")
                success = False
        
        return success

    def section_overview(self):
        """Section 1: Setup Overview"""
        self._print_header(
            "1. Setup Overview",
            "Introduction to the jobstats platform setup process"
        )
        
        # Add to document
        self._add_to_document("## 1. Setup Overview")
        self._add_to_document("")
        self._add_to_document("### Description")
        self._add_to_document("")
        self._add_to_document("The jobstats platform provides comprehensive job monitoring for Slurm clusters.")
        self._add_to_document("This guided setup will walk you through each step of the deployment process.")
        self._add_to_document("")
        self._add_to_document("### Setup Process Overview")
        self._add_to_document("")
        self._add_to_document("1. Switch to cgroup-based job accounting")
        self._add_to_document("2. Setup exporters (cgroup, node, GPU) on compute nodes")
        self._add_to_document("3. Setup prolog/epilog scripts on GPU nodes")
        self._add_to_document("4. Setup Prometheus server and configuration")
        self._add_to_document("5. Setup slurmctld epilog for job summaries")
        self._add_to_document("6. Configure Grafana interface")
        self._add_to_document("7. Install jobstats command-line tool")
        self._add_to_document("")
        self._add_to_document("### Reference Documentation")
        self._add_to_document("")
        self._add_to_document("- Princeton University: https://princetonuniversity.github.io/jobstats/setup/overview/")
        self._add_to_document("")
        
        print(f"{Colors.BLUE}The jobstats platform provides comprehensive job monitoring for Slurm clusters.{Colors.END}")
        print(f"{Colors.BLUE}This guided setup will walk you through each step of the deployment process.{Colors.END}")
        
        print(f"\n{Colors.BOLD}{Colors.WHITE}Setup Process Overview:{Colors.END}")
        print(f"1. {Colors.CYAN}Switch to cgroup-based job accounting{Colors.END}")
        print(f"2. {Colors.CYAN}Setup exporters (cgroup, node, GPU) on compute nodes{Colors.END}")
        print(f"3. {Colors.CYAN}Setup prolog/epilog scripts on GPU nodes{Colors.END}")
        print(f"4. {Colors.CYAN}Setup Prometheus server and configuration{Colors.END}")
        print(f"5. {Colors.CYAN}Setup slurmctld epilog for job summaries{Colors.END}")
        print(f"6. {Colors.CYAN}Configure Grafana interface{Colors.END}")
        print(f"7. {Colors.CYAN}Install jobstats command-line tool{Colors.END}")
        
        print(f"\n{Colors.BOLD}{Colors.GREEN}Reference Documentation:{Colors.END}")
        print(f"• Princeton University: https://princetonuniversity.github.io/jobstats/setup/overview/")
        
        if not self.dry_run:
            self._safe_continue()
        else:
            print(f"\n{Colors.BLUE}[DRY RUN] Continuing to next section...{Colors.END}")
        
        return True

    def section_cpu_job_stats(self):
        """Section 2: CPU Job Statistics"""
        self._print_header(
            "2. CPU Job Statistics",
            "Configure Slurm for cgroup-based job accounting and install cgroup exporter"
        )
        
        # Add to document
        self._add_to_document("## 2. CPU Job Statistics")
        self._add_to_document("")
        self._add_to_document("### Description")
        self._add_to_document("")
        self._add_to_document("Configure Slurm for cgroup-based job accounting and install cgroup exporter")
        self._add_to_document("")
        self._add_to_document("This section configures Slurm settings for cgroup accounting and installs")
        self._add_to_document("the cgroup_exporter for collecting cgroup metrics.")
        self._add_to_document("")
        self._add_to_document("### What we'll do")
        self._add_to_document("")
        self._add_to_document("- 2a. Configure slurm.conf settings (outside autogenerated section)")
        self._add_to_document("- 2b. Configure cgroup constraints via BCM cmsh")
        self._add_to_document("- 2c. Deploy cgroup_exporter")
        self._add_to_document("")
        
        print(f"{Colors.BLUE}Configure Slurm for cgroup-based job accounting and install cgroup exporter{Colors.END}")
        print(f"{Colors.BLUE}This section configures Slurm settings for cgroup accounting and installs{Colors.END}")
        print(f"{Colors.BLUE}the cgroup_exporter for collecting cgroup metrics.{Colors.END}")
        
        print(f"\n{Colors.BOLD}{Colors.WHITE}What we'll do:{Colors.END}")
        print(f"• 2a. Configure slurm.conf settings (outside autogenerated section)")
        print(f"• 2b. Configure cgroup constraints via BCM cmsh")
        print(f"• 2c. Deploy cgroup_exporter")
        
        # Get slurm controller host
        slurm_controller = self.config['systems']['slurm_controller'][0] if self.config['systems']['slurm_controller'] else 'slurm-controller'
        
        # Get cluster name for BCM slurm.conf path
        cluster_name = self.config.get('cluster_name', 'slurm')
        slurm_conf_path = f"/cm/shared/apps/slurm/var/etc/{cluster_name}/slurm.conf"
        
        # Subsection 2a: Configure slurm.conf settings
        print(f"\n{Colors.BOLD}{Colors.CYAN}2a. Configure slurm.conf settings (outside autogenerated section){Colors.END}")
        self._add_to_document("### 2a. Configure slurm.conf settings (outside autogenerated section)")
        self._add_to_document("")
        self._add_to_document("#### Slurm Configuration for Cgroups")
        self._add_to_document("")
        self._add_to_document("We need to configure Slurm to use cgroup-based job accounting.")
        self._add_to_document("The script will update slurm.conf with the following three settings:")
        self._add_to_document("")
        self._add_to_document("- `JobAcctGatherType=jobacct_gather/cgroup`")
        self._add_to_document("- `ProctrackType=proctrack/cgroup`")
        self._add_to_document("- `TaskPlugin=affinity,cgroup`")
        self._add_to_document("")
        self._add_to_document("These settings will be placed outside the AUTOGENERATED SECTION.")
        self._add_to_document("")
        
        # Step 1: Configure slurm.conf for cgroup accounting
        print(f"\n{Colors.BOLD}{Colors.YELLOW}Step 1: Configuring slurm.conf for cgroup accounting{Colors.END}")
        
        slurm_conf_commands = [
            {
                'host': slurm_controller,
                'command': f'cp {slurm_conf_path} {slurm_conf_path}.backup',
                'description': 'Backup slurm.conf before modification'
            },
            {
                'host': slurm_controller,
                'command': f'''cat > /tmp/update_slurm_conf.py << 'EOF'
import re
import sys

# Read the file
with open('{slurm_conf_path}', 'r') as f:
    content = f.read()

# Settings to update
settings = {{
    'JobAcctGatherType': 'jobacct_gather/cgroup',
    'ProctrackType': 'proctrack/cgroup', 
    'TaskPlugin': 'affinity,cgroup'
}}

# Find the AUTOGENERATED SECTION
autogen_match = re.search(r'^# BEGIN AUTOGENERATED SECTION.*$', content, re.MULTILINE)
if not autogen_match:
    print('ERROR: AUTOGENERATED SECTION not found')
    sys.exit(1)

autogen_pos = autogen_match.start()

# Process each setting
for key, value in settings.items():
    # Look for existing setting
    pattern = rf'^{{re.escape(key)}}\\s*=.*$'
    match = re.search(pattern, content, re.MULTILINE)
    
    if match:
        # Replace existing setting
        old_line = match.group(0)
        new_line = f'{{key}}={{value}}'
        content = content.replace(old_line, new_line)
        print(f'Updated {{key}}={{value}}')
    else:
        # Insert new setting before AUTOGENERATED SECTION
        new_line = f'{{key}}={{value}}'
        content = content[:autogen_pos] + new_line + '\\n' + content[autogen_pos:]
        print(f'Added {{key}}={{value}}')

# Write the updated file
with open('{slurm_conf_path}', 'w') as f:
    f.write(content)

print('slurm.conf updated successfully')
EOF
python3 /tmp/update_slurm_conf.py''',
                'description': 'Update slurm.conf with JobAcctGatherType, ProctrackType, and TaskPlugin settings'
            }
        ]
        
        if not self._execute_commands(slurm_conf_commands, "Slurm Configuration"):
            print(f"\n{Colors.RED}✗ Failed to configure slurm.conf{Colors.END}")
            return False
        
        # Add BCM configuration info to document
        self._add_to_document("#### BCM Configuration Commands")
        self._add_to_document("")
        self._add_to_document("The following BCM commands configure the slurmctld epilog:")
        self._add_to_document("")
        self._add_to_document("```bash")
        self._add_to_document("cmsh -c \"wlm;use slurm;set epilogslurmctld /usr/local/sbin/slurmctldepilog.sh;commit\"")
        self._add_to_document("```")
        self._add_to_document("")
        self._add_to_document("**Note:** BCM automatically manages prolog/epilog settings in slurm.conf.")
        self._add_to_document("The scripts we installed will be automatically discovered and executed.")
        self._add_to_document("")
        
        # Subsection 2b: Configure cgroup constraints via BCM
        print(f"\n{Colors.BOLD}{Colors.CYAN}2b. Configure cgroup constraints via BCM{Colors.END}")
        self._add_to_document("### 2b. Configure cgroup constraints via BCM")
        self._add_to_document("")
        self._add_to_document("#### BCM Cgroup Configuration")
        self._add_to_document("")
        self._add_to_document("We need to configure three BCM settings to enable cgroup support:")
        self._add_to_document("")
        self._add_to_document("1. **ConstrainRAMSpace**: Enable memory constraints for jobs")
        self._add_to_document("2. **ConstrainCores**: Enable CPU core constraints for jobs") 
        self._add_to_document("3. **SelectTypeParameters**: Set to `CR_CPU_Memory` for cgroup resource tracking")
        self._add_to_document("")
        
        # Step 2: Configure cgroup constraints using cmsh
        print(f"\n{Colors.BOLD}{Colors.YELLOW}Step 2: Configuring cgroup constraints using BCM cmsh{Colors.END}")
        
        # cmsh commands should run locally on the BCM headnode (where this script is executing)
        cluster_name = self.config['cluster_name']
        
        cgroup_cmsh_commands = [
            {
                'host': None,  # Run locally on BCM headnode
                'command': f'/cm/local/apps/cmd/bin/cmsh -c "wlm;use {cluster_name};cgroups;set constrainramspace yes;commit"',
                'description': f'cmsh -c "wlm;use {cluster_name};cgroups;set constrainramspace yes;commit"'
            },
            {
                'host': None,  # Run locally on BCM headnode
                'command': f'/cm/local/apps/cmd/bin/cmsh -c "wlm;use {cluster_name};cgroups;set constraincores yes;commit"',
                'description': f'cmsh -c "wlm;use {cluster_name};cgroups;set constraincores yes;commit"'
            },
            {
                'host': None,  # Run locally on BCM headnode
                'command': f'/cm/local/apps/cmd/bin/cmsh -c "wlm;use {cluster_name};set selecttypeparameters CR_Core_Memory;commit"',
                'description': f'cmsh -c "wlm;use {cluster_name};set selecttypeparameters CR_Core_Memory;commit"'
            }
        ]
        
        if not self._execute_commands(cgroup_cmsh_commands, "BCM Cgroup Configuration"):
            print(f"\n{Colors.RED}✗ Failed to configure cgroup constraints via BCM{Colors.END}")
            return False
        
        # Subsection 2c: Deploy cgroup_exporter
        print(f"\n{Colors.BOLD}{Colors.CYAN}2c. Deploy cgroup_exporter{Colors.END}")
        self._add_to_document("### 2c. Deploy cgroup_exporter")
        self._add_to_document("")
        
        # Step 3: Install cgroup_exporter on compute nodes
        print(f"\n{Colors.BOLD}{Colors.YELLOW}Step 3: Installing cgroup_exporter on compute nodes{Colors.END}")
        
        cgroup_commands = []
        for dgx_node in self.config['systems']['dgx_nodes']:
            cgroup_commands.extend([
                {
                    'host': dgx_node,
                    'command': f'mkdir -p {self.working_dir}',
                    'description': f'Create working directory on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': 'apt update && apt install -y golang-go',
                    'description': f'Install Go compiler on {dgx_node}'
                },
            {
                'host': dgx_node,
                'command': f'cd {self.working_dir} && if [ -d cgroup_exporter ]; then cd cgroup_exporter && git pull; else git clone {self.repositories["cgroup_exporter"]}; fi',
                'description': f'Clone or update cgroup_exporter on {dgx_node}'
            },
                {
                    'host': dgx_node,
                    'command': f'cd {self.working_dir}/cgroup_exporter && go build',
                    'description': f'Build cgroup_exporter on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': 'systemctl stop cgroup_exporter || true && sleep 3 && timeout 30 bash -c "while pgrep -x cgroup_exporter > /dev/null 2>&1; do echo \"Waiting for cgroup_exporter process to stop...\"; sleep 2; done" || echo "Timeout reached, proceeding anyway"',
                    'description': f'Stop cgroup_exporter service on {dgx_node} (if running)'
                },
                {
                    'host': dgx_node,
                    'command': f'cp {self.working_dir}/cgroup_exporter/cgroup_exporter /usr/local/bin/ || (echo "Binary busy, trying with temp file..." && cp {self.working_dir}/cgroup_exporter/cgroup_exporter /usr/local/bin/cgroup_exporter.new && mv /usr/local/bin/cgroup_exporter.new /usr/local/bin/cgroup_exporter)',
                    'description': f'Install cgroup_exporter binary on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': 'useradd --system --no-create-home --shell /bin/false prometheus || true',
                    'description': f'Create prometheus user on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': f'''# Create systemd service for cgroup_exporter
cat > /etc/systemd/system/cgroup_exporter.service << 'EOF'
[Unit]
Description=Cgroup Exporter
After=network.target

[Service]
Type=simple
User=prometheus
ExecStart=/usr/local/bin/cgroup_exporter --web.listen-address=:{self.config['cgroup_exporter_port']} --config.paths /slurm --collect.fullslurm
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF''',
                    'description': f'Create cgroup_exporter systemd service on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': 'systemctl daemon-reload && systemctl enable cgroup_exporter && systemctl start cgroup_exporter',
                    'description': f'Start cgroup_exporter service on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': 'setcap cap_sys_ptrace=eip /usr/local/bin/cgroup_exporter',
                    'description': f'Set capabilities for cgroup_exporter to read procfs on {dgx_node}'
                }
            ])
        
        if not self._execute_commands(cgroup_commands, "Cgroup Exporter Installation"):
            print(f"\n{Colors.RED}✗ Failed to install cgroup_exporter{Colors.END}")
            return False
        
        # Step 4: Verify cgroup_exporter installation
        print(f"\n{Colors.BOLD}{Colors.YELLOW}Step 4: Verifying cgroup_exporter installation{Colors.END}")
        
        verify_commands = []
        for dgx_node in self.config['systems']['dgx_nodes']:
            verify_commands.extend([
                {
                    'host': dgx_node,
                    'command': 'systemctl is-active cgroup_exporter',
                    'description': f'Check cgroup_exporter service status on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': f'curl -s http://localhost:{self.config["cgroup_exporter_port"]}/metrics | head -5',
                    'description': f'Test cgroup_exporter metrics endpoint on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': f'netstat -tlnp | grep :{self.config["cgroup_exporter_port"]} || ss -tlnp | grep :{self.config["cgroup_exporter_port"]}',
                    'description': f'Verify cgroup_exporter is listening on port {self.config["cgroup_exporter_port"]} on {dgx_node}'
                }
            ])
        
        if not self._execute_commands(verify_commands, "Cgroup Exporter Verification"):
            print(f"\n{Colors.RED}✗ Failed to verify cgroup_exporter installation{Colors.END}")
            return False
        
        print(f"\n{Colors.BOLD}{Colors.GREEN}✓ Cgroup configuration and exporter installation completed{Colors.END}")
        print(f"{Colors.BOLD}{Colors.GREEN}✓ Cgroup_exporter verification completed{Colors.END}")
        
        print(f"\n{Colors.BOLD}{Colors.GREEN}✓ CPU Job Statistics section completed{Colors.END}")
        print(f"{Colors.BOLD}{Colors.GREEN}✓ Slurm cgroup settings configured{Colors.END}")
        print(f"{Colors.BOLD}{Colors.GREEN}✓ BCM cgroup constraints and select type parameters configured{Colors.END}")
        print(f"{Colors.BOLD}{Colors.GREEN}✓ cgroup_exporter installed and running{Colors.END}")
        
        print(f"\n{Colors.BOLD}{Colors.YELLOW}Next Steps:{Colors.END}")
        print(f"1. Restart Slurm services to apply cgroup configuration:")
        print(f"   • {Colors.WHITE}systemctl restart slurmctld{Colors.END}")
        print(f"   • {Colors.WHITE}systemctl restart slurmd{Colors.END}")
        print(f"2. Verify cgroup_exporter is running (already checked):")
        print(f"   • {Colors.WHITE}systemctl status cgroup_exporter{Colors.END}")
        print(f"3. Check metrics endpoint (already tested):")
        print(f"   • {Colors.WHITE}curl http://localhost:{self.config['cgroup_exporter_port']}/metrics{Colors.END}")
        
        if not self.dry_run:
            self._safe_continue()
        else:
            print(f"\n{Colors.BLUE}[DRY RUN] Continuing to next section...{Colors.END}")
        return True

    def section_gpu_job_stats(self):
        """Section 3: GPU Job Statistics"""
        self._print_header(
            "3. GPU Job Statistics",
            "Setup GPU monitoring and prolog/epilog scripts"
        )
        
        # Add to document
        self._add_to_document("## 3. GPU Job Statistics")
        self._add_to_document("")
        self._add_to_document("### Description")
        self._add_to_document("")
        self._add_to_document("This section sets up GPU monitoring and the necessary scripts")
        self._add_to_document("to track which GPUs are assigned to which jobs.")
        self._add_to_document("")
        self._add_to_document("### What we'll do")
        self._add_to_document("")
        self._add_to_document("- 3a. Deploy nvidia_gpu_prometheus_exporter")
        self._add_to_document("- 3b. GPU Job Ownership Helper (prolog/epilog scripts)")
        self._add_to_document("")
        
        print(f"{Colors.BLUE}This section sets up GPU monitoring and the necessary scripts{Colors.END}")
        print(f"{Colors.BLUE}to track which GPUs are assigned to which jobs.{Colors.END}")
        
        print(f"\n{Colors.BOLD}{Colors.WHITE}What we'll do:{Colors.END}")
        print(f"• 3a. Deploy nvidia_gpu_prometheus_exporter")
        print(f"• 3b. GPU Job Ownership Helper (prolog/epilog scripts)")
        
        # Subsection 3a: Deploy nvidia_gpu_prometheus_exporter
        print(f"\n{Colors.BOLD}{Colors.CYAN}3a. Deploy nvidia_gpu_prometheus_exporter{Colors.END}")
        self._add_to_document("### 3a. Deploy nvidia_gpu_prometheus_exporter")
        self._add_to_document("")
        
        # Commands for GPU exporter
        gpu_exporter_commands = []
        
        for dgx_node in self.config['systems']['dgx_nodes']:
            gpu_exporter_commands.extend([
                {
                    'host': dgx_node,
                    'command': f'mkdir -p {self.working_dir}',
                    'description': f'Create working directory on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': 'apt update && apt install -y golang-go',
                    'description': f'Install Go compiler on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': f'cd {self.working_dir} && if [ -d nvidia_gpu_prometheus_exporter ]; then cd nvidia_gpu_prometheus_exporter && git pull; else git clone {self.repositories["nvidia_gpu_prometheus_exporter"]}; fi',
                    'description': f'Clone or update NVIDIA GPU exporter on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': f'cd {self.working_dir}/nvidia_gpu_prometheus_exporter && go build',
                    'description': f'Build NVIDIA GPU exporter on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': 'systemctl stop nvidia_gpu_exporter || true && sleep 3 && timeout 30 bash -c "while pgrep -x nvidia_gpu_prometheus_exporter > /dev/null 2>&1; do echo \"Waiting for nvidia_gpu_prometheus_exporter process to stop...\"; sleep 2; done" || echo "Timeout reached, proceeding anyway"',
                    'description': f'Stop nvidia_gpu_exporter service on {dgx_node} (if running)'
                },
                {
                    'host': dgx_node,
                    'command': f'cp {self.working_dir}/nvidia_gpu_prometheus_exporter/nvidia_gpu_prometheus_exporter /usr/local/bin/ || (echo "Binary busy, trying with temp file..." && cp {self.working_dir}/nvidia_gpu_prometheus_exporter/nvidia_gpu_prometheus_exporter /usr/local/bin/nvidia_gpu_prometheus_exporter.new && mv /usr/local/bin/nvidia_gpu_prometheus_exporter.new /usr/local/bin/nvidia_gpu_prometheus_exporter)',
                    'description': f'Install NVIDIA GPU exporter binary on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': f'''# Create systemd service for NVIDIA GPU exporter
cat > /tmp/nvidia_gpu_exporter.service << 'EOF'
[Unit]
Description=NVIDIA GPU Exporter
After=network.target

[Service]
Type=simple
User=prometheus
ExecStart=/usr/local/bin/nvidia_gpu_prometheus_exporter --web.listen-address=:{self.config['nvidia_gpu_exporter_port']}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
cp /tmp/nvidia_gpu_exporter.service /etc/systemd/system/
rm /tmp/nvidia_gpu_exporter.service''',
                    'description': f'Create NVIDIA GPU exporter systemd service on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': 'systemctl daemon-reload && systemctl enable nvidia_gpu_exporter && systemctl start nvidia_gpu_exporter',
                    'description': f'Start NVIDIA GPU exporter service on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': 'setcap cap_sys_ptrace=eip /usr/local/bin/nvidia_gpu_prometheus_exporter',
                    'description': f'Set capabilities for nvidia_gpu_prometheus_exporter to read procfs on {dgx_node}'
                }
            ])
        
        if not self._execute_commands(gpu_exporter_commands, "NVIDIA GPU Exporter Installation"):
            print(f"\n{Colors.RED}✗ NVIDIA GPU exporter installation failed{Colors.END}")
            return False
        
        # Verify GPU exporter installation
        print(f"\n{Colors.BOLD}{Colors.YELLOW}Verifying GPU exporter installation{Colors.END}")
        
        verify_commands = []
        for dgx_node in self.config['systems']['dgx_nodes']:
            verify_commands.extend([
                {
                    'host': dgx_node,
                    'command': 'systemctl is-active nvidia_gpu_exporter',
                    'description': f'Check NVIDIA GPU exporter service status on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': f'curl -s http://localhost:{self.config["nvidia_gpu_exporter_port"]}/metrics | head -5',
                    'description': f'Test NVIDIA GPU exporter metrics endpoint on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': f'netstat -tlnp | grep :{self.config["nvidia_gpu_exporter_port"]} || ss -tlnp | grep :{self.config["nvidia_gpu_exporter_port"]}',
                    'description': f'Verify NVIDIA GPU exporter is listening on port {self.config["nvidia_gpu_exporter_port"]} on {dgx_node}'
                }
            ])
        
        if not self._execute_commands(verify_commands, "GPU Exporter Verification"):
            print(f"\n{Colors.RED}✗ Failed to verify GPU exporter installation{Colors.END}")
            return False
        
        print(f"\n{Colors.BOLD}{Colors.GREEN}✓ NVIDIA GPU exporter installation and verification completed{Colors.END}")
        
        # Subsection 3b: GPU Job Ownership Helper (prolog/epilog scripts)
        print(f"\n{Colors.BOLD}{Colors.CYAN}3b. GPU Job Ownership Helper (prolog/epilog scripts){Colors.END}")
        self._add_to_document("### 3b. GPU Job Ownership Helper (prolog/epilog scripts)")
        self._add_to_document("")
        self._add_to_document("#### BCM Script Discovery System")
        self._add_to_document("")
        self._add_to_document("BCM uses a generic prolog/epilog system that automatically calls all scripts")
        self._add_to_document("in specific directories. We'll install jobstats scripts using BCM's pattern:")
        self._add_to_document("")
        self._add_to_document("- **Script locations:** `/cm/local/apps/slurm/var/prologs/` and `/cm/local/apps/slurm/var/epilogs/`")
        self._add_to_document("- **Shared storage:** `/cm/shared/apps/slurm/var/cm/` (accessible to all nodes)")
        self._add_to_document("- **Symlink pattern:** Local symlinks point to shared storage scripts")
        self._add_to_document("- **Naming convention:** Use `60-` prefix to run after existing BCM scripts")
        self._add_to_document("")
        
        # Get slurm controller from config
        slurm_controller = self.config['systems']['slurm_controller'][0]
        
        # Step 1: Clone jobstats repository
        print(f"\n{Colors.BOLD}{Colors.YELLOW}Step 1: Cloning jobstats repository{Colors.END}")
        
        clone_commands = [
            {
                'host': slurm_controller,
                'command': 'mkdir -p /opt/jobstats-deployment',
                'description': 'Create working directory for jobstats deployment'
            },
            {
                'host': slurm_controller,
                'command': 'cd /opt/jobstats-deployment && if [ -d jobstats ]; then cd jobstats && git pull; else git clone https://github.com/PrincetonUniversity/jobstats.git; fi',
                'description': 'Clone or update jobstats repository'
            },
            {
                'host': slurm_controller,
                'command': 'cd /opt/jobstats-deployment && if [ -d jobstats-on-superpod ]; then cd jobstats-on-superpod && git pull; else git clone https://github.com/twilson217/jobstats-on-superpod.git; fi',
                'description': 'Clone or update jobstats-on-superpod repository (for custom scripts)'
            },
            {
                'host': slurm_controller,
                'command': 'cd /opt/jobstats-deployment/jobstats-on-superpod && git checkout mig-enhancements',
                'description': 'Switch to mig-enhancements branch'
            }
        ]
        
        if not self._execute_commands(clone_commands, "Repository Cloning"):
            print(f"\n{Colors.RED}✗ Failed to clone jobstats repository{Colors.END}")
            return False
        
        # Step 2: Install prolog/epilog scripts using BCM pattern
        print(f"\n{Colors.BOLD}{Colors.YELLOW}Step 2: Installing prolog/epilog scripts using BCM pattern{Colors.END}")
        
        install_commands = [
            {
                'host': slurm_controller,
                'command': 'mkdir -p /cm/shared/apps/slurm/var/cm',
                'description': 'Create shared storage directory for jobstats scripts'
            },
            {
                'host': slurm_controller,
                'command': 'cp /opt/jobstats-deployment/jobstats-on-superpod/automation/scripts/prolog-jobstats.sh /cm/shared/apps/slurm/var/cm/prolog-jobstats.sh',
                'description': 'Copy MIG-optimized prolog script to shared storage'
            },
            {
                'host': slurm_controller,
                'command': 'chmod +x /cm/shared/apps/slurm/var/cm/prolog-jobstats.sh',
                'description': 'Make prolog script executable'
            },
            {
                'host': slurm_controller,
                'command': 'cp /opt/jobstats-deployment/jobstats-on-superpod/automation/scripts/epilog-jobstats.sh /cm/shared/apps/slurm/var/cm/epilog-jobstats.sh',
                'description': 'Copy MIG-optimized epilog script to shared storage'
            },
            {
                'host': slurm_controller,
                'command': 'chmod +x /cm/shared/apps/slurm/var/cm/epilog-jobstats.sh',
                'description': 'Make epilog script executable'
            },
            {
                'host': slurm_controller,
                'command': 'mkdir -p /cm/local/apps/slurm/var/prologs',
                'description': 'Create local prolog directory'
            },
            {
                'host': slurm_controller,
                'command': 'mkdir -p /cm/local/apps/slurm/var/epilogs',
                'description': 'Create local epilog directory'
            },
            {
                'host': slurm_controller,
                'command': 'ln -sf /cm/shared/apps/slurm/var/cm/prolog-jobstats.sh /cm/local/apps/slurm/var/prologs/60-prolog-jobstats.sh',
                'description': 'Create prolog symlink (60- prefix for execution order)'
            },
            {
                'host': slurm_controller,
                'command': 'ln -sf /cm/shared/apps/slurm/var/cm/epilog-jobstats.sh /cm/local/apps/slurm/var/epilogs/60-epilog-jobstats.sh',
                'description': 'Create epilog symlink (60- prefix for execution order)'
            }
        ]
        
        # Add commands for BCM headnode and login nodes
        login_nodes = self.config['systems'].get('login_nodes', [])
        all_job_submission_nodes = [None] + login_nodes  # None = BCM headnode (localhost)
        
        for node in all_job_submission_nodes:
            if node is None:  # BCM headnode
                node_name = "BCM headnode"
                install_commands.extend([
                    {
                        'host': None,  # BCM headnode (localhost)
                        'command': 'mkdir -p /cm/local/apps/slurm/var/prologs /cm/local/apps/slurm/var/epilogs',
                        'description': f'Create prolog/epilog directories on {node_name}'
                    },
                    {
                        'host': None,  # BCM headnode (localhost)
                        'command': 'ln -sf /cm/shared/apps/slurm/var/cm/prolog-jobstats.sh /cm/local/apps/slurm/var/prologs/60-prolog-jobstats.sh',
                        'description': f'Create prolog symlink on {node_name}'
                    },
                    {
                        'host': None,  # BCM headnode (localhost)
                        'command': 'ln -sf /cm/shared/apps/slurm/var/cm/epilog-jobstats.sh /cm/local/apps/slurm/var/epilogs/60-epilog-jobstats.sh',
                        'description': f'Create epilog symlink on {node_name}'
                    }
                ])
            else:  # Login node
                install_commands.extend([
                    {
                        'host': node,
                        'command': 'mkdir -p /cm/local/apps/slurm/var/prologs /cm/local/apps/slurm/var/epilogs',
                        'description': f'Create prolog/epilog directories on {node}'
                    },
                    {
                        'host': node,
                        'command': 'ln -sf /cm/shared/apps/slurm/var/cm/prolog-jobstats.sh /cm/local/apps/slurm/var/prologs/60-prolog-jobstats.sh',
                        'description': f'Create prolog symlink on {node}'
                    },
                    {
                        'host': node,
                        'command': 'ln -sf /cm/shared/apps/slurm/var/cm/epilog-jobstats.sh /cm/local/apps/slurm/var/epilogs/60-epilog-jobstats.sh',
                        'description': f'Create epilog symlink on {node}'
                    }
                ])
        
        if not self._execute_commands(install_commands, "BCM Script Installation"):
            print(f"\n{Colors.RED}✗ Failed to install BCM scripts{Colors.END}")
            return False
        
        print(f"\n{Colors.BOLD}{Colors.GREEN}✓ GPU Job Ownership Helper section completed{Colors.END}")
        print(f"{Colors.BOLD}{Colors.GREEN}✓ Prolog/epilog scripts installed using BCM method{Colors.END}")
        
        if not self.dry_run:
            self._safe_continue()
        else:
            print(f"\n{Colors.BLUE}[DRY RUN] Continuing to next section...{Colors.END}")
        return True

    def section_node_stats(self):
        """Section 4: Node Statistics"""
        self._print_header(
            "4. Node Statistics",
            "Setup node_exporter on compute nodes"
        )
        
        # Add to document
        self._add_to_document("## 4. Node Statistics")
        self._add_to_document("")
        self._add_to_document("### Description")
        self._add_to_document("")
        self._add_to_document("This section installs the Prometheus node_exporter")
        self._add_to_document("on all compute nodes to collect system metrics.")
        self._add_to_document("")
        self._add_to_document("### What we'll do")
        self._add_to_document("")
        self._add_to_document("- Clone node_exporter repository")
        self._add_to_document("- Build and install node_exporter")
        self._add_to_document("- Create systemd service for node_exporter")
        self._add_to_document("- Start and enable service")
        self._add_to_document("- Verify node_exporter is running and collecting metrics")
        self._add_to_document("")
        
        print(f"{Colors.BLUE}This section installs the Prometheus node_exporter{Colors.END}")
        print(f"{Colors.BLUE}on all compute nodes to collect system metrics.{Colors.END}")
        
        print(f"\n{Colors.BOLD}{Colors.WHITE}What we'll do:{Colors.END}")
        print(f"• Clone node_exporter repository")
        print(f"• Build and install node_exporter")
        print(f"• Create systemd service for node_exporter")
        print(f"• Start and enable service")
        print(f"• Verify node_exporter is running and collecting metrics")
        
        # Commands for all compute nodes
        node_commands = []
        
        for dgx_node in self.config['systems']['dgx_nodes']:
            node_commands.extend([
                {
                    'host': dgx_node,
                    'command': f'cd {self.working_dir} && if [ -d node_exporter ]; then cd node_exporter && git pull; else git clone {self.repositories["node_exporter"]}; fi',
                    'description': f'Clone or update node_exporter on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': f'cd {self.working_dir}/node_exporter && make build',
                    'description': f'Build node_exporter on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': 'systemctl stop node_exporter || true && sleep 3 && timeout 30 bash -c "while pgrep -x node_exporter > /dev/null 2>&1; do echo \"Waiting for node_exporter process to stop...\"; sleep 2; done" || echo "Timeout reached, proceeding anyway"',
                    'description': f'Stop node_exporter service on {dgx_node} (if running)'
                },
                {
                    'host': dgx_node,
                    'command': f'cp {self.working_dir}/node_exporter/node_exporter /usr/local/bin/ || (echo "Binary busy, trying with temp file..." && cp {self.working_dir}/node_exporter/node_exporter /usr/local/bin/node_exporter.new && mv /usr/local/bin/node_exporter.new /usr/local/bin/node_exporter)',
                    'description': f'Install node_exporter binary on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': 'useradd --system --no-create-home --shell /bin/false prometheus || true',
                    'description': f'Create prometheus user on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': f'''# Create systemd service for node_exporter
cat > /etc/systemd/system/node_exporter.service << 'EOF'
[Unit]
Description=Node Exporter
After=network.target

[Service]
Type=simple
User=prometheus
ExecStart=/usr/local/bin/node_exporter --web.listen-address=:{self.config['node_exporter_port']}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF''',
                    'description': f'Create node_exporter systemd service on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': 'systemctl daemon-reload && systemctl enable node_exporter && systemctl start node_exporter',
                    'description': f'Start node_exporter service on {dgx_node}'
                }
            ])
        
        if not self._execute_commands(node_commands, "Node Exporter Installation"):
            print(f"\n{Colors.RED}✗ Node exporter installation failed{Colors.END}")
            return False
        
        # Step 2: Verify node_exporter installation
        print(f"\n{Colors.BOLD}{Colors.YELLOW}Step 2: Verifying node_exporter installation{Colors.END}")
        
        verify_commands = []
        for dgx_node in self.config['systems']['dgx_nodes']:
            verify_commands.extend([
                {
                    'host': dgx_node,
                    'command': 'systemctl is-active node_exporter',
                    'description': f'Check node_exporter service status on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': f'curl -s http://localhost:{self.config["node_exporter_port"]}/metrics | head -5',
                    'description': f'Test node_exporter metrics endpoint on {dgx_node}'
                },
                {
                    'host': dgx_node,
                    'command': f'netstat -tlnp | grep :{self.config["node_exporter_port"]} || ss -tlnp | grep :{self.config["node_exporter_port"]}',
                    'description': f'Verify node_exporter is listening on port {self.config["node_exporter_port"]} on {dgx_node}'
                }
            ])
        
        if not self._execute_commands(verify_commands, "Node Exporter Verification"):
            print(f"\n{Colors.RED}✗ Failed to verify node_exporter installation{Colors.END}")
            return False
        
        print(f"\n{Colors.BOLD}{Colors.GREEN}✓ Node exporter installation completed{Colors.END}")
        print(f"{Colors.BOLD}{Colors.GREEN}✓ Node exporter verification completed{Colors.END}")
        
        if not self.dry_run:
            self._safe_continue()
        else:
            print(f"\n{Colors.BLUE}[DRY RUN] Continuing to next section...{Colors.END}")
        return True

    def section_job_summaries(self):
        """Section 5: Job Summaries"""
        self._print_header(
            "5. Job Summaries",
            "Setup slurmctld epilog for job summary retention"
        )
        
        # Add to document
        self._add_to_document("## 5. Job Summaries")
        self._add_to_document("")
        self._add_to_document("### Description")
        self._add_to_document("")
        self._add_to_document("This section sets up the slurmctld epilog script")
        self._add_to_document("to generate and store job summaries in the Slurm database.")
        self._add_to_document("")
        self._add_to_document("### What we'll do")
        self._add_to_document("")
        self._add_to_document("- Install slurmctld epilog script")
        self._add_to_document("- Configure BCM epilogslurmctld setting")
        self._add_to_document("")
        
        print(f"{Colors.BLUE}This section sets up the slurmctld epilog script{Colors.END}")
        print(f"{Colors.BLUE}to generate and store job summaries in the Slurm database.{Colors.END}")
        
        print(f"\n{Colors.BOLD}{Colors.WHITE}What we'll do:{Colors.END}")
        print(f"• Install slurmctld epilog script")
        print(f"• Configure BCM epilogslurmctld setting")
        
        # Get slurm controller from config
        slurm_controller = self.config['systems']['slurm_controller'][0]
        
        # Step 1: Clone jobstats-on-superpod repository for custom slurmctld epilog
        print(f"\n{Colors.BOLD}{Colors.YELLOW}Step 1: Cloning jobstats-on-superpod repository{Colors.END}")
        
        clone_commands = [
            {
                'host': slurm_controller,
                'command': 'mkdir -p /opt/jobstats-deployment',
                'description': 'Create working directory for jobstats deployment'
            },
            {
                'host': slurm_controller,
                'command': 'cd /opt/jobstats-deployment && if [ -d jobstats-on-superpod ]; then cd jobstats-on-superpod && git pull; else git clone https://github.com/twilson217/jobstats-on-superpod.git; fi',
                'description': 'Clone or update jobstats-on-superpod repository (for custom slurmctld epilog)'
            },
            {
                'host': slurm_controller,
                'command': 'cd /opt/jobstats-deployment/jobstats-on-superpod && git checkout mig-enhancements',
                'description': 'Switch to mig-enhancements branch'
            }
        ]
        
        if not self._execute_commands(clone_commands, "Repository Cloning"):
            print(f"\n{Colors.RED}✗ Failed to clone jobstats-on-superpod repository{Colors.END}")
            return False
        
        # Step 2: Install BCM-optimized slurmctld epilog script
        print(f"\n{Colors.BOLD}{Colors.YELLOW}Step 2: Installing BCM-optimized slurmctld epilog script{Colors.END}")
        
        install_commands = [
            {
                'host': slurm_controller,
                'command': 'cp /opt/jobstats-deployment/jobstats-on-superpod/automation/scripts/slurmctldepilog-jobstats.sh /usr/local/sbin/slurmctldepilog.sh',
                'description': 'Copy BCM-optimized slurmctld epilog script'
            },
            {
                'host': slurm_controller,
                'command': 'chmod +x /usr/local/sbin/slurmctldepilog.sh',
                'description': 'Make slurmctld epilog script executable'
            }
        ]
        
        if not self._execute_commands(install_commands, "Slurmctld Epilog Installation"):
            print(f"\n{Colors.RED}✗ Failed to install slurmctld epilog script{Colors.END}")
            return False
        
        # Step 3: Configure BCM epilogslurmctld setting
        print(f"\n{Colors.BOLD}{Colors.YELLOW}Step 3: Configuring BCM epilogslurmctld setting{Colors.END}")
        
        bcm_commands = [
            {
                'host': None,  # Run locally on BCM headnode
                'command': '/cm/local/apps/cmd/bin/cmsh -c "wlm;use slurm;set epilogslurmctld /usr/local/sbin/slurmctldepilog.sh;commit"',
                'description': 'cmsh -c "wlm;use slurm;set epilogslurmctld /usr/local/sbin/slurmctldepilog.sh;commit"'
            }
        ]
        
        if not self._execute_commands(bcm_commands, "BCM Configuration"):
            print(f"\n{Colors.RED}✗ Failed to configure BCM settings{Colors.END}")
            return False
        
        print(f"\n{Colors.BOLD}{Colors.GREEN}✓ Job Summaries section completed{Colors.END}")
        print(f"{Colors.BOLD}{Colors.GREEN}✓ Slurmctld epilog script installed{Colors.END}")
        print(f"{Colors.BOLD}{Colors.GREEN}✓ BCM epilogslurmctld setting configured{Colors.END}")
        
        if not self.dry_run:
            self._safe_continue()
        else:
            print(f"\n{Colors.BLUE}[DRY RUN] Continuing to next section...{Colors.END}")
        return True

    def section_prometheus(self):
        """Section 6: Prometheus"""
        self._print_header(
            "6. Prometheus",
            "Setup Prometheus server and configuration"
        )
        
        # Add to document
        self._add_to_document("## 6. Prometheus")
        self._add_to_document("")
        self._add_to_document("### Description")
        self._add_to_document("")
        self._add_to_document("This section sets up the Prometheus server")
        self._add_to_document("to collect and store metrics from all exporters.")
        self._add_to_document("")
        self._add_to_document("**MIG Support:** This deployment includes a recording rule that creates")
        self._add_to_document("`nvidia_gpu_duty_cycle` metrics for MIG instances using their")
        self._add_to_document("`nvidia_gpu_graphics_util_percent` metric (scaled by 100), ensuring")
        self._add_to_document("jobstats works out-of-the-box with MIG-enabled GPUs.")
        self._add_to_document("")
        self._add_to_document("### What we'll do")
        self._add_to_document("")
        self._add_to_document("- Download and install Prometheus")
        self._add_to_document("- Create Prometheus configuration")
        self._add_to_document("- Create MIG compatibility recording rule for GPU metrics")
        self._add_to_document("- Create systemd service for Prometheus")
        self._add_to_document("- Start and enable Prometheus service")
        self._add_to_document("")
        
        print(f"{Colors.BLUE}This section sets up the Prometheus time series database{Colors.END}")
        print(f"{Colors.BLUE}to collect and store metrics from all exporters.{Colors.END}")
        print(f"{Colors.BLUE}Includes MIG GPU support via recording rules.{Colors.END}")
        
        print(f"\n{Colors.BOLD}{Colors.WHITE}What we'll do:{Colors.END}")
        print(f"• Download and install Prometheus")
        print(f"• Create Prometheus configuration")
        print(f"• Create MIG compatibility recording rule for GPU metrics")
        print(f"• Setup systemd service")
        print(f"• Start Prometheus server")
        
        # Commands for Prometheus server
        prometheus_commands = [
            {
                'host': self.config['prometheus_server'],
                'command': 'wget https://github.com/prometheus/prometheus/releases/download/v2.45.0/prometheus-2.45.0.linux-amd64.tar.gz',
                'description': 'Download Prometheus'
            },
            {
                'host': self.config['prometheus_server'],
                'command': 'tar xzf prometheus-2.45.0.linux-amd64.tar.gz',
                'description': 'Extract Prometheus'
            },
            {
                'host': self.config['prometheus_server'],
                'command': 'systemctl stop prometheus || true && sleep 2',
                'description': 'Stop Prometheus service (if running)'
            },
            {
                'host': self.config['prometheus_server'],
                'command': 'cp prometheus-2.45.0.linux-amd64/prometheus /usr/local/bin/',
                'description': 'Install Prometheus binary'
            },
            {
                'host': self.config['prometheus_server'],
                'command': 'mkdir -p /etc/prometheus /var/lib/prometheus',
                'description': 'Create Prometheus directories'
            },
            {
                'host': self.config['prometheus_server'],
                'command': 'useradd --system --no-create-home --shell /bin/false prometheus || true',
                'description': 'Create prometheus user'
            },
            {
                'host': self.config['prometheus_server'],
                'command': 'chown prometheus:prometheus /var/lib/prometheus',
                'description': 'Set ownership of data directory'
            }
        ]
        
        if self._execute_commands(prometheus_commands):
            print(f"\n{Colors.GREEN}✓ Prometheus installation completed{Colors.END}")
        else:
            print(f"\n{Colors.RED}✗ Prometheus installation failed{Colors.END}")
            return False
        
        # Create Prometheus configuration
        self._create_prometheus_config()
        
        # Create and start Prometheus systemd service
        prometheus_service_commands = [
            {
                'host': self.config['prometheus_server'],
                'command': '''# Create systemd service for Prometheus
cat > /tmp/prometheus.service << 'EOF'
[Unit]
Description=Prometheus
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=prometheus
Group=prometheus
ExecStart=/usr/local/bin/prometheus \\
    --config.file=/etc/prometheus/prometheus.yml \\
    --storage.tsdb.path=/var/lib/prometheus \\
    --web.console.templates=/etc/prometheus/consoles \\
    --web.console.libraries=/etc/prometheus/console_libraries \\
    --web.listen-address=0.0.0.0:9090 \\
    --web.enable-lifecycle

[Install]
WantedBy=multi-user.target
EOF
cp /tmp/prometheus.service /etc/systemd/system/
rm /tmp/prometheus.service''',
                'description': 'Create Prometheus systemd service'
            },
            {
                'host': self.config['prometheus_server'],
                'command': 'systemctl daemon-reload && systemctl enable prometheus && systemctl start prometheus',
                'description': 'Start Prometheus service'
            }
        ]
        
        if self._execute_commands(prometheus_service_commands):
            print(f"\n{Colors.GREEN}✓ Prometheus service started{Colors.END}")
        else:
            print(f"\n{Colors.RED}✗ Failed to start Prometheus service{Colors.END}")
            return False
        
        if not self.dry_run:
            self._safe_continue()
        else:
            print(f"\n{Colors.BLUE}[DRY RUN] Continuing to next section...{Colors.END}")
        return True

    def _create_prometheus_config(self):
        """Create Prometheus configuration file."""
        print(f"\n{Colors.BOLD}{Colors.YELLOW}Creating Prometheus configuration...{Colors.END}")
        
        # Build targets list for each exporter
        node_targets = []
        cgroup_targets = []
        gpu_targets = []
        
        for node in self.config['systems']['dgx_nodes']:
            node_targets.append(f"        - '{node}:{self.config['node_exporter_port']}'")
            cgroup_targets.append(f"        - '{node}:{self.config['cgroup_exporter_port']}'")
            gpu_targets.append(f"        - '{node}:{self.config['nvidia_gpu_exporter_port']}'")
        
        node_targets_yaml = '\n'.join(node_targets)
        cgroup_targets_yaml = '\n'.join(cgroup_targets)
        gpu_targets_yaml = '\n'.join(gpu_targets)
        
        prometheus_config = f"""global:
  scrape_interval: 30s
  evaluation_interval: 30s
  external_labels:
    monitor: 'jobstats-{self.config['cluster_name']}'

# Load recording rules (includes MIG compatibility fix)
rule_files:
  - /etc/prometheus/rules/*.yml

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:{self.config['prometheus_port']}']

  - job_name: 'node_exporter'
    static_configs:
      - targets: 
{node_targets_yaml}
    metric_relabel_configs:
      - target_label: cluster
        replacement: {self.config['cluster_name']}
      - source_labels: [__name__]
        regex: '^go_.*'
        action: drop

  - job_name: 'cgroup_exporter'
    static_configs:
      - targets: 
{cgroup_targets_yaml}
    metric_relabel_configs:
      - target_label: cluster
        replacement: {self.config['cluster_name']}

  - job_name: 'nvidia_gpu_exporter'
    static_configs:
      - targets: 
{gpu_targets_yaml}
    metric_relabel_configs:
      - target_label: cluster
        replacement: {self.config['cluster_name']}
"""
        
        if self.dry_run:
            # In dry-run mode, just add the configuration content to the document
            self._add_to_document("")
            self._add_to_document("### Prometheus Configuration")
            self._add_to_document("")
            self._add_to_document("```yaml")
            self._add_to_document(prometheus_config)
            self._add_to_document("```")
            self._add_to_document("")
            print(f"{Colors.GREEN}✓ Prometheus configuration created{Colors.END}")
            return True
        
        # Create MIG recording rule (for MIG GPU utilization support)
        mig_recording_rule = """groups:
  - name: jobstats_mig_compatibility
    interval: 30s
    rules:
      # Create duty_cycle metric for MIG instances using graphics_util_percent * 100
      # Note: GPM metrics are stored in 0-1 range, multiply by 100 to match duty_cycle scale (0-100)
      - record: nvidia_gpu_duty_cycle
        expr: nvidia_gpu_graphics_util_percent{uuid=~"MIG-.*"} * 100
        labels:
          source: "mig_compat_rule"
"""
        
        # Create config file and recording rules directly on remote server
        config_commands = [
            {
                'host': self.config['prometheus_server'],
                'command': 'mkdir -p /etc/prometheus/rules',
                'description': 'Create Prometheus rules directory'
            },
            {
                'host': self.config['prometheus_server'],
                'command': f'''cat > /etc/prometheus/rules/jobstats_mig_compat.yml << 'EOF'
{mig_recording_rule}
EOF''',
                'description': 'Install MIG compatibility recording rule'
            },
            {
                'host': self.config['prometheus_server'],
                'command': f'''cat > /etc/prometheus/prometheus.yml << 'EOF'
{prometheus_config}
EOF''',
                'description': 'Install Prometheus configuration'
            },
            {
                'host': self.config['prometheus_server'],
                'command': 'chown -R prometheus:prometheus /etc/prometheus',
                'description': 'Set configuration ownership'
            }
        ]
        
        if self._execute_commands(config_commands):
            print(f"{Colors.GREEN}✓ Prometheus configuration created{Colors.END}")
            return True
        else:
            print(f"{Colors.RED}✗ Prometheus configuration failed{Colors.END}")
            return False

    def section_grafana(self):
        """Section 7: Grafana"""
        self._print_header(
            "7. Grafana",
            "Setup Grafana visualization interface"
        )
        
        # Add to document
        self._add_to_document("## 7. Grafana")
        self._add_to_document("")
        self._add_to_document("### Description")
        self._add_to_document("")
        self._add_to_document("This section sets up Grafana for visualizing")
        self._add_to_document("the collected metrics and creating dashboards.")
        self._add_to_document("")
        self._add_to_document("### What we'll do")
        self._add_to_document("")
        self._add_to_document("- Install Grafana")
        self._add_to_document("- Start and enable Grafana service")
        if not self.config.get('use_existing_grafana', False) and not self.config.get('use_existing_prometheus', False):
            self._add_to_document("- Automatically configure Prometheus data source")
            self._add_to_document("- Automatically change default admin password")
        else:
            self._add_to_document("- Manual configuration required (existing Grafana detected)")
        self._add_to_document("")
        
        print(f"{Colors.BLUE}This section sets up Grafana for visualizing{Colors.END}")
        print(f"{Colors.BLUE}the collected metrics and creating dashboards.{Colors.END}")
        print(f"{Colors.YELLOW}Note: Package repository updates may take several minutes.{Colors.END}")
        
        print(f"\n{Colors.BOLD}{Colors.WHITE}What we'll do:{Colors.END}")
        print(f"• Install Grafana")
        print(f"• Start Grafana service")
        if not self.config.get('use_existing_grafana', False) and not self.config.get('use_existing_prometheus', False):
            print(f"• Automatically configure Prometheus data source")
            print(f"• Automatically change default admin password")
        else:
            print(f"• Manual configuration required (existing Grafana detected)")
        
        # Commands for Grafana server
        grafana_commands = [
            {
                'host': self.config['grafana_server'],
                'command': 'wget -q -O - https://packages.grafana.com/gpg.key | apt-key add -',
                'description': 'Add Grafana repository key'
            },
            {
                'host': self.config['grafana_server'],
                'command': 'echo "deb https://packages.grafana.com/oss/deb stable main" > /etc/apt/sources.list.d/grafana.list',
                'description': 'Add Grafana repository'
            },
            {
                'host': self.config['grafana_server'],
                'command': 'apt update',
                'description': 'Update package lists'
            },
            {
                'host': self.config['grafana_server'],
                'command': 'DEBIAN_FRONTEND=noninteractive apt install -y grafana',
                'description': 'Install Grafana'
            }
        ]
        
        if self._execute_commands(grafana_commands):
            print(f"\n{Colors.GREEN}✓ Grafana installation completed{Colors.END}")
        else:
            print(f"\n{Colors.RED}✗ Grafana installation failed{Colors.END}")
            return False
        
        # Start and enable Grafana service
        grafana_service_commands = [
            {
                'host': self.config['grafana_server'],
                'command': 'systemctl daemon-reload && systemctl enable grafana-server && systemctl start grafana-server',
                'description': 'Start Grafana service'
            }
        ]
        
        if self._execute_commands(grafana_service_commands):
            print(f"\n{Colors.GREEN}✓ Grafana service started{Colors.END}")
        else:
            print(f"\n{Colors.RED}✗ Failed to start Grafana service{Colors.END}")
            return False
        
        # Automated Grafana configuration (only for fresh installations)
        if not self.config.get('use_existing_grafana', False) and not self.config.get('use_existing_prometheus', False):
            # Add configuration commands to dry-run documentation
            self._add_to_document("")
            self._add_to_document("### Automated Configuration")
            self._add_to_document("")
            print(f"\n{Colors.BOLD}{Colors.CYAN}Configuring Grafana automatically...{Colors.END}")
            
            grafana_config_commands = [
                {
                    'host': self.config['grafana_server'],
                    'command': f'sleep 15',  # Wait for Grafana to fully start
                    'description': 'Wait for Grafana to start'
                },
                {
                    'host': self.config['grafana_server'],
                    'command': f'''curl -X POST -H "Content-Type: application/json" -d '{{"name":"Prometheus","type":"prometheus","url":"http://{self.config["prometheus_server"]}:{self.config.get("prometheus_port", 9090)}","access":"proxy","isDefault":true}}' http://admin:admin@localhost:{self.config.get("grafana_port", 3000)}/api/datasources''',
                    'description': 'Add Prometheus data source'
                },
                {
                    'host': self.config['grafana_server'],
                    'command': f'''curl -X PUT -H "Content-Type: application/json" -d '{{"oldPassword":"admin","newPassword":"jobstats123","confirmNew":"jobstats123"}}' http://admin:admin@localhost:{self.config.get("grafana_port", 3000)}/api/user/password''',
                    'description': 'Change default admin password'
                }
            ]
            
            if self._execute_commands(grafana_config_commands):
                print(f"\n{Colors.GREEN}✓ Grafana configuration completed{Colors.END}")
                print(f"\n{Colors.BOLD}{Colors.WHITE}Grafana Access Information:{Colors.END}")
                print(f"• URL: http://{self.config['grafana_server']}:{self.config.get('grafana_port', 3000)}")
                print(f"• Username: admin")
                print(f"• Password: jobstats123")
                print(f"• Prometheus data source: Automatically configured")
            else:
                print(f"\n{Colors.YELLOW}⚠ Grafana configuration partially failed - manual setup may be required{Colors.END}")
                print(f"\n{Colors.BOLD}{Colors.YELLOW}Manual Configuration Required:{Colors.END}")
                print(f"1. Access Grafana at http://{self.config['grafana_server']}:{self.config.get('grafana_port', 3000)}")
                print(f"2. Login with admin/admin (change password)")
                print(f"3. Add Prometheus data source: http://{self.config['prometheus_server']}:{self.config.get('prometheus_port', 9090)}")
        else:
            # Add manual configuration note to dry-run documentation
            self._add_to_document("")
            self._add_to_document("### Manual Configuration Required")
            self._add_to_document("")
            self._add_to_document("**Note:** Existing Grafana detected - automated configuration skipped")
            self._add_to_document("")
            self._add_to_document("1. Access Grafana at http://{self.config['grafana_server']}:{self.config.get('grafana_port', 3000)}")
            self._add_to_document("2. Login with your existing credentials")
            self._add_to_document("3. Add Prometheus data source: http://{self.config['prometheus_server']}:{self.config.get('prometheus_port', 9090)}")
            self._add_to_document("4. Import jobstats dashboard from .jobstats/jobstats/grafana/")
            self._add_to_document("")
            
            print(f"\n{Colors.BOLD}{Colors.YELLOW}Manual Configuration Required (existing Grafana detected):{Colors.END}")
            print(f"1. Access Grafana at http://{self.config['grafana_server']}:{self.config.get('grafana_port', 3000)}")
            print(f"2. Login with your existing credentials")
            print(f"3. Add Prometheus data source: http://{self.config['prometheus_server']}:{self.config.get('prometheus_port', 9090)}")
            print(f"4. Import jobstats dashboard from .jobstats/jobstats/grafana/")
        
        if not self.dry_run:
            self._safe_continue()
        else:
            print(f"\n{Colors.BLUE}[DRY RUN] Continuing to next section...{Colors.END}")
        return True

    def section_ood(self):
        """Section 8: Open OnDemand Integration (Not Covered)"""
        self._print_header(
            "8. Open OnDemand Integration (Not Covered)",
            "Open OnDemand integration is not included in this setup"
        )
        
        # Add to document
        self._add_to_document("## 8. Open OnDemand Integration (Not Covered)")
        self._add_to_document("")
        self._add_to_document("### Description")
        self._add_to_document("")
        self._add_to_document("Open OnDemand (OOD) integration is not included in this guided setup.")
        self._add_to_document("OOD is a separate web portal application that requires its own installation")
        self._add_to_document("and configuration process.")
        self._add_to_document("")
        self._add_to_document("### Why OOD is not included")
        self._add_to_document("")
        self._add_to_document("- OOD is a full HPC web portal that requires separate installation")
        self._add_to_document("- OOD installation is beyond the scope of this jobstats setup")
        self._add_to_document("- The jobstats OOD helper files are available but require OOD to be installed first")
        self._add_to_document("")
        self._add_to_document("### OOD Helper Files Location")
        self._add_to_document("")
        self._add_to_document("If you have OOD installed and want to integrate jobstats:")
        self._add_to_document("- OOD helper files are available in the jobstats repository")
        self._add_to_document("- Path: `jobstats/ood-jobstats-helper/`")
        self._add_to_document("- Follow the README in that directory for integration instructions")
        self._add_to_document("")
        
        print(f"{Colors.BLUE}Open OnDemand integration is not included in this setup.{Colors.END}")
        print(f"{Colors.BLUE}OOD is a separate web portal application.{Colors.END}")
        
        print(f"\n{Colors.BOLD}{Colors.WHITE}Why OOD is not included:{Colors.END}")
        print(f"• OOD is a full HPC web portal requiring separate installation")
        print(f"• OOD installation is beyond the scope of this jobstats setup")
        print(f"• The jobstats OOD helper files are available but require OOD first")
        
        print(f"\n{Colors.BOLD}{Colors.YELLOW}OOD Helper Files:{Colors.END}")
        print(f"If you have OOD installed and want to integrate jobstats:")
        print(f"• OOD helper files are available in the jobstats repository")
        print(f"• Path: {Colors.WHITE}jobstats/ood-jobstats-helper/{Colors.END}")
        print(f"• Follow the README in that directory for integration instructions")
        
        # Mark as completed since we're explaining why it's not included
        return True
        
        if not self.dry_run:
            self._safe_continue()
        else:
            print(f"\n{Colors.BLUE}[DRY RUN] Continuing to next section...{Colors.END}")
        return True

    def section_jobstats_command(self):
        """Section 9: The jobstats Command"""
        self._print_header(
            "9. The jobstats Command",
            "Install and configure the jobstats command-line tool"
        )
        
        # Add to document
        self._add_to_document("## 9. The jobstats Command")
        self._add_to_document("")
        self._add_to_document("### Description")
        self._add_to_document("")
        self._add_to_document("This section installs the jobstats command-line tool")
        self._add_to_document("for querying job statistics from the command line.")
        self._add_to_document("")
        self._add_to_document("### What we'll do")
        self._add_to_document("")
        self._add_to_document("- Install Python dependencies (requests, blessed)")
        self._add_to_document("- Install jobstats files to shared storage (`/cm/shared/apps/jobstats/`)")
        self._add_to_document("- Create symlinks on all login nodes")
        self._add_to_document("- Configure jobstats for your cluster")
        self._add_to_document("- Test jobstats command functionality")
        self._add_to_document("")
        self._add_to_document("**Note:** Using shared storage ensures all nodes use the same jobstats files,")
        self._add_to_document("making maintenance and updates much easier.")
        self._add_to_document("")
        
        print(f"{Colors.BLUE}This section installs the jobstats command-line tool{Colors.END}")
        print(f"{Colors.BLUE}for generating job efficiency reports.{Colors.END}")
        
        print(f"\n{Colors.BOLD}{Colors.WHITE}What we'll do:{Colors.END}")
        print(f"• Install Python dependencies (requests, blessed)")
        print(f"• Install jobstats command files")
        print(f"• Configure jobstats settings")
        print(f"• Test jobstats functionality")
        
        # Install jobstats using shared storage approach
        jobstats_commands = []
        
        # Step 1: Install jobstats files to shared storage (run locally on BCM headnode)
        jobstats_commands.extend([
            {
                'host': None,  # Run locally on BCM headnode
                'command': 'mkdir -p /cm/shared/apps/jobstats',
                'description': 'Create shared jobstats directory'
            },
            {
                'host': None,  # Run locally on BCM headnode
                'command': 'rm -rf /tmp/jobstats-deployment',
                'description': 'Clean up any existing jobstats repo'
            },
            {
                'host': None,  # Run locally on BCM headnode
                'command': 'git clone https://github.com/PrincetonUniversity/jobstats.git /tmp/jobstats-deployment',
                'description': 'Clone jobstats repo'
            },
            {
                'host': None,  # Run locally on BCM headnode
                'command': 'cp /tmp/jobstats-deployment/jobstats /cm/shared/apps/jobstats/',
                'description': 'Install jobstats binary to shared storage'
            },
            {
                'host': None,  # Run locally on BCM headnode
                'command': 'cp /tmp/jobstats-deployment/jobstats.py /cm/shared/apps/jobstats/',
                'description': 'Install jobstats.py to shared storage'
            },
            {
                'host': None,  # Run locally on BCM headnode
                'command': 'cp /tmp/jobstats-deployment/output_formatters.py /cm/shared/apps/jobstats/',
                'description': 'Install output_formatters.py to shared storage'
            },
            {
                'host': None,  # Run locally on BCM headnode
                'command': 'cp /tmp/jobstats-deployment/config.py /cm/shared/apps/jobstats/',
                'description': 'Install config.py to shared storage'
            },
            {
                'host': None,  # Run locally on BCM headnode
                'command': 'chmod +x /cm/shared/apps/jobstats/jobstats',
                'description': 'Make jobstats executable'
            },
            {
                'host': None,  # Run locally on BCM headnode
                'command': 'rm -rf /tmp/jobstats-deployment',
                'description': 'Clean up jobstats repo'
            }
        ])
        
        # Step 2: Create symlinks on all login nodes
        for login_node in self.config['systems']['login_nodes']:
            jobstats_commands.append({
                'host': login_node,
                'command': 'ln -sf /cm/shared/apps/jobstats/jobstats /usr/local/bin/jobstats',
                'description': f'Create jobstats symlink on {login_node}'
            })
        
        if self._execute_commands(jobstats_commands):
            print(f"\n{Colors.GREEN}✓ Jobstats command installation completed{Colors.END}")
        else:
            print(f"\n{Colors.RED}✗ Jobstats command installation failed{Colors.END}")
            return False
        
        # Install Python dependencies for jobstats
        print(f"\n{Colors.BOLD}{Colors.WHITE}Installing Python dependencies for jobstats...{Colors.END}")
        print(f"{Colors.YELLOW}Note: Package updates can take several minutes, especially on first run.{Colors.END}")
        print(f"{Colors.YELLOW}Please be patient if the process appears to hang during 'apt update' steps.{Colors.END}")
        
        python_deps_commands = []
        for login_node in self.config['systems']['login_nodes']:
            python_deps_commands.extend([
                {
                    'host': login_node,
                    'command': 'apt update',
                    'description': f'Update package list on {login_node}'
                },
                {
                    'host': login_node,
                    'command': 'DEBIAN_FRONTEND=noninteractive apt install -y python3-requests python3-blessed',
                    'description': f'Install Python dependencies (requests, blessed) on {login_node}'
                }
            ])
        
        if self._execute_commands(python_deps_commands):
            print(f"\n{Colors.GREEN}✓ Python dependencies installed{Colors.END}")
        else:
            print(f"\n{Colors.RED}✗ Python dependencies installation failed{Colors.END}")
            return False
        
        # Update config.py with correct Prometheus server address
        # Since config.py is now in shared storage, we only need to update it once
        config_update_commands = [
            {
                'host': None,  # Run locally on BCM headnode
                'command': f'sed -i "s|http://cluster-stats:8480|http://{self.config["prometheus_server"]}:{self.config["prometheus_port"]}|g" /cm/shared/apps/jobstats/config.py',
                'description': 'Update Prometheus server address in shared config.py'
            },
            {
                'host': None,  # Run locally on BCM headnode
                'command': f'sed -i "s|PROM_RETENTION_DAYS = 365|PROM_RETENTION_DAYS = {self.config.get("prometheus_retention_days", 365)}|g" /cm/shared/apps/jobstats/config.py',
                'description': 'Update Prometheus retention days in shared config.py'
            }
        ]
        
        if self._execute_commands(config_update_commands):
            print(f"\n{Colors.GREEN}✓ Jobstats configuration updated{Colors.END}")
        else:
            print(f"\n{Colors.RED}✗ Jobstats configuration update failed{Colors.END}")
            return False
        
        print(f"\n{Colors.BOLD}{Colors.YELLOW}Configuration Applied:{Colors.END}")
        print(f"• {Colors.WHITE}PROM_SERVER = \"http://{self.config['prometheus_server']}:{self.config['prometheus_port']}\"{Colors.END}")
        print(f"• {Colors.WHITE}PROM_RETENTION_DAYS = {self.config.get('prometheus_retention_days', 365)}{Colors.END}")
        
        if not self.dry_run:
            self._safe_continue("Press Enter to continue...")
        else:
            print(f"\n{Colors.BLUE}[DRY RUN] Continuing to next section...{Colors.END}")
        return True

    def section_bcm_role_monitor(self):
        """Section 10: BCM Role Monitor"""
        self._print_header(
            "10. BCM Role Monitor (Optional)",
            "Deploy BCM role monitoring service to DGX nodes"
        )
        
        # Add to document
        self._add_to_document("## 10. BCM Role Monitor (Optional)")
        self._add_to_document("")
        self._add_to_document("### Description")
        self._add_to_document("")
        self._add_to_document("This section deploys the BCM role monitoring service to DGX nodes.")
        self._add_to_document("The service monitors BCM role assignments and automatically manages")
        self._add_to_document("jobstats exporter services and Prometheus targets based on whether")
        self._add_to_document("the node has the slurmclient role.")
        self._add_to_document("")
        self._add_to_document("### What we'll do")
        self._add_to_document("")
        self._add_to_document("- Discover BCM headnodes using cmsh")
        self._add_to_document("- Deploy BCM role monitor service to DGX nodes")
        self._add_to_document("- Configure service with BCM headnode information")
        self._add_to_document("- Configure Prometheus targets directory (default or custom)")
        self._add_to_document("- Copy BCM certificates to DGX nodes")
        self._add_to_document("- Enable and start the monitoring service")
        self._add_to_document("")
        
        print(f"{Colors.BLUE}This section deploys the BCM role monitoring service to DGX nodes.{Colors.END}")
        print(f"{Colors.BLUE}The service monitors BCM role assignments and automatically manages:{Colors.END}")
        print(f"{Colors.BLUE}  • Jobstats exporter services (start/stop based on role){Colors.END}")
        print(f"{Colors.BLUE}  • Prometheus target files (dynamic service discovery){Colors.END}")
        
        print(f"\n{Colors.BOLD}{Colors.WHITE}What we'll do:{Colors.END}")
        print(f"• Discover BCM headnodes using cmsh")
        print(f"• Deploy BCM role monitor service to DGX nodes")
        print(f"• Configure service with BCM headnode information")
        print(f"• Configure Prometheus targets directory")
        print(f"• Copy BCM certificates to DGX nodes")
        print(f"• Enable and start the monitoring service")
        
        # Ask if user wants to deploy BCM role monitor
        print(f"\n{Colors.BOLD}{Colors.YELLOW}Do you want to deploy the BCM role monitor?{Colors.END}")
        print(f"{Colors.CYAN}The BCM role monitor provides automatic management of:{Colors.END}")
        print(f"  • Exporter services based on BCM role assignment")
        print(f"  • Prometheus target files for dynamic service discovery")
        print(f"{Colors.CYAN}This is useful for dynamic cluster configurations where nodes")
        print(f"move between different BCM categories/roles.{Colors.END}")
        
        if self.non_interactive or self.dry_run:
            # In non-interactive/dry-run mode, determine defaults based on use_existing_prometheus
            use_existing_prometheus = self.config.get('use_existing_prometheus', False)
            
            # Default to deploying BCM role monitor
            deploy_monitor = self.config.get('deploy_bcm_role_monitor', True)
            
            print(f"\n{Colors.BLUE}[Non-interactive/Dry-run mode] Deploy BCM role monitor: {deploy_monitor}{Colors.END}")
            if use_existing_prometheus:
                print(f"{Colors.BLUE}[Auto-configured] Using existing Prometheus - will prompt for custom targets directory{Colors.END}")
            else:
                print(f"{Colors.BLUE}[Auto-configured] New Prometheus deployment - will use default targets directory{Colors.END}")
        else:
            response = input(f"\n{Colors.BOLD}Deploy BCM role monitor? (yes/no) [{Colors.GREEN}yes{Colors.END}]: ").strip().lower()
            deploy_monitor = response in ['', 'y', 'yes']
        
        if not deploy_monitor:
            print(f"\n{Colors.YELLOW}Skipping BCM role monitor deployment.{Colors.END}")
            self._add_to_document("**Note:** User chose to skip BCM role monitor deployment.")
            self._add_to_document("")
            self._add_to_document("If you need to deploy it later, you can run:")
            self._add_to_document("```bash")
            self._add_to_document("python3 automation/role-monitor/deploy_bcm_role_monitor.py --config automation/configs/config.json")
            self._add_to_document("```")
            self._add_to_document("")
            return True
        
        # Check if BCM role monitor deployment is enabled
        if not self.config.get('deploy_bcm_role_monitor', True):
            print(f"\n{Colors.YELLOW}BCM role monitor deployment is disabled in configuration.{Colors.END}")
            print(f"{Colors.YELLOW}Skipping BCM role monitor deployment.{Colors.END}")
            self._add_to_document("**Note:** BCM role monitor deployment is disabled in config - skipping deployment.")
            return True
        
        # Get DGX nodes from config
        dgx_nodes = []
        if 'systems' in self.config and 'dgx_nodes' in self.config['systems']:
            dgx_nodes = self.config['systems']['dgx_nodes']
        
        if not dgx_nodes:
            print(f"\n{Colors.YELLOW}No DGX nodes configured for deployment.{Colors.END}")
            print(f"{Colors.YELLOW}Skipping BCM role monitor deployment.{Colors.END}")
            self._add_to_document("**Note:** No DGX nodes configured - skipping deployment.")
            return True
        
        # Ask about Prometheus targets directory
        print(f"\n{Colors.BOLD}{Colors.YELLOW}Prometheus Targets Directory Configuration{Colors.END}")
        print(f"{Colors.CYAN}The BCM role monitor creates Prometheus target files for dynamic service discovery.{Colors.END}")
        print(f"{Colors.CYAN}Default location: /cm/shared/apps/jobstats/prometheus-targets/{Colors.END}")
        print(f"\n{Colors.CYAN}If you have an existing Prometheus server with a different shared storage")
        print(f"location, you can specify a custom directory.{Colors.END}")
        
        prometheus_targets_dir = None
        if self.non_interactive or self.dry_run:
            # Auto-configure based on use_existing_prometheus
            use_existing_prometheus = self.config.get('use_existing_prometheus', False)
            
            if use_existing_prometheus:
                # Using existing Prometheus - assume custom directory needed
                use_custom = self.config.get('use_custom_prometheus_targets_dir', True)
                if use_custom:
                    # Get from config or prompt would be needed (but we're non-interactive)
                    prometheus_targets_dir = self.config.get('prometheus_targets_dir')
                    if not prometheus_targets_dir:
                        # If not specified in config, we need to inform user
                        print(f"\n{Colors.YELLOW}[Warning] Using existing Prometheus but no custom targets directory specified in config.{Colors.END}")
                        print(f"{Colors.YELLOW}Please add 'prometheus_targets_dir' to your config.json{Colors.END}")
                        print(f"{Colors.YELLOW}Using default directory for now: /cm/shared/apps/jobstats/prometheus-targets{Colors.END}")
                        prometheus_targets_dir = None
                    else:
                        print(f"\n{Colors.BLUE}[Auto-configured] Using custom Prometheus targets directory: {prometheus_targets_dir}{Colors.END}")
                        self._add_to_document(f"**Prometheus Targets Directory:** `{prometheus_targets_dir}` (custom - existing Prometheus)")
            else:
                # New Prometheus deployment - use default directory
                use_custom = self.config.get('use_custom_prometheus_targets_dir', False)
                if use_custom and 'prometheus_targets_dir' in self.config:
                    prometheus_targets_dir = self.config['prometheus_targets_dir']
                    print(f"\n{Colors.BLUE}[Auto-configured] Using custom directory from config: {prometheus_targets_dir}{Colors.END}")
                    self._add_to_document(f"**Prometheus Targets Directory:** `{prometheus_targets_dir}` (custom)")
                else:
                    print(f"\n{Colors.BLUE}[Auto-configured] Using default Prometheus targets directory: /cm/shared/apps/jobstats/prometheus-targets{Colors.END}")
                    self._add_to_document("**Prometheus Targets Directory:** `/cm/shared/apps/jobstats/prometheus-targets` (default)")
        else:
            # Interactive mode - ask user
            response = input(f"\n{Colors.BOLD}Use custom Prometheus targets directory? (yes/no) [{Colors.GREEN}no{Colors.END}]: ").strip().lower()
            use_custom = response in ['y', 'yes']
            
            if use_custom:
                default_dir = '/cm/shared/apps/jobstats/prometheus-targets'
                prometheus_targets_dir = input(f"{Colors.BOLD}Enter Prometheus targets directory [{Colors.GREEN}{default_dir}{Colors.END}]: ").strip()
                if not prometheus_targets_dir:
                    prometheus_targets_dir = default_dir
                
                print(f"\n{Colors.CYAN}Using custom Prometheus targets directory: {prometheus_targets_dir}{Colors.END}")
                self._add_to_document(f"**Prometheus Targets Directory:** `{prometheus_targets_dir}` (custom)")
            else:
                print(f"\n{Colors.CYAN}Using default Prometheus targets directory: /cm/shared/apps/jobstats/prometheus-targets{Colors.END}")
                self._add_to_document("**Prometheus Targets Directory:** `/cm/shared/apps/jobstats/prometheus-targets` (default)")
        
        self._add_to_document("")
        
        print(f"\n{Colors.BOLD}{Colors.CYAN}Deploying BCM Role Monitor{Colors.END}")
        print(f"Target DGX nodes: {', '.join(dgx_nodes)}")
        if prometheus_targets_dir:
            print(f"Prometheus targets directory: {prometheus_targets_dir}")
        
        # Import and run the deployment script
        try:
            import sys
            from pathlib import Path
            
            # Add role-monitor directory to path
            role_monitor_dir = Path(__file__).parent / 'role-monitor'
            sys.path.insert(0, str(role_monitor_dir))
            
            # Import the deployer
            from deploy_bcm_role_monitor import BCMRoleMonitorDeployer
            
            # Create deployer with current config
            deployer_config = {
                'dgx_nodes': dgx_nodes
            }
            
            deployer = BCMRoleMonitorDeployer(deployer_config)
            
            if self.dry_run:
                print(f"\n{Colors.BLUE}[DRY RUN] Would deploy BCM role monitor to: {', '.join(dgx_nodes)}{Colors.END}")
                if prometheus_targets_dir:
                    print(f"{Colors.BLUE}[DRY RUN] With custom Prometheus targets directory: {prometheus_targets_dir}{Colors.END}")
                self._add_to_document("### Deployment Commands")
                self._add_to_document("")
                self._add_to_document("```bash")
                self._add_to_document("# Deploy BCM role monitor to DGX nodes")
                deploy_cmd = f"python3 automation/role-monitor/deploy_bcm_role_monitor.py --dgx-nodes {' '.join(dgx_nodes)}"
                if prometheus_targets_dir:
                    deploy_cmd += f" --prometheus-targets-dir {prometheus_targets_dir}"
                self._add_to_document(deploy_cmd)
                self._add_to_document("```")
                self._add_to_document("")
                return True
            else:
                # Run actual deployment
                print(f"\n{Colors.YELLOW}Deploying BCM role monitor...{Colors.END}")
                success = deployer.deploy(prometheus_targets_dir=prometheus_targets_dir)
                
                if success:
                    print(f"\n{Colors.GREEN}✓ BCM role monitor deployed successfully{Colors.END}")
                    self._add_to_document("### Deployment Results")
                    self._add_to_document("")
                    self._add_to_document("✓ BCM role monitor deployed successfully to all DGX nodes")
                    self._add_to_document("")
                    if prometheus_targets_dir:
                        self._add_to_document(f"✓ Configured with custom Prometheus targets directory: `{prometheus_targets_dir}`")
                        self._add_to_document("")
                    self._add_to_document("### Service Management")
                    self._add_to_document("")
                    self._add_to_document("The BCM role monitor service is now running on DGX nodes and will:")
                    self._add_to_document("- Monitor BCM role assignments every 60 seconds")
                    self._add_to_document("- Start jobstats exporters when slurmclient role is assigned")
                    self._add_to_document("- Stop jobstats exporters when slurmclient role is removed")
                    self._add_to_document("- Automatically manage Prometheus target files for service discovery")
                    self._add_to_document("- Retry failed service starts up to 3 times over 30 minutes")
                    self._add_to_document("")
                    self._add_to_document("### Useful Commands")
                    self._add_to_document("")
                    self._add_to_document("```bash")
                    self._add_to_document("# Check service status on DGX nodes")
                    self._add_to_document("ssh <dgx-node> systemctl status bcm-role-monitor.service")
                    self._add_to_document("")
                    self._add_to_document("# View service logs")
                    self._add_to_document("ssh <dgx-node> journalctl -u bcm-role-monitor.service -f")
                    self._add_to_document("")
                    self._add_to_document("# Check configuration")
                    self._add_to_document("ssh <dgx-node> cat /etc/bcm-role-monitor/config.json")
                    self._add_to_document("")
                    if prometheus_targets_dir:
                        self._add_to_document("# Check Prometheus target files")
                        self._add_to_document(f"ls -la {prometheus_targets_dir}/")
                    else:
                        self._add_to_document("# Check Prometheus target files")
                        self._add_to_document("ls -la /cm/shared/apps/jobstats/prometheus-targets/")
                    self._add_to_document("```")
                    self._add_to_document("")
                else:
                    print(f"\n{Colors.RED}✗ BCM role monitor deployment failed{Colors.END}")
                    self._add_to_document("### Deployment Results")
                    self._add_to_document("")
                    self._add_to_document("✗ BCM role monitor deployment failed")
                    self._add_to_document("")
                    self._add_to_document("Please check the deployment logs and retry manually if needed.")
                    return False
        
        except ImportError as e:
            print(f"\n{Colors.RED}✗ Failed to import BCM role monitor deployer: {e}{Colors.END}")
            return False
        except Exception as e:
            print(f"\n{Colors.RED}✗ BCM role monitor deployment failed: {e}{Colors.END}")
            return False
        
        if not self.dry_run:
            self._safe_continue("Press Enter to continue...")
        else:
            print(f"\n{Colors.BLUE}[DRY RUN] Continuing to next section...{Colors.END}")
        
        return True

    def section_bcm_configurations(self):
        """Section 11: BCM Imaging Workflow"""
        self._print_header(
            "11. BCM Imaging Workflow",
            "BCM imaging workflow instructions"
        )
        
        # Add to document
        self._add_to_document("## 11. BCM Imaging Workflow")
        self._add_to_document("")
        self._add_to_document("### Description")
        self._add_to_document("")
        self._add_to_document("This section provides instructions for BCM imaging workflow")
        self._add_to_document("to deploy jobstats to additional nodes of the same type.")
        self._add_to_document("")
        print(f"{Colors.BLUE}This section provides instructions for BCM imaging workflow{Colors.END}")
        print(f"{Colors.BLUE}to deploy jobstats to additional nodes of the same type.{Colors.END}")
        
        # BCM Imaging Workflow
        print(f"\n{Colors.BOLD}{Colors.CYAN}BCM imaging workflow instructions{Colors.END}")
        self._add_to_document("### BCM Imaging Process")
        self._add_to_document("")
        self._add_to_document("After successful deployment on representative nodes, capture images")
        self._add_to_document("for each node type to enable deployment to all nodes of the same type.")
        self._add_to_document("")
        
        # Get unique hosts by role
        hosts_by_role = {}
        for role, hosts in self.config['systems'].items():
            for host in hosts:
                if host not in hosts_by_role:
                    hosts_by_role[host] = []
                hosts_by_role[host].append(role)
        
        print(f"\n{Colors.BOLD}{Colors.YELLOW}BCM imaging instructions{Colors.END}")
        
        # Print imaging instructions for each unique host
        imaging_instructions = []
        for host, roles in hosts_by_role.items():
            if 'slurm_controller' in roles or 'login_nodes' in roles:
                node_type = "Slurm Controller/Login Node"
            elif 'dgx_nodes' in roles:
                node_type = "DGX Compute Node"
            elif 'prometheus_server' in roles or 'grafana_server' in roles:
                node_type = "Monitoring Server"
            else:
                node_type = "Unknown"
            
            print(f"\n{Colors.BOLD}{Colors.WHITE}{node_type} ({host}):{Colors.END}")
            print(f"  {Colors.CYAN}cmsh -c 'device;use {host};grabimage -w'{Colors.END}")
            
            imaging_instructions.append({
                'host': host,
                'node_type': node_type,
                'command': f"/cm/local/apps/cmd/bin/cmsh -c 'device;use {host};grabimage -w'",
                'description': f"cmsh -c 'device;use {host};grabimage -w'"
            })
        
        # Add imaging instructions to document
        self._add_to_document("#### Imaging Commands")
        self._add_to_document("")
        self._add_to_document("Execute the following commands to capture images for each node type:")
        self._add_to_document("")
        
        for instruction in imaging_instructions:
            self._add_to_document(f"**{instruction['node_type']} ({instruction['host']}):**")
            self._add_to_document("")
            self._add_to_document("```bash")
            self._add_to_document(instruction['command'])
            self._add_to_document("```")
            self._add_to_document("")
        
        self._add_to_document("#### Imaging Benefits")
        self._add_to_document("")
        self._add_to_document("- **Consistent deployment:** All nodes of the same type get identical configuration")
        self._add_to_document("- **Fast scaling:** New nodes automatically get the correct configuration")
        self._add_to_document("- **Easy maintenance:** Updates can be applied to images and redeployed")
        self._add_to_document("- **Service management:** Category-based services automatically start/stop")
        self._add_to_document("")
        
        # Subsection 10c: Setcap Commands Notification
        print(f"\n{Colors.BOLD}{Colors.CYAN}10c. Setcap Commands Notification{Colors.END}")
        self._add_to_document("### 10c. Setcap Commands Notification")
        self._add_to_document("")
        self._add_to_document("#### Important: Setcap Commands and Extended Attributes")
        self._add_to_document("")
        self._add_to_document("During the deployment, the following `setcap` commands were executed:")
        self._add_to_document("")
        
        # Track setcap commands that were run
        setcap_commands = []
        for dgx_node in self.config['systems']['dgx_nodes']:
            setcap_commands.append({
                'host': dgx_node,
                'command': 'setcap cap_sys_ptrace=eip /usr/local/bin/cgroup_exporter',
                'description': 'Set capabilities for cgroup_exporter to read procfs'
            })
            setcap_commands.append({
                'host': dgx_node,
                'command': 'setcap cap_sys_ptrace=eip /usr/local/bin/nvidia_gpu_prometheus_exporter',
                'description': 'Set capabilities for nvidia_gpu_prometheus_exporter to read procfs'
            })
        
        # Add setcap commands to document
        for cmd in setcap_commands:
            self._add_to_document(f"**{cmd['host']}:**")
            self._add_to_document(f"```bash")
            self._add_to_document(f"{cmd['command']}")
            self._add_to_document(f"```")
            self._add_to_document("")
        
        self._add_to_document("#### Extended Attributes (xattrs) Warning")
        self._add_to_document("")
        self._add_to_document("**IMPORTANT:** If your software images are stored on a file system")
        self._add_to_document("that does not support extended attributes (xattrs), such as an NFS export,")
        self._add_to_document("you may need to take additional steps to ensure that these `setcap` commands")
        self._add_to_document("are run when your systems boot.")
        self._add_to_document("")
        self._add_to_document("**Recommended solutions:**")
        self._add_to_document("- Add the `setcap` commands to your system startup scripts")
        self._add_to_document("- Include them in your BCM imaging process")
        self._add_to_document("- Create a systemd service that runs the commands on boot")
        self._add_to_document("")
        
        print(f"\n{Colors.BOLD}{Colors.YELLOW}Setcap Commands Executed:{Colors.END}")
        for cmd in setcap_commands:
            print(f"• {Colors.WHITE}{cmd['host']}: {cmd['command']}{Colors.END}")
        
        print(f"\n{Colors.BOLD}{Colors.YELLOW}Extended Attributes (xattrs) Warning:{Colors.END}")
        print(f"If your software images are stored on a file system that does not")
        print(f"support extended attributes (xattrs), such as an NFS export, you may")
        print(f"need to take additional steps to ensure that these setcap commands")
        print(f"are run when your systems boot.")
        print(f"")
        print(f"Recommended solutions:")
        print(f"• Add the setcap commands to your system startup scripts")
        print(f"• Include them in your BCM imaging process")
        print(f"• Create a systemd service that runs the commands on boot")
        
        print(f"\n{Colors.BOLD}{Colors.GREEN}✓ BCM configuration completed{Colors.END}")
        print(f"{Colors.BOLD}{Colors.GREEN}✓ Imaging instructions provided{Colors.END}")
        print(f"{Colors.BOLD}{Colors.GREEN}✓ Setcap commands documented{Colors.END}")
        
        if not self.dry_run:
            self._safe_continue("Press Enter to continue...")
        else:
            print(f"\n{Colors.BLUE}[DRY RUN] Continuing to next section...{Colors.END}")
        return True

    def run_guided_setup(self):
        """Run the complete guided setup process."""
        print(f"{Colors.BOLD}{Colors.PURPLE}{'='*80}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.WHITE}BCM Jobstats Guided Setup{Colors.END}")
        if self.dry_run:
            print(f"{Colors.BOLD}{Colors.YELLOW}[DRY RUN MODE]{Colors.END}")
        print(f"{Colors.BOLD}{Colors.PURPLE}{'='*80}{Colors.END}")
        
        # Initialize document (only in dry-run mode)
        if self.dry_run:
            self._init_document()
        
        if self.resume and self.progress['current_section'] > 0:
            print(f"\n{Colors.YELLOW}Resuming from section {self.progress['current_section'] + 1}{Colors.END}")
            start_section = self.progress['current_section']
        else:
            start_section = 0
        
        # Run each section
        for i, section in enumerate(self.setup_sections[start_section:], start_section):
            section_id = section['id']
            section_title = section['title']
            
            print(f"\n{Colors.BOLD}{Colors.CYAN}Section {i+1}/{len(self.setup_sections)}: {section_title}{Colors.END}")
            
            # Execute section
            if hasattr(self, f'section_{section_id}'):
                success = getattr(self, f'section_{section_id}')()
                
                if success:
                    self.progress['completed_sections'].append(section_id)
                    self.progress['current_section'] = i + 1
                    self._save_progress()
                    print(f"\n{Colors.GREEN}✓ Section {i+1} completed successfully{Colors.END}")
                else:
                    print(f"\n{Colors.RED}✗ Section {i+1} failed{Colors.END}")
                    if not self.dry_run:
                        print(f"{Colors.YELLOW}You can resume from this section later using --resume{Colors.END}")
                    return False
            else:
                print(f"{Colors.RED}Section {section_id} not implemented{Colors.END}")
                return False
        
        # Save final document (only in dry-run mode)
        if self.dry_run:
            self._save_document()
        
        # Final summary
        print(f"\n{Colors.BOLD}{Colors.GREEN}{'='*80}{Colors.END}")
        if self.dry_run:
            print(f"{Colors.BOLD}{Colors.WHITE}Dry Run Complete!{Colors.END}")
        else:
            print(f"{Colors.BOLD}{Colors.WHITE}Setup Complete!{Colors.END}")
        print(f"{Colors.BOLD}{Colors.GREEN}{'='*80}{Colors.END}")
        
        print(f"\n{Colors.BLUE}All sections have been completed successfully.{Colors.END}")
        print(f"\n{Colors.BOLD}{Colors.WHITE}Documentation Generated:{Colors.END}")
        print(f"• {Colors.CYAN}Setup document: {self.document_file}{Colors.END}")
        print(f"• {Colors.CYAN}This document contains all commands and can be used for manual implementation{Colors.END}")
        
        if not self.dry_run:
            print(f"\n{Colors.BOLD}{Colors.WHITE}Next Steps:{Colors.END}")
            print(f"1. {Colors.CYAN}Test the deployment with a sample job{Colors.END}")
            print(f"2. {Colors.CYAN}Access Grafana at http://{self.config['grafana_server']}:{self.config['grafana_port']}{Colors.END}")
            print(f"3. {Colors.CYAN}Test jobstats command: jobstats --help{Colors.END}")
            print(f"4. {Colors.CYAN}Review the documentation for troubleshooting{Colors.END}")
        else:
            print(f"\n{Colors.BOLD}{Colors.WHITE}Dry Run Summary:{Colors.END}")
            print(f"1. {Colors.CYAN}Review the generated document: {self.document_file}{Colors.END}")
            print(f"2. {Colors.CYAN}Use the document to implement the setup manually{Colors.END}")
            print(f"3. {Colors.CYAN}Run without --dry-run to execute the setup{Colors.END}")
        
        return True

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="BCM Jobstats Guided Setup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run guided setup (interactive)
    python guided_setup.py
    
    # Run dry-run to generate documentation only
    python guided_setup.py --dry-run
    
    # Run in non-interactive mode (auto-confirm all prompts)
    python guided_setup.py --non-interactive
    
    # Resume from where you left off
    python guided_setup.py --resume
    
    # Use custom configuration
    python guided_setup.py --config my_config.json
        """
    )
    
    parser.add_argument(
        '--resume',
        action='store_true',
        help='Resume setup from where it was left off'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        default='automation/configs/config.json',
        help='Path to configuration JSON file (default: automation/configs/config.json)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Generate documentation without executing commands'
    )
    
    parser.add_argument(
        '--non-interactive',
        action='store_true',
        help='Run in non-interactive mode (auto-confirm all prompts)'
    )
    
    args = parser.parse_args()
    
    # Create guided setup instance
    setup = GuidedJobstatsSetup(resume=args.resume, config_file=args.config, dry_run=args.dry_run, non_interactive=args.non_interactive)
    
    # Run guided setup
    success = setup.run_guided_setup()
    
    if success:
        if args.dry_run:
            print(f"\n{Colors.GREEN}Dry run completed successfully!{Colors.END}")
        else:
            print(f"\n{Colors.GREEN}Guided setup completed successfully!{Colors.END}")
        sys.exit(0)
    else:
        print(f"\n{Colors.RED}Guided setup failed!{Colors.END}")
        sys.exit(1)

if __name__ == "__main__":
    main()
