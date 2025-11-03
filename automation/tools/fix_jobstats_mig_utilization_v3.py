#!/usr/bin/env python3
"""
Enhanced MIG GPU Utilization Fix for Jobstats (v3 - Fixed)
===========================================================

This version properly handles the code replacement without syntax errors.

Three-tier fallback for GPU utilization:
1. nvidia_gpu_duty_cycle (traditional GPUs)
2. nvidia_gpu_graphics_util_percent (Hopper+ GPUs with GPM, including MIG)
3. nvidia_gpu_sm_util_percent (fallback for MIG without GPM)

Usage:
    sudo python3 fix_jobstats_mig_utilization_v3.py [--dry-run]

CRITICAL WARNING:
================
DO NOT change nvidia_gpu_jobId to nvidia_gpu_jobid (lowercase)!

nvidia_gpu_jobId (with capital I) is the CORRECT metric name exposed by
the nvidia_gpu_prometheus_exporter. It's used in PromQL queries like:
  nvidia_gpu_duty_cycle{cluster='slurm'} and nvidia_gpu_jobId == 167506

Changing to lowercase will break all GPU utilization queries!
This script intentionally preserves the capital I.
"""

import os
import sys
import shutil
import re
from datetime import datetime

def backup_file(filepath):
    """Create timestamped backup of the original file"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{filepath}.backup.{timestamp}"
    shutil.copy2(filepath, backup_path)
    print(f"✅ Created backup: {backup_path}")
    return backup_path

def apply_mig_fix(filepath, dry_run=False):
    """Apply MIG utilization fix with three-tier fallback to jobstats.py"""
    
    print(f"\n{'='*60}")
    print(f"Enhanced MIG GPU Utilization Fix for Jobstats (v3)")
    print(f"{'='*60}\n")
    
    if not os.path.exists(filepath):
        print(f"❌ Error: File not found: {filepath}")
        return False
    
    print(f"Target file: {filepath}")
    print(f"Dry run: {dry_run}")
    print()
    
    # Read the original file
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    original_content = ''.join(lines)
    changes_made = []
    
    # Track if we found and replaced the gpu_utilization line
    found_gpu_util = False
    new_lines = []
    
    for i, line in enumerate(lines):
        # Replace gpu_utilization line with multi-tier fallback
        if "self.get_data('gpu_utilization'," in line and 'nvidia_gpu_duty_cycle' in line:
            found_gpu_util = True
            changes_made.append("Added three-tier GPU utilization fallback")
            
            # Get the indentation from the original line
            indent = len(line) - len(line.lstrip())
            indent_str = ' ' * indent
            
            # Replace this single line with our multi-line fallback logic
            # NOTE: get_data() does the string formatting internally, so we just pass the template
            # IMPORTANT: Keep nvidia_gpu_jobId with capital I - it's a metric name, not a label
            # NOTE: get_data() stores results in self.sp_node[node]['gpu_utilization'], not self.data
            # NOTE: GPM metrics (graphics_util, sm_util) are stored as 0-1 range, must multiply by 100
            new_code = f'''{indent_str}# Three-tier fallback for GPU utilization (duty_cycle → graphics_util → sm_util)
{indent_str}# Try duty_cycle first (regular GPUs) - stored as 0-100 range
{indent_str}self.get_data('gpu_utilization', "avg_over_time((nvidia_gpu_duty_cycle{{cluster='%s'}} and nvidia_gpu_jobId == %s)[%ds:])")
{indent_str}
{indent_str}# Check if any node has gpu_utilization data (get_data stores in self.sp_node)
{indent_str}has_gpu_util_data = any('gpu_utilization' in node_data and node_data['gpu_utilization'] for node_data in self.sp_node.values())
{indent_str}
{indent_str}# If no results, try graphics_util_percent (Hopper+ with GPM, including MIG)
{indent_str}if not has_gpu_util_data:
{indent_str}    if self.debug:
{indent_str}        print("DEBUG: duty_cycle not available, trying graphics_util_percent", file=sys.stderr)
{indent_str}    # NOTE: graphics_util_percent is stored as 0-1 range, multiply by 100 to match duty_cycle scale
{indent_str}    self.get_data('gpu_utilization', "avg_over_time((nvidia_gpu_graphics_util_percent{{cluster='%s'}} and nvidia_gpu_jobId == %s)[%ds:]) * 100")
{indent_str}    has_gpu_util_data = any('gpu_utilization' in node_data and node_data['gpu_utilization'] for node_data in self.sp_node.values())
{indent_str}    
{indent_str}    # If still no results, try sm_util_percent (fallback for MIG without GPM)
{indent_str}    if not has_gpu_util_data:
{indent_str}        if self.debug:
{indent_str}            print("DEBUG: graphics_util_percent not available, trying sm_util_percent", file=sys.stderr)
{indent_str}        # NOTE: sm_util_percent is also stored as 0-1 range, multiply by 100
{indent_str}        self.get_data('gpu_utilization', "avg_over_time((nvidia_gpu_sm_util_percent{{cluster='%s'}} and nvidia_gpu_jobId == %s)[%ds:]) * 100")
{indent_str}        if self.debug:
{indent_str}            has_gpu_util_data = any('gpu_utilization' in node_data and node_data['gpu_utilization'] for node_data in self.sp_node.values())
{indent_str}            if has_gpu_util_data:
{indent_str}                print("DEBUG: Using sm_util_percent (SM hardware utilization)", file=sys.stderr)
{indent_str}    elif self.debug:
{indent_str}        print("DEBUG: Using graphics_util_percent (compute/graphics active time)", file=sys.stderr)
{indent_str}elif self.debug:
{indent_str}    print("DEBUG: Using duty_cycle (standard GPU utilization)", file=sys.stderr)
'''
            new_lines.append(new_code)
            continue  # Skip adding the original line
        
        new_lines.append(line)
    
    if not found_gpu_util:
        print("❌ Could not find gpu_utilization line to replace")
        print("   The file may have been modified already or has unexpected format")
        return False
    
    if not changes_made:
        print("\n❌ No changes were made")
        return False
    
    new_content = ''.join(new_lines)
    
    print(f"\n{'='*60}")
    print("Summary of Changes:")
    print(f"{'='*60}")
    for i, change in enumerate(changes_made, 1):
        print(f"{i}. {change}")
    print(f"{'='*60}\n")
    
    if dry_run:
        print("🔍 DRY RUN - No files were modified")
        print("\nPreview of first change:")
        print("-" * 60)
        # Show context around the change
        for i, line in enumerate(new_lines[355:390], start=356):
            print(f"{i:3}: {line}", end='')
        return True
    
    # Create backup
    backup_path = backup_file(filepath)
    
    # Write the modified content
    try:
        with open(filepath, 'w') as f:
            f.write(new_content)
        print(f"✅ Successfully updated {filepath}")
        print(f"\n📝 Original backed up to: {backup_path}")
        print("\n✅ Done! Test with: jobstats --debug <jobid>")
        print("\nLook for DEBUG lines showing which metric was used:")
        print("  - 'Using duty_cycle' = regular GPU")
        print("  - 'Using graphics_util_percent' = MIG with GPM (GOOD!)")
        print("  - 'Using sm_util_percent' = MIG without GPM")
        return True
    except Exception as e:
        print(f"❌ Error writing file: {e}")
        print(f"   Restoring from backup: {backup_path}")
        shutil.copy2(backup_path, filepath)
        return False

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Apply enhanced MIG GPU utilization fix to jobstats.py (v3 - fixed syntax)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Apply the fix
  sudo python3 fix_jobstats_mig_utilization_v3.py
  
  # Preview changes
  python3 fix_jobstats_mig_utilization_v3.py --dry-run
  
  # Custom location
  python3 fix_jobstats_mig_utilization_v3.py --file /path/to/jobstats.py
        '''
    )
    
    parser.add_argument(
        '--file',
        default='/cm/shared/apps/jobstats/jobstats.py',
        help='Path to jobstats.py'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without modifying files'
    )
    
    args = parser.parse_args()
    
    if not os.path.exists(args.file):
        print(f"❌ Error: File not found: {args.file}")
        sys.exit(1)
    
    if not args.dry_run and not os.access(args.file, os.W_OK):
        print(f"❌ Error: No write permission for {args.file}")
        print("Try running with sudo:")
        print(f"  sudo python3 {sys.argv[0]} --file {args.file}")
        sys.exit(1)
    
    success = apply_mig_fix(args.file, dry_run=args.dry_run)
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()

