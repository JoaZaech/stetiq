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


class GraphSourceNotBoundError(StetiqError):
    """The Knowledge Graph has no Graph Source scope bound to it."""


class GraphSourceUnavailableError(StetiqError):
    """The Client was built without a Graph Source adapter, so it cannot observe."""


class RunNotActiveError(StetiqError):
    """The Construction Run has already ended (finished or failed)."""
