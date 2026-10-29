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
