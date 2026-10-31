class StetiqError(Exception):
    """Base class for all errors stetiq raises to users."""


class OntologyValidationError(StetiqError):
    """A Declared Ontology is malformed; the message names the offending path."""


class MissingDeclaredOntologyError(StetiqError):
    """A Knowledge Graph (or Construction Run) was created without a Declared Ontology."""


class KnowledgeGraphAlreadyExistsError(StetiqError):
    pass


class NotFoundError(StetiqError):
    pass


class NoUseCaseError(NotFoundError):
    """The Knowledge Graph has no Use Case version yet, so there is no latest one."""


class EvaluatorError(StetiqError):
    """An Evaluator is malformed, failed, or returned an invalid Evaluation."""


class GraphSourceNotBoundError(StetiqError):
    """The Knowledge Graph has no Graph Source scope bound to it."""


class GraphSourceUnavailableError(StetiqError):
    """The Client was built without a Graph Source adapter, so it cannot observe."""


class InvalidEvolutionModeError(StetiqError, ValueError):
    """An Evolution Mode other than "strict" or "evolving"."""


class ConflictingArgumentsError(StetiqError, ValueError):
    """Two arguments that exclude each other were both given (e.g. a run's
    `ontology_version` and `alias`)."""


class RunNotActiveError(StetiqError):
    """The Construction Run has already ended (finished or failed)."""


class UseCaseValidationError(StetiqError):
    """A Use Case or Competency Question is malformed; the message names the offending path."""


class InvalidAliasNameError(StetiqError):
    """An Alias name is empty or contains characters other than letters, digits, `_`, `-`, `.`."""


class GraphSourceWriteRejectedError(StetiqError):
    """A query sent to a Graph Source was not read-only; adapters never issue writes."""


class InvalidDriftConfigError(StetiqError, ValueError):
    """The `drift:` section of the repo config (Drift thresholds) is malformed."""


class AuthenticationError(StetiqError):
    """Server mode: the request carried no API token, or one that is unknown or revoked."""


class PermissionDeniedError(StetiqError):
    """Server mode: the API token lacks the permission this Knowledge Graph operation needs."""


class GateConfigError(StetiqError, ValueError):
    """The Gates in the repo config file are malformed; the message names the Gate."""


class InvalidEntryPointError(StetiqError, ValueError):
    """The repo config has no usable `entry_point` section."""


class EntryPointError(StetiqError):
    """The Construction Entry Point could not be started (e.g. command not found)."""
