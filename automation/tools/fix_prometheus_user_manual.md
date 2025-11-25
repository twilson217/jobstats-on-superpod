# Fix Prometheus User - Manual Steps (BCM SuperPOD)

This document provides step-by-step instructions to fix the prometheus user issue on BCM-managed DGX nodes where the user was created with a regular UID (>= 1000) instead of a system UID (< 1000).

## Problem Description

When the prometheus user is created without the `--system` flag, it gets assigned a regular UID (typically 1000+). This causes:

1. **UID conflicts** with BCM LDAP/OpenLDAP users that also start at UID 1000+
2. **BCM rogueprocess healthcheck** flags the jobstats exporters as rogue processes
3. The healthcheck considers processes with UID >= UID_MIN (1000) as potentially rogue unless explicitly whitelisted

## Important: BCM Software Image Approach

In a BCM SuperPOD environment, DGX nodes are provisioned from software images. **Do NOT attempt to fix this directly on the DGX nodes** - the fix must be applied to the software image and then pushed to the nodes.

**Why?**
- Direct changes to nodes will be overwritten when the image is next pushed
- UID conflicts with LDAP users can cause problems when modifying users directly on nodes
- The software image approach ensures all nodes get the fix consistently

## Prerequisites

- Root access to BCM head node
- Knowledge of which software image category your DGX nodes use
- The `cm-chroot-sw-img` tool available

## Step-by-Step Instructions

### Step 1: Identify the Software Image

First, determine which software image is used by your DGX nodes:

```bash
# From BCM head node, check which image a DGX node uses
cmsh -c "device;use dgx-01;get softwareimage"
```

Or list all categories and their images:

```bash
cmsh -c "category;foreach * (get softwareimage)"
```

Note the software image name (e.g., `dgx-compute-image`).

### Step 2: Check Current Prometheus User in the Image

Enter the software image chroot and check the current prometheus user:

```bash
# Enter the software image chroot
cm-chroot-sw-img <image-name>

# Check prometheus user status
id prometheus
```

**Expected output (if problem exists):**
```
uid=1001(prometheus) gid=1001(prometheus) groups=1001(prometheus)
```

If the UID is already below 1000 (e.g., `uid=998`), no fix is needed. Exit with `exit`.

### Step 3: Delete the Current Prometheus User (in chroot)

While still in the chroot:

```bash
# Delete the prometheus user
userdel prometheus
```

### Step 4: Clean Up the Prometheus Group (in chroot)

Check if the prometheus group still exists:

```bash
getent group prometheus
```

If it exists, remove it:

```bash
# Try groupdel first
groupdel prometheus 2>/dev/null || true

# If that fails, remove directly from /etc/group
sed -i '/^prometheus:/d' /etc/group
```

### Step 5: Create Prometheus as a System User (in chroot)

Create the prometheus user with the `--system` flag:

```bash
useradd --system --no-create-home --shell /bin/false prometheus
```

Verify the new UID is below 1000:

```bash
id prometheus
```

**Expected output:**
```
uid=998(prometheus) gid=998(prometheus) groups=998(prometheus)
```

### Step 6: Exit the Chroot

```bash
exit
```

### Step 7: Push the Updated Image to DGX Nodes

Use cmsh to push the updated software image to the affected nodes:

```bash
# Push to all nodes in a category (recommended)
cmsh -c "device;imageupdate -c <category-name> -w --wait"

# Or push to specific nodes
cmsh -c "device;imageupdate -n dgx-01,dgx-02,dgx-03 -w --wait"
```

**Note:** The `-w --wait` flags ensure the command waits for the update to complete.

**Alternative:** You can also reboot the nodes to pick up the new image:

```bash
cmsh -c "device;reboot -c <category-name>"
```

### Step 8: Verify the Fix on DGX Nodes

After the image update completes, verify the fix:

```bash
# Check prometheus user on a DGX node
ssh dgx-01 "id prometheus"
# Should show uid < 1000

# Check services are running
ssh dgx-01 "systemctl status cgroup_exporter nvidia_gpu_exporter node_exporter"

# Check processes are running with correct UID
ssh dgx-01 "ps -eo uid,user,comm | grep -E 'cgroup_exporter|nvidia_gpu|node_exporter'"
# Should show UID < 1000 (e.g., 998)
```

### Step 9: Verify BCM Healthcheck Passes

Run the rogueprocess healthcheck to confirm it passes:

```bash
# On the DGX node
ssh dgx-01 "/cm/local/apps/cmd/scripts/healthchecks/rogueprocess"
```

**Expected output:**
```
PASS
```

Or check via cmsh from the BCM head node:

```bash
cmsh -c "device;use dgx-01;latesthealthdata"
```

