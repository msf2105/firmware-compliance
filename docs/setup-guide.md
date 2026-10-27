# Firmware Compliance with Ansible — Step-by-Step Setup Guide

Covers Cisco IOS-XE, Cisco Catalyst Center (SWIM), Cisco Catalyst SD-WAN, Palo Alto PAN-OS and F5 BIG-IP, with credentials from a secrets manager and every change wrapped in a CAB-approved ServiceNow change.

| | Dev / demo | Prod |
|---|---|---|
| Automation controller | AWX on a VM (k3s) | Ansible Automation Platform |
| Source control | GitHub (`msf2105/firmware-compliance`) | GitHub Enterprise |
| Device credentials | Bitwarden Secrets Manager (`credential_source: bitwarden_sm`) | Delinea Secret Server (`credential_source: secret_server`) |
| ITSM | ServiceNow Personal Developer Instance (or `SNOW_MODE=mock`) | ServiceNow prod |
| Devices | EVE-NG lab + Cisco DevNet sandbox for Catalyst Center | Real fleet |
| Inventory | `workflow/inventory/dev.yml` | `workflow/inventory/hosts.yml` |

The roles are identical in both columns. Promotion to prod is a change of inventory, credential and URL — not of code.

---

## 1. How the workflow works

```
AWX job ──► Play 1 (localhost)   apply mode only: open NORMAL change → state Assess (CAB)
                                  or read approval on an existing CHG
        ──► Play 2 (every device)
               secret_server role   → Bitwarden / Secret Server / vault → dev_username/password/enable
               preflight role       → apply_cleared = apply_updates AND in window AND CHG AND CAB approved
               <platform>_firmware  → audit always; remediate only when apply_cleared
               (failures are caught per device and reported, never silently dropped)
               work note per device → ServiceNow
        ──► Play 3 (localhost)   JSON + HTML report → attached to the change → close (or note)
```

**Three-run lifecycle**

1. **Audit** — `apply_updates=false` (default). Read-only. No ServiceNow writes.
2. **Open change** — `apply_updates=true`. Audits, opens a *normal* change, moves it to *Assess* so the CAB approval starts. Touches nothing.
3. **Apply** — `apply_updates=true snow_change_number=CHG…`. Remediates only if that change is **approved**, not already closed, and the run is **inside the maintenance window**. Afterwards the change goes Implement → Review → Closed with the report attached.

**Per-platform behaviour**

| Platform | Inventory host | Audit | Remediation |
|---|---|---|---|
| IOS-XE (not under Catalyst Center) | each switch/router | `show version`, install vs bundle mode | backup → copy image → MD5 → `install add` (stage). `activate commit` only with `reboot_after_upgrade=true`, then waits and re-verifies |
| Catalyst Center | the cluster | appliance release + every managed device vs per-series golden | SWIM: import → tag golden → distribute; activate only with reboot flag. Appliance itself is report-only |
| Catalyst SD-WAN | SD-WAN Manager | Manager, Validators, Controllers, WAN edges | Edges only: image must be in the Manager repository → install (stage); activate + set default with reboot flag. Controllers are report-only |
| PAN-OS | each firewall | version, HA state, firewall's own "software check" | export config → `panos_software` download + install; reboot with flag. **Active HA member is held** |
| F5 BIG-IP | each unit | version, failover state, volumes | UCS backup → upload ISO → install to inactive volume; activate with flag. **Active unit is held** |

Devices running *newer* than golden are flagged `AHEAD` and never downgraded.

---

## 2. Run the demo on any machine (10 minutes)

Do this first — it proves the toolchain before any lab exists.

```bash
git clone https://github.com/msf2105/firmware-compliance.git
cd firmware-compliance
python3 -m venv .venv && source .venv/bin/activate
pip install "ansible-core>=2.16,<2.19" -r awx/requirements.txt
ansible-galaxy collection install -r workflow/requirements.yml

cd workflow
export SNOW_MODE=mock
ansible-playbook playbooks/site.yml -i inventory/demo.yml                      # 1 audit
ansible-playbook playbooks/site.yml -i inventory/demo.yml -e apply_updates=true # 2 open change
python3 scripts/mock_snow.py list                                              # find the CHG
python3 scripts/mock_snow.py approve CHG…                                      #   play the CAB
ansible-playbook playbooks/site.yml -i inventory/demo.yml -e apply_updates=true -e snow_change_number=CHG…  # 3 apply
```

Open the newest `reports/compliance-*.html`. Every row is marked SIMULATED; nothing is contacted.

