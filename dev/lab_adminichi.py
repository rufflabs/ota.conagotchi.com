"""Adminichi's offline campaign: diagnose and repair.

Defensive counterpart to Hackachi's labs. Where Hackachi proves a flaw, Adminichi
keeps the fleet running: read the evidence, find the actual cause, apply the fix
that holds, and prove it afterwards.

Each lab has a plausible wrong answer that appears to work. Choosing it returns a
result explaining what it cost rather than silently failing, and does not solve
the lab.

Presentation is structured: title, difficulty and a plainly worded objective. The
objective does not restate the difficulty or that the target is simulated - the
screen shows both.
"""
from lab_engine import Lab


class OutOfSpace(Lab):
    id = "adminichi_out_of_space"
    title = "Out of Space"
    difficulty = "Entry"
    objective = ("/var is full and the service cannot write. Get it writing "
                 "again without losing data.")
    evidence = (
        ("df", "Disk usage",
         "/ 40% used. /var 100% used, 18G. /home 22% used.\n"
         "Writes to /var/log are failing."),
        ("rotation", "Log rotation",
         "logrotate for app.log: DISABLED 2026-02-11, note 'temporary, while "
         "debugging'. app.log is now 16G of one service's debug output."),
        ("data", "What else is on /var",
         "/var/lib/app/uploads: 1.2G of customer uploads. Not reproducible. "
         "No verified backup."),
    )
    fields = (("target", "Target", ("app.log", "uploads", "partition")),
              ("remedy", "Remedy", ("Delete", "Truncate+rotate", "Extend")))
    actions = (("apply", "Apply remedy"), ("check", "Check free space"))
    hints = ("Something on /var grew without limit. Find out what, and why.",
             "One candidate is regenerable debug output. One is irreplaceable.",
             "Truncate app.log and re-enable its rotation, then check space.")

    def act(self, s, action):
        v = s.values
        if action == "apply":
            if v["target"] == "uploads":
                if v["remedy"] == "Delete":
                    s.fact("data_loss")
                    return ("1.2G freed by deleting unbacked customer uploads. "
                            "The service is writing; the data is unrecoverable.")
                return "Uploads are not the cause. Leave them alone."
            if v["target"] == "partition":
                if v["remedy"] == "Extend":
                    s.fact("extended")
                    return ("Volume extended by 20G. app.log still grows without "
                            "limit, so you will be back here.")
                return "A partition is not a file. Pick a remedy that fits."
            if v["remedy"] == "Delete":
                s.fact("deleted_open_file")
                return ("Deleted app.log, but the service still holds it open. "
                        "df shows no space returned. Truncation releases it.")
            if v["remedy"] == "Truncate+rotate":
                s.drop("deleted_open_file")
                s.fact("rotation_fixed")
                return ("app.log truncated to 0 and rotation re-enabled, "
                        "14 day retention. 16G returned.")
            return "Extending a volume does not shrink a runaway log."
        if not s.has("rotation_fixed"):
            if s.has("data_loss"):
                return ("/var has space, but the runaway log is still unbounded "
                        "and the uploads are unrecoverable. Not resolved.")
            if s.has("deleted_open_file"):
                return "/var still 100% used. A deleted open file frees nothing."
            return "/var still 100% used. The cause has not been addressed."
        s.solve()
        note = (" The deleted uploads are not coming back."
                if s.has("data_loss") else "")
        return ("/var 12% used and rotation is enforced. Service writing "
                "normally." + note)


