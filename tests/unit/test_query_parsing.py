# SPDX-License-Identifier: Apache-2.0
"""Unit tests for common's Datalog-query parsing helpers.

These are the string-aware parsers that both ask_router and (after #99)
run_logic_check rely on. The headline case is a comma *inside* a quoted
literal, which the naive ``split(",")`` parser gets wrong.
"""
from __future__ import annotations

import common
import pytest


class TestQueryArgs:
    def test_plain_three_args(self):
        assert common._query_args('relation("A", "born_in", "Paris")?') == [
            '"A"',
            '"born_in"',
            '"Paris"',
        ]

    def test_comma_inside_quoted_literal_stays_one_arg(self):
        # The bug from #99: a comma inside a quoted object must not split.
        args = common._query_args('relation("A", "born_in", "Paris, France")?')
        assert args == ['"A"', '"born_in"', '"Paris, France"']
        assert len(args) == 3

    def test_escaped_quote_inside_literal(self):
        args = common._query_args(r'relation("A", "said", "she \"left\"")?')
        assert len(args) == 3
        assert common._arg_value(args[2]) == 'she "left"'

    def test_variables_and_constants_mixed(self):
        assert common._query_args('relation(X, "born_in", Y)?') == [
            "X",
            '"born_in"',
            "Y",
        ]

    def test_non_query_returns_empty(self):
        assert common._query_args("not a query") == []


class TestArgValue:
    def test_unquotes_string(self):
        assert common._arg_value('"Paris"') == "Paris"

    def test_decodes_json_escapes(self):
        assert common._arg_value(r'"a\tb"') == "a\tb"

    def test_passes_through_variable(self):
        assert common._arg_value("X") == "X"


class TestArgPredicates:
    @pytest.mark.parametrize("arg", ['"x"', '"hello world"', '""'])
    def test_quoted_strings(self, arg):
        assert common._is_quoted_string(arg)

    @pytest.mark.parametrize("arg", ["X", "unquoted", '"unterminated'])
    def test_not_quoted_strings(self, arg):
        assert not common._is_quoted_string(arg)

    @pytest.mark.parametrize("arg", ["X", "Foo", "_x", "X1"])
    def test_variables(self, arg):
        assert common._is_variable(arg)

    @pytest.mark.parametrize("arg", ["x", "1X", '"X"', "X-Y"])
    def test_not_variables(self, arg):
        assert not common._is_variable(arg)
