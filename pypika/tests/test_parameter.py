import unittest
from datetime import date

import pytest

from pypika import (
    FormatParameter,
    NamedParameter,
    NumericParameter,
    Parameter,
    PyformatParameter,
    QmarkParameter,
    Query,
    Table,
    Tables,
)
from pypika.dialects import ClickHouseQuery, MySQLQuery
from pypika.terms import DictParameter, ListParameter, ParameterValueWrapper
from pypika.utils import ParameterException


class ParametrizedTests(unittest.TestCase):
    table_abc, table_efg = Tables("abc", "efg")

    def test_param_insert(self):
        q = Query.into(self.table_abc).columns("a", "b", "c").insert(Parameter("?"), Parameter("?"), Parameter("?"))

        self.assertEqual('INSERT INTO "abc" ("a","b","c") VALUES (?,?,?)', q.get_sql())

    def test_param_select_join(self):
        q = (
            Query.from_(self.table_abc)
            .select("*")
            .where(self.table_abc.category == Parameter("%s"))
            .join(self.table_efg)
            .on(self.table_abc.id == self.table_efg.abc_id)
            .where(self.table_efg.date >= Parameter("%s"))
            .limit(10)
        )

        self.assertEqual(
            'SELECT * FROM "abc" JOIN "efg" ON "abc"."id"="efg"."abc_id" WHERE "abc"."category"=%s AND "efg"."date">=%s LIMIT 10',
            q.get_sql(),
        )

    def test_param_select_subquery(self):
        q = (
            Query.from_(self.table_abc)
            .select("*")
            .where(self.table_abc.category == Parameter(":1"))
            .where(
                self.table_abc.id.isin(
                    Query.from_(self.table_efg)
                    .select(self.table_efg.abc_id)
                    .where(self.table_efg.date >= Parameter(":2"))
                )
            )
            .limit(10)
        )

        self.assertEqual(
            'SELECT * FROM "abc" WHERE "category"=:1 AND "id" IN (SELECT "abc_id" FROM "efg" WHERE "date">=:2) LIMIT 10',
            q.get_sql(),
        )

    def test_join(self):
        subquery = (
            Query.from_(self.table_efg)
            .select(self.table_efg.fiz, self.table_efg.buz)
            .where(self.table_efg.buz == Parameter(":buz"))
        )

        q = (
            Query.from_(self.table_abc)
            .join(subquery)
            .on(self.table_abc.bar == subquery.buz)
            .select(self.table_abc.foo, subquery.fiz)
            .where(self.table_abc.bar == Parameter(":bar"))
        )

        self.assertEqual(
            'SELECT "abc"."foo","sq0"."fiz" FROM "abc" JOIN (SELECT "fiz","buz" FROM "efg" WHERE "buz"=:buz)'
            ' "sq0" ON "abc"."bar"="sq0"."buz" WHERE "abc"."bar"=:bar',
            q.get_sql(),
        )

    def test_qmark_parameter(self):
        self.assertEqual('?', QmarkParameter().get_sql())

    def test_numeric_parameter(self):
        self.assertEqual(':14', NumericParameter('14').get_sql())
        self.assertEqual(':15', NumericParameter(15).get_sql())

    def test_named_parameter(self):
        self.assertEqual(':buz', NamedParameter('buz').get_sql())

    def test_format_parameter(self):
        self.assertEqual('%s', FormatParameter().get_sql())

    def test_pyformat_parameter(self):
        self.assertEqual('%(buz)s', PyformatParameter('buz').get_sql())