class CertificateOfAttendance(Lab):
    id = "adminichi_certificate_of_attendance"
    title = "Certificate of Attendance"
    difficulty = "Junior"
    objective = ("HTTPS is failing, but the renewal job reports success. "
                 "Find the actual cause and fix it.")
    evidence = (
        ("cert", "Certificate",
         "Leaf: notBefore 2026-08-01, notAfter 2026-11-01. Chain valid, "
         "key matches. Issued 12 days ago."),
        ("clock", "Host time",
         "Host clock reads 2027-03-14. NTP service: inactive (dead). "
         "CMOS battery replaced last week."),
        ("renewal", "Renewal job",
         "renew.timer last run: OK, exit 0.\n"
         "Log: 'certificate valid for 89 more days, skipping renewal'."),
    )
    fields = (("fix", "Fix", ("Reissue cert", "Fix clock+NTP", "Skip verify")),)
    actions = (("apply", "Apply fix"), ("test", "Test HTTPS"))
    hints = ("The certificate dates and the failure do not agree. "
             "Something else decides what 'now' means.",
             "The renewal job is not lying; it is comparing against a bad clock.",
             "Correct the clock and enable NTP, then test.")

    def act(self, s, action):
        v = s.values
        if action == "apply":
            if v["fix"] == "Reissue cert":
                s.fact("reissued")
                return ("New certificate issued with the same validity window. "
                        "The host still believes it is 2027.")
            if v["fix"] == "Skip verify":
                s.fact("insecure")
                return ("Verification disabled on the clients. The error is gone "
                        "and so is the guarantee. This is not a fix.")
            s.fact("clock_fixed")
            return ("Clock corrected and NTP enabled. Time now tracks upstream "
                    "within milliseconds.")
        if not s.has("clock_fixed"):
            if s.has("reissued"):
                return ("Handshake fails: certificate expired. A second correct "
                        "certificate does not change the host's idea of now.")
            if s.has("insecure"):
                return ("Handshake 'succeeds' because nothing is being checked. "
                        "Any certificate would pass. Restore verification.")
            return "Handshake fails: certificate expired."
        s.solve()
        note = (" Re-enable client verification before you call this done."
                if s.has("insecure") else "")
        return ("HTTPS restored. The certificate was never expired; the host "
                "clock was eight months ahead." + note)


class LockedOut(Lab):
    id = "adminichi_locked_out"
    title = "Locked Out"
    difficulty = "Intermediate"
    objective = ("Apply the proposed SSH hardening without losing your own "
                 "access, and confirm it before you depend on it.")
    evidence = (
        ("config", "Proposed sshd_config",
         "PermitRootLogin no\nPasswordAuthentication no\nAllowGroups sshusers"),
        ("groups", "Your account",
         "opsuser is a member of: ops, wheel.\n"
         "opsuser is NOT a member of sshusers."),
        ("access", "Available routes",
         "Out-of-band serial console: available.\n"
         "Your current SSH session: active, authenticated before any change."),
    )
    fields = (("change", "Change", ("As written", "Add to group", "Drop clause")),
              ("route", "Verify via", ("Old session", "New session", "Serial")))
    actions = (("apply", "Apply config"), ("reload", "Reload sshd"),
               ("verify", "Verify access"))
    hints = ("Read the AllowGroups clause against your own group membership.",
             "Your current session authenticated before the change, so it "
             "cannot tell you whether the change is safe.",
             "Add opsuser to sshusers, apply, reload, then verify a NEW session.")

    def act(self, s, action):
        v = s.values
        if action == "apply":
            s.drop_prefix("verified")
            if v["change"] == "Add to group":
                s.fact("group_fixed")
                s.fact("applied")
                return ("opsuser added to sshusers and config staged. "
                        "Not live until sshd reloads.")
            if v["change"] == "Drop clause":
                s.drop("group_fixed")
                s.fact("applied")
                s.fact("weakened")
                return ("AllowGroups removed and config staged. Every account "
                        "can log in again, which was not the goal.")
            s.drop("group_fixed")
            s.fact("applied")
            return "Config staged as written. Not live until sshd reloads."
        if action == "reload":
            if not s.has("applied"):
                return "Nothing staged to reload."
            s.fact("reloaded")
            if s.has("group_fixed") or s.has("weakened"):
                # Clear a previous lockout: the live config now permits access,
                # so a player who locked themselves out can recover.
                s.drop("locked")
                return "sshd reloaded. Configuration active."
            s.fact("locked")
            return ("sshd reloaded. New sessions for opsuser are refused: not in "
                    "sshusers. Your existing session still works, for now.")
        if v["route"] == "Old session":
            return ("Your existing session responds, but it authenticated before "
                    "the change. It proves nothing about the new config.")
        if v["route"] == "Serial":
            if s.has("locked"):
                s.fact("recovered")
                return ("Serial console reached. You still have a way in; fix the "
                        "group membership and reload again.")
            return "Serial console reached. Nothing to recover."
        if not s.has("reloaded"):
            return "New session uses the old config. Reload sshd first."
        if s.has("locked"):
            return ("New session refused: opsuser is not in sshusers. This is "
                    "what applying it blind would have cost you.")
        if s.has("weakened"):
            return ("New session accepted, but only because the restriction was "
                    "removed. The host is no more hardened than before.")
        s.fact("verified_new")
        s.solve()
        note = (" You found out the hard way first."
                if s.has("recovered") else "")
        return ("New session accepted with key auth, root login refused, "
                "AllowGroups enforced. Hardened and still reachable." + note)


