class TalkeditError(Exception):
    """Base error. `message` says what went wrong and `hint` says what the user can do,
    both in plain Portuguese because the CLI prints them as they are."""

    def __init__(self, message: str, hint: str) -> None:
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        return f"{self.message} {self.hint}"


class ConfigError(TalkeditError):
    pass


class MediaError(TalkeditError):
    pass


class ProjectError(TalkeditError):
    pass


class OpenRouterError(TalkeditError):
    pass


class AIResponseError(TalkeditError):
    pass
