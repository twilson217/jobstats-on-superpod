# Jobstats Allocation Fix Scripts Comparison

This document compares the three allocation-related fix scripts to clarify what each one addresses.

## Quick Reference

| Script | Error Type | Problematic Code | Root Cause |
|--------|-----------|------------------|------------|
| `fix_jobstats_alloc_cores.py` | Division type error | `alloc / cores` | `alloc` is string, `cores` is int |
| `fix_jobstats_alloc_none.py` | NoneType error | `human_bytes(alloc)` | `alloc` is `None` |
| `fix_jobstats_timelimit.py` | String comparison/multiplication | `timelimitraw` operations | `timelimitraw` is "UNLIMITED" string |

## Detailed Comparison

### 1. fix_jobstats_alloc_cores.py

**Error Messages:**
```
TypeError: unsupported operand type(s) for /: 'str' and 'int'
TypeError: unsupported operand type(s) for /: 'NoneType' and 'NoneType'
ZeroDivisionError: division by zero
```

**Problematic Lines:**
```python
hb_alloc = self.human_bytes(alloc / cores).replace(".0GB", "GB")
                           ^^^^^^^^^^^^^^
report += f"({self.human_bytes(used/cores)}/{hb_alloc}...)"
                               ^^^^^^^^^^^
```

**Root Causes:** 
- `alloc` or `used` is returned as a string from Slurm API
- `cores` is an integer (can't divide string by int)
- `alloc`, `used`, or `cores` may be `None` (can't divide None)
- `cores` may be 0 (division by zero)

**Fix Strategy:**
```python
# Wrap ALL division operations in try-except with proper handling
try:
    alloc_value = float(alloc) if isinstance(alloc, str) else alloc
    hb_alloc = self.human_bytes(alloc_value / cores).replace(".0GB", "GB")
except (ValueError, TypeError, ZeroDivisionError):
    hb_alloc = "Unknown"

# Similarly for used/cores and other division patterns
```

**Script Features:**
- Finds and fixes **ALL** division patterns in the file, not just one
- Handles: `alloc / cores`, `used/cores`, `used / cores`
- Proper indentation detection and preservation

---

### 2. fix_jobstats_alloc_none.py (NEW)

**Error Message:**
```
TypeError: float() argument must be a string or a real number, not 'NoneType'
```

**Problematic Lines:**
```python
# Can occur anywhere human_bytes() is called with None value
hb_alloc = self.human_bytes(alloc).replace(".0GB", "GB")
                           ^^^^^
report += f"{node}: {self.human_bytes(used)}/{hb_alloc}"
                                     ^^^^
```

Where `human_bytes()` contains:
```python
def human_bytes(self, size):
    size = float(size)  # <-- Fails when size is None
    ...
```

**Root Cause:**
- Variables like `alloc` or `used` are `None` (job has missing metric data)
- `human_bytes()` tries to convert `None` to float
- Can happen with any variable passed to `human_bytes()`
- This is a DIFFERENT issue than the division fix above (no `/cores`)

**Fix Strategy:**
```python
# Fix the human_bytes() method itself to handle None
def human_bytes(self, size):
    # Handle None values
    if size is None:
        return "Unknown"
    try:
        size = float(size)
    except (ValueError, TypeError):
        return "Unknown"
    # ... rest of method continues
```

**Why This Approach:**
- Fixes ALL call sites at once (alloc, used, or any future variables)
- Works even when called inside f-strings
- Root cause fix rather than patching each call site

---

### 3. fix_jobstats_timelimit.py

**Error Message:**
```
TypeError: '>' not supported between instances of 'str' and 'int'
TypeError: can't multiply sequence by non-int of type 'int'
```

**Problematic Lines:**
```python
# Line 1: String vs int comparison
if self.js.state == "COMPLETED" and self.js.timelimitraw > 0:
                                    ^^^^^^^^^^^^^^^^^^^^^^^^

# Line 2: String multiplication
hs = self.human_seconds(SECONDS_PER_MINUTE * self.js.timelimitraw)
                                             ^^^^^^^^^^^^^^^^^^^^^
```

**Root Cause:**
- `timelimitraw` is "UNLIMITED" (string) instead of numeric value
- Can't compare string "UNLIMITED" > 0
- Can't multiply constant with string

**Fix Strategy:**
```python
# Line 1: Check for UNLIMITED string first
if self.js.state == "COMPLETED" and str(self.js.timelimitraw) != "UNLIMITED" and self.js.timelimitraw > 0:

# Line 2: Handle UNLIMITED separately
if self.js.timelimitraw == "UNLIMITED" or str(self.js.timelimitraw).upper() == "UNLIMITED":
    hs = "UNLIMITED"
else:
    hs = self.human_seconds(SECONDS_PER_MINUTE * self.js.timelimitraw)
```

---

## When to Use Each Fix

### Use fix_jobstats_alloc_cores.py when you see:
- Error mentions division (`/`)
- Error message: `unsupported operand type(s) for /`
- Line contains: `alloc / cores`

### Use fix_jobstats_alloc_none.py when you see:
- Error mentions `NoneType`
- Error message: `float() argument must be a string or a real number, not 'NoneType'`
- Line contains: `human_bytes(alloc)` WITHOUT division
- Job ID: 167249 (or similar jobs with missing allocation data)

### Use fix_jobstats_timelimit.py when you see:
- Error mentions time limits or "UNLIMITED"
- Error message: `'>' not supported` or `can't multiply sequence`
- Line contains: `timelimitraw`

---

## Example Job Scenarios

| Job Characteristic | Which Fix? | Why? |
|-------------------|------------|------|
| Job with string allocation from Slurm | `alloc_cores` | Division type mismatch |
| Job with no allocation data (None) | `alloc_none` | NoneType error |
| Job with unlimited time limit | `timelimit` | String comparison error |
| Job on node with missing cgroup data | `alloc_none` | Missing data returns None |
| Normal completed job with numeric data | None needed | Works correctly |

---

## Testing Strategy

After applying any fix:

```bash
# Test with the specific job ID that caused the error
jobstats <problematic_job_id>

# Test with a recent job
jobstats $(sacct --format=JobID --noheader -n 1 | head -1)

# Test with debug output
jobstats --debug <job_id>
```

---

## Backup Files

All three scripts create automatic backups:

```bash
/cm/shared/apps/jobstats/output_formatters.py.backup.alloc_cores.YYYYMMDD_HHMMSS
/cm/shared/apps/jobstats/output_formatters.py.backup.alloc_none.YYYYMMDD_HHMMSS
/cm/shared/apps/jobstats/output_formatters.py.backup.timelimit_fix
```

To rollback any fix:
```bash
# Find the backup you want
ls -la /cm/shared/apps/jobstats/output_formatters.py.backup.*

# Restore it
cp /cm/shared/apps/jobstats/output_formatters.py.backup.XXXX /cm/shared/apps/jobstats/output_formatters.py
```

---

## Summary

These are **three distinct issues** that require **three separate fixes**:

1. **Type mismatch in division** → `fix_jobstats_alloc_cores.py`
2. **None value handling** → `fix_jobstats_alloc_none.py` ✨ NEW
3. **String time limits** → `fix_jobstats_timelimit.py`

Each fix can be applied independently, and all three can coexist in the same installation.

