"""Errors every provider raises (PROVIDER_SPEC.md §1). Callers degrade; they never crash a run."""


class ProviderError(Exception):
    """The provider answered, but not usefully (bad response, refused, too large...)."""

    code = "provider_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class ProviderUnavailable(ProviderError):
    """The provider is not configured or not reachable."""

    code = "provider_unavailable"