---

## 3. Build the EVE-NG lab

### 3.1 Nodes

| Role in demo | EVE-NG node | Notes |
|---|---|---|
| IOS-XE | 2 × Catalyst 8000V | Use an *older* image on one node so it shows DRIFT. Golden image is the newer `c8000v-universalk9.<ver>.SPA.bin` |
| PAN-OS | 1–2 × VM-Series | Needs an eval/lab license for `software check` and downloads. Without one, upload the image manually to the firewall and the role installs it |
| F5 | 1–2 × BIG-IP VE | Needs a trial/lab license. Put the golden ISO in `workflow/images/` on the runner |
| SD-WAN | SD-WAN Manager + Validator + Controller + 1–2 C8000V edges | Controllers are memory-heavy; if the EVE host can't carry them, reserve the Cisco DevNet SD-WAN sandbox instead and point `lab-vmanage01` at it |
| Catalyst Center | — | Does not run in EVE-NG. Use the DevNet Catalyst Center sandbox for a live **audit**; `simulate_apply_only: true` keeps SWIM simulated |

Check each vendor's current minimum vCPU/RAM for the release you load.

### 3.2 Management network

1. Add a **Network → Management(Cloud0)** object and connect every node's management interface to it, so nodes share the EVE host's management LAN.
2. Give each node a static management IP on that LAN, reachable from the AWX VM.
3. Put those IPs in `workflow/inventory/dev.yml`.

### 3.3 Minimum device config

Create one automation account per platform (`netauto` is used below) and enable the API/transport the role uses:

```
! Catalyst 8000V
hostname lab-c8kv-01
ip domain name lab.local
crypto key generate rsa modulus 2048
username netauto privilege 15 secret <pw>
enable secret <enable-pw>
ip ssh version 2
line vty 0 4
 login local
 transport input ssh
```

- **PAN-OS**: admin role `netauto` with XML API enabled on the management profile.
- **BIG-IP**: user `netauto` with Administrator role, terminal access tmsh, management HTTPS reachable.
- **SD-WAN Manager**: user in the `netadmin` group.

### 3.4 Image server for IOS-XE

The switch pulls its image from `image_server`. Simplest option on the AWX VM:

```bash
mkdir -p ~/images && cp c8000v-universalk9.*.SPA.bin ~/images/
cd ~/images && python3 -m http.server 80        # or nginx for anything longer-lived
```

Set `ios_golden_override.image_server` in `dev.yml` to `http://<vm-ip>/images`, and fill `image_md5` from software.cisco.com so the MD5 check runs.

---

## 4. Bitwarden (dev credentials)

The recommended dev path is **Bitwarden Secrets Manager** because AWX can hold a single machine-account token and the lookup needs no interactive unlock.

1. In the Bitwarden web vault, open **Secrets Manager** for your organization.
2. Create a **project**: `firmware-compliance-dev`.
3. Create one **secret per credential set** (per device, or one shared by identical lab devices). Value is JSON:
   ```json
   {"username": "netauto", "password": "<pw>", "enable": "<enable-pw>"}
   ```
4. Copy each secret's **ID** into `bws_secret_id` for the matching host(s) in `inventory/dev.yml`.
5. Create a **machine account** with *read* access to the project and generate an **access token**. This token goes into AWX (step 7) — never into Git.

Local test:

```bash
export BWS_ACCESS_TOKEN=…           # needs the bws CLI on PATH
ansible-playbook playbooks/site.yml -i inventory/dev.yml --limit lab-c8kv-01,localhost
```

Alternative: `credential_source: bitwarden` uses the personal Password Manager via the `bw` CLI (`export BW_SESSION=$(bw unlock --raw)`) with a `bw_item` name per host and a custom field `enable`. Fine on a laptop, awkward in AWX.

---

## 5. ServiceNow Personal Developer Instance

1. Request a PDI at developer.servicenow.com (pick the newest release). Note the instance name (`devNNNNN`).
2. Create an integration user, e.g. `svc_ansible`, with roles **itil** and **rest_service**; set a password; untick *Password needs reset*.
3. Confirm an assignment group exists for network changes (the PDI demo data includes groups such as *Network*; otherwise create one) and that it has a manager — that manager receives the CAB approval.
4. Test from your workstation:
   ```bash
   export SNOW_MODE=live SNOW_INSTANCE=devNNNNN SNOW_USERNAME=svc_ansible SNOW_PASSWORD=… SNOW_ASSIGNMENT_GROUP=Network
   ansible-playbook playbooks/site.yml -i inventory/demo.yml -e apply_updates=true
   ```
   A new change should appear in **Change → All** in state *Assess*.
