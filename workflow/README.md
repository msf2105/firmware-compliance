# Firmware Compliance Workflow (Ansible)

Multi-platform firmware **audit + guarded remediation** across F5 BIG-IP, Cisco
(ACI, ASA, Catalyst Center/DNAC, IOS/IOS-XE, IOS-XR, ISE, NX-OS, UCS) and Palo
Alto — with credentials pulled at run time from **Delinea Secret Server** and
every change wrapped in a **ServiceNow** change record.

## Safety model (read this first)

Dry-run / audit is the **default**. A real firmware push happens only when ALL
of these are true at once:

1. `apply_updates=true` is passed explicitly (`-e apply_updates=true`)
2. The run is **inside the maintenance window** (see `roles/preflight/defaults/main.yml`)
3. A ServiceNow change ticket exists (when `require_change_ticket=true`, the default)
4. **CAB approval** has been granted on that change ticket (when `require_cab_approval=true`, the default)

Miss any one and every platform role falls back to **audit only** — it reports
drift but never touches the device. Cisco ISE is intentionally **audit-only**
(persona-aware upgrades are not safely one-shot automatable).

Additional guardrails baked into each platform role:
- Running config is **backed up** (to `backups/<host>/`) before any change.
- Reload/activation is gated behind `reboot_after_upgrade` (default `false`).
- All credential handling uses `no_log: true`.

## Layout

```
ansible.cfg                 # yaml stdout, explicit gathering, persistent-conn timeouts
requirements.yml            # collection deps (installed already on this host)
vars/golden_versions.yml    # << EDIT: desired firmware per platform + global switches
inventory/
  hosts.yml                 # << EDIT: your devices; each host needs a secret_id
  group_vars/*.yml          # platform_label per group (report tagging)
playbooks/site.yml          # orchestrator (3 plays: open SNOW -> audit/apply -> report+close)
roles/
  secret_server/            # Delinea: fetch dev_username/dev_password/dev_enable at runtime
  preflight/                # maintenance-window + apply-flag + CAB gate -> sets apply_cleared
  servicenow/               # open/check_approval/note/close change records (snow_action)
  <platform>_firmware/ x10  # facts -> compare vs golden -> backup -> guarded install
  compliance_report/        # aggregate table + reports/compliance-<ts>.json artifact
reports/  backups/          # run artifacts
```

## Setup

Collections are already installed on this host. To reinstall elsewhere:

```bash
ansible-galaxy collection install -r requirements.yml
```

Export the secret-store and ITSM credentials (never stored in the repo):

```bash
export TSS_USERNAME=... TSS_PASSWORD=...            # Delinea Secret Server
export SNOW_INSTANCE=dev12345 SNOW_USERNAME=... SNOW_PASSWORD=...   # ServiceNow
export CISCO_CLIENT_ID=... CISCO_CLIENT_SECRET=... # Cisco Support API (OAuth2)
```

Then edit `vars/golden_versions.yml` (your approved software matrix) and
`inventory/hosts.yml` (real management IPs + Secret Server `secret_id` per host).

## Usage

```bash
# Audit everything — safe, default, touches nothing
ansible-playbook playbooks/site.yml

# Audit one platform
ansible-playbook playbooks/site.yml --limit nxos

# Dry-run a single host
ansible-playbook playbooks/site.yml --limit core-sw01

# Open a change for CAB review (audits all devices, does NOT apply)
ansible-playbook playbooks/site.yml -e apply_updates=true

# Apply after CAB approval (inside maintenance window)
ansible-playbook playbooks/site.yml -e apply_updates=true -e snow_change_number=CHGxxxxxx

# Apply AND activate (reload) — highest blast radius, use in a window
ansible-playbook playbooks/site.yml -e apply_updates=true -e snow_change_number=CHGxxxxxx -e reboot_after_upgrade=true
```

### CAB approval workflow

Changes are now **normal** (CAB-reviewed) rather than **standard** (pre-approved).
This means a real firmware push is a two-run process:

1. **Run 1 (open):** `ansible-playbook playbooks/site.yml -e apply_updates=true`
   - Opens a normal ServiceNow change request
   - Audits all devices (reports drift, touches nothing)
   - Prints the change number (e.g. CHG0123456) for CAB review
   - Adds a work note: "CAB approval is pending"

2. **CAB reviews and approves** the change in ServiceNow (approval = approved)

3. **Run 2 (apply):** `ansible-playbook playbooks/site.yml -e apply_updates=true -e snow_change_number=CHG0123456`
   - Queries the existing change's approval state
   - If approved AND inside the maintenance window → applies firmware
   - If not approved → audits only, adds a work note, does NOT close the change

To bypass CAB approval (e.g. emergency change, dev environment):
`-e require_cab_approval=false`

Each run prints a compliance table and writes `reports/compliance-<timestamp>.json`.

## How credentials flow

`inventory/hosts.yml` carries **no secrets** — only a `secret_id` per host. The
`secret_server` role calls Delinea at run time (authenticating with the
`TSS_*` env vars), pulls that secret's `username`/`password`/`enable-password`
items, and sets host-scoped facts (`dev_username`, `dev_password`, `dev_enable`)
with `no_log`. Platform roles consume those facts for the device connection.

## Notes / limitations

- **ISE** is report-only (see safety model).
- **ACI / DNAC / UCS / PANOS / F5** use HTTP APIs (`ansible_connection: local`);
  the SSH platforms (IOS/XR/NXOS/ASA) use `network_cli`.
- The default maintenance window is a simple same-day check. For overnight
  windows spanning midnight, adjust `roles/preflight/defaults/main.yml` or run
  in two invocations (documented inline).
- This ships with **sample hosts** and **example golden versions** — both must
  be replaced with your real environment before an apply run.

## Version discovery (vendor API integration)

The system queries vendor APIs to discover the latest available software version,
then compares the running version against both the discovered latest and the
golden target. This replaces the old static golden-only check.

### Cisco platforms (IOS, IOS-XR, NX-OS, ASA, ACI, DNAC, ISE, UCS)

Uses the **Cisco Support API — Software Suggestion API**:
- Endpoint: `GET https://api.cisco.com/software/suggestion/v2/suggests?product={PID}`
- Auth: OAuth2 client credentials (`CISCO_CLIENT_ID` / `CISCO_CLIENT_SECRET`)
- Token URL: `https://id.cisco.com/oauth2/default/v1/token`
- Returns Cisco's recommended release (stability/longevity/adoption-based)

Each platform needs a **Cisco Product ID (PID)** in `golden_versions.yml`:
```yaml
ios:
  version: "17.09.05"
  cisco_pid: "C9300-24T"    # your actual device PID
```
The PIDs shipped are examples — replace them with your real device PIDs.

If no Cisco credentials are set, the system falls back to the golden version
(graceful degradation — audit still works, just without latest-version discovery).

API responses are cached for 1 hour in `~/.cache/firmware-compliance/` to avoid
rate-limiting.

### Palo Alto PAN-OS

Uses the **device-local XML API** (no cloud API needed):
- `type=op&cmd=<request><system><software><check></check></software></system></request>`
- Queries the firewall directly for available PAN-OS updates
- The first `<version>` in the response is the latest available release
- Requires the device to have internet access + active support license

### F5 BIG-IP

Uses the **device-local iControl REST API**:
- `GET /mgmt/tm/sys/software/update` with X-F5-Auth-Token
- Reads the `factiveBuildVersion` from the update status
- Requires the device to have internet access + active support license
