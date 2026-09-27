"""Shared challenges measured from the games (game_scores)."""
from challenges.criteria import (BeatHighScoreChallenge, GameScoreChallenge,
                                 MetaChallenge, PlayAnyGameChallenge,
                                 PlayGameChallenge)


class GamesPlayAny(PlayAnyGameChallenge):
    id          = "games_play_any"
    name        = "Game On"
    description = "Play any game."


class GamesPlaySimon(PlayGameChallenge):
    id          = "games_play_simon"
    name        = "Simon Says"
    description = "Play a game of Simon."
    game        = "simon"


class GamesPlaySnake(PlayGameChallenge):
    id          = "games_play_snake"
    name        = "Snake Charmer"
    description = "Play a game of Snake."
    game        = "snake"


class GamesSimonRound10(GameScoreChallenge):
    id          = "games_simon_round_10"
    name        = "Total Recall"
    description = "Clear 10 rounds in one game of Simon."
    game        = "simon"
    target      = 10


class GamesSnakeScore20(GameScoreChallenge):
    id          = "games_snake_score_20"
    name        = "Long Snake"
    description = "Eat 20 food in one game of Snake."
    game        = "snake"
    target      = 20


class GamesBeatHighScore(BeatHighScoreChallenge):
    id          = "games_beat_high_score"
    name        = "Personal Best"
    description = "Beat your own high score in any game."


class GamesGamer(MetaChallenge):
    """CTF meta challenge: its parts give no flag; this one does."""
    id          = "games_gamer"
    name        = "Gamer"
    description = "Complete Game On and Personal Best."
    is_ctf      = True
    requires    = ("games_play_any", "games_beat_high_score")


# Gamer comes after its parts, so the sweep that completes them completes it.
GAME_QUESTS = [
    GamesPlayAny,
    GamesPlaySimon,
    GamesPlaySnake,
    GamesSimonRound10,
    GamesSnakeScore20,
    GamesBeatHighScore,
    GamesGamer,
]
