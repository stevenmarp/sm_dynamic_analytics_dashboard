# -*- coding: utf-8 -*-

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSmAnalytics(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Analysis = self.env["sm.analytics.analysis"]

    def _sql(self, query):
        return self.Analysis.new({"source_type": "sql", "sql_query": query})

    # --- SQL guard (security path) -------------------------------------
    def test_sql_valid_select_passes(self):
        self.assertTrue(self._sql("SELECT 1").sm_validate_sql("SELECT 1"))
        self.assertTrue(self._sql("WITH x AS (SELECT 1) SELECT * FROM x")
                        .sm_validate_sql("WITH x AS (SELECT 1) SELECT * FROM x"))

    def test_sql_non_select_rejected(self):
        with self.assertRaises(UserError):
            self._sql("TABLE res_users").sm_validate_sql("TABLE res_users")

    def test_sql_forbidden_keyword_rejected(self):
        for bad in ("DELETE FROM res_users", "SELECT 1; DROP TABLE res_users"):
            with self.assertRaises(UserError):
                self._sql(bad).sm_validate_sql(bad)

    def test_sql_stacked_statement_rejected(self):
        # Two SELECTs stacked must not be allowed even without a forbidden word.
        with self.assertRaises(UserError):
            self._sql("SELECT 1; SELECT 2").sm_validate_sql("SELECT 1; SELECT 2")

    # --- Model data / drill-down payload -------------------------------
    def test_model_groupby_returns_drill_domains(self):
        analysis = self.Analysis.create({
            "name": "Users by company",
            "source_type": "model",
            "model_id": self.env["ir.model"]._get_id("res.users"),
            "groupby_field_id": self.env["ir.model.fields"]._get(
                "res.users", "company_id").id,
            "aggregate": "count",
        })
        data = analysis.sm_get_data()
        self.assertEqual(len(data["labels"]), len(data["values"]))
        self.assertEqual(len(data["domains"]), len(data["labels"]))
        self.assertEqual(data["model"], "res.users")
        self.assertTrue(all(isinstance(d, list) for d in data["domains"]))

    def test_groupby_count_key_not_zero(self):
        # Regression: Odoo 18 lazy read_group returns count under "<field>_count",
        # not "__count". A wrong key silently yields 0 and empty charts.
        analysis = self.Analysis.create({
            "name": "Users by company",
            "source_type": "model",
            "model_id": self.env["ir.model"]._get_id("res.users"),
            "groupby_field_id": self.env["ir.model.fields"]._get(
                "res.users", "company_id").id,
            "aggregate": "count",
        })
        data = analysis.sm_get_data()
        self.assertTrue(data["values"], "expected at least one group")
        self.assertGreater(sum(data["values"]), 0, "count values must not be zero")

    def test_save_layout_persists(self):
        dashboard = self.env["sm.analytics.dashboard"].create({"name": "L"})
        block = self.env["sm.analytics.block"].create({
            "name": "B", "dashboard_id": dashboard.id, "block_type": "kpi",
        })
        self.env["sm.analytics.dashboard"].sm_save_layout(
            dashboard.id, [{"id": block.id, "x": 3, "y": 2, "w": 5, "h": 4}])
        self.assertEqual(
            (block.grid_x, block.grid_y, block.grid_w, block.grid_h), (3, 2, 5, 4))

    def test_date_range_narrows_count(self):
        analysis = self.Analysis.create({
            "name": "Partners in range",
            "source_type": "model",
            "model_id": self.env["ir.model"]._get_id("res.partner"),
            "aggregate": "count",
            "date_field_id": self.env["ir.model.fields"]._get(
                "res.partner", "create_date").id,
        })
        full = analysis.sm_get_data().get("total", 0)
        ranged = analysis.sm_get_data("1900-01-01", "1900-01-02").get("total", 0)
        self.assertLessEqual(ranged, full)
