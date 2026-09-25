"""Generic offline lab engine. Actions never touch real networks or run code.

Nothing here is character-specific. A campaign is an ordinary module that defines
`Lab` subclasses and exposes `LABS`; add its module name to `CAMPAIGNS` and its
labs become playable. Progress is stored per lab in `data/lab_<id>.json`.

A Lab carries both its presentation and its logic:

    class OutOfSpace(Lab):
        id = "adminichi_out_of_space"
        title = "Out of Space"              # shown in the title bar
        difficulty = "Entry"                # shown as the Objective row's value
        objective = "..."                   # plain statement of the goal
        evidence = (("key", "Label", "text"), ...)     # documents to read
        fields = (("key", "Label", ("a", "b")), ...)   # selectable values
        actions = (("key", "Label"), ...)              # things to do
        hints = ("first", "second", "third")

        def act(self, s, action):
            if s.values["remedy"] == "...":
                s.solve()
                return "..."
            return "..."

`s` is the live LabSession. Labs read `s.values` and use `s.fact` / `s.has` /
`s.drop` / `s.drop_prefix` to record multi-step progress, then `s.solve()`. Keep
labs pure decision logic: the engine owns persistence, validation and the screen
contract.
"""
import json
import os

# Campaign modules, each exposing LABS. Add a module name to register it.
CAMPAIGNS = ("lab_hackachi", "lab_adminichi")

_DATA_DIR = "data"
_MAX_HINTS = 3
_MAX_NOTES = 32

_registry = None   # id -> Lab instance, built on first use


class LabError(Exception):
    pass


# Ordered hardest-last, so a campaign can be sorted or labelled consistently.
DIFFICULTIES = ("Entry", "Junior", "Intermediate", "Advanced", "Capstone")


class Lab:
    """One simulated target. Subclass per lab; see the module docstring.

    Presentation is structured rather than prose: the screen renders `title` in
    the title bar and `difficulty` as a metadata value, so neither has to be
    written into the objective text. Objectives state the goal plainly - no
    difficulty prefix, no sign-off line."""

    id = ""
    title = ""
    difficulty = "Entry"
    objective = ""
    evidence = ()
    fields = ()
    actions = ()
    hints = ()

    def act(self, s, action):
        """Handle an action and return the text to show. Override."""
        raise NotImplementedError

    # ── introspection used by the engine and tests ───────────────────────────

    @classmethod
    def field_keys(cls):
        return tuple(f[0] for f in cls.fields)

    @classmethod
    def action_keys(cls):
        return tuple(a[0] for a in cls.actions)


# ── registry ──────────────────────────────────────────────────────────────────

def _build_registry():
    labs = {}
    for name in CAMPAIGNS:
        try:
            module = __import__(name)
        except ImportError:
            continue   # a campaign may legitimately not ship on every badge
        for lab in getattr(module, "LABS", ()):
            instance = lab() if isinstance(lab, type) else lab
            if not instance.id:
                raise LabError("Lab without an id in %s" % name)
            if instance.id in labs:
                raise LabError("Duplicate lab id: %s" % instance.id)
            if instance.difficulty not in DIFFICULTIES:
                raise LabError("Unknown difficulty %r on %s"
                               % (instance.difficulty, instance.id))
            labs[instance.id] = instance
    return labs


def registry():
    global _registry
    if _registry is None:
        _registry = _build_registry()
    return _registry


def reset_registry():
    """Drop the cached registry. For tests that swap CAMPAIGNS."""
    global _registry
    _registry = None


def lab_for(cid):
    try:
        return registry()[cid]
    except KeyError:
        raise ValueError("Unknown lab")


def known_ids():
    return tuple(sorted(registry()))


# ── persistence ───────────────────────────────────────────────────────────────

def _path(cid):
    lab_for(cid)   # rejects unknown ids, so no path can be constructed from one
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
    """Live state for one lab: selected values, evidence seen, facts, hints."""

    def __init__(self, cid):
        self.lab = lab_for(cid)
        self.cid = cid
        self.spec = {
            "title": self.lab.title,
            "difficulty": self.lab.difficulty,
            "objective": self.lab.objective,
            "evidence": self.lab.evidence,
            "fields": self.lab.fields,
            "actions": self.lab.actions,
            "hints": self.lab.hints,
        }
        saved = _load(cid)
        self.state = {"version": 1, "solved": saved.get("solved") is True,
                      "values": {}, "facts": [], "seen": [], "hints": 0}
        values = saved.get("values", {})
        if not isinstance(values, dict):
            values = {}
        for key, _, options in self.lab.fields:
            value = values.get(key)
            self.state["values"][key] = value if value in options else options[0]
        for key in ("facts", "seen"):
            raw = saved.get(key, [])
            if isinstance(raw, list):
                self.state[key] = [v for v in raw[:_MAX_NOTES] if isinstance(v, str)]
        hints = saved.get("hints", 0)
        if isinstance(hints, int):
            self.state["hints"] = max(0, min(_MAX_HINTS, hints))
        self._saved = json.dumps(self.state)

    # ── the small API labs are written against ───────────────────────────────

    @property
    def values(self):
        return self.state["values"]

    @property
    def facts(self):
        return self.state["facts"]

    def has(self, *names):
        """True only if every named fact has been recorded."""
        return all(n in self.state["facts"] for n in names)

    def fact(self, name):
        if name not in self.state["facts"]:
            self.state["facts"].append(name)

    def drop(self, name):
        if name in self.state["facts"]:
            self.state["facts"].remove(name)

    def drop_prefix(self, prefix):
        """Forget a group of facts, e.g. when a repair invalidates earlier proof."""
        self.state["facts"] = [f for f in self.state["facts"]
                               if not f.startswith(prefix)]

    def solve(self):
        self.state["solved"] = True

    @property
    def solved(self):
        return self.state["solved"]

    # ── persistence ──────────────────────────────────────────────────────────

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

    # ── screen contract ──────────────────────────────────────────────────────

    def set_value(self, key, value):
        for name, _, options in self.lab.fields:
            if name == key and value in options:
                self.state["values"][key] = value
                self.save()
                return
        raise ValueError("Invalid field")

    def inspect(self, key):
        for name, _, text in self.lab.evidence:
            if name == key:
                if key not in self.state["seen"]:
                    self.state["seen"].append(key)
                    self.save()
                return text
        raise ValueError("Invalid evidence")

    def notebook(self):
        notes = [text for key, _, text in self.lab.evidence
                 if key in self.state["seen"]]
        return "\n\n".join(notes) if notes else "No evidence collected."

    def hint(self):
        hints = self.lab.hints or ("No hints for this lab.",)
        index = min(self.state["hints"], len(hints) - 1)
        self.state["hints"] = index + 1
        self.save()
        return hints[index]

    def act(self, action):
        if action not in self.lab.action_keys():
            raise ValueError("Invalid action")
        if self.state["solved"]:
            return "Assessment already complete."
        result = self.lab.act(self, action)
        self.save()
        return result