class HelpfulBackup(Lab):
    id = "adminichi_helpful_backup"
    title = "The Helpful Backup"
    difficulty = "Advanced"
    objective = ("Establish whether the backups can actually be restored, "
                 "and fix them if they cannot.")
    evidence = (
        ("logs", "Backup history",
         "184 consecutive successful runs. Exit 0 every time. "
         "Duration steady at ~40s."),
        ("script", "backup.sh",
         "tar over /etc /srv /home\n"
         "Exclude: *.sql, /var/lib/postgresql\n"
         "Exclusion added 2025-11-03, note 'backup was too slow'."),
        ("targets", "Restore targets",
         "Staging host: safe to overwrite, isolated.\n"
         "Production restore: outside lab scope, refused."),
    )
    fields = (("dataset", "Dataset", ("Config", "Database", "Everything")),
              ("target", "Restore to", ("Staging", "Production")),
              ("change", "Change", ("Drop exclude", "More retention", "None")))
    actions = (("restore", "Test restore"), ("fix", "Change backup"),
               ("run", "Run backup"), ("verify", "Verify assessment"))
    hints = ("A backup that has never been restored is a hope, not a backup.",
             "Compare what the script excludes against what the service needs.",
             "Restore the database to staging to expose the gap, drop the "
             "exclude, run a fresh backup, then restore it again.")

    def act(self, s, action):
        v = s.values
        if action == "restore":
            if v["target"] == "Production":
                return "Refused: production restore is outside lab scope."
            if v["dataset"] == "Config":
                s.fact("config_ok")
                return "/etc restored to staging and verified. 3,114 files."
            if v["dataset"] == "Database":
                if not s.has("rerun"):
                    s.fact("gap_found")
                    return ("Restore failed: the archive contains no database "
                            "objects. 184 green runs backed up everything except "
                            "the data that matters.")
                s.fact("db_ok")
                return ("Database restored to staging and consistency-checked. "
                        "Row counts match production.")
            if not s.has("rerun"):
                s.fact("gap_found")
                return ("Partial restore. Files came back; the database did not. "
                        "The exclude list is doing more than it claims.")
            s.fact("db_ok")
            s.fact("config_ok")
            return "Full restore to staging verified, database included."
        if action == "fix":
            if not s.has("gap_found"):
                return ("Change what, exactly? Establish what is missing before "
                        "editing the job.")
            if v["change"] == "Drop exclude":
                s.fact("fixed")
                s.drop("rerun")
                s.drop("db_ok")
                return ("Exclusion removed; the database is in scope again. "
                        "The next run will take longer. Run it.")
            if v["change"] == "More retention":
                return ("Retention raised. You now keep more copies of a backup "
                        "that is still missing the database.")
            return "No change made."
        if action == "run":
            if not s.has("fixed"):
                return ("Backup completed in 40s, exit 0. Same gap as the "
                        "previous 184 runs.")
            s.fact("rerun")
            return ("Backup completed in 6m20s, exit 0. Archive is 7.4x larger "
                    "than the previous runs.")
        if not s.has("gap_found", "fixed", "rerun", "db_ok"):
            return ("Assessment incomplete: expose the gap, fix the job, run a "
                    "fresh backup, and restore the database from THAT backup.")
        s.solve()
        return ("Assessment accepted. The gap is closed and the fix is evidenced "
                "by a restore rather than an exit code.")


