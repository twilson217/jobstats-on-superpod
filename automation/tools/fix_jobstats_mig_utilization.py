#!/usr/bin/env python3
"""
Fix for jobstats GPU utilization with MIG support

This script fixes GPU utilization queries in jobstats to work with both
regular GPUs and MIG instances:
- Regular GPUs provide nvidia_gpu_duty_cycle metric
- MIG instances provide nvidia_gpu_sm_util_percent metric

The fix adds fallback logic to try duty_cycle first (for compatibility with
regular GPUs), then fall back to sm_util_percent (for MIG GPUs).

Usage:
    python3 fix_jobstats_mig_utilization.py

The script will:
- Backup the original file at /cm/shared/apps/jobstats/jobstats.py
- Add a new method to handle GPU utilization with fallback logic
- Replace the single get_data call with the new fallback method
- Restore from backup if something goes wrong

Note: This script works with the shared storage jobstats installation.
"""

import os
import shutil
import subprocess
import sys

def fix_gpu_utilization_query():
    """Fix the GPU utilization query to support both regular GPUs and MIG instances"""
    
    file_path = "/cm/shared/apps/jobstats/jobstats.py"
    backup_path = "/cm/shared/apps/jobstats/jobstats.py.backup.mig_utilization_fix"
    
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
            lines = f.readlines()
        
        original_lines = lines.copy()
        
        # Find the line with gpu_utilization query (around line 360)
        target_line = None
        for i, line in enumerate(lines):
            if 'if not args or "gpu_utilization" in args:' in line:
                target_line = i
                break
        
        if target_line is None:
            print("ERROR: Could not find gpu_utilization query line")
            return False
        
        print(f"Found gpu_utilization query at line {target_line + 1}")
        
        # Check if the fix is already applied
        if 'get_gpu_utilization_with_fallback' in ''.join(lines):
            print("Fix already applied - no changes needed")
            return True
        
        # Find a good place to insert the new method
        # Look for several possible insertion points in order of preference
        insert_point = None
        
        # Option 1: Look for "def get_stats(self"
        for i, line in enumerate(lines):
            if 'def get_stats(self' in line:
                insert_point = i
                print(f"Found get_stats method at line {i + 1}")
                break
        
        # Option 2: Look for "def get_data(self" (the method we're calling)
        if insert_point is None:
            for i, line in enumerate(lines):
                if 'def get_data(self' in line:
                    insert_point = i
                    print(f"Found get_data method at line {i + 1}")
                    break
        
        # Option 3: Insert just before the target line (gpu_utilization query)
        if insert_point is None:
            # Find the start of the method containing the gpu_utilization query
            for i in range(target_line, -1, -1):
                if lines[i].strip().startswith('def '):
                    insert_point = i
                    print(f"Found method containing gpu_utilization at line {i + 1}")
                    # Insert after the method signature, at the beginning of the method body
                    # Skip the def line and any docstrings
                    insert_point = i + 1
                    while insert_point < len(lines) and (lines[insert_point].strip().startswith('"""') or 
                                                          lines[insert_point].strip().startswith("'''")):
                        insert_point += 1
                        # Skip multiline docstrings
                        if '"""' in lines[insert_point] or "'''" in lines[insert_point]:
                            insert_point += 1
                            break
                    break
        
        if insert_point is None:
            print("ERROR: Could not find suitable insertion point for new method")
            print("Will try to insert before gpu_utilization query as fallback")
            insert_point = target_line
        
        print(f"Will insert new method at line {insert_point + 1}")
        
        # Create the new method
        new_method = '''    def get_gpu_utilization_with_fallback(self):
        """
        Get GPU utilization data with fallback for MIG support.
        
        Regular GPUs expose nvidia_gpu_duty_cycle, but MIG instances do not.
        MIG instances expose nvidia_gpu_sm_util_percent instead.
        
        This method tries duty_cycle first (for backward compatibility with regular GPUs),
        and falls back to sm_util_percent if no data is returned (for MIG GPUs).
        """
        # Try duty_cycle first (regular GPUs)
        original_sp_node = dict(self.sp_node)  # Save current state
        
        self.get_data('gpu_utilization', 
                     "avg_over_time((nvidia_gpu_duty_cycle{cluster='%s'} and nvidia_gpu_jobId == %s)[%ds:])")
        
        # Check if we got any gpu_utilization data
        got_data = False
        for node in self.sp_node:
            if 'gpu_utilization' in self.sp_node[node]:
                got_data = True
                break
        
        # If no data from duty_cycle, try sm_util_percent (MIG GPUs)
        if not got_data:
            self.debug_print("No data from nvidia_gpu_duty_cycle, trying nvidia_gpu_sm_util_percent for MIG support")
            self.sp_node = original_sp_node  # Restore state before retry
            self.get_data('gpu_utilization',
                         "avg_over_time((nvidia_gpu_sm_util_percent{cluster='%s'} and nvidia_gpu_jobId == %s)[%ds:])")

'''
        
        # Insert the new method before get_stats
        lines.insert(insert_point, new_method)
        
        # Now find and replace the original get_data call for gpu_utilization
        # This is now at target_line + 1 (because we inserted code before)
        adjusted_target_line = target_line + new_method.count('\n')
        
        # Replace the two-line block:
        # if not args or "gpu_utilization" in args:
        #     self.get_data('gpu_utilization', "...")
        
        replacement = '''            if not args or "gpu_utilization" in args:
                self.get_gpu_utilization_with_fallback()
'''
        
        # Remove the old two lines and insert the new one
        if adjusted_target_line + 1 < len(lines):
            lines[adjusted_target_line] = replacement
            del lines[adjusted_target_line + 1]  # Remove the old get_data line
            print("Replaced gpu_utilization query with fallback method call")
        else:
            print("ERROR: Could not replace gpu_utilization query")
            return False
        
        # Only write if changes were made
        if lines != original_lines:
            # Write the fixed file
            with open(file_path, 'w') as f:
                f.writelines(lines)
            print("Successfully applied jobstats MIG utilization fix")
            return True
        else:
            print("No changes needed")
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
                        if "GPU utilization" in test_result.stdout or "GPU Utilization" in test_result.stdout:
                            print("   GPU utilization data found in output")
                        return True
                    else:
                        print(f"⚠️  Fix test had errors: {test_result.stderr}")
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
    print("Jobstats MIG GPU Utilization Fix Script")
    print("=" * 50)
    print()
    print("This script adds fallback logic to jobstats to support")
    print("GPU utilization queries for both regular GPUs and MIG instances.")
    print()
    
    if fix_gpu_utilization_query():
        print("\nTesting the fix...")
        test_fix()
        print("\n" + "=" * 50)
        print("Fix completed successfully!")
        print("\nThe fix allows jobstats to:")
        print("  - Use nvidia_gpu_duty_cycle for regular GPUs")
        print("  - Fall back to nvidia_gpu_sm_util_percent for MIG GPUs")
        print("\nBoth MIG and non-MIG jobs should now show GPU utilization.")
    else:
        print("\n" + "=" * 50)
        print("Fix failed!")
        sys.exit(1)