## Quick Reference: Complete Chroot Commands

Here's the complete sequence of commands to run inside the software image chroot:

```bash
# Enter chroot
cm-chroot-sw-img <image-name>

# Fix prometheus user
userdel prometheus 2>/dev/null || true
sed -i '/^prometheus:/d' /etc/group
useradd --system --no-create-home --shell /bin/false prometheus

# Verify
id prometheus

# Exit
exit
```

Then push the image:

```bash
cmsh -c "device;imageupdate -c <category-name> -w --wait"
```

## Troubleshooting

### Issue: "userdel: user prometheus is currently used by process XXX" (in chroot)

This shouldn't happen in the chroot environment since no services are running. If it does:

```bash
# Inside chroot, just force remove from passwd
sed -i '/^prometheus:/d' /etc/passwd
sed -i '/^prometheus:/d' /etc/group
```

### Issue: "useradd: group prometheus exists" (in chroot)

**Solution:** The prometheus group exists from a previous user. Remove it first:

```bash
# In chroot
sed -i '/^prometheus:/d' /etc/group
useradd --system --no-create-home --shell /bin/false prometheus
```

### Issue: Services fail to start after image update

**Solution:** SSH to the node and check the journal:

```bash
ssh dgx-01 "journalctl -u cgroup_exporter -n 50"
```

Common fixes:
```bash
# Ensure binaries are executable
ssh dgx-01 "chmod +x /usr/local/bin/cgroup_exporter"
ssh dgx-01 "chmod +x /usr/local/bin/nvidia_gpu_prometheus_exporter"
ssh dgx-01 "chmod +x /usr/local/bin/node_exporter"

# Restart services
ssh dgx-01 "systemctl restart cgroup_exporter nvidia_gpu_exporter node_exporter"
```

### Issue: Rogueprocess healthcheck still fails after image update

**Solution:** Verify the services are running with the correct UID:

```bash
ssh dgx-01 "ps -eo uid,user,comm | grep -E 'exporter'"
```

If UID is still >= 1000, the image update didn't apply correctly. Check:

```bash
# Verify prometheus user on the node
ssh dgx-01 "id prometheus"
ssh dgx-01 "grep prometheus /etc/passwd"

# Compare with the software image
cm-chroot-sw-img <image-name>
id prometheus
exit
```

If they don't match, try rebooting the node to force a fresh image load:

```bash
cmsh -c "device;use dgx-01;reboot"
```

### Issue: UID conflict with LDAP user when applying fix directly to node

This is why we recommend the software image approach. If you tried to fix directly on a node:

1. The prometheus user in `/etc/passwd` conflicts with an LDAP user with the same UID
2. Commands like `userdel` or `useradd` may behave unexpectedly

**Solution:** Apply the fix to the software image instead (see main instructions above).

## Understanding the BCM Rogueprocess Healthcheck

The BCM rogueprocess healthcheck (`/cm/local/apps/cmd/scripts/healthchecks/rogueprocess`) flags processes as "rogue" if:

1. Process runs as a user with UID >= UID_MIN (typically 1000)
2. Process is NOT in the legitimate users list
3. Process path/name is NOT in the legitimate process list

**Why system users (UID < 1000) are not flagged:**
```python
def has_legit_users(process):
    return (process["uname"] in rogueprocess.legitUsers) or \
           (UID_MIN is not None and process["uid"] < UID_MIN)
```

By creating prometheus as a system user (UID < 1000), the exporters automatically pass this check.

## Prevention

To prevent this issue in future deployments, ensure the `useradd` command includes the `--system` flag:

```bash
# Correct way to create prometheus user
useradd --system --no-create-home --shell /bin/false prometheus
```

The `guided_setup.py` script has been updated to use the `--system` flag automatically.

## What About the Prometheus Server?

In a SuperPOD environment, the Prometheus server is typically:
- Not a BCM-managed DGX node
- Not subject to the BCM rogueprocess healthcheck
- A separate VM or dedicated server

If your Prometheus server IS a BCM-managed node and you need to fix it, the same software image approach applies. Additionally, you'll need to fix ownership of the data directory:

```bash
# In the chroot (after fixing the user)
chown -R prometheus:prometheus /var/lib/prometheus
```

## Related Documentation

- [BCM Rogueprocess Healthcheck](/cm/local/apps/cmd/scripts/healthchecks/rogueprocess)
- [Rogueprocess Config](/cm/local/apps/cmd/scripts/healthchecks/configfiles/rogueprocess.py)
- [Guided Setup Script](../guided_setup.py)
- [BCM cm-chroot-sw-img Documentation](https://support.brightcomputing.com/)

