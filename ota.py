# ota.py — file-level over-the-air update for the badge.
#
# This does NOT reflash firmware (the badge ships on a non-OTA partition table:
# a single `factory` app slot, no ota_0/ota_1/otadata). Instead it syncs the
# loose app files that live in the badge filesystem (`*.py`, `screens/`, `img/`,
# ...) from an HTTP(S) manifest, then reboots into the new code.
#
# Safety model (best-effort atomic on a FAT filesystem with no bootloader help):
#   1. Fetch a manifest listing every file as `file <sha256> <size> <path>`.
#   2. Download only the files whose local sha256 differs, into a staging dir.
#      Each file is hash-verified as it streams; a bad checksum aborts before
#      anything real is touched.
#   3. Only once EVERY file is downloaded and verified do we commit: a pending
#      marker is written listing the staged files, then each is renamed over its
#      real target. If power is lost mid-commit, `resume_if_pending()` (called on
#      boot) finishes the remaining renames from the still-present staging files.
#   4. Record the new version and reboot.
#
# Security note: updates are integrity-checked (sha256) but NOT signed, and are
# only ever run when the user manually triggers them (never auto-checked on
# boot). On an adversarial network a malicious server could still serve valid
# hashes for malicious files; a future signed-manifest step (ed25519 pubkey
# baked into config, private key held by organizers) is the real fix. The
# manifest parser already ignores unknown keys so a `sig` line can be added
# without breaking older badges.

import os
import hashlib
import binascii
import asyncio

VERSION_FILE = "data/ota_version.txt"
STAGE_DIR = "data/ota_stage"
PENDING_FILE = "data/ota_pending"
CHUNK = 1024

_S_IFDIR = 0x4000


class OTAError(Exception):
    pass


# ── hashing ──────────────────────────────────────────────────────────────────

def sha256_file(path, chunk=CHUNK):
    """Hex sha256 of a file, or None if it does not exist."""
    try:
        f = open(path, "rb")
    except OSError:
        return None
    h = hashlib.sha256()
    try:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    finally:
        f.close()
    return binascii.hexlify(h.digest()).decode()


# ── manifest ─────────────────────────────────────────────────────────────────

def parse_manifest(text):
    """Parse a manifest into {'version': int, 'files': [(path, sha, size), ...]}.

    Format (blank lines and `#` comments ignored):
        version 3
        file <sha256hex> <size> <path/relative/to/fs/root>
    Unknown leading keywords are ignored so the format can grow (e.g. `sig`).
    """
    version = 0
    files = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        key = parts[0]
        arg = parts[1] if len(parts) > 1 else ""
        if key == "version":
            version = int(arg)
        elif key == "file":
            sha, size, path = arg.split(None, 2)
            files.append((path, sha, int(size)))
        # else: unknown keyword, ignore for forward-compat
    return {"version": version, "files": files}


def compute_plan(manifest):
    """Files from the manifest whose local sha256 differs (need downloading)."""
    todo = []
    for path, sha, size in manifest["files"]:
        if sha256_file(path) != sha:
            todo.append((path, sha, size))
    return todo


# ── version persistence ──────────────────────────────────────────────────────

def local_version():
    try:
        f = open(VERSION_FILE)
    except OSError:
        return 0
    try:
        return int((f.read().strip() or "0"))
    except ValueError:
        return 0
    finally:
        f.close()


def _set_local_version(v):
    _ensure_parent(VERSION_FILE)
    f = open(VERSION_FILE, "w")
    try:
        f.write(str(v))
    finally:
        f.close()


# ── filesystem helpers (MicroPython os has no makedirs/rmtree) ────────────────

def _ensure_parent(path):
    parts = path.split("/")
    cur = ""
    for p in parts[:-1]:
        if not p:
            continue
        cur = p if not cur else cur + "/" + p
        try:
            os.mkdir(cur)
        except OSError:
            pass  # already exists (or a race); real errors surface on open()


def _rmtree(path):
    try:
        entries = os.listdir(path)
    except OSError:
        return
    for e in entries:
        full = path + "/" + e
        try:
            mode = os.stat(full)[0]
        except OSError:
            continue
        if mode & _S_IFDIR:
            _rmtree(full)
        else:
            try:
                os.remove(full)
            except OSError:
                pass
    try:
        os.rmdir(path)
    except OSError:
        pass


def _replace(src, dst):
    try:
        os.remove(dst)
    except OSError:
        pass
    os.rename(src, dst)


def _stage_path(path):
    return STAGE_DIR + "/" + path


# ── commit + crash recovery ──────────────────────────────────────────────────

