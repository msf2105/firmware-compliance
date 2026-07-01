# Platform Notes

Per-platform quirks, caveats, and remediation approach. Read before enabling
apply mode on a given platform.

## Cisco IOS / IOS-XE (`cisco.ios`)
- Audit via `ios_facts` (`ansible_net_version`).
- Remediation sets the `boot system` variable to the golden image and saves.
  Activation requires a reload, gated by `reboot_after_upgrade`.
- Assumes the golden image is already staged on `flash:` (or the configured
  `image_disk`). Image transfer is out of scope — stage via your image-distribution
  process or extend the role.

## Cisco IOS-XR (`cisco.iosxr`)
- Install-based (`install add` / `install activate`). More involved than IOS;
  the role stages the approach and should be validated per XR release train
  before unattended apply.

## Cisco NX-OS (`cisco.nxos`)
- `install all` model. Watch for EPLD upgrades separately — not covered here.
- Version string format (e.g. `10.3(5)`) must match the golden value exactly.

## Cisco ASA (`cisco.asa`)
- Boot-image model, similar to IOS. Multi-context and failover pairs need extra
  care (upgrade standby first, failover, then active) — not automated here.

## Cisco ACI (`cisco.aci`)
- Controller (APIC) and switch fabric firmware are managed via firmware policies,
  not a direct push. The role targets the golden APIC/switch versions; fabric
  upgrades are staged, group-by-group, through the policy — never all leaves at once.

## Cisco Catalyst Center / DNAC (`cisco.catalystcenter`)
- Uses SWIM (Software Image Management). Catalyst Center orchestrates the device
  upgrades; the role targets the golden image/tag. Note the collection was
  renamed from `cisco.dnac` to `cisco.catalystcenter`.

## Cisco ISE (`cisco.ise`) — AUDIT ONLY
- ISE upgrades are node-persona-aware (PAN/MnT/PSN) and sequence-sensitive. There
  is no safe single-call upgrade. The role reports running version/patch vs golden
  and flags for the manual ISE upgrade runbook. It never pushes.

## Cisco UCS (`cisco.ucs`)
- UCS Manager infrastructure bundle (A-bundle) + server/adapter firmware via host
  firmware packages. The role targets the infra bundle version. Blade/rack server
  firmware and reboot coordination is a separate, careful process.

## Palo Alto (`paloaltonetworks.panos`)
- PAN-OS install via the panos modules. Mind the upgrade path — PAN-OS often
  requires stepping through intermediate versions rather than jumping directly.
  HA pairs: upgrade passive first.

## F5 BIG-IP (`f5networks.f5_modules`)
- Image install to an inactive boot location (volume), then boot into it. The
  role targets the golden ISO; volume management and the reboot-into-new-volume
  step should be validated for your HA/DSC setup.

---

## General caveats

- **Image staging is out of scope.** Roles assume the golden image is reachable
  (on-device or on a server). Wire in your image-distribution mechanism as needed.
- **Version string exactness.** `compliant` is a string equality check against
  the golden value. Match the vendor's exact format.
- **HA / clustering.** None of the roles coordinate HA-pair or cluster upgrade
  ordering. For redundant pairs, upgrade standby/passive first, verify, then failover.
- **Validate per release.** Vendor upgrade procedures change between trains. Test
  each platform's apply path in a lab (EVE-NG) before production.
