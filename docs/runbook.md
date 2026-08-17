# Runbook

Operating procedures for the firmware compliance workflow. All commands run from
the `workflow/` directory unless noted.

## Prerequisites

```bash
# collections (already present on the eve-ng server)
ansible-galaxy collection install -r requirements.yml
# Secret Server SDK for the community.general.tss lookup
pip install python-tss-sdk
```

Export credentials (never stored in the repo):

```bash
export TSS_BASE_URL='https://secretserver.example.com/SecretServer'
export TSS_USERNAME='svc-ansible'
export TSS_PASSWORD='<secret-server-password>'   # reference via env var, don't paste literals
export SNOW_INSTANCE='dev12345'
export SNOW_USERNAME='svc-ansible'
export SNOW_PASSWORD='<servicenow-password>'
```

## 1. Audit everything (safe, default)

```bash
ansible-playbook playbooks/site.yml
```

Touches nothing. Prints a compliance table and writes
`reports/compliance-<timestamp>.json`.

## 2. Audit a single platform or host

```bash
ansible-playbook playbooks/site.yml --limit 'nxos,localhost'
ansible-playbook playbooks/site.yml --limit 'core-sw01,localhost'
```

Always include `localhost` in scoped limits. The ServiceNow and report plays run
on the controller; excluding it would skip those controller-side steps.

## 3. Remediate (real firmware push)

Only inside the maintenance window. Opens/closes a ServiceNow change automatically.

```bash
ansible-playbook playbooks/site.yml -e apply_updates=true
```

Stage images without activating (defer the reload to a later window):

```bash
ansible-playbook playbooks/site.yml -e apply_updates=true -e reboot_after_upgrade=false
```

Stage **and** reload (highest blast radius):

```bash
ansible-playbook playbooks/site.yml -e apply_updates=true -e reboot_after_upgrade=true
```

## 4. Override the maintenance window (emergency change)

Requires an approved emergency change. Widen or shift the window with extra-vars:

```bash
ansible-playbook playbooks/site.yml -e apply_updates=true \
  -e '{"maint_days":[1,2,3,4,5],"maint_start_hour":0,"maint_end_hour":24}'
```

## 5. Roll back

Each platform role backs up running config to `backups/<host>/` before changes.
For boot-variable platforms (IOS/ASA), restore the previous boot statement and
reload. For install-based platforms (NX-OS/IOS-XR), re-point to the prior image.
ACI/DNAC/UCS/PANOS/F5 roll back via their respective management planes. Always
verify reachability after a reload before declaring success.

## 6. Reading the report

- Console: a table with `[OK]` / `[DRIFT]` per host and a compliant count.
- Artifact: `reports/compliance-<timestamp>.json` — machine-readable, includes
  mode, change number, and per-host running/target/compliant/action.

## Pre-flight checklist before an apply run

- [ ] Golden versions in `vars/golden_versions.yml` match the approved matrix
- [ ] `inventory/hosts.yml` has real hosts + correct `secret_id` per device
- [ ] `TSS_*` and `SNOW_*` env vars exported and valid
- [ ] Inside (or explicitly overriding) the maintenance window
- [ ] Ran an audit first and reviewed the drift report
