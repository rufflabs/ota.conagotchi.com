class Challenge:
    """Base class for all Conagotchi challenges.

    A challenge is an objective with completion criteria read from live badge
    state.  Every challenge belonging to a character the badge has unlocked is
    tracked automatically — there is no per-challenge activation.  ConagotchiScreen
    periodically checks each unlocked, not-yet-completed challenge via `is_met()`;
    the first time it returns True the reward in `on_complete()` is applied and
    the challenge is marked complete (challenge_manager).

    Subclass and override the class attributes below:
        id, name, description   — identity shown in the challenge list / detail view
        character               — id of the character this challenge belongs to; the
                                  challenge is only listed/tracked once that
                                  character is unlocked.  "" = every badge.
        is_met()                — completion criteria (usually via a criteria base)

    Multi-step challenges also override `progress()` to report (current, target) so
    the detail view can show "IN PROGRESS (1/10)".

    Commonly overridden:
        reward_happiness / reward_xp — completion reward amounts
        on_complete()                — custom reward / side effects
    """

    id          = ""
    name        = "Unnamed Challenge"
    description = ""
    character   = ""      # owning character id; "" = universal (any badge)

    # Reward applied by the default on_complete().
    reward_happiness = 2
    reward_xp        = 25

    # ── Completion criteria (override via a criteria base) ──────────────────────

    @classmethod
    def is_met(cls) -> bool:
        """Return True when the criteria are satisfied, read from live state."""
        return False

    @classmethod
    def progress(cls):
        """Return (current, target) for multi-step challenges, else None (binary)."""
        return None

    # ── Reward ──────────────────────────────────────────────────────────────────

    def on_complete(self, pet) -> None:
        """Called once when the challenge is first completed.

        Default reward: bump Happiness and grant XP.  Override for custom
        rewards or side effects (call super().on_complete(pet) to keep the
        default reward).
        pet — live PetState instance
        """
        if self.reward_happiness:
            pet.add_happiness(self.reward_happiness)
        if self.reward_xp:
            pet.gain_xp(self.reward_xp)
