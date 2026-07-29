"""Exception hierarchy for the application.

A single base class lets callers catch everything from this package with one
except clause. The `SourceError` subtree is the important one: the retrieval
service treats any `SourceError` as "this source failed, try the next".
"""


class PatentRetrieverError(Exception):
    """Base class for every error raised by this package."""


class InvalidPatentNumberError(PatentRetrieverError):
    """The supplied patent number is malformed. Not retryable - user error."""


class InvalidPatentDocumentError(PatentRetrieverError):
    """A PatentDocument was constructed in an invalid state."""


class SourceError(PatentRetrieverError):
    """Base class for failures originating from a patent source.

    The retrieval service catches this to decide whether to fall back to the
    next source in the chain.
    """


class PatentNotFoundError(SourceError):
    """The source responded correctly but has no record of this patent."""


class SourceUnavailableError(SourceError):
    """The source could not be reached: network error, timeout, 5xx, auth failure."""


class ParseError(SourceError):
    """The source responded, but its content could not be parsed.

    Usually means the source changed its structure. Should be logged loudly.
    """


class IncompleteDocumentError(PatentRetrieverError):
    """A document was retrieved but is missing content required for rendering."""


class RenderError(PatentRetrieverError):
    """A document could not be rendered to the requested output format."""
