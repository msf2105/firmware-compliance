# Architecture

## Overview

The workflow is a single Ansible playbook (`workflow/playbooks/site.yml`) made of
three plays, backed by a set of small, single-responsibility roles. Every
platform role follows the same shape so the system is uniform and predictable.

```
Play 1 (localhost)   Open a ServiceNow change request        [apply mode only]
Play 2 (devices)     Per host:
                       secret_server  -> fetch creds from Secret Server
                       preflight      -> evaluate the safety gate
                       <platform>_firmware -> audit, and remediate if cleared
                       servicenow     -> post per-device work note   [apply mode]
Play 3 (localhost)   compliance_report -> table + JSON artifact
                     Close the ServiceNow change                [apply mode only]
```

## Roles

| Role | Responsibility |
|------|----------------|
| `secret_server` | Resolve `dev_username` / `dev_password` / `dev_enable` from Secret Server via the `community.general.tss` lookup, using a per-host `secret_id`. Never writes secrets to disk (`no_log`). |
| `preflight` | Compute `apply_cleared` — true only inside the maintenance window with an explicit apply flag (and a change ticket when required). |
| `<platform>_firmware` (×10) | Gather facts → compare running vs golden → set `running_version`/`target_version`/`compliant` → back up + install **only** when `apply_cleared`. |
| `servicenow` | Open / note / close change records (`snow_action`). |
| `compliance_report` | Aggregate all hosts into a printed table and a JSON artifact under `reports/`. |

## The per-platform contract

Every `<platform>_firmware` role sets the same facts, which is what lets the
report and ServiceNow notes work generically:

- `running_version` — what's on the device now
- `target_version` — the golden target for that platform
- `compliant` — boolean, `running == target`
- `upgrade_action` — set only when a change was actually staged/applied

Remediation is always guarded by two conditions: `not compliant` **and**
`apply_cleared`. In dry-run, the audit facts are still set — you get the full
drift report without touching anything.

## Data / control flow

1. **Inventory** carries no secrets — only `ansible_host` and a `secret_id` per
   device, plus per-group connection vars (network_os, connection type).
2. **Golden versions** (`vars/golden_versions.yml`) define the approved matrix
   and the global toggles (`apply_updates`, `require_change_ticket`,
   `reboot_after_upgrade`).
3. **Secrets** for Secret Server and ServiceNow arrive as environment variables
   (`TSS_*`, `SNOW_*`) — injected by Semaphore's environment or exported in the
   shell. Nothing sensitive lives in the repo.

## Design principles

- **Dry-run by default.** The dangerous path is opt-in and multiply-gated.
- **Backup before change.** Running config is saved before any mutation.
- **Idempotent audit.** Re-running in audit mode is always safe and side-effect free.
- **Secrets out of the repo.** Credentials are referenced, never stored.
- **Uniform roles.** One shape for every platform keeps it maintainable.
