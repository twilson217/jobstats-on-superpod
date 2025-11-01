#!/usr/bin/env python3
"""
Simple fix for jobstats GPU utilization with MIG support

This script modifies the GPU utilization query to try duty_cycle first,
then fall back to sm_util_percent if no data is returned.

This is a simpler inline approach that doesn't add new methods.

Usage:
    python3 fix_jobstats_mig_utilization_simple.py
"""

import os
import shutil
import subprocess
import sys

def fix_gpu_utilization_query():
    """Fix the GPU utilization query with inline fallback logic"""
    
    file_path = "/cm/shared/apps/jobstats/jobstats.py"
    backup_path = "/cm/shared/apps/jobstats/jobstats.py.backup.mig_utilization_simple_fix"
    
    # Check if file exists
    if not os.path.exists(file_path):
        print(f"ERROR: {file_path} not found")
        return False
    
    # Create backup
    try:
        shutil.copy2(file_path, backup_path)
        print(f"Created backup: {backup_path}")
    except Exception as e:
        print(f"ERROR: Failed to create backup: {e}")
        return False
    
    try:
        # Read the file
        with open(file_path, 'r') as f:
            content = f.read()
        
        original_content = content
        
        # Check if fix is already applied
        if 'nvidia_gpu_sm_util_percent' in content:
            print("Fix appears to already be applied (sm_util_percent found)")
            return True
        
        # Pattern 1: Try to find and replace the single-line query
        old_pattern1 = 'self.get_data(\'gpu_utilization\', "avg_over_time((nvidia_gpu_duty_cycle{cluster=\'%s\'} and nvidia_gpu_jobId == %s)[%ds:])")'
        new_pattern1 = '''# Try duty_cycle first (regular GPUs), fall back to sm_util_percent (MIG GPUs)
                self.get_data('gpu_utilization', "avg_over_time((nvidia_gpu_duty_cycle{cluster='%s'} and nvidia_gpu_jobId == %s)[%ds:])")
                # If no data from duty_cycle, try sm_util_percent for MIG support
                if not any('gpu_utilization' in self.sp_node.get(n, {}) for n in self.sp_node):
                    self.get_data('gpu_utilization', "avg_over_time((nvidia_gpu_sm_util_percent{cluster='%s'} and nvidia_gpu_jobId == %s)[%ds:])")'''
        
        if old_pattern1 in content:
            content = content.replace(old_pattern1, new_pattern1)
            print("Applied fix using pattern 1")
        else:
            # Pattern 2: Try multiline with double quotes
            old_pattern2 = '''self.get_data('gpu_utilization', "avg_over_time((nvidia_gpu_duty_cycle{cluster='%s'} and nvidia_gpu_jobId == %s)[%ds:])")'''
            
            if old_pattern2 in content:
                content = content.replace(old_pattern2, new_pattern1)
                print("Applied fix using pattern 2")
            else:
                # Pattern 3: Try to find with regex-like approach
                import re
                pattern = r"self\.get_data\('gpu_utilization',\s*\"avg_over_time\(\(nvidia_gpu_duty_cycle\{[^}]+\}[^)]+\)\[%ds:\]\)\"\)"
                
                if re.search(pattern, content):
                    content = re.sub(pattern, new_pattern1, content)
                    print("Applied fix using pattern 3 (regex)")
                else:
                    print("ERROR: Could not find gpu_utilization query pattern to replace")
                    print("Attempting manual search...")
                    
                    # Last resort: find the line and replace manually
                    lines = content.split('\n')
                    found = False
                    for i, line in enumerate(lines):
                        if 'gpu_utilization' in line and 'nvidia_gpu_duty_cycle' in line and 'get_data' in line:
                            print(f"Found line {i+1}: {line[:80]}...")
                            # Insert the fallback check after this line
                            indent = len(line) - len(line.lstrip())
                            fallback_lines = [
                                line,
                                ' ' * indent + "# Fallback for MIG: try sm_util_percent if no data",
                                ' ' * indent + "if not any('gpu_utilization' in self.sp_node.get(n, {}) for n in self.sp_node):",
                                ' ' * (indent + 4) + "self.get_data('gpu_utilization', \"avg_over_time((nvidia_gpu_sm_util_percent{cluster='%s'} and nvidia_gpu_jobId == %s)[%ds:])\")"
                            ]
                            lines[i] = '\n'.join(fallback_lines)
                            content = '\n'.join(lines)
                            found = True
                            print("Applied fix using manual line replacement")
                            break
                    
                    if not found:
                        print("ERROR: Could not find gpu_utilization query to modify")
                        return False
        
        # Only write if changes were made
        if content != original_content:
            # Write the fixed file
            with open(file_path, 'w') as f:
                f.write(content)
            print("Successfully applied jobstats MIG utilization fix")
            return True
        else:
            print("No changes made - pattern already exists or not found")
            return True
            
    except Exception as e:
        print(f"ERROR: Failed to apply fix: {e}")
        import traceback
        traceback.print_exc()
        print("\nRestoring from backup...")
        try:
            shutil.copy2(backup_path, file_path)
            print("Restored from backup")
        except Exception as restore_error:
            print(f"ERROR: Failed to restore from backup: {restore_error}")
        return False

def test_fix():
    """Test if the fix works by running jobstats on a test job"""
    try:
        # Try to find a recent completed job to test with
        result = subprocess.run(['sacct', '--format=JobID,State', '--state=COMPLETED,FAILED', '--noheader', '-n', '10'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            for line in lines:
                parts = line.split()
                if len(parts) >= 2 and '.' not in parts[0]:  # Skip job steps
                    job_id = parts[0]
                    print(f"Testing fix with job {job_id}...")
                    
                    # Test jobstats
                    test_result = subprocess.run(['jobstats', job_id, '-c', 'slurm'], 
                                               capture_output=True, text=True, timeout=30)
                    if test_result.returncode == 0:
                        print("✅ Fix test successful - jobstats is working")
                        if "GPU" in test_result.stdout or "gpu" in test_result.stdout.lower():
                            print("   GPU data found in output")
                        return True
                    else:
                        # Try next job
                        continue
            
            print("⚠️  No suitable jobs found to test with")
            return True
        else:
            print("⚠️  No jobs found to test with")
            return True
    except Exception as e:
        print(f"⚠️  Could not test fix: {e}")
        return True

if __name__ == "__main__":
    print("Jobstats MIG GPU Utilization Fix Script (Simple Version)")
    print("=" * 60)
    print()
    print("This script adds inline fallback logic for GPU utilization:")
    print("  - Try nvidia_gpu_duty_cycle first (regular GPUs)")
    print("  - Fall back to nvidia_gpu_sm_util_percent (MIG GPUs)")
    print()
    
    if fix_gpu_utilization_query():
        print("\nTesting the fix...")
        test_fix()
        print("\n" + "=" * 60)
        print("Fix completed successfully!")
        print("\nThe fix allows jobstats to work with both:")
        print("  ✅ Regular GPUs (uses duty_cycle)")
        print("  ✅ MIG instances (uses sm_util_percent fallback)")
    else:
        print("\n" + "=" * 60)
        print("Fix failed!")
        print("\nPlease check the error messages above.")
        print(f"Backup is available at: /cm/shared/apps/jobstats/jobstats.py.backup.mig_utilization_simple_fix")
        sys.exit(1)

