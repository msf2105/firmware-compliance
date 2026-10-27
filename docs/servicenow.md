# ServiceNow Integration

Every real firmware change is wrapped in a ServiceNow change record for audit
and approval trail. In audit/dry-run mode, no ServiceNow interaction happens.

## Flow

| Phase | `snow_action` | What it does |
|-------|--------------|--------------|
| Play 1 run 1 | `open` | Create a **normal** change (state new) then move it to **assess** to start CAB approval. |
| Play 1 run 2 | `check_approval` / `implement` | Read approval + state of `snow_change_number`; approved and still open → move to implement. |
| Play 2 (per device) | `note` | Work note with running/golden/status/action (and managed-device counts). |
| Play 3 | `attach` + `close` | Attach JSON + HTML report; review → closed with close code, or a work note if nothing was applied. |

`snow_mode: mock` (or `SNOW_MODE=mock`) keeps records in `reports/mock_snow/`;
approve them with `scripts/mock_snow.py approve CHG…`.

## Requirements

- Ansible collection: `servicenow.itsm`
- Environment variables:
  - `SNOW_INSTANCE` — `dev12345` or a full URL (normalised to https://…service-now.com)
  - `SNOW_ASSIGNMENT_GROUP` — required by the collection for every state past *new*
  - `SNOW_USERNAME` / `SNOW_PASSWORD` — a service account with change_management

## Behavior by mode

- **Audit / dry-run** (`apply_updates=false`): Play 1's open task is skipped, so
  no `snow_change_*` facts exist. The per-device note tasks and the close task
  are conditioned on those facts and skip cleanly. Result: zero ServiceNow
  writes during an audit.
- **Apply** (`apply_updates=true` + `require_change_ticket=true`): a change is
  opened before any device is touched, each device posts a note, and the change
  is closed at the end.

## Customization

All in `roles/servicenow/defaults/main.yml`: `snow_assignment_group`,
`snow_category`, `snow_risk`, `snow_impact`, `snow_cmdb_ci`. Close code is chosen
automatically (successful / successful_issues / unsuccessful) from the run's errors.
