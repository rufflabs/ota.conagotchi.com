"""Offline simulated targets. Actions never access real networks or run code."""
import json
import os

_DATA_DIR = "data"
_IDS = ("hackachi_open_secret", "hackachi_wrong_directory",
        "hackachi_yours_apparently", "hackachi_scheduled_promotion",
        "hackachi_you_made_this")

# Only this small session state is saved. Target fixtures stay in firmware.
_SPECS = (
    {
        "brief": "ENTRY IT. Lab only. Reach the maintenance console. They left the instructions. How considerate.",
        "evidence": (
            ("services", "Service inventory", "22: SSH, keys only. 80: public status. 8080: setup console, HTTP login."),
            ("manual", "Setup manual", "Setup console: port 8080. Factory account setup, password welcome. Remove after deployment."),
        ),
        "fields": (("port", "Port", ("22", "80", "8080")),
                   ("user", "User", ("guest", "setup", "admin")),
                   ("password", "Password", ("blank", "admin", "welcome"))),
        "actions": (("login", "Connect / log in"),),
        "hints": ("Compare each service's purpose.", "The setup manual documents a factory login.",
                  "Use port 8080 with setup / welcome."),
    },
    {
        "brief": "JUNIOR. Lab only. Retrieve recovery.txt from the private folder. That restriction looks like a suggestion.",
        "evidence": (
            ("request", "Viewer request", "GET /view\nfile=status.txt\nBase: /srv/public/\nNo resolved-path boundary check."),
            ("tree", "Directory listing", "/srv contains public and private. public: status.txt. private: recovery.txt. Paths are case sensitive."),
        ),
        "fields": (("parents", "Parent steps", ("0", "1", "2")),
                   ("folder", "Folder", ("public", "private", "logs")),
                   ("file", "File", ("status.txt", "recovery.txt", "notes.txt"))),
        "actions": (("request", "Request file"),),
        "hints": ("Start at /srv/public, not at the filesystem root.",
                  "A parent step moves up one directory.", "One parent step, private, recovery.txt."),
    },
    {
        "brief": "INTERMEDIATE. Lab only. Compare two identities against the same records. It checked someone, not who.",
        "evidence": (
            ("accounts", "Test identities", "Authorized lab accounts: Alice owns ticket 41. Bob owns ticket 42. Both accounts have the same role."),
            ("api", "Portal request", "GET /ticket?id=41 with Alice's session returns 200. The record ID is client-controlled."),
        ),
        "fields": (("account", "Session", ("Alice", "Bob", "Logged out")),
                   ("ticket", "Ticket ID", ("41", "42", "99")),
                   ("cause", "Finding", ("Weak password", "Missing owner check", "No encryption"))),
        "actions": (("request", "Request ticket"), ("report", "Submit finding")),
        "hints": ("Establish a valid owner request first.", "Keep Alice's session but request ticket 42.",
                  "Prove access with both owners, then report the missing owner check."),
    },
    {
        "brief": "ADVANCED. Lab only. Produce root-owned proof.txt through a scheduled job. Admin ran my work.",
        "evidence": (
            ("jobs", "Scheduled jobs", "backup: root runs backup.sh. metrics: monitor runs metrics.sh. rotate: root runs rotate.sh."),
            ("permissions", "File permissions", "backup.sh: operator can write. metrics.sh: operator can write. rotate.sh: root-only write. You are operator."),
            ("payloads", "Proof operations", "Proof writes a harmless proof.txt owned by the executing user. No-op changes nothing. Destructive actions are outside lab scope."),
        ),
        "fields": (("script", "Script", ("metrics.sh", "backup.sh", "rotate.sh")),
                   ("payload", "Operation", ("No-op", "Write proof")),
                   ("job", "Job", ("metrics", "backup", "rotate"))),
        "actions": (("edit", "Edit script"), ("run", "Run job"), ("inspect", "Inspect proof")),
        "hints": ("Compare who can write a script with who executes it.",
                  "A writable script alone does not imply root execution.",
                  "Put proof in backup.sh, run backup, then inspect its owner."),
    },
    {
        "brief": "CAPSTONE. Lab only. Prove an export-to-job attack chain. Repair both trust boundaries, then test attacks and legitimate operations.",
        "evidence": (
            ("public", "Public service", "A public diagnostic exposes a lab-only analyst token: demo-key. Analyst owns object 11. Object 12 belongs to ops."),
            ("export", "Export handler", "Authenticated export trusts the supplied owner field. An ops export reveals the maintenance console route."),
            ("runner", "Job runner", "Maintenance runs as root and accepts a client script path. approved.sh is root-owned. user.sh is analyst-writable. Proof is the only lab payload."),
        ),
        "fields": (("token", "Token", ("none", "demo-key", "wrong")),
                   ("object", "Object", ("11", "12")),
                   ("owner", "Claimed owner", ("analyst", "ops")),
                   ("script", "Job path", ("approved.sh", "user.sh")),
                   ("fix", "Repair", ("Hide diagnostics", "Enforce owner", "Restrict job path"))),
        "actions": (("export", "Request export"), ("job", "Run maintenance"),
                    ("proof", "Inspect proof"), ("fix", "Apply repair"), ("verify", "Verify assessment")),
        "hints": ("Trace data from public diagnostics to export to the job runner.",
                  "A supplied owner is not a trusted identity. A writable job path crosses another boundary.",
                  "After proof, repair owner checks and job paths. Retest object 12, object 11, user.sh and approved.sh."),
    },
)


