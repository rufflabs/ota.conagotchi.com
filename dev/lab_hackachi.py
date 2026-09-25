"""Hackachi's offline campaign: find the flaw and prove it.

Offensive counterpart to Adminichi's diagnose-and-repair labs. Puzzle logic is
carried over from the original hackachi_lab.py; presentation is structured
(title, difficulty, objective) instead of prose with the level written into it.
"""
from lab_engine import Lab


class OpenSecret(Lab):
    id = "hackachi_open_secret"
    title = "Open Secret"
    difficulty = "Entry"
    objective = ("A maintenance console is reachable on this host. "
                 "Get a session on it.")
    evidence = (
        ("services", "Service inventory",
         "22: SSH, keys only. 80: public status. 8080: setup console, HTTP login."),
        ("manual", "Setup manual",
         "Setup console: port 8080. Factory account setup, password welcome. "
         "Remove after deployment."),
    )
    fields = (("port", "Port", ("22", "80", "8080")),
              ("user", "User", ("guest", "setup", "admin")),
              ("password", "Password", ("blank", "admin", "welcome")))
    actions = (("login", "Connect / log in"),)
    hints = ("Compare each service's purpose.",
             "The setup manual documents a factory login.",
             "Use port 8080 with setup / welcome.")

    def act(self, s, action):
        v = s.values
        if v["port"] == "22":
            return "SSH requires a key. Password login refused."
        if v["port"] == "80":
            return "200: Public status. No maintenance console here."
        if (v["user"], v["password"]) != ("setup", "welcome"):
            return "401: Invalid setup credentials."
        s.solve()
        return ("Maintenance access granted. The factory setup account was "
                "never removed after deployment.")


class WrongDirectory(Lab):
    id = "hackachi_wrong_directory"
    title = "Wrong Directory"
    difficulty = "Junior"
    objective = ("The file viewer serves /srv/public. Retrieve recovery.txt "
                 "from the private folder beside it.")
    evidence = (
        ("request", "Viewer request",
         "GET /view\nfile=status.txt\nBase: /srv/public/\n"
         "No resolved-path boundary check."),
        ("tree", "Directory listing",
         "/srv contains public and private. public: status.txt. "
         "private: recovery.txt. Paths are case sensitive."),
    )
    fields = (("parents", "Parent steps", ("0", "1", "2")),
              ("folder", "Folder", ("public", "private", "logs")),
              ("file", "File", ("status.txt", "recovery.txt", "notes.txt")))
    actions = (("request", "Request file"),)
    hints = ("Start at /srv/public, not at the filesystem root.",
             "A parent step moves up one directory.",
             "One parent step, private, recovery.txt.")

    def act(self, s, action):
        v = s.values
        parts = ["srv", "public"]
        for _ in range(int(v["parents"])):
            if parts:
                parts.pop()
        parts.extend((v["folder"], v["file"]))
        path = "/" + "/".join(parts)
        if path == "/srv/private/recovery.txt":
            s.solve()
            return ("200: Protected recovery file retrieved. "
                    "The viewer trusted an unresolved path.")
        return "404: No virtual file at " + path


class YoursApparently(Lab):
    id = "hackachi_yours_apparently"
    title = "Yours, Apparently"
    difficulty = "Intermediate"
    objective = ("Show that the ticket portal returns records belonging to "
                 "other users, then identify the cause.")
    evidence = (
        ("accounts", "Test identities",
         "Authorized lab accounts: Alice owns ticket 41. Bob owns ticket 42. "
         "Both accounts have the same role."),
        ("api", "Portal request",
         "GET /ticket?id=41 with Alice's session returns 200. "
         "The record ID is client-controlled."),
    )
    fields = (("account", "Session", ("Alice", "Bob", "Logged out")),
              ("ticket", "Ticket ID", ("41", "42", "99")),
              ("cause", "Finding",
               ("Weak password", "Missing owner check", "No encryption")))
    actions = (("request", "Request ticket"), ("report", "Submit finding"))
    hints = ("Establish a valid owner request first.",
             "Keep Alice's session but request ticket 42.",
             "Prove access with both owners, then report the missing owner check.")

    def act(self, s, action):
        v = s.values
        if action == "report":
            if not s.has("alice_own", "bob_own", "cross_access"):
                return ("Finding incomplete. Capture owner baselines for both "
                        "accounts and a cross-account request.")
            if v["cause"] != "Missing owner check":
                return "Finding not supported by the collected evidence."
            s.solve()
            return ("Finding accepted: authenticated users can read records they "
                    "do not own. Authorization is missing.")
        if v["account"] == "Logged out":
            return "401: Authentication required."
        if v["ticket"] == "99":
            return "404: Ticket not found."
        owner = "Alice" if v["ticket"] == "41" else "Bob"
        if owner == v["account"]:
            s.fact(owner.lower() + "_own")
        else:
            s.fact("cross_access")
        return ("200: Ticket " + v["ticket"] + ", owner " + owner +
                ". Session: " + v["account"] + ".")


