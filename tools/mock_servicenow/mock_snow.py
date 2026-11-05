#!/usr/bin/env python3
"""
mock-snow — a small ServiceNow look-alike for rehearsing change / CAB flows.

Implements enough of the ServiceNow REST surface for the `servicenow.itsm`
Ansible collection to work unmodified:

  Table API       /api/now/table/<table>[/<sys_id>]      GET POST PATCH PUT DELETE
  Attachment API  /api/now/attachment                    GET (list)
                  /api/now/attachment/file               POST (binary body)
                  /api/now/attachment/<sys_id>[/file]    GET DELETE
  Auth            HTTP Basic (SNOW_USERNAME / SNOW_PASSWORD)

Plus a human UI at / for the CAB: list changes, open one, read work notes and
attachments, Approve / Reject / Cancel / Close.

Change-request state model (same numeric codes as ServiceNow):
  -5 new  -4 assess  -3 authorize  -2 scheduled  -1 implement  0 review  3 closed  4 canceled
  approval: not requested | requested | approved | rejected

Rules enforced like a real instance would:
  * moving to assess/authorize sets approval=requested (CAB must act)
  * CAB approve  -> approval=approved, state=scheduled
  * CAB reject   -> approval=rejected, state=canceled
  * implement requires approval=approved (403 otherwise)
  * work_notes in a PATCH are appended to the journal, never stored on the record

stdlib only. Config via env: MOCK_SNOW_BIND, MOCK_SNOW_PORT, MOCK_SNOW_DATA,
SNOW_USERNAME, SNOW_PASSWORD.
"""
import base64
import html
import json
import os
import re
import sqlite3
import sys
import threading
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse, quote

