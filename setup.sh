#!/bin/bash

# BCM Jobstats Project Setup Script
# This script sets up the complete environment for BCM jobstats deployment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to prompt for user input with default
prompt_with_default() {
    local prompt="$1"
    local default="$2"
    local var_name="$3"
    
    if [ -n "$default" ]; then
        read -p "$prompt [$default]: " input
        eval "$var_name=\${input:-$default}"
    else
        read -p "$prompt: " input
        eval "$var_name=\"$input\""
    fi
}

# Function to prompt for multiple hostnames
prompt_hostnames() {
    local role="$1"
    local var_name="$2"
    local existing_var="$3"  # Name of variable containing existing hosts JSON
    local hosts=()
    local existing_hosts=()
    
    echo ""
    
    # Check if we have existing hosts
    if [ -n "$existing_var" ]; then
        # Parse existing JSON array into bash array using Python
        if command_exists python3; then
            local existing_json="${!existing_var}"
            if [ -n "$existing_json" ] && [ "$existing_json" != "[]" ]; then
                # Load existing hosts
                mapfile -t existing_hosts < <(python3 -c "
import json
import sys
try:
    hosts = json.loads('$existing_json')
    for host in hosts:
        print(host)
except:
    pass
" 2>/dev/null)
                
                # Display existing hosts
                if [ ${#existing_hosts[@]} -gt 0 ]; then
                    print_warning "Existing hosts for $role:"
                    for host in "${existing_hosts[@]}"; do
                        echo "  - $host"
                    done
                    echo ""
                    
                    # Offer options
                    echo "Options:"
                    echo "  [K]eep - Keep existing hosts (default)"
                    echo "  [A]dd  - Add new hosts to existing list"
                    echo "  [C]hange - Replace with completely new list"
                    echo ""
                    read -p "Choose option (K/a/c): " host_option
                    host_option=$(echo "$host_option" | tr '[:upper:]' '[:lower:]')
                    
                    case "$host_option" in
                        a|add)
                            print_status "Adding to existing hosts. Enter new hostnames (press Enter twice when done):"
                            # Start with existing hosts
                            hosts=("${existing_hosts[@]}")
                            while true; do
                                read -p "  New hostname: " hostname
                                if [ -z "$hostname" ]; then
                                    break
                                fi
                                hosts+=("$hostname")
                            done
                            ;;
                        c|change)
                            print_status "Enter new hostnames for $role (press Enter twice when done):"
                            while true; do
                                read -p "  Hostname: " hostname
                                if [ -z "$hostname" ]; then
                                    break
                                fi
                                hosts+=("$hostname")
                            done
                            ;;
                        *|k|keep)
                            print_status "Keeping existing hosts."
                            hosts=("${existing_hosts[@]}")
                            ;;
                    esac
                else
                    # Empty existing array, prompt for new hosts
                    print_status "Enter hostnames for $role (one per line, press Enter twice when done):"
                    while true; do
                        read -p "  Hostname: " hostname
                        if [ -z "$hostname" ]; then
                            break
                        fi
                        hosts+=("$hostname")
                    done
                fi
            else
                # No existing hosts, prompt for new
                print_status "Enter hostnames for $role (one per line, press Enter twice when done):"
                while true; do
                    read -p "  Hostname: " hostname
                    if [ -z "$hostname" ]; then
                        break
                    fi
                    hosts+=("$hostname")
                done
            fi
        fi
    else
        # No existing config, prompt for new hosts
        print_status "Enter hostnames for $role (one per line, press Enter twice when done):"
        while true; do
            read -p "  Hostname: " hostname
            if [ -z "$hostname" ]; then
                break
            fi
            hosts+=("$hostname")
        done
    fi
    
    # Convert array to JSON array format
    local json_array="["
    for i in "${!hosts[@]}"; do
        if [ $i -gt 0 ]; then
            json_array+=","
        fi
        json_array+="\"${hosts[$i]}\""
    done
    json_array+="]"
    
    eval "$var_name='$json_array'"
}

# Function to validate hostname format
validate_hostname() {
    local hostname="$1"
    if [[ "$hostname" =~ ^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$ ]]; then
        return 0
    else
        return 1
    fi
}