def _path(cid):
    if cid not in _IDS:
        raise ValueError("Unknown lab")
    return _DATA_DIR + "/lab_" + cid + ".json"


def _load(cid):
    try:
        with open(_path(cid)) as f:
            value = json.load(f)
        if isinstance(value, dict) and value.get("version") == 1:
            return value
    except (OSError, ValueError):
        pass
    return {}


def is_solved(cid):
    return _load(cid).get("solved") is True


class LabSession:
    def __init__(self, cid):
        self.cid = cid
        self.level = _IDS.index(cid)
        self.spec = _SPECS[self.level]
        saved = _load(cid)
        self.state = {"version": 1, "solved": saved.get("solved") is True,
                      "values": {}, "facts": [], "seen": [], "hints": 0}
        values = saved.get("values", {})
        if not isinstance(values, dict):
            values = {}
        for key, _, options in self.spec["fields"]:
            value = values.get(key)
            self.state["values"][key] = value if value in options else options[0]
        for key in ("facts", "seen"):
            raw = saved.get(key, [])
            if isinstance(raw, list):
                self.state[key] = [v for v in raw[:32] if isinstance(v, str)]
        hints = saved.get("hints", 0)
        if isinstance(hints, int):
            self.state["hints"] = max(0, min(3, hints))
        self._saved = json.dumps(self.state)

    def save(self):
        encoded = json.dumps(self.state)
        if encoded == self._saved:
            return
        path = _path(self.cid)
        try:
            try:
                os.mkdir(_DATA_DIR)
            except OSError:
                pass
            with open(path + ".tmp", "w") as f:
                f.write(encoded)
            getattr(os, "replace", os.rename)(path + ".tmp", path)
        except OSError:
            self.state = json.loads(self._saved)
            raise
        self._saved = encoded

    def set_value(self, key, value):
        for name, _, options in self.spec["fields"]:
            if name == key and value in options:
                self.state["values"][key] = value
                self.save()
                return
        raise ValueError("Invalid field")

    def inspect(self, key):
        for name, _, text in self.spec["evidence"]:
            if name == key:
                if key not in self.state["seen"]:
                    self.state["seen"].append(key)
                    self.save()
                return text
        raise ValueError("Invalid evidence")

    def notebook(self):
        notes = [text for key, _, text in self.spec["evidence"] if key in self.state["seen"]]
        return "\n\n".join(notes) if notes else "No evidence collected."

    def hint(self):
        index = min(self.state["hints"], 2)
        self.state["hints"] = index + 1
        self.save()
        return self.spec["hints"][index]

    def _fact(self, name):
        if name not in self.state["facts"]:
            self.state["facts"].append(name)

    def act(self, action):
        if action not in [key for key, _ in self.spec["actions"]]:
            raise ValueError("Invalid action")
        if self.state["solved"]:
            return "Assessment already complete."
        result = getattr(self, "_level%d" % self.level)(action)
        self.save()
        return result

    def _level0(self, action):
        v = self.state["values"]
        if v["port"] == "22":
            return "SSH requires a key. Password login refused."
        if v["port"] == "80":
            return "200: Public status. No maintenance console here."
        if (v["user"], v["password"]) != ("setup", "welcome"):
            return "401: Invalid setup credentials."
        self.state["solved"] = True
        return "Maintenance access granted. Default credentials survived deployment. Open secret, closed case."

    def _level1(self, action):
        v = self.state["values"]
        parts = ["srv", "public"]
        for _ in range(int(v["parents"])):
            if parts:
                parts.pop()
        parts.extend((v["folder"], v["file"]))
        path = "/" + "/".join(parts)
        if path == "/srv/private/recovery.txt":
            self.state["solved"] = True
            return "200: Protected recovery file retrieved. The viewer trusted an unresolved path."
        return "404: No virtual file at " + path

    def _level2(self, action):
        v, facts = self.state["values"], self.state["facts"]
        if action == "report":
            if not all(k in facts for k in ("alice_own", "bob_own", "cross_access")):
                return "Finding incomplete. Capture owner baselines for both accounts and a cross-account request."
            if v["cause"] != "Missing owner check":
                return "Finding not supported by the collected evidence."
            self.state["solved"] = True
            return "Finding accepted: authenticated users can read records they do not own. Authorization is missing."
        if v["account"] == "Logged out":
            return "401: Authentication required."
        if v["ticket"] == "99":
            return "404: Ticket not found."
        owner = "Alice" if v["ticket"] == "41" else "Bob"
        if owner == v["account"]:
            self._fact(owner.lower() + "_own")
        else:
            self._fact("cross_access")
        return "200: Ticket " + v["ticket"] + ", owner " + owner + ". Session: " + v["account"] + "."

    def _level3(self, action):
        v = self.state["values"]
        if action == "edit":
            if v["script"] == "rotate.sh":
                return "Permission denied. Only root may edit rotate.sh."
            key = "payload_" + v["script"]
            if key in self.state["facts"]:
                self.state["facts"].remove(key)
            if v["payload"] == "Write proof":
                self._fact(key)
            return "Saved virtual script: " + v["script"]
        if action == "run":
            key = "payload_" + v["job"] + ".sh"
            if key not in self.state["facts"]:
                return "Job finished. No proof operation executed."
            self.state["facts"] = [f for f in self.state["facts"] if not f.startswith("proof_")]
            owner = "root" if v["job"] == "backup" else "monitor"
            self._fact("proof_" + owner)
            return "Job wrote proof.txt. Inspect the resulting owner."
        if "proof_root" in self.state["facts"]:
            self.state["solved"] = True
            return "proof.txt owner: root. A privileged job trusted your writable script."
        return "No root-owned proof. A monitor-owned file does not demonstrate privilege escalation."

    def _level4(self, action):
        v, facts = self.state["values"], self.state["facts"]
        if action == "export":
            if v["token"] != "demo-key":
                return "401: Invalid analyst token."
            actual_owner = "analyst" if v["object"] == "11" else "ops"
            supplied_owner = "analyst" if "owner_fixed" in facts else v["owner"]
            if supplied_owner != actual_owner:
                if "owner_fixed" in facts and v["object"] == "12":
                    self._fact("blocked_export")
                return "403: Object not owned by the effective identity."
            if v["object"] == "12":
                self._fact("route")
                return "200: Ops export discloses the maintenance route. It accepts analyst sessions."
            if "owner_fixed" in facts:
                self._fact("valid_export")
            return "200: Analyst export delivered."
        if action == "job":
            if v["token"] != "demo-key" or "route" not in facts:
                return "Maintenance unavailable: valid session and discovered route required."
            if v["script"] == "user.sh":
                if "job_fixed" in facts:
                    self._fact("blocked_job")
                    return "403: Client-writable job path rejected."
                self._fact("root_proof")
                return "Root runner executed user.sh and wrote a harmless proof artifact."
            if "job_fixed" in facts:
                self._fact("valid_job")
            return "Approved maintenance completed normally."
        if action == "proof":
            if "root_proof" not in facts:
                return "No privileged proof artifact found."
            self._fact("proof_checked")
            return "Artifact owner: root. Export impersonation exposed a runner that trusted your script path."
        if action == "fix":
            if "proof_checked" not in facts:
                return "Assessment needs a verified proof before repair."
            if v["fix"] == "Enforce owner":
                self._fact("owner_fixed")
                return "Exports now use the authenticated identity, not the supplied owner. Retest allowed and denied access."
            if v["fix"] == "Restrict job path":
                self._fact("job_fixed")
                return "Runner now allows only its root-owned approved script. Retest both paths."
            return "Diagnostics hidden. Existing tokens and both trust flaws remain exploitable."
        required = ("proof_checked", "owner_fixed", "job_fixed", "blocked_export",
                    "valid_export", "blocked_job", "valid_job")
        if not all(k in facts for k in required):
            return "Assessment incomplete. Verify proof, both repairs, and successful negative AND positive retests."
        self.state["solved"] = True
        return "Assessment accepted. Exploit chain proven; both boundaries repaired without breaking legitimate work. Mine? Yours again."
