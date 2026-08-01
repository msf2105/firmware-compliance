# ServiceNow Integration

Every real firmware change is wrapped in a ServiceNow change record for audit
and approval trail. In audit/dry-run mode, no ServiceNow interaction happens.

## Flow

| Phase | `snow_action` | What it does |
|-------|--------------|--------------|
| Play 1 (apply mode) | `open` | Create a Change Request (type standard, state assess). Registers `snow_change_sys_id` and `snow_change_number`. |
| Play 2 (per device) | `note` | Add a work note with the device's running/target/compliant/action. |
| Play 3 (apply mode) | `close` | Move the change to closed with an outcome code. |

## Requirements

- Ansible collection: `servicenow.itsm`
- Environment variables:
  - `SNOW_INSTANCE` — the instance name (e.g. `dev12345`, not the full URL)
  - `SNOW_USERNAME` / `SNOW_PASSWORD` — a service account with change_management
  - `SNOW_ASSIGNMENT_GROUP` — assignment group used for change state transitions

## Behavior by mode

- **Audit / dry-run** (`apply_updates=false`): Play 1's open task is skipped, so
  no `snow_change_*` facts exist. The per-device note tasks and the close task
  are conditioned on those facts and skip cleanly. Result: zero ServiceNow
  writes during an audit.
- **Apply** (`apply_updates=true` + `require_change_ticket=true`): a change is
  opened before any device is touched, each device posts a note, and the change
  is closed at the end.

## Customization

- Change **type / state / assignment group**: set `snow_assignment_group` or
  export `SNOW_ASSIGNMENT_GROUP`. The `servicenow.itsm.change_request` module
  requires this when opening in `assess` and closing the change.
- **Close code**: pass `snow_close_code` (default `successful`).
- To require an **approved** change before applying (not just an open one), add
  an assertion in `preflight` that queries the change state via
  `servicenow.itsm.change_request_info` and gates `apply_cleared` on approval.
