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
  preflight/                # maintenance-window + apply-flag gate -> sets apply_cleared
  servicenow/               # open/note/close change records (snow_action)
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
```

Then edit `vars/golden_versions.yml` (your approved software matrix) and
`inventory/hosts.yml` (real management IPs + Secret Server `secret_id` per host).

## Usage

```bash
# Audit everything — safe, default, touches nothing
ansible-playbook playbooks/site.yml

# Audit one platform
ansible-playbook playbooks/site.yml --limit 'nxos,localhost'

# Dry-run a single host
ansible-playbook playbooks/site.yml --limit 'core-sw01,localhost'

# Real remediation: opens a SNOW change, applies inside the window, closes it
ansible-playbook playbooks/site.yml -e apply_updates=true

# Apply AND activate (reload) — highest blast radius, use in a window
ansible-playbook playbooks/site.yml -e apply_updates=true -e reboot_after_upgrade=true
```

Each run prints a compliance table and writes `reports/compliance-<timestamp>.json`.
When using `--limit`, include `localhost` so the controller-side ServiceNow and
reporting plays still run.

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
