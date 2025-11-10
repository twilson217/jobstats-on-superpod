#!/usr/bin/env python3
"""
Fix for jobstats alloc NoneType error

This script fixes the TypeError in output_formatters.py where alloc is None
when passed to human_bytes(), causing a "float() argument must be a string or 
a real number, not 'NoneType'" error.

Error occurs at:
- Line 30: hb_alloc = self.human_bytes(alloc).replace(".0GB", "GB")
- Line 52 in human_bytes: size = float(size) fails when size is None

Note: This script works with the shared storage jobstats installation
at /cm/shared/apps/jobstats/output_formatters.py.

Usage:
    python3 fix_jobstats_alloc_none.py
"""

import os
import sys
import shutil
from datetime import datetime

def fix_jobstats_alloc_none():
    """Fix the alloc NoneType error in jobstats"""
    
    jobstats_file = "/cm/shared/apps/jobstats/output_formatters.py"
    backup_file = f"/cm/shared/apps/jobstats/output_formatters.py.backup.alloc_none.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    if not os.path.exists(jobstats_file):
        print(f"Error: {jobstats_file} not found")
        return False
    
    # Create backup
    print(f"Creating backup: {backup_file}")
    shutil.copy2(jobstats_file, backup_file)
    
    # Read the file
    with open(jobstats_file, 'r') as f:
        content = f.read()
    
    # Find and fix the human_bytes() function itself to handle None
    # This is better than wrapping every call site
    print("Searching for the human_bytes() function definition...")
    
    lines = content.split('\n')
    found = False
    
    for i, line in enumerate(lines):
        # Look for the human_bytes function definition (both method and function versions)
        if 'def human_bytes' in line and ('size' in line):
            print(f"Found human_bytes() function at line {i+1}: {line.strip()}")
            
            # Look for the line that does size = float(size) or similar conversion
            for j in range(i+1, min(i+30, len(lines))):
                if 'float(size)' in lines[j] and '=' in lines[j]:
                    print(f"Found float conversion at line {j+1}: {lines[j].strip()}")
                    
                    # Detect indentation
                    indent = len(lines[j]) - len(lines[j].lstrip())
                    indent_str = ' ' * indent
                    
                    # Replace with None-safe version
                    new_lines = [
                        f"{indent_str}# Handle None values",
                        f"{indent_str}if size is None:",
                        f"{indent_str}    return \"Unknown\"",
                        f"{indent_str}try:",
                        f"{indent_str}    {lines[j].strip()}",
                        f"{indent_str}except (ValueError, TypeError):",
                        f"{indent_str}    return \"Unknown\""
                    ]
                    
                    # Use list splicing to replace the single line with multiple lines
                    lines[j:j+1] = new_lines
                    content = '\n'.join(lines)
                    print("Applied fix to human_bytes() function")
                    found = True
                    break
            
            if found:
                break
    
    if not found:
        print("Error: Could not find the human_bytes() function or float conversion line")
        print("Searching for 'def human_bytes' in file...")
        for i, line in enumerate(lines):
            if 'human_bytes' in line and 'def ' in line:
                print(f"  Line {i+1}: {line.strip()}")
        
        print("\nSearching for 'float(size)' in file...")
        for i, line in enumerate(lines):
            if 'float(size)' in line:
                print(f"  Line {i+1}: {line.strip()}")
        return False
    
    # Write the fixed content
    with open(jobstats_file, 'w') as f:
        f.write(content)
    
    print(f"Successfully fixed {jobstats_file}")
    return True

def test_fix(job_id=None):
    """Test the fix by running jobstats on a specific job or recent job"""
    print("\nTesting the fix...")
    
    import subprocess
    
    if job_id:
        test_job = job_id
        print(f"Testing with job {test_job}...")
    else:
        # Get a recent job
        try:
            result = subprocess.run(['sacct', '--format=JobID,State', '--noheader', '-n', '10'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                # Get the first job ID without a dot (main job, not job step)
                for line in lines:
                    parts = line.split()
                    if parts and '.' not in parts[0]:
                        test_job = parts[0]
                        break
                else:
                    print("No suitable test job found")
                    return True
                print(f"Testing with job {test_job}...")
            else:
                print("Could not get job list for testing")
                return True
        except Exception as e:
            print(f"Error getting test job: {e}")
            return True
    
    # Test jobstats
    try:
        test_result = subprocess.run(['jobstats', test_job], 
                                   capture_output=True, text=True, timeout=30)
        if test_result.returncode == 0:
            print("✅ Fix successful! jobstats is working")
            print("\nOutput sample:")
            print(test_result.stdout[:500])  # Show first 500 chars
            return True
        else:
            print(f"❌ jobstats still has issues")
            print(f"stderr: {test_result.stderr}")
            return False
    except Exception as e:
        print(f"Error during testing: {e}")
        return True

def main():
    print("Jobstats alloc NoneType fix")
    print("=" * 40)
    
    # Check if a specific job ID was provided as argument
    test_job = None
    if len(sys.argv) > 1:
        test_job = sys.argv[1]
        print(f"Will test with job ID: {test_job}")
    
    if fix_jobstats_alloc_none():
        print("\nFix applied successfully!")
        test_fix(test_job)
    else:
        print("\nFix failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()