class ParametrizedTestsWithValues(unittest.TestCase):
    table_abc, table_efg = Tables("abc", "efg")

    def test_param_insert(self):
        q = Query.into(self.table_abc).columns("a", "b", "c").insert(1, 2.2, 'foo')

        parameter = QmarkParameter()
        sql = q.get_sql(parameter=parameter)
        self.assertEqual('INSERT INTO "abc" ("a","b","c") VALUES (?,?,?)', sql)
        self.assertEqual([1, 2.2, 'foo'], parameter.get_parameters())

    def test_param_select_join(self):
        q = (
            Query.from_(self.table_abc)
            .select("*")
            .where(self.table_abc.category == 'foobar')
            .join(self.table_efg)
            .on(self.table_abc.id == self.table_efg.abc_id)
            .where(self.table_efg.date >= date(2024, 2, 22))
            .limit(10)
        )

        parameter = FormatParameter()
        sql = q.get_sql(parameter=parameter)
        self.assertEqual(
            'SELECT * FROM "abc" JOIN "efg" ON "abc"."id"="efg"."abc_id" WHERE "abc"."category"=%s AND "efg"."date">=%s LIMIT 10',
            sql,
        )
        self.assertEqual(['foobar', '2024-02-22'], parameter.get_parameters())

    def test_param_select_subquery(self):
        q = (
            Query.from_(self.table_abc)
            .select("*")
            .where(self.table_abc.category == 'foobar')
            .where(
                self.table_abc.id.isin(
                    Query.from_(self.table_efg)
                    .select(self.table_efg.abc_id)
                    .where(self.table_efg.date >= date(2024, 2, 22))
                )
            )
            .limit(10)
        )

        parameter = NumericParameter(placeholder=lambda idx: idx + 1)
        sql = q.get_sql(parameter=parameter)
        self.assertEqual(
            'SELECT * FROM "abc" WHERE "category"=:1 AND "id" IN (SELECT "abc_id" FROM "efg" WHERE "date">=:2) LIMIT 10',
            sql,
        )
        self.assertEqual(['foobar', '2024-02-22'], parameter.get_parameters())

    def test_join(self):
        subquery = (
            Query.from_(self.table_efg)
            .select(self.table_efg.fiz, self.table_efg.buz)
            .where(self.table_efg.buz == 'buz')
        )

        q = (
            Query.from_(self.table_abc)
            .join(subquery)
            .on(self.table_abc.bar == subquery.buz)
            .select(self.table_abc.foo, subquery.fiz)
            .where(self.table_abc.bar == 'bar')
        )

        parameter = NamedParameter()
        sql = q.get_sql(parameter=parameter)
        self.assertEqual(
            'SELECT "abc"."foo","sq0"."fiz" FROM "abc" JOIN (SELECT "fiz","buz" FROM "efg" WHERE "buz"=:param1)'
            ' "sq0" ON "abc"."bar"="sq0"."buz" WHERE "abc"."bar"=:param2',
            sql,
        )
        self.assertEqual({'param1': 'buz', 'param2': 'bar'}, parameter.get_parameters())

    def test_join_with_parameter_value_wrapper(self):
        subquery = (
            Query.from_(self.table_efg)
            .select(self.table_efg.fiz, self.table_efg.buz)
            .where(self.table_efg.buz == ParameterValueWrapper(Parameter(':buz'), 'buz'))
        )

        q = (
            Query.from_(self.table_abc)
            .join(subquery)
            .on(self.table_abc.bar == subquery.buz)
            .select(self.table_abc.foo, subquery.fiz)
            .where(self.table_abc.bar == ParameterValueWrapper(NamedParameter('bar'), 'bar'))
        )

        parameter = NamedParameter()
        sql = q.get_sql(parameter=parameter)
        self.assertEqual(
            'SELECT "abc"."foo","sq0"."fiz" FROM "abc" JOIN (SELECT "fiz","buz" FROM "efg" WHERE "buz"=:buz)'
            ' "sq0" ON "abc"."bar"="sq0"."buz" WHERE "abc"."bar"=:bar',
            sql,
        )
        self.assertEqual({':buz': 'buz', 'bar': 'bar'}, parameter.get_parameters())

    def test_pyformat_parameter(self):
        q = Query.into(self.table_abc).columns("a", "b", "c").insert(1, 2.2, 'foo')

        parameter = PyformatParameter()
        sql = q.get_sql(parameter=parameter)
        self.assertEqual('INSERT INTO "abc" ("a","b","c") VALUES (%(param1)s,%(param2)s,%(param3)s)', sql)
        self.assertEqual({"param1": 1, "param2": 2.2, "param3": "foo"}, parameter.get_parameters())


