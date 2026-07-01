# Safety Model

Firmware changes reboot production infrastructure. This workflow is built so
that an accidental or careless run **cannot** push firmware. The dangerous path
is opt-in and gated three ways.

## The three gates

A device is upgraded only when **all three** are true at once (computed in the
`preflight` role as `apply_cleared`):

1. **Explicit intent** — `apply_updates=true` passed at run time
   (`-e apply_updates=true` or the Semaphore survey field). Default is `false`.
2. **Maintenance window** — the run is inside the configured change window
   (`roles/preflight/defaults/main.yml`: `maint_days`, `maint_start_hour`,
   `maint_end_hour`). Outside the window, apply is refused.
3. **Change ticket** — when `require_change_ticket=true` (the default), a
   ServiceNow change record must exist for the run.

Miss any one → every platform role falls back to **audit only**: it reports
drift but never touches the device.

```
apply_cleared = apply_updates
                AND in_maintenance_window
                AND (change_ticket_exists OR NOT require_change_ticket)
```

## Additional guardrails

- **Backup before change.** Each platform role backs up the running config to
  `backups/<host>/` before staging an image or changing boot variables.
- **Reload is separately gated.** Staging an image is distinct from activating
  it. Reload/reboot only happens when `reboot_after_upgrade=true` (default
  `false`), so you can stage during the day and activate in a later window.
- **ISE is audit-only.** Cisco ISE upgrades are node-persona-aware and are not
  safely automatable as a single module call. The `ise_firmware` role reports
  compliance and recommends the manual runbook; it never pushes.
- **`no_log` on credential handling.** Secret Server responses and credential
  facts are never printed to logs or console.
- **Fail-open to safe.** Any error in the credential or preflight path fails the
  host before the remediation path can run.

## What "apply mode" actually does

1. Play 1 opens a ServiceNow change (state: assess).
2. Each device: audit → if drifted and cleared → backup → stage image / set boot
   → optionally reload → record `upgrade_action` → post a work note to the change.
3. Play 3 builds the report and closes the change.

## Business-hours caution

Per site policy, the maintenance window defaults exclude business hours. Do not
widen `maint_days` / `maint_start_hour` / `maint_end_hour` to cover 9am–5pm
Mon–Fri without an explicit approved change. Reboots during business hours are a
hard stop.
