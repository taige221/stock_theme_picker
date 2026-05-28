# -*- coding: utf-8 -*-

from __future__ import annotations

import pytest

from theme_picker.strategy.params import StrategyParamValidationError, StrategyParams


def test_strategy_params_reject_unknown_fields_by_default() -> None:
    with pytest.raises(StrategyParamValidationError, match="Unknown StrategyParams field"):
        StrategyParams.from_dict({"min_breakout_pcnt": 2.0})


def test_strategy_params_can_ignore_unknown_fields_explicitly_for_legacy_payloads() -> None:
    params = StrategyParams.from_dict({"min_breakout_pcnt": 2.0, "min_breakout_pct": 3.0}, strict=False)

    assert params.min_breakout_pct == 3.0


def test_strategy_params_reject_invalid_ranges() -> None:
    with pytest.raises(StrategyParamValidationError, match="position_size_pct"):
        StrategyParams.from_dict({"position_size_pct": 1.5})

    with pytest.raises(StrategyParamValidationError, match="stop_loss_pct"):
        StrategyParams.from_dict({"stop_loss_pct": -0.01})
