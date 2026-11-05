# mock_servicenow — rehearse the CAB flow without a ServiceNow instance

A single-file, stdlib-only ServiceNow look-alike. It speaks enough of the
Table API and Attachment API that the `servicenow.itsm` collection (and therefore
the `servicenow` role in this repo, in its normal `SNOW_MODE=live`) works
unmodified. A small web console lets a human play the Change Advisory Board.

    SNOW_USERNAME=ansible SNOW_PASSWORD=secret MOCK_SNOW_BIND=0.0.0.0 MOCK_SNOW_PORT=8900 \
      python3 tools/mock_servicenow/mock_snow.py

Point the AWX "ServiceNow" credential at it: instance `http://<host>:8900`,
username/password as above, assignment group `Network` (seeded, together with
`CAB Approval`, users, and the lab CIs).

## What it models

| ServiceNow                                   | mock behaviour                                         |
|----------------------------------------------|--------------------------------------------------------|
| `POST /api/now/table/change_request`         | creates `CHG00100xx`, state `new`                      |
| `PATCH ... state=assess`                      | sets `approval=requested` — CAB must act               |
| CAB **Approve** in the console                | `approval=approved`, state `scheduled`                 |
| CAB **Reject**                                | `approval=rejected`, state `canceled`                  |
| `PATCH ... state=implement` before approval   | `403 Operation Failed` (like the real state model)     |
| `PATCH ... work_notes=...`                    | appended to the journal, shown in the console          |
| `POST /api/now/attachment/file`               | stored on disk, downloadable from the change page      |
| `PATCH ... state=closed` + close_code/notes   | final; further transitions refused                     |

Encoded queries (`sysparm_query` with `^`, `^OR`, `LIKE`, `IN`, `ORDERBY`), plain
`field=value` filters, `sysparm_limit/offset` paging with `X-Total-Count`,
`sysparm_display_value` and `sysparm_fields` are supported. Any other table
name works as a generic record store.

Console: `http://<host>:8900/` — list, open a change, approve/reject/close,
add work notes, read the attached compliance reports.

Data lives in `$MOCK_SNOW_DATA` (sqlite + files); delete it to reset.
