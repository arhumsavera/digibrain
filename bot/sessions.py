from dataclasses import dataclass, field


@dataclass
class UserSession:
    agent: str = "opencode"
    session_id: str | None = None
    message_count: int = 0

    def reset(self, agent: str | None = None):
        if agent:
            self.agent = agent
        self.session_id = None
        self.message_count = 0


class SessionStore:
    def __init__(self):
        self._sessions: dict[int, UserSession] = {}

    def get(self, user_id: int) -> UserSession:
        if user_id not in self._sessions:
            self._sessions[user_id] = UserSession()
        return self._sessions[user_id]

    def reset(self, user_id: int, agent: str | None = None):
        self.get(user_id).reset(agent)


sessions = SessionStore()
