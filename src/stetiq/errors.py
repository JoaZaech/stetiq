class StetiqError(Exception):
    """Base class for all errors stetiq raises to users."""


class OntologyValidationError(StetiqError):
    """A Declared Ontology is malformed; the message names the offending element."""


class MissingDeclaredOntologyError(StetiqError):
    """A Knowledge Graph (or Construction Run) was created without a Declared Ontology."""


class KnowledgeGraphAlreadyExistsError(StetiqError):
    pass


class NotFoundError(StetiqError):
    pass


class EvaluatorError(StetiqError):
    """An Evaluator is malformed, failed, or returned an invalid Evaluation."""


class GraphSourceNotBoundError(StetiqError):
    """The Knowledge Graph has no Graph Source scope bound to it."""


class GraphSourceUnavailableError(StetiqError):
    """The Client was built without a Graph Source adapter, so it cannot observe."""


class RunNotActiveError(StetiqError):
    """The Construction Run has already ended (finished or failed)."""


class InvalidAliasNameError(StetiqError):
    """An Alias name is empty or contains characters other than letters, digits, `_`, `-`, `.`."""


class AuthenticationError(StetiqError):
    """Server mode: the request carried no API token, or one that is unknown or revoked."""


class PermissionDeniedError(StetiqError):
    """Server mode: the API token lacks the permission this Knowledge Graph operation needs."""
