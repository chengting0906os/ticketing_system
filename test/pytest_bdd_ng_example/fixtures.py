from typing import Any

import pytest


@pytest.fixture
def calculator_state() -> dict[str, Any]:
    return {'numbers': [], 'result': None}