class PatchTuesday(Lab):
    id = "adminichi_patch_tuesday"
    title = "Patch Tuesday"
    difficulty = "Capstone"
    objective = ("Get every host onto 5.2 without leaving an outage or an "
                 "unpatched host behind.")
    evidence = (
        ("inventory", "Fleet",
         "web01-web09: standard image.\n"
         "db01: pinned vendor storage module, vendor-supported."),
        ("advisory", "Advisory",
         "Critical remote code execution. Fixed in 5.2.\n"
         "5.2 removes the legacy module db01's storage depends on. "
         "A vendor build for 5.2 exists."),
        ("policy", "Change policy",
         "Canary ring first (web01), then the fleet. Rollback available for 24h. "
         "Unpatched hosts stay exposed, so stopping halfway is not success."),
    )
    fields = (("ring", "Ring", ("canary", "fleet", "db01")),
              ("step", "Step",
               ("Deploy 5.2", "Rollback", "5.2 + vendor")))
    actions = (("deploy", "Execute step"), ("status", "Fleet status"),
               ("verify", "Verify rollout"))
    hints = ("The policy names the order. The advisory names the host that will "
             "break, and the way around it.",
             "Canary before fleet. db01 needs the vendor build, not the plain "
             "one, and rollback buys time if you get it wrong.",
             "canary 5.2, fleet 5.2, then db01 with the vendor build. "
             "Check status, then verify.")

    def act(self, s, action):
        v = s.values
        if action == "deploy":
            ring, step = v["ring"], v["step"]
            if step == "Rollback":
                if ring == "db01" and s.has("db_broken"):
                    s.drop("db_broken")
                    s.fact("db_rolled")
                    return ("db01 rolled back and booting again on the old "
                            "kernel. Still unpatched, still exposed.")
                s.drop_prefix("ring_" + ring)
                return "Rolled back " + ring + " to the previous build."
            if ring == "canary":
                s.fact("ring_canary")
                return ("web01 patched to 5.2 and healthy for 30 minutes. "
                        "Canary ring green.")
            if ring == "fleet":
                if not s.has("ring_canary"):
                    return ("Blocked by change policy: the canary ring has not "
                            "reported healthy.")
                if step == "5.2 + vendor":
                    return ("The vendor build is for db01's module, not the "
                            "standard image. Use the plain 5.2 here.")
                s.fact("ring_fleet")
                return "web02-web09 patched to 5.2. All eight healthy."
            if step == "Deploy 5.2":
                s.fact("db_broken")
                return ("db01 patched and failed to boot: storage module missing. "
                        "This is what the canary ring could not tell you. "
                        "Rollback is still available.")
            if s.has("db_broken"):
                return ("db01 will not boot. Roll it back before deploying "
                        "anything else to it.")
            s.fact("ring_db01")
            return ("db01 patched to 5.2 with the vendor storage module. "
                    "Booted, storage mounted, healthy.")
        if action == "status":
            done = []
            for name, key in (("web01", "ring_canary"), ("web02-09", "ring_fleet"),
                              ("db01", "ring_db01")):
                done.append(name + ": " + ("5.2" if s.has(key) else "vulnerable"))
            if s.has("db_broken"):
                done[-1] = "db01: DOWN, will not boot"
            return "\n".join(done)
        if s.has("db_broken"):
            return "Rollout incomplete: db01 is down."
        if not s.has("ring_canary", "ring_fleet", "ring_db01"):
            return ("Rollout incomplete: every host must be on 5.2. An unpatched "
                    "host is still exposed.")
        s.solve()
        note = (" db01 was broken and rolled back on the way."
                if s.has("db_rolled") else "")
        return ("Rollout verified. Ten of ten hosts on 5.2, db01 on the vendor "
                "module." + note)


LABS = (OutOfSpace, CertificateOfAttendance, LockedOut, HelpfulBackup,
        PatchTuesday)
