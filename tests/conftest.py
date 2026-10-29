import pytest

import stetiq


@pytest.fixture
def client(tmp_path):
    return stetiq.Client(tracking_uri=f"sqlite:///{tmp_path / 'stetiq.db'}")


SUPPORT_ONTOLOGY = """
node_types:
  - label: Customer
    properties:
      - name: name
        type: STRING
        required: true
  - label: Ticket
    description: A support request
    properties:
      - name: opened_at
        type: DATE
relationship_types:
  - label: OPENED
patterns:
  - [Customer, OPENED, Ticket]
"""


@pytest.fixture
def support_ontology():
    return SUPPORT_ONTOLOGY