5. **Approving during the demo**: open the change → *Approvers* related list → approve as the group manager (impersonate the user, or approve as admin). The change moves to *Scheduled*; run 3 then remediates.

PDIs hibernate after inactivity — wake yours the morning of the demo.

---

## 6. AWX on a VM

AWX's last upstream release is 24.6.1 with awx-operator 2.19.1; the project has been in a long refactor since. That pair is stable for a lab — just pin it.

**VM**: Ubuntu Server 22.04/24.04, 4 vCPU, 16 GB RAM, 60 GB disk, static IP on the same LAN as EVE-NG's management cloud.

```bash
# 6.1 single-node Kubernetes
curl -sfL https://get.k3s.io | sh -
sudo chmod 644 /etc/rancher/k3s/k3s.yaml
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# 6.2 operator first (comment out "- awx.yaml" in awx/k3s/kustomization.yaml for this pass)
kubectl apply -k awx/k3s/
kubectl -n awx get pods -w            # wait for awx-operator-controller-manager Running

# 6.3 then the AWX instance (re-enable "- awx.yaml")
kubectl apply -k awx/k3s/
kubectl -n awx get pods -w            # ~5-10 min until awx-web / awx-task are Running

# 6.4 admin password
kubectl -n awx get secret awx-admin-password -o jsonpath='{.data.password}' | base64 -d; echo
```

AWX is now at `http://<vm-ip>:30080` (user `admin`).

---

## 7. Execution environment and AWX configuration (as code)

### 7.1 Build the execution environment

```bash
sudo apt install -y podman
./awx/build-ee.sh ghcr.io/msf2105/firmware-compliance-ee:1.0
echo $GHCR_PAT | podman login ghcr.io -u msf2105 --password-stdin
podman push ghcr.io/msf2105/firmware-compliance-ee:1.0
```

The image contains all collections, the Python SDKs (tss, pan-os, catalystcenter…) and the `bws` CLI. If the GHCR package is private, add a *Container Registry* credential in AWX and attach it to the EE.

### 7.2 Bootstrap AWX

```bash
pip install "ansible-core>=2.16" && ansible-galaxy collection install awx.awx
export CONTROLLER_HOST=http://<vm-ip>:30080 CONTROLLER_USERNAME=admin CONTROLLER_PASSWORD=…
export BWS_ACCESS_TOKEN=… SNOW_INSTANCE=devNNNNN SNOW_USERNAME=svc_ansible SNOW_PASSWORD=… SNOW_ASSIGNMENT_GROUP=Network
ansible-playbook awx/bootstrap.yml
```

This creates, idempotently:

- Organization **Network Automation**
- Credential types **Bitwarden Secrets Manager**, **Delinea Secret Server**, **ServiceNow ITSM** (each injects env vars the roles already read)
- Credentials from your exported env (stored encrypted in AWX only)
- Execution environment, Git project, inventories `firmware-compliance-dev` and `firmware-compliance-demo`
- Job templates **1 Audit**, **2 Open change (CAB review)**, **3 Apply (CAB-approved change)** with surveys
- A weekly Monday-morning audit schedule

If the GitHub repo is private, add a *Source Control* credential (PAT or deploy key) to the project.

> In AWX use `SNOW_MODE=live` (the PDI). Mock change files live inside the job container and vanish between runs, so the mock CAB flow only works from a workstation.

---

## 8. First live run (dev)

1. **1 Audit** against `firmware-compliance-dev`, limit one host, e.g. `lab-c8kv-01`. Expect a row in the report and no changes.
2. **1 Audit** with no limit. Fix any `ERROR` rows (credentials, reachability, API access) before going further — the error column says which task failed.
3. **2 Open change** → note the CHG number in the job output and in ServiceNow.
4. Approve the change in the PDI.
5. **3 Apply** with that CHG, reboot = `false` first (stages images only). Inside the Mon–Fri 08:00–18:00 dev window.
6. Repeat 3–5 with reboot = `true` on one IOS-XE node to show the activate + post-reload verification.

---

## 9. Demo-day checklist

- [ ] PDI awake; integration user can log in
- [ ] EVE-NG nodes up; one node of each platform deliberately on an older release
- [ ] AWX project synced; EE pulled; inventories synced
- [ ] Dry-run 1 → 2 → approve → 3 end to end the day before
- [ ] Fallback ready: `firmware-compliance-demo` inventory (simulated) in AWX, or `SNOW_MODE=mock` from a laptop
- [ ] Previous HTML report open in a tab in case the network misbehaves

