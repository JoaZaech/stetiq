"""An LLM behind the `CompetencyQuestionMapper` model interface.

`LlmQuestionMapper` asks a Claude model to map a natural-language Competency
Question onto the Concepts and paths of an Ontology, as Concept references
(`Label`, `Owner.property`, `(Source)-[REL]->(Target)`). Structural answerability
then judges those references against the Ontology Version like any other mapping.

The `anthropic` SDK is an optional extra (`pip install 'stetiq[llm]'`); it is only
imported when no `client` is injected.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from typing import Any

from stetiq.ontology import Ontology
from stetiq.ontology.yaml_format import to_yaml
from stetiq.use_case.concepts import parse_concept_reference
from stetiq.use_case.model import CompetencyQuestion

DEFAULT_MODEL = "claude-opus-5-5"
MODEL_ENV = "STETIQ_QUESTION_MAPPER_MODEL"

# Models that accept the server-side refusal fallback (`fallbacks: "default"`).
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"

_SYSTEM = """\
You map a domain question onto the ontology of a knowledge graph. Name the Concepts \
and paths a Cypher query answering the question would need, as Concept references:

- `Label`: a node type or relationship type
- `Owner.property`: a property of a node type or relationship type
- `(Source)-[REL]->(Target)`: a path; `(Source)-[REL]-(Target)` if direction does not \
matter; `()` leaves an end open; `[A|B]` allows either relationship type

Map the question to what it actually needs, even when the ontology lacks it: a \
question about customer satisfaction needs `Customer.satisfaction` whether or not \
that property exists. Use the ontology's names where it has a fitting Concept. \
Return an empty list only when the question is not about the domain at all.

The ontology (stetiq YAML):

{ontology}"""

_SCHEMA = {
    "type": "object",
    "properties": {"concepts": {"type": "array", "items": {"type": "string"}}},
    "required": ["concepts"],
    "additionalProperties": False,
}


class LlmMappingError(RuntimeError):
    """The model gave no usable mapping (refusal, truncation, malformed output)."""


class LlmQuestionMapper:
    """Maps Competency Questions onto an Ontology with a Claude model.

    `client` is an `anthropic.Anthropic` (or anything with the same
    `messages.create` / `beta.messages.create`); by default one is built from the
    environment (`ANTHROPIC_API_KEY` etc.). `model` defaults to
    $STETIQ_QUESTION_MAPPER_MODEL, else `claude-opus-5-5`.

    Unparseable references in the model's answer are dropped; if none remain, the
    question stays unmapped. Errors propagate: structural answerability records
    them on the question (`data.error`) without blocking versioning.
    """

    def __init__(
        self,
        *,
        client: Any = None,
        model: str | None = None,
        effort: str | None = None,
        max_tokens: int = 16000,
    ) -> None:
        self.model = model or os.environ.get(MODEL_ENV) or DEFAULT_MODEL
        self.effort = effort
        self.max_tokens = max_tokens
        self._client = client

    @property
    def description(self) -> str:
        """Provenance stored with each model-mapped question (`data.mapper`)."""
        return f"anthropic:{self.model}"

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - depends on the environment
                raise LlmMappingError(
                    "LLM mapping needs the anthropic SDK: pip install 'stetiq[llm]'"
                ) from exc
            self._client = anthropic.Anthropic()
        return self._client

    def map_question(self, question: CompetencyQuestion, ontology: Ontology) -> Sequence[str]:
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": [
                {
                    "type": "text",
                    "text": _SYSTEM.format(ontology=to_yaml(ontology)),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [{"role": "user", "content": f"Question: {question.question}"}],
            "output_config": {"format": {"type": "json_schema", "schema": _SCHEMA}},
        }
        if self.effort:
            request["output_config"]["effort"] = self.effort
        if self.model in _FALLBACK_MODELS:
            response = self.client.beta.messages.create(
                **request, betas=[_FALLBACK_BETA], fallbacks="default"
            )
        else:
            response = self.client.messages.create(**request)
        return _concepts(response)


def _concepts(response: Any) -> list[str]:
    if response.stop_reason == "refusal":
        raise LlmMappingError("the model declined to map the question")
    if response.stop_reason == "max_tokens":
        raise LlmMappingError("the model's answer was cut off (max_tokens)")
    text = next((b.text for b in response.content if b.type == "text"), None)
    try:
        concepts = json.loads(text)["concepts"] if text else None
    except (ValueError, KeyError, TypeError):
        concepts = None
    if not isinstance(concepts, list):
        raise LlmMappingError(f"the model returned no concept list: {text!r}")
    usable: list[str] = []
    for ref in concepts:
        if not isinstance(ref, str):
            continue
        try:
            parse_concept_reference(ref)
        except ValueError:
            continue
        if ref not in usable:
            usable.append(ref)
    return usable


QUESTION_MAPPER_ENV = "STETIQ_QUESTION_MAPPER"


def question_mapper_from_spec(spec: str | None):
    """The `CompetencyQuestionMapper` a configuration string names.

    - unset, `""` or `none`: no mapper (questions without a mapping or query stay unmapped)
    - `anthropic`: an `LlmQuestionMapper` (model from $STETIQ_QUESTION_MAPPER_MODEL)
    - `package.module:attr`: a custom mapper; a class is instantiated with no arguments,
      anything else is used as the mapper itself
    """
    spec = (spec or "").strip()
    if not spec or spec.lower() == "none":
        return None
    if spec.lower() == "anthropic":
        return LlmQuestionMapper()
    module_name, sep, attr = spec.partition(":")
    if not sep or not module_name or not attr:
        raise ValueError(
            f"Unknown question mapper {spec!r} (expected 'anthropic', 'none' or 'module:attr')"
        )
    import importlib

    try:
        target = getattr(importlib.import_module(module_name), attr)
    except (ImportError, AttributeError) as exc:
        raise ValueError(f"Cannot load question mapper {spec!r}: {exc}") from exc
    mapper = target() if isinstance(target, type) else target
    if not callable(getattr(mapper, "map_question", None)):
        raise ValueError(f"Question mapper {spec!r} has no map_question(question, ontology)")
    return mapper


def question_mapper_from_env():
    """The mapper $STETIQ_QUESTION_MAPPER names (see `question_mapper_from_spec`)."""
    return question_mapper_from_spec(os.environ.get(QUESTION_MAPPER_ENV))