class ParametrizedBackslashTests(unittest.TestCase):
    # MySQL and ClickHouse escape backslashes in inline SQL string literals, but a
    # value collected for a bound parameter is not an SQL literal: the bound value
    # must be the original, unescaped value.

    def test_mysql_format_parameter_keeps_original_value(self):
        parameter = FormatParameter()
        q = MySQLQuery.update(Table("t")).set("col", "a\\b")

        self.assertEqual("UPDATE `t` SET `col`=%s", q.get_sql(parameter=parameter))
        self.assertEqual(["a\\b"], parameter.get_parameters())

    def test_mysql_qmark_parameter_keeps_original_value(self):
        parameter = QmarkParameter()
        q = MySQLQuery.update(Table("t")).set("col", "a\\b")

        self.assertEqual("UPDATE `t` SET `col`=?", q.get_sql(parameter=parameter))
        self.assertEqual(["a\\b"], parameter.get_parameters())

    def test_mysql_named_parameter_keeps_original_value(self):
        parameter = NamedParameter("param")
        q = MySQLQuery.update(Table("t")).set("col", "a\\b")

        self.assertEqual("UPDATE `t` SET `col`=:param", q.get_sql(parameter=parameter))
        self.assertEqual({"param": "a\\b"}, parameter.get_parameters())

    def test_clickhouse_format_parameter_keeps_original_value(self):
        parameter = FormatParameter()
        q = ClickHouseQuery.update(Table("t")).set("col", "a\\b")

        self.assertEqual('ALTER TABLE "t" UPDATE "col"=%s', q.get_sql(parameter=parameter))
        self.assertEqual(["a\\b"], parameter.get_parameters())

    def test_mysql_inline_literal_is_still_escaped(self):
        # Side by side with the parameter tests above: the inline path still escapes
        q = MySQLQuery.update(Table("t")).set("col", "a\\b")

        self.assertEqual("UPDATE `t` SET `col`='a\\\\b'", q.get_sql())


# Inputs that must never be accepted as a placeholder: they contain a statement
# separator, whitespace/newline, quotes or SQL comment markers and would let a
# caller supplied string break out of the placeholder boundary.
MALICIOUS_PLACEHOLDERS = [
    "?; DELETE FROM users",
    "?\nDELETE FROM users",
    ":1; DROP TABLE t",
    ":name; DELETE FROM t",
    "%s; DELETE FROM t",
    "%(name)s; DELETE FROM t",
    "1; DELETE FROM t",
    "name\n--",
    "' OR '1'='1",
    "1 --",
    ":1/*comment*/",
    "",
]

PARAMETER_CLASSES = [
    Parameter,
    QmarkParameter,
    NumericParameter,
    NamedParameter,
    FormatParameter,
    PyformatParameter,
]


