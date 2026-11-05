import pytest
from pydantic import ValidationError

from checkweigher.config import MachineConfig


def machine(mode: str = "modbus", **modbus) -> MachineConfig:
    return MachineConfig.model_validate(
        {"id": 1, "code": "CW-01", "name": "CW", "mode": mode, "modbus": {"host": "10.0.0.1", **modbus}})


def test_default_layout_is_the_manual():
    layout = machine().modbus.layout
    assert (layout.summary, layout.weighing_result, layout.product_settings) == (190, 282, 619)


def test_shifted_layout_without_product_settings_needs_decimals_for_weights():
    with pytest.raises(ValidationError, match="decimals"):
        machine(summary_address=216, weighing_result_address=214, product_settings_address=None)
    assert machine(summary_address=216, weighing_result_address=214, product_settings_address=None, decimals=1)
    assert machine(summary_address=216, weighing_result_address=None, product_settings_address=None)


def test_counters_and_weight_must_fit_one_read():
    with pytest.raises(ValidationError, match="125-register"):
        machine(summary_address=216, weighing_result_address=600)
