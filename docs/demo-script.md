# Demo Script (~15 minutes)

**Setup on screen:** AWX (templates list), ServiceNow PDI (Change → All), EVE-NG topology, last HTML report in a spare tab.

## 1. The problem (1 min)
Firmware drift across five platforms, each with its own upgrade tool, credentials in a vault, and change control that must be honoured. Today that is manual, inconsistent and hard to audit.

## 2. Audit — "what do we have?" (3 min)
- Launch **Firmware Compliance — 1 Audit**.
- While it runs: credentials come from Bitwarden at run time (prod: Secret Server); the inventory holds only an ID per device.
- Open the HTML report: running vs golden per device, plus the devices Catalyst Center and SD-WAN Manager manage underneath them. Point out `AHEAD` (never downgraded) and `NO-TARGET` (no approved release yet).
- Nothing was changed and no ticket was opened.

## 3. Request the change — "ask permission" (3 min)
- Launch **2 Open change (CAB review)**.
- Show the new normal change in ServiceNow in *Assess*, with one work note per device and the report attached.
- Point out the job output: "NOT approved — this run is AUDIT ONLY".

## 4. CAB approves (1 min)
Approve the change in ServiceNow (Approvers → Approve). State becomes *Scheduled*.

## 5. Apply — "do it safely" (5 min)
- Launch **3 Apply**, enter the CHG, reboot = false.
- Narrate the gates on the `MODE:` line: apply flag, maintenance window, change number, CAB approval — all four required.
- Results to point at:
  - IOS-XE: config backed up, image copied and MD5-verified, staged with `install add`.
  - PAN-OS / F5 HA pair: active member **HELD**, passive/standby upgraded first.
  - SD-WAN: edge install queued in SD-WAN Manager; controllers report-only; unreachable edge skipped.
  - Catalyst Center: SWIM import → golden tag → distribute.
- ServiceNow: change moved to *Closed* with close code and notes; report attached.

## 6. Production story (2 min)
Same repo moves to GitHub Enterprise, same job templates in AAP (created by `awx/bootstrap.yml -e fc_env=prod`), credentials switch from Bitwarden to Secret Server with one variable, CI lints and rehearses every commit.

**If the lab misbehaves:** switch the template inventory to `firmware-compliance-demo` — same flow, simulated devices, clearly labelled in the report.
