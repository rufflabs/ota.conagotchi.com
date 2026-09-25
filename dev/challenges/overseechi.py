"""Overseechi's unique challenges."""
from challenges.criteria import CollectStampsChallenge


class OverseechiFullSweep(CollectStampsChallenge):
    id          = "overseechi_full_sweep"
    name        = "Full Sweep"
    description = "Collect 15 stamps"
    character   = "overseechi"
    target      = 15