BIND = os.environ.get("MOCK_SNOW_BIND", "127.0.0.1")
PORT = int(os.environ.get("MOCK_SNOW_PORT", "8900"))
DATA = os.environ.get("MOCK_SNOW_DATA", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
USERNAME = os.environ.get("SNOW_USERNAME", "ansible")
PASSWORD = os.environ.get("SNOW_PASSWORD", "ansible")
INSTANCE_NAME = os.environ.get("MOCK_SNOW_NAME", "dev-mock")

os.makedirs(os.path.join(DATA, "files"), exist_ok=True)
DB_PATH = os.path.join(DATA, "mock_snow.db")
LOCK = threading.RLock()

STATE_LABEL = {"-5": "New", "-4": "Assess", "-3": "Authorize", "-2": "Scheduled",
               "-1": "Implement", "0": "Review", "3": "Closed", "4": "Canceled"}
STATE_CLASS = {"-5": "new", "-4": "assess", "-3": "assess", "-2": "sched",
               "-1": "impl", "0": "review", "3": "closed", "4": "canceled"}
APPROVAL_CLASS = {"not requested": "muted", "requested": "warn", "approved": "ok", "rejected": "bad"}
RISK_LABEL = {"1": "Very High", "2": "High", "3": "Moderate", "4": "Low"}
IMPACT_LABEL = {"1": "High", "2": "Medium", "3": "Low"}
PREFIX = {"change_request": "CHG", "incident": "INC", "problem": "PRB", "change_task": "CTASK"}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def sid():
    return uuid.uuid4().hex


# --------------------------------------------------------------------------- storage
class Store:
    def __init__(self):
        self.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS records (tbl TEXT, sys_id TEXT PRIMARY KEY, created TEXT, data TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS journal (id INTEGER PRIMARY KEY AUTOINCREMENT, sys_id TEXT, ts TEXT, who TEXT, kind TEXT, text TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS counters (prefix TEXT PRIMARY KEY, n INTEGER)")
        self.db.commit()
        self.seed()

    def seed(self):
        if not self.list("sys_user_group"):
            for name in ("Network", "CAB Approval", "Network Operations", "Change Management"):
                self.insert("sys_user_group", {"name": name, "description": f"{name} group", "active": "true"})
        if not self.list("sys_user"):
            for u, first, last in (("admin", "System", "Administrator"), ("ansible", "Ansible", "Automation"),
                                   ("cab.chair", "CAB", "Chair")):
                self.insert("sys_user", {"user_name": u, "first_name": first, "last_name": last,
                                         "name": f"{first} {last}", "email": f"{u}@example.com", "active": "true"})
        if not self.list("cmdb_ci"):
            for name, ip, cls in (("lab-r1", "192.168.122.51", "cmdb_ci_ip_router"),
                                  ("lab-sw1", "192.168.122.52", "cmdb_ci_ip_switch")):
                self.insert("cmdb_ci", {"name": name, "ip_address": ip, "sys_class_name": cls, "operational_status": "1"})

    def next_number(self, prefix):
        with LOCK:
            row = self.db.execute("SELECT n FROM counters WHERE prefix=?", (prefix,)).fetchone()
            n = (row[0] if row else 10000) + 1
            self.db.execute("INSERT OR REPLACE INTO counters(prefix,n) VALUES(?,?)", (prefix, n))
            self.db.commit()
            return f"{prefix}{n:07d}"

    def insert(self, tbl, data):
        with LOCK:
            rec = dict(data)
            rec["sys_id"] = rec.get("sys_id") or sid()
            rec["sys_created_on"] = rec.get("sys_created_on") or now()
            rec["sys_updated_on"] = now()
            rec["sys_created_by"] = rec.get("sys_created_by") or USERNAME
            rec["sys_updated_by"] = USERNAME
            rec["sys_class_name"] = rec.get("sys_class_name") or tbl
            if tbl in PREFIX and not rec.get("number"):
                rec["number"] = self.next_number(PREFIX[tbl])
            self.db.execute("INSERT INTO records(tbl,sys_id,created,data) VALUES(?,?,?,?)",
                            (tbl, rec["sys_id"], rec["sys_created_on"], json.dumps(rec)))
            self.db.commit()
            return rec

    def get(self, tbl, sys_id):
        with LOCK:
            row = self.db.execute("SELECT data FROM records WHERE tbl=? AND sys_id=?", (tbl, sys_id)).fetchone()
        return json.loads(row[0]) if row else None

    def save(self, tbl, rec):
        with LOCK:
            rec["sys_updated_on"] = now()
            rec["sys_updated_by"] = USERNAME
            self.db.execute("UPDATE records SET data=? WHERE tbl=? AND sys_id=?", (json.dumps(rec), tbl, rec["sys_id"]))
            self.db.commit()
            return rec

    def delete(self, tbl, sys_id):
        with LOCK:
            self.db.execute("DELETE FROM records WHERE tbl=? AND sys_id=?", (tbl, sys_id))
            self.db.execute("DELETE FROM journal WHERE sys_id=?", (sys_id,))
            self.db.commit()

    def list(self, tbl):
        with LOCK:
            rows = self.db.execute("SELECT data FROM records WHERE tbl=? ORDER BY created DESC", (tbl,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def note(self, sys_id, kind, text, who=None):
        with LOCK:
            self.db.execute("INSERT INTO journal(sys_id,ts,who,kind,text) VALUES(?,?,?,?,?)",
                            (sys_id, now(), who or USERNAME, kind, text))
            self.db.commit()

    def journal(self, sys_id):
        with LOCK:
            rows = self.db.execute("SELECT ts,who,kind,text FROM journal WHERE sys_id=? ORDER BY id DESC", (sys_id,)).fetchall()
        return [dict(ts=r[0], who=r[1], kind=r[2], text=r[3]) for r in rows]


STORE = Store()


# --------------------------------------------------------------------------- query filters
def _match_term(rec, term):
    """One ServiceNow encoded-query term: field=value, field!=v, fieldLIKEv, fieldSTARTSWITHv, fieldIN a,b, fieldISEMPTY."""
    for op in ("!=", "=", "STARTSWITH", "ENDSWITH", "LIKE", "IN", "ISEMPTY", "ISNOTEMPTY"):
        if op in term:
            field, _, value = term.partition(op)
            actual = str(rec.get(field, "") or "")
            if op == "=":
                return actual == value
            if op == "!=":
                return actual != value
            if op == "LIKE":
                return value.lower() in actual.lower()
            if op == "STARTSWITH":
                return actual.lower().startswith(value.lower())
            if op == "ENDSWITH":
                return actual.lower().endswith(value.lower())
            if op == "IN":
                return actual in value.split(",")
            if op == "ISEMPTY":
                return actual == ""
            if op == "ISNOTEMPTY":
                return actual != ""
    return True


def apply_query(records, params):
    """Filter by sysparm_query (encoded, ^-joined, ^OR supported) AND by plain field=value params."""
    plain = {k: v[0] for k, v in params.items() if not k.startswith("sysparm_")}
    out = [r for r in records if all(str(r.get(k, "") or "") == v for k, v in plain.items())]
    q = params.get("sysparm_query", [""])[0]
    order = None
    if q:
        groups = q.split("^NQ")
        def match(rec):
            for grp in groups:
                ok = True
                for clause in grp.split("^"):
                    if not clause:
                        continue
                    if clause.startswith("ORDERBY"):
                        continue
                    if clause.startswith("OR"):
                        ok = ok or _match_term(rec, clause[2:])
                    else:
                        ok = ok and _match_term(rec, clause)
                if ok:
                    return True
            return False
        out = [r for r in out if match(r)]
        m = re.search(r"ORDERBY(DESC)?([A-Za-z_]+)", q)
        if m:
            out.sort(key=lambda r: str(r.get(m.group(2), "")), reverse=bool(m.group(1)))
    return out


def display_shape(rec, params):
    """sysparm_display_value=true/all -> add display_value for a few fields like SN does."""
    dv = params.get("sysparm_display_value", ["false"])[0]
    fields = params.get("sysparm_fields", [""])[0]
    r = dict(rec)
    if dv in ("true", "all"):
        def wrap(k, disp):
            r[k] = {"display_value": disp, "value": rec.get(k, "")} if dv == "all" else disp
        if "state" in rec:
            wrap("state", STATE_LABEL.get(str(rec["state"]), rec["state"]))
        if "assignment_group" in rec:
            g = STORE.get("sys_user_group", rec["assignment_group"]) or {}
            wrap("assignment_group", g.get("name", rec["assignment_group"]))
    if fields:
        keep = [f.strip() for f in fields.split(",")]
        r = {k: v for k, v in r.items() if k in keep}
    return r


# --------------------------------------------------------------------------- change-request state machine
def apply_change_rules(rec, patch, who):
    """Mutates rec with patch, enforcing the approval model. Returns (ok, error_message)."""
    old_state = str(rec.get("state", "-5"))
    new_state = str(patch.get("state", old_state))
    approval = rec.get("approval", "not requested")

    if "work_notes" in patch:
        STORE.note(rec["sys_id"], "work_notes", str(patch.pop("work_notes")), who)
    if "comments" in patch:
        STORE.note(rec["sys_id"], "comments", str(patch.pop("comments")), who)

    if new_state != old_state:
        if old_state in ("3", "4"):
            return False, f"Change is {STATE_LABEL[old_state]}; state transitions are no longer allowed."
        if new_state in ("-4", "-3") and approval in ("not requested", "rejected"):
            patch["approval"] = "requested"
            STORE.note(rec["sys_id"], "system", "Approval requested from CAB Approval group", "system")
        if new_state in ("-2", "-1") and approval != "approved":
            return False, f"Change cannot move to {STATE_LABEL[new_state]}: CAB approval is '{approval}'."
        if new_state == "3":
            if not (patch.get("close_code") or rec.get("close_code")):
                return False, "close_code is mandatory when closing a change."
            if not (patch.get("close_notes") or rec.get("close_notes")):
                return False, "close_notes is mandatory when closing a change."
            patch.setdefault("closed_at", now())
            patch.setdefault("closed_by", who)
        STORE.note(rec["sys_id"], "system", f"State: {STATE_LABEL.get(old_state, old_state)} -> {STATE_LABEL.get(new_state, new_state)}", who)
    rec.update({k: v for k, v in patch.items() if v is not None})
    return True, ""


def new_change_defaults(data):
    d = {"state": "-5", "approval": "not requested", "type": data.get("type", "normal"),
         "priority": "3", "risk": "3", "impact": "2", "urgency": "2", "category": "Network",
         "short_description": "", "description": "", "close_code": "", "close_notes": "",
         "assignment_group": "", "requested_by": "", "cmdb_ci": "", "on_hold": "false",
         "active": "true", "opened_at": now(), "opened_by": USERNAME}
    d.update({k: v for k, v in data.items() if v is not None})
    d["state"] = str(d["state"])
    return d


def cab_action(rec, action, who, note=""):
    if action == "approve":
        if rec.get("state") in ("3", "4"):
            return False, "Change is closed/canceled."
        rec["approval"] = "approved"
        rec["state"] = "-2"
        STORE.note(rec["sys_id"], "approval", f"APPROVED by {who}. {note}".strip(), who)
    elif action == "reject":
        rec["approval"] = "rejected"
        rec["state"] = "4"
        STORE.note(rec["sys_id"], "approval", f"REJECTED by {who}. {note}".strip(), who)
    elif action == "cancel":
        rec["state"] = "4"
        STORE.note(rec["sys_id"], "system", f"Canceled by {who}. {note}".strip(), who)
    elif action == "close":
        rec["state"] = "3"
        rec["close_code"] = rec.get("close_code") or "successful"
        rec["close_notes"] = rec.get("close_notes") or note or "Closed from CAB console."
        rec["closed_at"] = now()
        rec["closed_by"] = who
        STORE.note(rec["sys_id"], "system", f"Closed by {who}. {note}".strip(), who)
    elif action == "reset":
        rec["approval"] = "requested"
        rec["state"] = "-4"
        STORE.note(rec["sys_id"], "system", f"Approval reset to requested by {who}.", who)
    elif action == "note":
        STORE.note(rec["sys_id"], "work_notes", note, who)
    else:
        return False, "unknown action"
    STORE.save("change_request", rec)
    return True, ""


# --------------------------------------------------------------------------- HTML UI
CSS = """
*{box-sizing:border-box}body{margin:0;font:14px/1.45 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:#0f1419;color:#e6edf3}
a{color:#58a6ff;text-decoration:none}a:hover{text-decoration:underline}
header{background:#161b22;border-bottom:1px solid #30363d;padding:12px 24px;display:flex;align-items:center;gap:16px}
header .logo{font-weight:700;font-size:17px;color:#fff}header .logo span{color:#81b5a1}header .sub{color:#8b949e;font-size:12px}
main{max-width:1100px;margin:24px auto;padding:0 24px}
table{width:100%;border-collapse:collapse;background:#161b22;border:1px solid #30363d;border-radius:6px;overflow:hidden}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid #21262d;vertical-align:top}th{background:#1c2129;color:#8b949e;font-weight:600;font-size:12px;text-transform:uppercase}
tr:hover td{background:#1c2129}
.pill{display:inline-block;padding:2px 9px;border-radius:12px;font-size:12px;font-weight:600;white-space:nowrap}
.new{background:#30363d;color:#c9d1d9}.assess{background:#3d2e00;color:#e3b341}.sched{background:#0d3a2e;color:#56d4a4}.impl{background:#0c2d6b;color:#79c0ff}
.review{background:#2d2158;color:#c3a6ff}.closed{background:#1b3d1b;color:#7ee787}.canceled{background:#4a1c1c;color:#ff7b72}
.ok{background:#1b3d1b;color:#7ee787}.warn{background:#3d2e00;color:#e3b341}.bad{background:#4a1c1c;color:#ff7b72}.muted{background:#30363d;color:#8b949e}
.card{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:16px 20px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:8px 24px}.grid div b{color:#8b949e;font-weight:500;display:block;font-size:12px;text-transform:uppercase}
pre{white-space:pre-wrap;background:#0d1117;padding:10px;border-radius:4px;border:1px solid #30363d;margin:0}
.btn{display:inline-block;padding:7px 14px;border-radius:6px;border:1px solid #30363d;background:#21262d;color:#c9d1d9;cursor:pointer;font:inherit;font-weight:600}
.btn.approve{background:#238636;border-color:#2ea043;color:#fff}.btn.reject{background:#b62324;border-color:#da3633;color:#fff}.btn.close{background:#1f6feb;border-color:#388bfd;color:#fff}
form.inline{display:inline}.actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
input[type=text]{background:#0d1117;border:1px solid #30363d;color:#e6edf3;padding:7px 10px;border-radius:6px;min-width:320px;font:inherit}
.journal li{list-style:none;border-left:3px solid #30363d;padding:4px 10px;margin:6px 0}.journal li.approval{border-color:#2ea043}.journal li.system{border-color:#8b949e;color:#8b949e}.journal li.work_notes{border-color:#e3b341}
.journal small{color:#8b949e;display:block}
h1{font-size:20px;margin:0 0 14px}h2{font-size:15px;margin:0 0 10px;color:#8b949e;text-transform:uppercase}
.empty{color:#8b949e;padding:30px;text-align:center}
code{background:#0d1117;padding:1px 5px;border-radius:3px;border:1px solid #30363d}
"""


def esc(s):
    return html.escape(str(s if s is not None else ""))


def page(title, body):
    return f"""<!doctype html><html><head><meta charset=utf-8><title>{esc(title)} · mock ServiceNow</title><style>{CSS}</style></head>
<body><header><div class=logo>mock<span>ServiceNow</span></div><div class=sub>instance <code>{esc(INSTANCE_NAME)}</code> · Change Advisory Board console</div>
<div style="margin-left:auto"><a href="/">Changes</a> &nbsp;·&nbsp; <a href="/api/now/table/change_request">API</a></div></header><main>{body}</main></body></html>"""


def pill(rec):
    st = str(rec.get("state", "-5"))
    ap = rec.get("approval", "not requested")
    return (f"<span class='pill {STATE_CLASS.get(st, 'new')}'>{esc(STATE_LABEL.get(st, st))}</span> "
            f"<span class='pill {APPROVAL_CLASS.get(ap, 'muted')}'>{esc(ap)}</span>")


def group_name(sys_id):
    g = STORE.get("sys_user_group", sys_id or "") or {}
    return g.get("name", sys_id or "—")


def ui_list():
    recs = STORE.list("change_request")
    rows = "".join(
        f"<tr><td><a href='/change/{esc(r['sys_id'])}'><b>{esc(r.get('number'))}</b></a></td>"
        f"<td>{esc(r.get('short_description'))}</td><td>{pill(r)}</td><td>{esc(group_name(r.get('assignment_group')))}</td>"
        f"<td>{esc(RISK_LABEL.get(str(r.get('risk')), r.get('risk')))}</td><td>{esc(r.get('opened_at'))}</td>"
        f"<td class=actions>" + (
            f"<form class=inline method=post action='/change/{esc(r['sys_id'])}/approve'><button class='btn approve'>Approve</button></form>"
            f"<form class=inline method=post action='/change/{esc(r['sys_id'])}/reject'><button class='btn reject'>Reject</button></form>"
            if r.get("approval") == "requested" else "") + "</td></tr>"
        for r in recs)
    pending = sum(1 for r in recs if r.get("approval") == "requested")
    body = f"<h1>Change requests <span class='pill warn'>{pending} awaiting CAB</span></h1>"
    body += "<table><tr><th>Number</th><th>Short description</th><th>State / approval</th><th>Assignment group</th><th>Risk</th><th>Opened</th><th></th></tr>"
    body += rows or "<tr><td colspan=7 class=empty>No change requests yet. Run the AWX job template “2 Open change” to create one.</td></tr>"
    body += "</table>"
    return page("Changes", body)


def ui_change(sys_id):
    r = STORE.get("change_request", sys_id)
    if not r:
        return None
    atts = [a for a in STORE.list("sys_attachment") if a.get("table_sys_id") == sys_id]
    att_html = "".join(f"<li><a href='/api/now/attachment/{esc(a['sys_id'])}/file' target=_blank>{esc(a['file_name'])}</a> "
                       f"<small>({esc(a.get('content_type'))}, {esc(a.get('size_bytes'))} bytes)</small></li>" for a in atts) or "<li class=empty>none</li>"
    jr = "".join(f"<li class='{esc(j['kind'])}'><small>{esc(j['ts'])} · {esc(j['who'])} · {esc(j['kind'])}</small>{esc(j['text'])}</li>"
                 for j in STORE.journal(sys_id)) or "<li class=empty>no journal entries</li>"
    st, ap = str(r.get("state")), r.get("approval")
    actions = ""
    if st not in ("3", "4"):
        if ap == "requested":
            actions += f"<form class=inline method=post action='/change/{sys_id}/approve'><button class='btn approve'>✔ Approve (CAB)</button></form>" \
                       f"<form class=inline method=post action='/change/{sys_id}/reject'><button class='btn reject'>✖ Reject (CAB)</button></form>"
        if ap == "approved":
            actions += f"<form class=inline method=post action='/change/{sys_id}/reset'><button class=btn>Reset to Assess</button></form>"
        actions += f"<form class=inline method=post action='/change/{sys_id}/close'><button class='btn close'>Close (successful)</button></form>" \
                   f"<form class=inline method=post action='/change/{sys_id}/cancel'><button class=btn>Cancel change</button></form>"
    else:
        actions += "<span class=muted>Record is final.</span>"
    body = f"""<h1><a href='/'>Changes</a> / {esc(r.get('number'))} &nbsp; {pill(r)}</h1>
<div class=card><div class=grid>
<div><b>Short description</b>{esc(r.get('short_description'))}</div><div><b>Type</b>{esc(r.get('type'))}</div>
<div><b>Assignment group</b>{esc(group_name(r.get('assignment_group')))}</div><div><b>Category</b>{esc(r.get('category'))}</div>
<div><b>Risk</b>{esc(RISK_LABEL.get(str(r.get('risk')), r.get('risk')))}</div><div><b>Impact</b>{esc(IMPACT_LABEL.get(str(r.get('impact')), r.get('impact')))}</div>
<div><b>Opened</b>{esc(r.get('opened_at'))} by {esc(r.get('opened_by'))}</div><div><b>Updated</b>{esc(r.get('sys_updated_on'))}</div>
<div><b>Close code</b>{esc(r.get('close_code') or '—')}</div><div><b>sys_id</b><code>{esc(r['sys_id'])}</code></div>
</div></div>
<div class=card><h2>Description</h2><pre>{esc(r.get('description'))}</pre></div>
{"<div class=card><h2>Close notes</h2><pre>" + esc(r.get('close_notes')) + "</pre></div>" if r.get('close_notes') else ""}
<div class=card><h2>CAB actions</h2><div class=actions>{actions}</div>
<form method=post action='/change/{sys_id}/note' style='margin-top:12px'><input type=text name=note placeholder='Add a work note…'> <button class=btn>Add note</button></form></div>
<div class=card><h2>Attachments</h2><ul style='margin:0;padding-left:18px'>{att_html}</ul></div>
<div class=card><h2>Activity / work notes</h2><ul class=journal style='margin:0;padding:0'>{jr}</ul></div>"""
    return page(r.get("number", "change"), body)


# --------------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "mock-snow/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.client_address[0], fmt % args))

    # ---- helpers
    def _json(self, status, obj, headers=None):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json;charset=UTF-8")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _html(self, body, status=200):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html;charset=UTF-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, to):
        self.send_response(303)
        self.send_header("Location", to)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _error(self, status, msg, detail=""):
        self._json(status, {"error": {"message": msg, "detail": detail}, "status": "failure"})

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _authed(self):
        h = self.headers.get("Authorization", "")
        if h.startswith("Basic "):
            try:
                u, _, p = base64.b64decode(h[6:]).decode().partition(":")
                return u == USERNAME and p == PASSWORD
            except Exception:
                return False
        return False

    def _who(self):
        h = self.headers.get("Authorization", "")
        if h.startswith("Basic "):
            try:
                return base64.b64decode(h[6:]).decode().partition(":")[0]
            except Exception:
                pass
        return "cab.chair"

    # ---- routing
    def do_HEAD(self): self._route()
    def do_GET(self): self._route()
    def do_POST(self): self._route()
    def do_PATCH(self): self._route()
    def do_PUT(self): self._route()
    def do_DELETE(self): self._route()

    def _route(self):
        u = urlparse(self.path)
        params = parse_qs(u.query, keep_blank_values=True)
        path = u.path.rstrip("/") or "/"
        try:
            if path.startswith("/api/"):
                if not self._authed():
                    self.send_response(401)
                    self.send_header("WWW-Authenticate", 'Basic realm="mock-snow"')
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                return self._api(path, params)
            return self._ui(path, params)
        except Exception as e:  # keep the server alive, surface the error
            import traceback
            traceback.print_exc()
            self._error(500, "internal error", str(e))

    # ---- UI
    def _ui(self, path, params):
        if path == "/" and self.command == "GET":
            return self._html(ui_list())
        m = re.match(r"^/change/([0-9a-f]{32})(?:/(approve|reject|cancel|close|reset|note))?$", path)
        if m:
            sys_id, action = m.groups()
            rec = STORE.get("change_request", sys_id)
            if not rec:
                return self._html(page("not found", "<div class=empty>No such change.</div>"), 404)
            if self.command == "GET" and not action:
                return self._html(ui_change(sys_id))
            if self.command == "POST" and action:
                form = parse_qs(self._body().decode(), keep_blank_values=True)
                ok, err = cab_action(rec, action, "cab.chair", form.get("note", [""])[0])
                if not ok:
                    return self._html(page("error", f"<div class=card>{esc(err)}</div><a href='/change/{sys_id}'>back</a>"), 400)
                return self._redirect(f"/change/{sys_id}")
        if path == "/healthz":
            return self._json(200, {"status": "ok", "instance": INSTANCE_NAME})
        self._html(page("not found", "<div class=empty>404</div>"), 404)

    # ---- REST API
    def _api(self, path, params):
        who = self._who()
        # attachments ------------------------------------------------------
        if path == "/api/now/attachment/file" and self.command == "POST":
            data = self._body()
            tbl = params.get("table_name", [""])[0]
            tsid = params.get("table_sys_id", [""])[0]
            if not STORE.get(tbl, tsid):
                return self._error(404, "Record not found", f"{tbl}/{tsid}")
            rec = STORE.insert("sys_attachment", {
                "table_name": tbl, "table_sys_id": tsid,
                "file_name": params.get("file_name", ["file"])[0],
                "content_type": params.get("content_type", [self.headers.get("Content-Type", "application/octet-stream")])[0],
                "hash": params.get("hash", [""])[0], "size_bytes": str(len(data))})
            with open(os.path.join(DATA, "files", rec["sys_id"]), "wb") as f:
                f.write(data)
            rec["download_link"] = f"http://{self.headers.get('Host')}/api/now/attachment/{rec['sys_id']}/file"
            STORE.save("sys_attachment", rec)
            STORE.note(tsid, "system", f"Attachment added: {rec['file_name']}", who)
            return self._json(201, {"result": rec})
        m = re.match(r"^/api/now/attachment/([0-9a-f]{32})(/file)?$", path)
        if m:
            att = STORE.get("sys_attachment", m.group(1))
            if not att:
                return self._error(404, "No Record found")
            if self.command == "GET" and m.group(2):
                fp = os.path.join(DATA, "files", att["sys_id"])
                data = open(fp, "rb").read() if os.path.exists(fp) else b""
                self.send_response(200)
                self.send_header("Content-Type", att.get("content_type") or "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if self.command == "GET":
                return self._json(200, {"result": att})
            if self.command == "DELETE":
                STORE.delete("sys_attachment", att["sys_id"])
                try:
                    os.remove(os.path.join(DATA, "files", att["sys_id"]))
                except OSError:
                    pass
                return self._json(204, {})
        if path == "/api/now/attachment" and self.command == "GET":
            recs = apply_query(STORE.list("sys_attachment"), params)
            return self._json(200, {"result": recs}, {"X-Total-Count": str(len(recs))})
        # tables -----------------------------------------------------------
        m = re.match(r"^/api/now/table/([A-Za-z0-9_]+)(?:/([0-9a-f]{32}))?$", path)
        if not m:
            return self._error(404, "Not found", path)
        tbl, sys_id = m.groups()
        if self.command == "GET" and not sys_id:
            recs = apply_query(STORE.list(tbl), params)
            total = len(recs)
            off = int(params.get("sysparm_offset", ["0"])[0])
            lim = int(params.get("sysparm_limit", ["10000"])[0])
            recs = [display_shape(r, params) for r in recs[off:off + lim]]
            return self._json(200, {"result": recs}, {"X-Total-Count": str(total)})
        if self.command == "GET":
            rec = STORE.get(tbl, sys_id)
            if not rec:
                return self._error(404, "No Record found", f"Record doesn't exist or ACL restricts the record retrieval")
            return self._json(200, {"result": display_shape(rec, params)})
        if self.command == "POST" and not sys_id:
            data = json.loads(self._body() or b"{}")
            if tbl == "change_request":
                notes = {k: data.pop(k) for k in ("work_notes", "comments") if k in data}
                rec = STORE.insert(tbl, new_change_defaults(data))
                STORE.note(rec["sys_id"], "system", f"Change created by {who} (state {STATE_LABEL.get(rec['state'], rec['state'])})", who)
                for k, v in notes.items():
                    STORE.note(rec["sys_id"], k, str(v), who)
                if rec["state"] in ("-4", "-3"):
                    rec["approval"] = "requested"
                    STORE.save(tbl, rec)
                    STORE.note(rec["sys_id"], "system", "Approval requested from CAB Approval group", "system")
            else:
                rec = STORE.insert(tbl, data)
            return self._json(201, {"result": display_shape(rec, params)})
        if self.command in ("PATCH", "PUT") and sys_id:
            rec = STORE.get(tbl, sys_id)
            if not rec:
                return self._error(404, "No Record found")
            patch = json.loads(self._body() or b"{}")
            with LOCK:  # read-modify-write must be atomic: per-host work notes arrive concurrently
                rec = STORE.get(tbl, sys_id)
                if tbl == "change_request":
                    ok, err = apply_change_rules(rec, patch, who)
                    if not ok:
                        return self._error(403, "Operation Failed", err)
                else:
                    rec.update(patch)
                STORE.save(tbl, rec)
            return self._json(200, {"result": display_shape(rec, params)})
        if self.command == "DELETE" and sys_id:
            if not STORE.get(tbl, sys_id):
                return self._error(404, "No Record found")
            STORE.delete(tbl, sys_id)
            return self._json(204, {})
        self._error(405, "Method not allowed")


def main():
    srv = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f"mock-snow listening on http://{BIND}:{PORT}  data={DATA}  user={USERNAME}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
