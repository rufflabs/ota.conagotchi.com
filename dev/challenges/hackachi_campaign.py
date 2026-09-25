"""Stable identities for Hackachi's offline lab campaign."""
from challenges.base import LabChallenge


class HackachiLab(LabChallenge):
    character = "hackachi"


class OpenSecret(HackachiLab):
    id = "hackachi_open_secret"
    name = "Open Secret"
    description = "Investigate services and gain access to a forgotten setup console."
    reward_xp = 25


class WrongDirectory(HackachiLab):
    id = "hackachi_wrong_directory"
    name = "Wrong Directory"
    description = "Escape a public file viewer and recover a protected training file."
    prerequisite = OpenSecret.id
    reward_xp = 50


class YoursApparently(HackachiLab):
    id = "hackachi_yours_apparently"
    name = "Yours, Apparently"
    description = "Prove a ticket portal exposes another user's records and identify why."
    prerequisite = WrongDirectory.id
    reward_xp = 75


class ScheduledPromotion(HackachiLab):
    id = "hackachi_scheduled_promotion"
    name = "Scheduled Promotion"
    description = "Find a writable dependency trusted by a privileged maintenance job."
    prerequisite = YoursApparently.id
    reward_xp = 100


class YouMadeThis(HackachiLab):
    id = "hackachi_you_made_this"
    name = "You Made This?"
    description = "Chain an export flaw and a privileged job, then fix and retest both boundaries."
    prerequisite = ScheduledPromotion.id
    reward_xp = 150


HACKACHI_QUESTS = [OpenSecret, WrongDirectory, YoursApparently,
                  ScheduledPromotion, YouMadeThis]