def _commit(paths):
    """Move every staged file over its real target, guarded by a marker so an
    interrupted commit can be resumed on the next boot."""
    _ensure_parent(PENDING_FILE)
    f = open(PENDING_FILE, "w")
    try:
        f.write("\n".join(paths))
    finally:
        f.close()
    for path in paths:
        _ensure_parent(path)
        _replace(_stage_path(path), path)
    try:
        os.remove(PENDING_FILE)
    except OSError:
        pass


def resume_if_pending():
    """If a commit was interrupted, finish it. Call once early on boot.

    Returns True if a pending commit was recovered."""
    try:
        f = open(PENDING_FILE)
    except OSError:
        return False
    try:
        paths = [l.strip() for l in f.read().split("\n") if l.strip()]
    finally:
        f.close()
    for path in paths:
        src = _stage_path(path)
        try:
            os.stat(src)
        except OSError:
            continue  # already moved before the crash
        _ensure_parent(path)
        _replace(src, path)
    try:
        os.remove(PENDING_FILE)
    except OSError:
        pass
    _rmtree(STAGE_DIR)
    return True


# ── HTTP transport (device) ──────────────────────────────────────────────────

class _RequestsTransport:
    """Streams over the bundled MicroPython `requests`/`urequests` module.

    Kept behind an interface so host tests can inject a filesystem-backed fake."""

    def get_text(self, url):
        import requests
        r = requests.get(url)
        try:
            if r.status_code != 200:
                raise OTAError("HTTP %d for %s" % (r.status_code, url))
            return r.text
        finally:
            r.close()

    def open(self, url):
        import requests
        r = requests.get(url)
        if r.status_code != 200:
            r.close()
            raise OTAError("HTTP %d for %s" % (r.status_code, url))
        return _RespStream(r)


class _RespStream:
    def __init__(self, r):
        self._r = r
        self._raw = r.raw

    def read(self, n):
        return self._raw.read(n)

    def close(self):
        self._r.close()


# ── updater ──────────────────────────────────────────────────────────────────

class OTAUpdater:
    """Drives a manual, integrity-checked file-level update.

    progress(done_bytes, total_bytes) and status(str) callbacks are optional and
    let a UI screen render a progress bar / status line."""

    def __init__(self, manifest_url, transport=None):
        self.manifest_url = manifest_url
        # Files are fetched relative to the manifest's directory.
        self.base_url = manifest_url.rsplit("/", 1)[0] + "/"
        self.transport = transport or _RequestsTransport()

    def fetch_manifest(self):
        return parse_manifest(self.transport.get_text(self.manifest_url))

    async def _download(self, path, sha, size, base_done, total, progress):
        dest = _stage_path(path)
        _ensure_parent(dest)
        h = hashlib.sha256()
        written = 0
        stream = self.transport.open(self.base_url + path)
        try:
            f = open(dest, "wb")
            try:
                while True:
                    chunk = stream.read(CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    h.update(chunk)
                    written += len(chunk)
                    if progress:
                        progress(base_done + written, total)
                    await asyncio.sleep(0)  # keep the UI/event loop responsive
            finally:
                f.close()
        finally:
            stream.close()
        got = binascii.hexlify(h.digest()).decode()
        if got != sha:
            raise OTAError("checksum mismatch: %s" % path)
        return written

    async def run(self, progress=None, status=None):
        """Check for and apply an update. Returns a result dict:
            {'updated': bool, 'reason': str, 'version': int, 'count': int}
        Raises OTAError on network/checksum failure (nothing real is modified
        unless 'updated' is True)."""
        def _s(msg):
            if status:
                status(msg)

        _s("Fetching manifest")
        manifest = self.fetch_manifest()
        remote_v = manifest["version"]
        cur_v = local_version()
        if remote_v <= cur_v:
            return {"updated": False, "reason": "up-to-date",
                    "version": cur_v, "count": 0}

        _s("Comparing files")
        plan = compute_plan(manifest)
        if not plan:
            # Same content, higher version number — just adopt the version.
            _set_local_version(remote_v)
            return {"updated": False, "reason": "already-current",
                    "version": remote_v, "count": 0}

        total = sum(sz for _, _, sz in plan)
        _rmtree(STAGE_DIR)
        base_done = 0
        for path, sha, size in plan:
            _s("Get " + path)
            base_done += await self._download(
                path, sha, size, base_done, total, progress)

        _s("Installing")
        _commit([p for p, _, _ in plan])
        _set_local_version(remote_v)
        _rmtree(STAGE_DIR)
        return {"updated": True, "reason": "updated",
                "version": remote_v, "count": len(plan)}
