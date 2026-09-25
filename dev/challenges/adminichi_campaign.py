"""Stable identities for Adminichi's offline lab campaign.

Diagnose-and-repair counterpart to Hackachi's labs. Ordered by prerequisite, so
each lab unlocks the next; rewards rise with difficulty.
"""
from challenges.base import LabChallenge


class AdminichiLab(LabChallenge):
    character = "adminichi"


class OutOfSpace(AdminichiLab):
    id = "adminichi_out_of_space"
    name = "Out of Space"
    description = "Restore a full filesystem without destroying data."
    reward_xp = 25


class CertificateOfAttendance(AdminichiLab):
    id = "adminichi_certificate_of_attendance"
    name = "Certificate of Attendance"
    description = "Fix failing HTTPS that a renewal job reports as healthy."
    prerequisite = OutOfSpace.id
    reward_xp = 50


class LockedOut(AdminichiLab):
    id = "adminichi_locked_out"
    name = "Locked Out"
    description = "Harden SSH access without losing your own way in."
    prerequisite = CertificateOfAttendance.id
    reward_xp = 75


class HelpfulBackup(AdminichiLab):
    id = "adminichi_helpful_backup"
    name = "The Helpful Backup"
    description = "Prove a backup can be restored, and repair it when it cannot."
    prerequisite = LockedOut.id
    reward_xp = 100


class PatchTuesday(AdminichiLab):
    id = "adminichi_patch_tuesday"
    name = "Patch Tuesday"
    description = "Patch an entire fleet, including the host that breaks."
    prerequisite = HelpfulBackup.id
    reward_xp = 150


ADMINICHI_QUESTS = [OutOfSpace, CertificateOfAttendance, LockedOut,
                    HelpfulBackup, PatchTuesday]
