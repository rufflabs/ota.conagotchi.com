# Only registered quests are listed or checked for new completion rewards.
# Legacy class names and IDs are retained so existing saves keep their progress.
from challenges.hackachi import HackachiFirstContact, HackachiJackIn
from challenges.cryptachi import CryptachiKeyExchange, CryptachiWebOfTrust
from challenges.freedomchi import FreedomchiFreeData
from challenges.hackachi_campaign import HACKACHI_QUESTS
from challenges.adminichi_campaign import ADMINICHI_QUESTS

BASE_QUESTS = [
    CryptachiWebOfTrust,
    CryptachiKeyExchange,
    FreedomchiFreeData,
    HackachiFirstContact,
    HackachiJackIn,
]

# Add future chi-specific classes here, with their owning `character` ID set.
# Former sample quests remain defined but inactive; saved IDs are not removed.
CHI_QUESTS = HACKACHI_QUESTS + ADMINICHI_QUESTS

CHALLENGES = BASE_QUESTS + CHI_QUESTS
