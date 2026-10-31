"""Every example Use Case on the Python SDK guide page parses with the real parser."""

import pytest
from guide_pages import code_blocks, read_page

from stetiq.use_case.format import parse_use_case_yaml

EXAMPLES = [
    body
    for language, body in code_blocks(read_page("03-python-sdk.md"))
    if language in {"yaml", "yml"} and "competency_questions:" in body
]


@pytest.mark.parametrize("example", EXAMPLES)
def test_example_use_case_parses_with_the_real_parser(example):
    parse_use_case_yaml(example)


def test_an_example_use_case_declares_consumers_whose_tasks_need_its_questions():
    use_cases = [parse_use_case_yaml(example) for example in EXAMPLES]

    tasks = [task for uc in use_cases for consumer in uc.consumers for task in consumer.tasks]
    assert any(task.competency_questions for task in tasks)
