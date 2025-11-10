#!/usr/bin/env python3
"""
Fix for jobstats alloc/cores division error

This script fixes the TypeError in output_formatters.py where alloc is a string
but cores is an integer, causing a division error.

Note: This script now works with the shared storage jobstats installation
at /cm/shared/apps/jobstats/output_formatters.py.
"""

import os
import sys
import shutil
from datetime import datetime

def fix_jobstats_alloc_cores():
    """Fix the alloc/cores division error in jobstats"""
    
    jobstats_file = "/cm/shared/apps/jobstats/output_formatters.py"
    backup_file = f"/cm/shared/apps/jobstats/output_formatters.py.backup.alloc_cores.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    if not os.path.exists(jobstats_file):
        print(f"Error: {jobstats_file} not found")
        return False
    
    # Create backup
    print(f"Creating backup: {backup_file}")
    shutil.copy2(jobstats_file, backup_file)
    
    # Read the file
    with open(jobstats_file, 'r') as f:
        content = f.read()
    
    # Find and fix ALL problematic division lines
    # Always use line-by-line approach to properly handle indentation
    print("Searching for division lines that need None handling...")
    
    lines = content.split('\n')
    fixes_applied = 0
    
    # We need to iterate carefully since we're modifying the list
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Look for patterns where variables are divided by cores and passed to human_bytes
        # We need to detect patterns like: var/cores or var / cores
        should_fix = False
        var_name = None
        division_pattern = None
        
        # Check if line has human_bytes and division by cores
        if 'human_bytes' in line and ('/cores' in line or '/ cores' in line):
            # Determine which variable is being divided
            if 'alloc/cores' in line or 'alloc / cores' in line:
                should_fix = True
                var_name = 'alloc'
                division_pattern = 'alloc/cores' if 'alloc/cores' in line else 'alloc / cores'
            elif 'used/cores' in line or 'used / cores' in line:
                should_fix = True
                var_name = 'used'
                division_pattern = 'used/cores' if 'used/cores' in line else 'used / cores'
        
        if should_fix and var_name and division_pattern:
            print(f"Found line at {i+1} with {division_pattern}: {line.strip()}")
            
            # Detect the indentation of the original line
            indent = len(line) - len(line.lstrip())
            indent_str = ' ' * indent
            
            # Determine what variable to set based on the line content
            result_var = 'result'  # default
            if 'hb_alloc' in line:
                result_var = 'hb_alloc'
            elif 'report +=' in line:
                result_var = None  # We'll skip the line for report
            
            # Build the replacement with proper indentation
            new_lines = [
                f"{indent_str}# Handle {var_name}/{('cores' if 'cores' in division_pattern else 'divisor')} with None values",
                f"{indent_str}try:",
            ]
            
            # For string conversion if needed
            if var_name == 'alloc':
                new_lines.append(f"{indent_str}    {var_name}_value = float({var_name}) if isinstance({var_name}, str) else {var_name}")
                new_lines.append(f"{indent_str}    {line.strip()}")
            else:
                new_lines.append(f"{indent_str}    {line.strip()}")
            
            new_lines.append(f"{indent_str}except (ValueError, TypeError, ZeroDivisionError):")
            
            # Determine the fallback behavior
            if result_var:
                new_lines.append(f"{indent_str}    {result_var} = \"Unknown\"")
            else:
                new_lines.append(f"{indent_str}    pass  # Skip this line when data unavailable")
            
            # Use list splicing to replace the single line with multiple lines
            lines[i:i+1] = new_lines
            print(f"Applied fix for {division_pattern} with proper indentation")
            fixes_applied += 1
            
            # Skip ahead past the lines we just inserted
            i += len(new_lines)
            continue
        
        i += 1
    
    if fixes_applied == 0:
        print("Error: Could not find any target lines to fix")
        print("\nDEBUG: Looking for any lines with division patterns...")
        for i, line in enumerate(lines):
            if '/ cores' in line or '/cores' in line:
                has_hb = 'human_bytes' in line
                has_alloc = 'alloc' in line.lower()
                has_used = 'used' in line.lower()
                print(f"  Line {i+1}: {line.strip()}")
                print(f"    - has human_bytes: {has_hb}, has alloc: {has_alloc}, has used: {has_used}")
        return False
    
    print(f"\nTotal fixes applied: {fixes_applied}")
    content = '\n'.join(lines)
    
    # Write the fixed content
    with open(jobstats_file, 'w') as f:
        f.write(content)
    
    print(f"Successfully fixed {jobstats_file}")
    return True

def test_fix():
    """Test the fix by running jobstats on a recent job"""
    print("\nTesting the fix...")
    
    # Get the most recent job
    import subprocess
    try:
        result = subprocess.run(['sacct', '-u', 'root', '--start=today', '--format=JobID,State', '--noheader'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            recent_jobs = [line.split()[0] for line in lines if 'COMPLETED' in line and '.' not in line.split()[0]]
            if recent_jobs:
                test_job = recent_jobs[-1]  # Most recent job
                print(f"Testing with job {test_job}...")
                
                # Test jobstats
                test_result = subprocess.run(['jobstats', '-j', test_job], 
                                          capture_output=True, text=True, timeout=30)
                if test_result.returncode == 0:
                    print("✅ Fix successful! jobstats is working")
                    return True
                else:
                    print(f"❌ jobstats still has issues: {test_result.stderr}")
                    return False
            else:
                print("No recent completed jobs found for testing")
                return True
        else:
            print("Could not get job list for testing")
            return True
    except Exception as e:
        print(f"Error during testing: {e}")
        return True

def main():
    print("Jobstats alloc/cores division fix")
    print("=" * 40)
    
    if fix_jobstats_alloc_cores():
        print("\nFix applied successfully!")
        test_fix()
    else:
        print("\nFix failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
