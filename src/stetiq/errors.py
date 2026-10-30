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


class InvalidEvolutionModeError(StetiqError, ValueError):
    """An Evolution Mode other than "strict" or "evolving"."""


class RunNotActiveError(StetiqError):
    """The Construction Run has already ended (finished or failed)."""


class InvalidAliasNameError(StetiqError):
    """An Alias name is empty or contains characters other than letters, digits, `_`, `-`, `.`."""


class GraphSourceWriteRejectedError(StetiqError):
    """A query sent to a Graph Source was not read-only; adapters never issue writes."""


class InvalidDriftConfigError(StetiqError, ValueError):
    """The `drift:` section of the repo config (Drift thresholds) is malformed."""
