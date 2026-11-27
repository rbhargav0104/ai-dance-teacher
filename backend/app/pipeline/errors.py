"""Pipeline errors (no heavy imports: the API must boot without the vision stack)."""

from __future__ import annotations


class AnalysisFailed(Exception):
    """User-actionable failure. `retryable` = trying the same input again may succeed."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class SubjectChoiceNeeded(AnalysisFailed):
    """Several people are in the video: analysis stops until the user picks whom to follow
    (spec amendment A2). Not a failure of the video, and not retryable without a choice."""

    def __init__(self, message: str) -> None:
        super().__init__("choose_dancer", message, retryable=False)