class ScheduledPromotion(Lab):
    id = "hackachi_scheduled_promotion"
    title = "Scheduled Promotion"
    difficulty = "Advanced"
    objective = ("Produce a root-owned proof.txt by way of a scheduled job "
                 "you do not control.")
    evidence = (
        ("jobs", "Scheduled jobs",
         "backup: root runs backup.sh. metrics: monitor runs metrics.sh. "
         "rotate: root runs rotate.sh."),
        ("permissions", "File permissions",
         "backup.sh: operator can write. metrics.sh: operator can write. "
         "rotate.sh: root-only write. You are operator."),
        ("payloads", "Proof operations",
         "Proof writes a harmless proof.txt owned by the executing user. "
         "No-op changes nothing. Destructive actions are outside lab scope."),
    )
    fields = (("script", "Script", ("metrics.sh", "backup.sh", "rotate.sh")),
              ("payload", "Operation", ("No-op", "Write proof")),
              ("job", "Job", ("metrics", "backup", "rotate")))
    actions = (("edit", "Edit script"), ("run", "Run job"),
               ("inspect", "Inspect proof"))
    hints = ("Compare who can write a script with who executes it.",
             "A writable script alone does not imply root execution.",
             "Put proof in backup.sh, run backup, then inspect its owner.")

    def act(self, s, action):
        v = s.values
        if action == "edit":
            if v["script"] == "rotate.sh":
                return "Permission denied. Only root may edit rotate.sh."
            key = "payload_" + v["script"]
            s.drop(key)
            if v["payload"] == "Write proof":
                s.fact(key)
            return "Saved virtual script: " + v["script"]
        if action == "run":
            key = "payload_" + v["job"] + ".sh"
            if not s.has(key):
                return "Job finished. No proof operation executed."
            s.drop_prefix("proof_")
            owner = "root" if v["job"] == "backup" else "monitor"
            s.fact("proof_" + owner)
            return "Job wrote proof.txt. Inspect the resulting owner."
        if s.has("proof_root"):
            s.solve()
            return ("proof.txt owner: root. A privileged job trusted your "
                    "writable script.")
        return ("No root-owned proof. A monitor-owned file does not demonstrate "
                "privilege escalation.")


class YouMadeThis(Lab):
    id = "hackachi_you_made_this"
    title = "You Made This?"
    difficulty = "Capstone"
    objective = ("Chain the export flaw into the job runner, then repair both "
                 "trust boundaries and retest allowed and denied paths.")
    evidence = (
        ("public", "Public service",
         "A public diagnostic exposes a lab-only analyst token: demo-key. "
         "Analyst owns object 11. Object 12 belongs to ops."),
        ("export", "Export handler",
         "Authenticated export trusts the supplied owner field. An ops export "
         "reveals the maintenance console route."),
        ("runner", "Job runner",
         "Maintenance runs as root and accepts a client script path. "
         "approved.sh is root-owned. user.sh is analyst-writable. "
         "Proof is the only lab payload."),
    )
    fields = (("token", "Token", ("none", "demo-key", "wrong")),
              ("object", "Object", ("11", "12")),
              ("owner", "Claimed owner", ("analyst", "ops")),
              ("script", "Job path", ("approved.sh", "user.sh")),
              ("fix", "Repair",
               ("Hide diagnostics", "Enforce owner", "Restrict job path")))
    actions = (("export", "Request export"), ("job", "Run maintenance"),
               ("proof", "Inspect proof"), ("fix", "Apply repair"),
               ("verify", "Verify assessment"))
    hints = ("Trace data from public diagnostics to export to the job runner.",
             "A supplied owner is not a trusted identity. A writable job path "
             "crosses another boundary.",
             "After proof, repair owner checks and job paths. Retest object 12, "
             "object 11, user.sh and approved.sh.")

    def act(self, s, action):
        v = s.values
        if action == "export":
            if v["token"] != "demo-key":
                return "401: Invalid analyst token."
            actual_owner = "analyst" if v["object"] == "11" else "ops"
            supplied_owner = "analyst" if s.has("owner_fixed") else v["owner"]
            if supplied_owner != actual_owner:
                if s.has("owner_fixed") and v["object"] == "12":
                    s.fact("blocked_export")
                return "403: Object not owned by the effective identity."
            if v["object"] == "12":
                s.fact("route")
                return ("200: Ops export discloses the maintenance route. "
                        "It accepts analyst sessions.")
            if s.has("owner_fixed"):
                s.fact("valid_export")
            return "200: Analyst export delivered."
        if action == "job":
            if v["token"] != "demo-key" or not s.has("route"):
                return ("Maintenance unavailable: valid session and discovered "
                        "route required.")
            if v["script"] == "user.sh":
                if s.has("job_fixed"):
                    s.fact("blocked_job")
                    return "403: Client-writable job path rejected."
                s.fact("root_proof")
                return ("Root runner executed user.sh and wrote a harmless "
                        "proof artifact.")
            if s.has("job_fixed"):
                s.fact("valid_job")
            return "Approved maintenance completed normally."
        if action == "proof":
            if not s.has("root_proof"):
                return "No privileged proof artifact found."
            s.fact("proof_checked")
            return ("Artifact owner: root. Export impersonation exposed a runner "
                    "that trusted your script path.")
        if action == "fix":
            if not s.has("proof_checked"):
                return "Assessment needs a verified proof before repair."
            if v["fix"] == "Enforce owner":
                s.fact("owner_fixed")
                return ("Exports now use the authenticated identity, not the "
                        "supplied owner. Retest allowed and denied access.")
            if v["fix"] == "Restrict job path":
                s.fact("job_fixed")
                return ("Runner now allows only its root-owned approved script. "
                        "Retest both paths.")
            return ("Diagnostics hidden. Existing tokens and both trust flaws "
                    "remain exploitable.")
        if not s.has("proof_checked", "owner_fixed", "job_fixed",
                     "blocked_export", "valid_export", "blocked_job", "valid_job"):
            return ("Assessment incomplete. Verify proof, both repairs, and "
                    "successful negative AND positive retests.")
        s.solve()
        return ("Assessment accepted. Chain proven, both boundaries repaired, "
                "legitimate work still succeeds.")


LABS = (OpenSecret, WrongDirectory, YoursApparently, ScheduledPromotion,
        YouMadeThis)
