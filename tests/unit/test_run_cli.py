# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the FactlogError -> exit-1 boundary helper (#109)."""
from __future__ import annotations

import common


class TestRunCli:
    def test_passes_through_return_code(self):
        assert common.run_cli(lambda: 0) == 0
        assert common.run_cli(lambda: 2) == 2

    def test_none_return_is_zero(self):
        assert common.run_cli(lambda: None) == 0

    def test_factlog_error_becomes_exit_1(self, capsys):
        def boom():
            raise common.FactlogError("missing facts/accepted.dl")

        assert common.run_cli(boom) == 1
        assert "missing facts/accepted.dl" in capsys.readouterr().err

    def test_other_exceptions_propagate(self):
        import pytest

        def boom():
            raise ValueError("not a factlog error")

        with pytest.raises(ValueError):
            common.run_cli(boom)