class TestParameterInjection:
    """pytest parameterized acceptance tests for placeholder boundary hardening."""

    @pytest.mark.parametrize("parameter_cls", PARAMETER_CLASSES)
    @pytest.mark.parametrize("placeholder", MALICIOUS_PLACEHOLDERS)
    def test_malicious_placeholder_rejected_at_construction(self, parameter_cls, placeholder):
        with pytest.raises(ParameterException):
            parameter_cls(placeholder)

    @pytest.mark.parametrize("parameter_cls", PARAMETER_CLASSES)
    @pytest.mark.parametrize("placeholder", MALICIOUS_PLACEHOLDERS)
    def test_malicious_placeholder_never_rendered(self, parameter_cls, placeholder):
        with pytest.raises(ParameterException):
            parameter_cls(placeholder).get_sql()

    @pytest.mark.parametrize("parameter_cls", PARAMETER_CLASSES)
    @pytest.mark.parametrize(
        "placeholder",
        [
            "?; DELETE FROM users",
            "?\nDELETE FROM users",
            ":1; SELECT 1",
            ":name; SELECT 1",
            "%s; SELECT 1",
            "%(name)s; SELECT 1",
        ],
    )
    def test_multi_statement_input_fails_during_query_generation(self, parameter_cls, placeholder):
        table = Table("abc")
        with pytest.raises(ParameterException):
            Query.from_(table).select("*").where(table.category == parameter_cls(placeholder)).get_sql()

    @pytest.mark.parametrize(
        ("parameter_cls", "placeholder"),
        [
            (QmarkParameter, ":1"),
            (QmarkParameter, "%s"),
            (NumericParameter, ":name"),
            (NumericParameter, "?"),
            (NamedParameter, ":1"),
            (NamedParameter, "%(name)s"),
            (FormatParameter, "?"),
            (FormatParameter, ":name"),
            (PyformatParameter, ":name"),
            (PyformatParameter, "%s"),
        ],
    )
    def test_paramstyle_conflict_rejected(self, parameter_cls, placeholder):
        with pytest.raises(ParameterException):
            parameter_cls(placeholder)

    @pytest.mark.parametrize(
        ("parameter_cls", "placeholder", "expected_sql"),
        [
            (QmarkParameter, "?", "?"),
            (NumericParameter, 14, ":14"),
            (NumericParameter, "14", ":14"),
            (NumericParameter, ":15", ":15"),
            (NamedParameter, "buz", ":buz"),
            (NamedParameter, ":buz", ":buz"),
            (FormatParameter, "%s", "%s"),
            (PyformatParameter, "buz", "%(buz)s"),
            (PyformatParameter, "%(buz)s", "%(buz)s"),
        ],
    )
    def test_legal_tokens_render_unchanged(self, parameter_cls, placeholder, expected_sql):
        assert parameter_cls(placeholder).get_sql() == expected_sql

    @pytest.mark.parametrize(
        ("parameter_cls", "expected_sql", "expected_params"),
        [
            (QmarkParameter, "?,?", [1, "foo"]),
            (FormatParameter, "%s,%s", [1, "foo"]),
            (NamedParameter, ":param1,:param2", {"param1": 1, "param2": "foo"}),
            (PyformatParameter, "%(param1)s,%(param2)s", {"param1": 1, "param2": "foo"}),
        ],
    )
    def test_legal_parameter_collection_preserved(self, parameter_cls, expected_sql, expected_params):
        table = Table("abc")
        query = Query.into(table).columns("a", "b").insert(1, "foo")
        parameter = parameter_cls()

        sql = query.get_sql(parameter=parameter)

        assert sql == f'INSERT INTO "abc" ("a","b") VALUES ({expected_sql})'
        assert parameter.get_parameters() == expected_params

    def test_numeric_generator_collection_preserved(self):
        table = Table("abc")
        query = Query.from_(table).select("*").where(table.category == "foobar").where(table.id >= 2)
        parameter = NumericParameter(placeholder=lambda idx: idx + 1)

        sql = query.get_sql(parameter=parameter)

        assert sql == 'SELECT * FROM "abc" WHERE "category"=:1 AND "id">=:2'
        assert parameter.get_parameters() == ["foobar", 2]

    def test_malicious_generator_output_rejected_at_render(self):
        parameter = NumericParameter(placeholder=lambda idx: f"{idx + 1}; DELETE FROM t")

        with pytest.raises(ParameterException):
            parameter.placeholder

    @pytest.mark.parametrize("parameter_cls", [QmarkParameter, FormatParameter])
    def test_non_string_placeholder_rejected(self, parameter_cls):
        with pytest.raises(ParameterException):
            parameter_cls(["?"])

    def test_named_parameter_conflicting_values_fail(self):
        parameter = NamedParameter("p")
        parameter.update_parameters(param_key="p", value=1)

        with pytest.raises(ParameterException):
            parameter.update_parameters(param_key="p", value=2)

    def test_named_parameter_repeated_placeholder_keeps_value(self):
        table = Table("abc")
        parameter = NamedParameter("p")
        Query.from_(table).select("*").where(table.a == "v").where(table.b == "v").get_sql(parameter=parameter)

        assert parameter.get_parameters() == {"p": "v"}


class ListParameterCompatibilityTests(unittest.TestCase):
    def test_generic_list_generator_must_emit_full_token(self):
        parameter = ListParameter(placeholder=lambda idx: f":{idx + 1}")
        self.assertEqual(":1", parameter.placeholder)

    def test_generic_list_rejects_bare_generator_output(self):
        # The built-in generator emits a bare digit; only the numeric subclass can
        # turn it into a valid ":n" token, the generic base must not render it raw.
        with self.assertRaises(ParameterException):
            ListParameter().placeholder

    def test_generic_list_static_placeholder_is_validated(self):
        self.assertEqual("?", ListParameter("?").get_sql())
        with self.assertRaises(ParameterException):
            ListParameter("?; DELETE FROM t").get_sql()

    def test_generic_dict_rejects_bare_generator_output(self):
        with self.assertRaises(ParameterException):
            DictParameter().placeholder

    def test_generic_dict_static_placeholder_is_validated(self):
        self.assertEqual(":buz", DictParameter(":buz").get_sql())
        with self.assertRaises(ParameterException):
            DictParameter(":buz; DELETE FROM t").get_sql()
