"""Theme picker — select and persist the active UI theme.

LEFT/RIGHT move the selection; START applies the highlighted theme (persisted to
data/theme.txt) and redraws immediately so the new look previews live; SELECT /
BOOT returns. The active theme is marked ACTIVE.
"""
import theme

from menu import ListScreen


class ThemeMenuScreen(ListScreen):

    title = "THEME"

    def __init__(self) -> None:
        super().__init__()
        names = theme.available()
        active = theme.name()
        self.menu.sel = names.index(active) if active in names else 0

    def rows(self):
        active = theme.name()
        return [(n.upper(), "ACTIVE" if n == active else None, n)
                for n in theme.available()]

    def confirm(self):
        return "APPLY"

    def activate(self, mgr) -> None:
        theme.set_active(self.menu.key)    # persists + live preview
        self.redraw(mgr)
