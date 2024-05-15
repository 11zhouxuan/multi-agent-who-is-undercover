from enum import Enum, unique


@unique
class ErrorEnum(Enum):
    SUCCEEDED = {1: "Operation succeeded"}
    NOT_SUPPORTED = {1001: "Your query statement is currently not supported by the system"}
    INVAILD_SESSION_ID = {1003: f"Invalid session id."}
    UNKNOWN_ERROR = {9999: "Unknown error."}

    def get_code(self):
        return list(self.value.keys())[0]

    def get_message(self):
        return list(self.value.values())[0]


@unique
class ContentEnum(Enum):
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