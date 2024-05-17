from enum import Enum, unique


@unique
class ContentType(Enum):
    GAME_BEGIN = "GameBegin"
    GAME_END = "GameEnd"
    TURN_SPEAK_BEGIN = "TurnSpeakBegin"
    TURN_SPEAK_END = "TurnSpeakEnd"
    AGENT_SPEAK_BEGIN = "AgentSpeakBegin"
    AGENT_SPEAK_CHOOSE = "AgentSpeakChoose"
    AGENT_SPEAK_THINKING = "AgentSpeakThinking"
    AGENT_SPEAK = "AgentSpeak"
    AGENT_SPEAK_END = "AgentSpeakEnd"
    TURN_VOTE_BEGIN = "TurnVoteBegin"
    TURN_VOTE_END = "TurnVoteEnd"
    AGENT_VOTE_BEGIN = "AgentVoteBegin"
    AGENT_VOTE_THINKING = "AgentVoteThinking"
    AGENT_VOTE = "AgentVote"
    AGENT_VOTE_END = "AgentVoteEnd"
    EXCEPTION = "Exception"
    END = "End"


@unique
class GameStatus(Enum):
    RUNNING = "Running"
    STOPPING = "Stopping"
    STOPED = "Stoped"