See `docs/demo-script.md` for the talk track.

---

## 10. Promote to production

1. **Repo**: push this branch to GitHub Enterprise (`git remote add ghe … && git push ghe main`). CI (`.github/workflows/ci.yml`) runs on a GHE runner as-is; set `runs-on` to your runner label if hosted runners are disabled.
2. **Inventory**: fill `workflow/inventory/hosts.yml` with real hosts and `secret_id`s. Keep IOS-XE devices that Catalyst Center manages *out* of the `ios` group — they are upgraded through SWIM.
3. **Golden matrix**: replace the examples in `workflow/vars/golden_versions.yml` with your approved releases, image names, MD5s and PIDs.
4. **Secret Server**: confirm the device template's field slugs; if they differ from `username` / `password` / `enable-password`, set `tss_field_*` in group_vars. Use a dedicated service account with read on the device folder.
5. **ServiceNow**: production service account with change-request write; set `snow_assignment_group`, optional `snow_cmdb_ci`. Confirm the normal-change state model allows New → Assess and Implement → Review → Closed via API; if not, the role leaves a work note instead of failing.
6. **Maintenance window**: production defaults are Sat/Sun 22:00–06:00 in the *runner's* timezone (`roles/preflight/defaults/main.yml`).
7. **AAP**: `ansible-playbook awx/bootstrap.yml -e fc_env=prod -e fc_scm_url=https://<ghe>/…/firmware-compliance.git` with `CONTROLLER_HOST` pointing at AAP (for AAP 2.5+ use the platform gateway URL; `ansible.controller` is the supported twin of `awx.awx`). Rebuild the EE from an AAP-supported base image and push it to your internal registry.
8. **Cisco Support API (optional)**: set `CISCO_CLIENT_ID` / `CISCO_CLIENT_SECRET` in a credential to show Cisco's suggested release next to golden.

---

## 11. Troubleshooting

| Symptom (report "error" column / job output) | Fix |
|---|---|
| `needs bws_secret_id … BWS_ACCESS_TOKEN` | Bitwarden credential not attached to the job template, or host missing `bws_secret_id` |
| `credential lookup … returned no username/password` | Secret JSON keys (Bitwarden) or field slugs (Secret Server) don't match |
| `Set SNOW_INSTANCE, SNOW_USERNAME and SNOW_PASSWORD` | ServiceNow credential not attached to templates 2/3 |
| Change stays in New | Assignment group missing or the integration user lacks itil |
| `NOT approved — this run is AUDIT ONLY` | Expected until the CAB approves |
| Apply ran but nothing changed | Outside the maintenance window — check the `MODE:` line from preflight |
| IOS `MD5 mismatch` | Wrong/partial image on flash; delete it and re-run |
| `Version … not in the SD-WAN Manager software repository` | Upload the edge image to Maintenance → Software Repository first |
| PAN-OS / F5 row says `HELD` | Working as designed: upgrade the passive/standby peer, fail over, re-run |
| Catalyst Center `NO-TARGET` rows | Add a `device_targets` entry whose `series` matches that device family |

---

## Appendix — fixes made while preparing the demo

- Drift made `firmware_check.py` exit 2, which failed every non-compliant device; it now reports drift without failing (`--exit-zero`).
- Missing enable password stored Ansible's internal *omit* placeholder as the enable secret; now falls back to the login password.
- `SNOW_INSTANCE=dev12345` was passed to the collection as a host; it is now expanded to `https://dev12345.service-now.com`.
- ServiceNow changes were created straight into *Assess* without the required assignment group and closed directly from *Assess*; now New → Assess on open, Implement → Review → Closed on close, with a work-note fallback.
- An already-closed approved change could authorise a second push; it can't now.
- Catalyst Center role called a module that doesn't exist (`swim_image_url_import`) and compared the string "golden image imported" as a version; rewritten around `swim_workflow_manager` and the real device inventory.
- IOS-XE used `boot system` on install-mode switches; now uses `install add/activate/commit` with MD5 verification.
- F5 install was missing the required target volume; PAN-OS put the admin password in a URL. Both fixed, and both are now HA-aware.
- Devices running newer than golden would have been "upgraded" (downgraded) to golden; now flagged `AHEAD` and left alone.
- New: Cisco SD-WAN role, Bitwarden credential backends, simulated demo inventory, HTML report attached to the change, AWX bootstrap, EE definition, CI.
