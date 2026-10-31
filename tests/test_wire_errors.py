"""Errors on the wire: each keeps its class across the HTTP boundary and gets its status."""

import importlib
import pkgutil

import pytest

import stetiq
from stetiq import errors
from stetiq.tracking import wire


def _stetiq_error_classes() -> set[type[errors.StetiqError]]:
    """Every StetiqError subclass defined anywhere in the stetiq package."""
    for module in pkgutil.walk_packages(stetiq.__path__, "stetiq."):
        try:
            importlib.import_module(module.name)
        except ImportError:  # an optional extra (e.g. `llm`) is not installed
            continue
    found: set[type[errors.StetiqError]] = set()
    todo: list[type[errors.StetiqError]] = [errors.StetiqError]
    while todo:
        cls = todo.pop()
        if cls.__module__.startswith("stetiq") and cls not in found:
            found.add(cls)
            todo.extend(cls.__subclasses__())
    return found


ERROR_CLASSES = sorted(_stetiq_error_classes(), key=lambda cls: cls.__name__)


@pytest.mark.parametrize("cls", ERROR_CLASSES, ids=lambda cls: cls.__name__)
def test_every_error_class_is_defined_in_stetiq_errors(cls):
    # `error_from_json` finds the class by name in `stetiq.errors`; one defined elsewhere
    # would come back from the server as a plain StetiqError.
    assert cls.__module__ == "stetiq.errors"


@pytest.mark.parametrize("cls", ERROR_CLASSES, ids=lambda cls: cls.__name__)
def test_every_error_keeps_its_class_and_message_across_the_wire(cls):
    error = wire.error_from_json(wire.error_to_json(cls("boom")))

    assert type(error) is cls
    assert str(error) == "boom"


def test_an_unknown_error_name_comes_back_as_a_stetiq_error():
    error = wire.error_from_json({"error": {"type": "Exception", "message": "boom"}})

    assert type(error) is errors.StetiqError


def test_an_error_takes_the_status_of_its_most_specific_listed_class(monkeypatch):
    class Gone(errors.NotFoundError):
        pass

    # Listed after its base class: insertion order alone would give it 404.
    monkeypatch.setitem(wire.ERROR_STATUS, Gone, 410)

    assert wire.error_status(Gone("gone")) == 410
    assert wire.error_status(errors.NoUseCaseError("none")) == 404
    assert wire.error_status(errors.StetiqError("plain")) == 400