# Main setup function
main() {
    echo "=========================================="
    echo "  BCM Jobstats Project Setup"
    echo "=========================================="
    echo ""
    
    # Check if running as root
    if [ "$EUID" -eq 0 ]; then
        print_warning "Running as root. This is recommended for BCM deployments."
    else
        print_warning "Not running as root. You may need sudo privileges for some operations."
    fi
    
    # Step 1: Install uv if not present
    print_status "Step 1: Installing uv package manager..."
    
    if command_exists uv; then
        print_success "uv is already installed: $(uv --version)"
    else
        print_status "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        
        # Add uv to PATH for current session
        export PATH="$HOME/.cargo/bin:$PATH"
        
        # Source bashrc to make uv available
        if [ -f "$HOME/.bashrc" ]; then
            source "$HOME/.bashrc"
        fi
        
        if command_exists uv; then
            print_success "uv installed successfully: $(uv --version)"
        else
            print_error "Failed to install uv. Please install manually and run this script again."
            exit 1
        fi
    fi
    
    # Step 2: Sync dependencies
    print_status "Step 2: Installing Python dependencies..."
    
    if [ -f "pyproject.toml" ]; then
        # Check if dependencies are already installed
        if [ -d ".venv" ] && [ -f ".venv/pyvenv.cfg" ]; then
            print_status "Virtual environment already exists. Checking if dependencies are up to date..."
            if uv sync --check; then
                print_success "Dependencies are already up to date"
            else
                print_status "Dependencies need updating. Installing..."
                uv sync
                print_success "Dependencies updated successfully"
            fi
        else
            print_status "Installing dependencies..."
            uv sync
            print_success "Dependencies installed successfully"
        fi
    else
        print_error "pyproject.toml not found. Are you in the correct directory?"
        exit 1
    fi
    
    # Step 3: Check for existing configuration
    print_status "Step 3: Checking for existing configuration..."
    echo ""
    
    local config_file="automation/configs/config.json"
    local config_dir="automation/configs"
    
    # Ensure config directory exists
    mkdir -p "$config_dir"
    
    # Check if config.json already exists and load existing values
    local existing_config=false
    if [ -f "$config_file" ]; then
        existing_config=true
        echo ""
        print_warning "Configuration file already exists: $config_file"
        echo ""
        print_status "You can update individual settings or keep existing values."
        print_status "Press Enter to keep the current value shown in [brackets]."
        echo ""
        
        # Load existing configuration values using Python
        if command_exists python3; then
            eval "$(python3 -c "
import json
import sys
try:
    with open('$config_file', 'r') as f:
        config = json.load(f)
    
    # Extract values with defaults
    print(f\"existing_cluster_name='{config.get('cluster_name', 'slurm')}'\")
    print(f\"existing_prometheus_server='{config.get('prometheus_server', 'prometheus-server')}'\")
    print(f\"existing_grafana_server='{config.get('grafana_server', 'grafana-server')}'\")
    print(f\"existing_prometheus_port={config.get('prometheus_port', 9090)}\")
    print(f\"existing_grafana_port={config.get('grafana_port', 3000)}\")
    print(f\"existing_node_exporter_port={config.get('node_exporter_port', 9100)}\")
    print(f\"existing_cgroup_exporter_port={config.get('cgroup_exporter_port', 9306)}\")
    print(f\"existing_nvidia_gpu_exporter_port={config.get('nvidia_gpu_exporter_port', 9445)}\")
    print(f\"existing_prometheus_retention_days={config.get('prometheus_retention_days', 365)}\")
    print(f\"existing_use_existing_prometheus='{str(config.get('use_existing_prometheus', False)).lower()}'\")
    print(f\"existing_use_existing_grafana='{str(config.get('use_existing_grafana', False)).lower()}'\")
    print(f\"existing_deploy_bcm_role_monitor='{str(config.get('deploy_bcm_role_monitor', True)).lower()}'\")
    print(f\"existing_prometheus_targets_dir='{config.get('prometheus_targets_dir', '')}'\")
    
    # Extract systems arrays as JSON strings
    systems = config.get('systems', {})
    import json as j
    print(f\"existing_slurm_controller_hosts='{j.dumps(systems.get('slurm_controller', []))}'\")
    print(f\"existing_login_nodes_hosts='{j.dumps(systems.get('login_nodes', []))}'\")
    print(f\"existing_dgx_nodes_hosts='{j.dumps(systems.get('dgx_nodes', []))}'\")
    print(f\"existing_prometheus_server_hosts='{j.dumps(systems.get('prometheus_server', []))}'\")
    print(f\"existing_grafana_server_hosts='{j.dumps(systems.get('grafana_server', []))}'\")
except Exception as e:
    print(f\"echo 'Error loading config: {e}' >&2\", file=sys.stderr)
    sys.exit(1)
" 2>/dev/null)"
        fi
    fi
    
    # Step 4: Collect configuration information
    print_status "Step 4: Collecting configuration information..."
    echo ""
    
    # Set defaults based on whether we have existing config
    if [ "$existing_config" = true ]; then
        default_cluster_name="${existing_cluster_name:-slurm}"
        default_prometheus_server="${existing_prometheus_server:-prometheus-server}"
        default_grafana_server="${existing_grafana_server:-grafana-server}"
        default_prometheus_port="${existing_prometheus_port:-9090}"
        default_grafana_port="${existing_grafana_port:-3000}"
        default_node_exporter_port="${existing_node_exporter_port:-9100}"
        default_cgroup_exporter_port="${existing_cgroup_exporter_port:-9306}"
        default_nvidia_gpu_exporter_port="${existing_nvidia_gpu_exporter_port:-9445}"
        default_prometheus_retention_days="${existing_prometheus_retention_days:-365}"
    else
        default_cluster_name="slurm"
        default_prometheus_server="prometheus-server"
        default_grafana_server="grafana-server"
        default_prometheus_port="9090"
        default_grafana_port="3000"
        default_node_exporter_port="9100"
        default_cgroup_exporter_port="9306"
        default_nvidia_gpu_exporter_port="9445"
        default_prometheus_retention_days="365"
    fi
    
    # Basic configuration
    prompt_with_default "BCM wlm cluster name" "$default_cluster_name" cluster_name
    prompt_with_default "Prometheus server hostname" "$default_prometheus_server" prometheus_server
    prompt_with_default "Grafana server hostname" "$default_grafana_server" grafana_server
    
    # Ports
    prompt_with_default "Prometheus port" "$default_prometheus_port" prometheus_port
    prompt_with_default "Grafana port" "$default_grafana_port" grafana_port
    prompt_with_default "Node exporter port" "$default_node_exporter_port" node_exporter_port
    prompt_with_default "Cgroup exporter port" "$default_cgroup_exporter_port" cgroup_exporter_port
    prompt_with_default "NVIDIA GPU exporter port" "$default_nvidia_gpu_exporter_port" nvidia_gpu_exporter_port
    prompt_with_default "Prometheus retention days" "$default_prometheus_retention_days" prometheus_retention_days
    
    # Advanced options
    echo ""
    print_status "Advanced configuration options:"
    
    # Determine prompts based on existing config
    if [ "$existing_config" = true ]; then
        if [[ "$existing_use_existing_prometheus" == "true" ]]; then
            prom_prompt="Use existing Prometheus installation? (Y/n) [current: yes]: "
            prom_default="yes"
        else
            prom_prompt="Use existing Prometheus installation? (y/N) [current: no]: "
            prom_default="no"
        fi
        
        if [[ "$existing_use_existing_grafana" == "true" ]]; then
            grafana_prompt="Use existing Grafana installation? (Y/n) [current: yes]: "
            grafana_default="yes"
        else
            grafana_prompt="Use existing Grafana installation? (y/N) [current: no]: "
            grafana_default="no"
        fi
    else
        prom_prompt="Use existing Prometheus installation? (y/N): "
        prom_default="no"
        grafana_prompt="Use existing Grafana installation? (y/N): "
        grafana_default="no"
    fi
    
    read -p "$prom_prompt" use_existing_prometheus
    use_existing_prometheus=$(echo "$use_existing_prometheus" | tr '[:upper:]' '[:lower:]')
    if [ -z "$use_existing_prometheus" ]; then
        use_existing_prometheus="$prom_default"
    fi
    if [[ "$use_existing_prometheus" == "y" || "$use_existing_prometheus" == "yes" ]]; then
        use_existing_prometheus="true"
    else
        use_existing_prometheus="false"
    fi
    
    read -p "$grafana_prompt" use_existing_grafana
    use_existing_grafana=$(echo "$use_existing_grafana" | tr '[:upper:]' '[:lower:]')
    if [ -z "$use_existing_grafana" ]; then
        use_existing_grafana="$grafana_default"
    fi
    if [[ "$use_existing_grafana" == "y" || "$use_existing_grafana" == "yes" ]]; then
        use_existing_grafana="true"
    else
        use_existing_grafana="false"
    fi
    
    # BCM Role Monitor deployment
    echo ""
    print_status "BCM Role Monitor Configuration:"
    echo "The BCM role monitor service automatically manages jobstats exporters on DGX nodes"
    echo "based on BCM role assignments. It also manages Prometheus target files for dynamic"
    echo "service discovery."
    echo ""
    
    # Determine BCM role monitor prompt based on existing config
    if [ "$existing_config" = true ]; then
        if [[ "$existing_deploy_bcm_role_monitor" == "true" ]]; then
            bcm_prompt="Deploy BCM role monitor service? (Y/n) [current: yes]: "
            bcm_default="yes"
        else
            bcm_prompt="Deploy BCM role monitor service? (y/N) [current: no]: "
            bcm_default="no"
        fi
    else
        bcm_prompt="Deploy BCM role monitor service? (Y/n): "
        bcm_default="yes"
    fi
    
    read -p "$bcm_prompt" deploy_bcm_role_monitor
    deploy_bcm_role_monitor=$(echo "$deploy_bcm_role_monitor" | tr '[:upper:]' '[:lower:]')
    if [ -z "$deploy_bcm_role_monitor" ]; then
        deploy_bcm_role_monitor="$bcm_default"
    fi
    
    if [[ "$deploy_bcm_role_monitor" == "n" || "$deploy_bcm_role_monitor" == "no" ]]; then
        deploy_bcm_role_monitor="false"
        prometheus_targets_dir=""
        print_status "BCM role monitor will not be deployed."
    else
        deploy_bcm_role_monitor="true"
        
        # Only ask about Prometheus targets directory if deploying the role monitor
        echo ""
        print_status "Prometheus Targets Configuration:"
        echo "The BCM role monitor manages Prometheus target files for dynamic service discovery."
        echo ""
        
        # Determine default for targets directory
        if [ "$existing_config" = true ] && [ -n "$existing_prometheus_targets_dir" ]; then
            default_targets_dir="$existing_prometheus_targets_dir"
            targets_prompt="Prometheus targets directory [$default_targets_dir]: "
            prompt_with_default "Prometheus targets directory" "$default_targets_dir" prometheus_targets_dir
            if [ -n "$prometheus_targets_dir" ]; then
                print_status "Using directory: $prometheus_targets_dir"
            fi
        else
            read -p "Use default Prometheus targets directory (/cm/shared/apps/jobstats/prometheus-targets)? (Y/n): " use_default_targets_dir
            use_default_targets_dir=$(echo "$use_default_targets_dir" | tr '[:upper:]' '[:lower:]')
            
            if [[ "$use_default_targets_dir" == "n" || "$use_default_targets_dir" == "no" ]]; then
                prompt_with_default "Custom Prometheus targets directory" "/srv/prometheus/service-discovery" prometheus_targets_dir
                print_status "Using custom directory: $prometheus_targets_dir"
            else
                prometheus_targets_dir=""
                print_status "Using default directory: /cm/shared/apps/jobstats/prometheus-targets"
            fi
        fi
    fi
    
    # System hostnames
    echo ""
    print_status "System hostname configuration:"
    if [ "$existing_config" = false ]; then
        echo "Enter hostnames for each system type. Press Enter twice when done with each type."
    fi
    
    # Pass existing values if available
    if [ "$existing_config" = true ]; then
        prompt_hostnames "Slurm controller nodes" slurm_controller_hosts "existing_slurm_controller_hosts"
        prompt_hostnames "Login nodes" login_nodes_hosts "existing_login_nodes_hosts"
        prompt_hostnames "DGX compute nodes" dgx_nodes_hosts "existing_dgx_nodes_hosts"
    else
        prompt_hostnames "Slurm controller nodes" slurm_controller_hosts
        prompt_hostnames "Login nodes" login_nodes_hosts
        prompt_hostnames "DGX compute nodes" dgx_nodes_hosts
    fi
    
    if [[ "$use_existing_prometheus" == "false" ]]; then
        if [ "$existing_config" = true ]; then
            prompt_hostnames "Prometheus server nodes" prometheus_server_hosts "existing_prometheus_server_hosts"
        else
            prompt_hostnames "Prometheus server nodes" prometheus_server_hosts
        fi
    else
        prometheus_server_hosts="[]"
    fi
    
    if [[ "$use_existing_grafana" == "false" ]]; then
        if [ "$existing_config" = true ]; then
            prompt_hostnames "Grafana server nodes" grafana_server_hosts "existing_grafana_server_hosts"
        else
            prompt_hostnames "Grafana server nodes" grafana_server_hosts
        fi
    else
        grafana_server_hosts="[]"
    fi
    
    # Step 5: Create config.json
    print_status "Step 5: Creating configuration file..."
    
    # Create the JSON configuration
    # Build the base configuration
    cat > "$config_file" << EOF
{
  "cluster_name": "$cluster_name",
  "prometheus_server": "$prometheus_server",
  "grafana_server": "$grafana_server",
  "prometheus_port": $prometheus_port,
  "grafana_port": $grafana_port,
  "node_exporter_port": $node_exporter_port,
  "cgroup_exporter_port": $cgroup_exporter_port,
  "nvidia_gpu_exporter_port": $nvidia_gpu_exporter_port,
  "prometheus_retention_days": $prometheus_retention_days,
  "use_existing_prometheus": $use_existing_prometheus,
  "use_existing_grafana": $use_existing_grafana,
  "deploy_bcm_role_monitor": $deploy_bcm_role_monitor,
EOF
    
    # Add prometheus_targets_dir if custom directory was specified
    if [ -n "$prometheus_targets_dir" ]; then
        cat >> "$config_file" << EOF
  "prometheus_targets_dir": "$prometheus_targets_dir",
EOF
    fi
    
    # Complete the configuration
    cat >> "$config_file" << EOF
  "systems": {
    "slurm_controller": $slurm_controller_hosts,
    "login_nodes": $login_nodes_hosts,
    "dgx_nodes": $dgx_nodes_hosts,
    "prometheus_server": $prometheus_server_hosts,
    "grafana_server": $grafana_server_hosts
  }
}
EOF
    
    print_success "Configuration file created: $config_file"
    
    # Step 6: Display next steps
    echo ""
    echo "=========================================="
    print_success "Setup completed successfully!"
    echo "=========================================="
    echo ""
    print_status "Next steps:"
    echo "1. Review your configuration: cat $config_file"
    echo "2. Run a dry-run deployment:"
    echo "   uv run python automation/guided_setup.py --config $config_file --dry-run"
    echo "3. Deploy jobstats:"
    echo "   uv run python automation/guided_setup.py --config $config_file"
    echo ""
    print_status "Configuration file location: $config_file"
    print_status "Dry-run output will be saved to: automation/logs/dry-run-output.txt"
    echo ""
    
    # Step 7: Show configuration summary
    print_status "Configuration Summary:"
    echo "  Cluster: $cluster_name"
    echo "  Prometheus: $prometheus_server:$prometheus_port"
    echo "  Grafana: $grafana_server:$grafana_port"
    echo "  Existing Prometheus: $use_existing_prometheus"
    echo "  Existing Grafana: $use_existing_grafana"
    echo "  Deploy BCM Role Monitor: $deploy_bcm_role_monitor"
    if [[ "$deploy_bcm_role_monitor" == "true" ]]; then
        if [ -n "$prometheus_targets_dir" ]; then
            echo "  Prometheus Targets Directory: $prometheus_targets_dir (custom)"
        else
            echo "  Prometheus Targets Directory: /cm/shared/apps/jobstats/prometheus-targets (default)"
        fi
    fi
    echo ""
    
    print_success "Setup complete! You can now run the deployment script."
    
    # Step 8: Offer to run guided setup
    run_guided_setup_step "$config_file"
}

# Function to handle guided setup step
run_guided_setup_step() {
    local config_file="$1"
    
    echo ""
    print_status "Step 8: Optional Guided Setup"
    echo ""
    print_status "Would you like to run the guided setup process?"
    print_status "This will walk you through the deployment step-by-step with detailed explanations."
    echo ""
    read -p "Run guided setup? (y/N): " run_guided_setup
    run_guided_setup=$(echo "$run_guided_setup" | tr '[:upper:]' '[:lower:]')
    
    if [[ "$run_guided_setup" == "y" || "$run_guided_setup" == "yes" ]]; then
        echo ""
        print_status "Guided setup options:"
        echo "1. Full automation - Execute all commands automatically"
        echo "2. Dry run - Generate documentation only (no commands executed)"
        echo ""
        read -p "Choose option (1 or 2): " guided_option
        
        if [[ "$guided_option" == "1" ]]; then
            print_status "Running guided setup with full automation..."
            echo ""
            uv run python automation/guided_setup.py --config "$config_file"
        elif [[ "$guided_option" == "2" ]]; then
            print_status "Running guided setup in dry-run mode..."
            echo ""
            uv run python automation/guided_setup.py --config "$config_file" --dry-run
            echo ""
            print_success "Documentation generated! Check automation/logs/guided_setup_document.md"
        else
            print_warning "Invalid option. Skipping guided setup."
        fi
    else
        print_status "Skipping guided setup."
    fi
}

# Run main function
main "$@"
