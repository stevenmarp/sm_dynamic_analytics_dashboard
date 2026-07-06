# -*- coding: utf-8 -*-

import ast
import re
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.safe_eval import safe_eval

EMPTY = {"labels": [], "values": [], "rows": [], "domains": [], "total": 0}
NUMERIC_TTYPES = ("integer", "float", "monetary")
MANAGER_GROUP = "sm_dynamic_analytics_dashboard.group_sm_analytics_manager"


class SmAnalyticsAnalysis(models.Model):
    _name = "sm.analytics.analysis"
    _description = "SM Analytics Analysis"
    _order = "name"

    name = fields.Char(required=True)
    source_type = fields.Selection(
        [("model", "Point & Click (recommended)"), ("sql", "Advanced SQL (experts only)")],
        default="model", required=True,
    )
    model_id = fields.Many2one("ir.model", ondelete="cascade")
    model_name = fields.Char(related="model_id.model", string="Technical Model", store=True)
    domain = fields.Char(default="[]")
    measure_field_id = fields.Many2one("ir.model.fields", domain="[('model_id', '=', model_id), ('ttype', 'in', ('integer', 'float', 'monetary'))]")
    groupby_field_id = fields.Many2one("ir.model.fields", domain="[('model_id', '=', model_id), ('store', '=', True)]")
    groupby_field_2_id = fields.Many2one(
        "ir.model.fields", string="Second Group By",
        domain="[('model_id', '=', model_id), ('store', '=', True)]",
        help="Add a second dimension to build a pivot table or heatmap "
             "(rows x columns).",
    )
    date_field_id = fields.Many2one(
        "ir.model.fields",
        string="Date Field",
        domain="[('model_id', '=', model_id), ('ttype', 'in', ('date', 'datetime')), ('store', '=', True)]",
        help="Field used by the dashboard date range filter and KPI trend comparison.",
    )
    aggregate = fields.Selection([
        ("count", "Count"),
        ("sum", "Sum"),
        ("avg", "Average"),
        ("min", "Minimum"),
        ("max", "Maximum"),
    ], default="count", required=True)
    sql_query = fields.Text()
    limit = fields.Integer(default=20)
    order_by = fields.Char()

    @api.onchange("model_id")
    def _onchange_model_id(self):
        self.measure_field_id = False
        self.groupby_field_id = False
        self.date_field_id = False

    @api.constrains("aggregate", "measure_field_id", "source_type")
    def _check_measure_field(self):
        for rec in self:
            if rec.source_type != "model" or rec.aggregate == "count":
                continue
            if not rec.measure_field_id:
                raise ValidationError(_(
                    "Aggregate '%s' needs a Measure field. Choose a numeric field, "
                    "or set Aggregate to Count."
                ) % rec.aggregate)
            if rec.measure_field_id.ttype not in NUMERIC_TTYPES:
                raise ValidationError(_(
                    "Measure '%s' is a %s field. Sum, Average, Minimum and Maximum "
                    "only work on numeric fields (integer, float, monetary)."
                ) % (rec.measure_field_id.name, rec.measure_field_id.ttype))

    def sm_test_analysis(self):
        self.ensure_one()
        data = self.sm_get_data()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Analysis Test"),
                "message": _("Loaded %s rows (total %s).") % (len(data.get("rows", [])), data.get("total", 0)),
                "type": "success",
                "sticky": False,
            },
        }

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------
    def sm_get_data(self, date_from=False, date_to=False):
        self.ensure_one()
        if self.source_type == "sql":
            return self.sm_get_sql_data()
        return self.sm_get_model_data(date_from=date_from, date_to=date_to)

    def sm_get_model_data(self, date_from=False, date_to=False):
        self.ensure_one()
        if not self.model_id:
            return dict(EMPTY)
        model = self.env[self.model_id.model].with_context(active_test=False)
        domain = self.sm_parse_domain() + self._sm_date_domain(date_from, date_to)
        limit = self.limit if self.limit > 0 else 20
        if self.groupby_field_id:
            group_name = self.groupby_field_id.name
            fields_spec = [group_name]
            # Defensive: only aggregate a genuinely numeric field. Guards legacy
            # rows saved before the constraint (e.g. avg on a date) — falls back
            # to count instead of crashing read_group.
            use_measure = (
                self.aggregate != "count"
                and self.measure_field_id
                and self.measure_field_id.ttype in NUMERIC_TTYPES
            )
            if use_measure:
                fields_spec.append("%s:%s" % (self.measure_field_id.name, self.aggregate))
            rows = model.read_group(domain, fields_spec, [group_name], limit=limit, orderby=self.order_by or False)
            # Odoo 18 lazy read_group keys: a measured field comes back under the
            # field's own name, and the count under "<groupby>_count" (not
            # "__count"). Fall back to "__count" for safety.
            measure_key = self.measure_field_id.name if use_measure else "%s_count" % group_name
            labels, values, result_rows, domains = [], [], [], []
            for row in rows:
                raw_label = row.get(group_name)
                label = raw_label[1] if isinstance(raw_label, (tuple, list)) and len(raw_label) == 2 else raw_label
                label = self._sm_clean_label(label)
                value = self._sm_num(row.get(measure_key, row.get("__count", 0)))
                row_domain = row.get("__domain") or domain
                labels.append(label)
                values.append(value)
                domains.append(row_domain)
                result_rows.append({"label": label, "value": value})
            return {
                "labels": labels,
                "values": values,
                "rows": result_rows,
                "domains": domains,
                "total": self._sm_num(sum(values)),
                "model": self.model_id.model,
                "base_domain": domain,
            }
        # No group-by: a single aggregate over the whole domain. Honor the
        # chosen measure (sum/avg/max/min) so KPI/gauge blocks show the real
        # figure, not just the record count.
        use_measure = (
            self.aggregate != "count"
            and self.measure_field_id
            and self.measure_field_id.ttype in NUMERIC_TTYPES
        )
        if use_measure:
            spec = "%s:%s" % (self.measure_field_id.name, self.aggregate)
            grouped = model.read_group(domain, [spec], [])
            total = self._sm_num(grouped[0].get(self.measure_field_id.name, 0)) if grouped else 0.0
        else:
            total = model.search_count(domain)
        records = model.search_read(domain, ["display_name"], limit=limit)
        return {
            "labels": [_("Records")],
            "values": [total],
            "rows": [{"label": rec.get("display_name"), "value": rec.get("id")} for rec in records],
            "domains": [domain for _rec in records],
            "total": total,
            "model": self.model_id.model,
            "base_domain": domain,
        }

    def sm_get_matrix_data(self, date_from=False, date_to=False):
        """Two-dimensional aggregation for pivot tables and heatmaps.

        Groups by [groupby_field_id, groupby_field_2_id] and returns
        {rows, cols, matrix, total}. Falls back to the 1-D payload when a
        second dimension is not configured, so a block can always render.
        """
        self.ensure_one()
        if self.source_type != "model" or not self.model_id or not self.groupby_field_2_id:
            return dict(self.sm_get_data(date_from, date_to), matrix=[], rows=[], cols=[])
        model = self.env[self.model_id.model].with_context(active_test=False)
        domain = self.sm_parse_domain() + self._sm_date_domain(date_from, date_to)
        g1, g2 = self.groupby_field_id.name, self.groupby_field_2_id.name
        use_measure = (
            self.aggregate != "count" and self.measure_field_id
            and self.measure_field_id.ttype in NUMERIC_TTYPES
        )
        fields_spec = [g1, g2]
        if use_measure:
            fields_spec.append("%s:%s" % (self.measure_field_id.name, self.aggregate))
        groups = model.read_group(domain, fields_spec, [g1, g2], lazy=False)
        measure_key = self.measure_field_id.name if use_measure else "__count"
        row_labels, col_labels, cells = [], [], {}
        for grp in groups:
            r = self._sm_clean_label(self._sm_pair(grp.get(g1)))
            c = self._sm_clean_label(self._sm_pair(grp.get(g2)))
            if r not in row_labels:
                row_labels.append(r)
            if c not in col_labels:
                col_labels.append(c)
            cells[(r, c)] = self._sm_num(grp.get(measure_key, 0))
        matrix = [[cells.get((r, c), 0) for c in col_labels] for r in row_labels]
        return {
            "rows": row_labels,
            "cols": col_labels,
            "matrix": matrix,
            "total": self._sm_num(sum(sum(line) for line in matrix)),
            "model": self.model_id.model,
        }

    @staticmethod
    def _sm_pair(raw):
        return raw[1] if isinstance(raw, (tuple, list)) and len(raw) == 2 else raw

    def sm_get_trend(self, date_from, date_to, mode="previous"):
        """Total compared with a baseline period.

        mode="previous": the period immediately before [date_from, date_to].
        mode="year": the same range shifted back exactly one year (YoY).

        Returns {previous, delta, delta_pct, direction} or False when a
        comparison is not possible. Defensive: any failure yields False.
        """
        self.ensure_one()
        if self.source_type != "model" or not self.date_field_id or not (date_from and date_to):
            return False
        try:
            start = fields.Date.to_date(date_from)
            end = fields.Date.to_date(date_to)
            if not start or not end or end < start:
                return False
            if mode == "year":
                prev_from = start - relativedelta(years=1)
                prev_to = end - relativedelta(years=1)
            else:
                span = end - start
                prev_from = start - span - timedelta(days=1)
                prev_to = start - timedelta(days=1)
            # savepoint so a failing query rolls back cleanly instead of
            # leaving the request transaction aborted.
            with self.env.cr.savepoint():
                current = self.sm_get_data(date_from, date_to).get("total", 0)
                previous = self.sm_get_data(
                    fields.Date.to_string(prev_from), fields.Date.to_string(prev_to)
                ).get("total", 0)
        except Exception:
            return False
        delta = self._sm_num(current) - self._sm_num(previous)
        delta_pct = (delta / abs(previous) * 100.0) if previous else (100.0 if delta else 0.0)
        return {
            "previous": self._sm_num(previous),
            "delta": self._sm_num(delta),
            "delta_pct": round(delta_pct, 1),
            "direction": "up" if delta > 0 else ("down" if delta < 0 else "flat"),
        }

    def sm_get_sql_data(self):
        self.ensure_one()
        # Raw SQL bypasses record rules, ACLs and the company boundary, so only
        # trusted managers may run it. A shared read-only viewer opening a
        # dashboard that embeds an SQL block gets a clear access error instead
        # of silently reading another company's rows.
        if not self.env.su and not self.env.user.has_group(MANAGER_GROUP):
            raise AccessError(_(
                "SQL analytics can only be run by an Analytics Manager."))
        query = (self.sql_query or "").strip().rstrip(";").strip()
        if not query:
            return dict(EMPTY)
        self.sm_validate_sql(query)
        if self.limit > 0 and not re.search(r"\blimit\b", query, re.I):
            query = "%s LIMIT %s" % (query, int(self.limit))
        # Read-only guard: run inside a savepoint that caps runtime, so a paid
        # module can expose SQL blocks without a runaway query freezing the DB.
        with self.env.cr.savepoint():
            self.env.cr.execute("SET LOCAL statement_timeout = '15s'")
            self.env.cr.execute(query)
            columns = [desc[0] for desc in self.env.cr.description or []]
            result = [dict(zip(columns, row)) for row in self.env.cr.fetchall()]
        labels, values = [], []
        for row in result:
            label = row.get("label") or row.get("name") or next(iter(row.values()), "")
            value = row.get("value") or row.get("total") or row.get("count") or 0
            labels.append(str(label))
            values.append(self._sm_num(value))
        return {
            "labels": labels,
            "values": values,
            "rows": [self._sm_jsonify_row(r) for r in result],
            "domains": [],
            "total": self._sm_num(sum(values)),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _sm_date_domain(self, date_from, date_to):
        self.ensure_one()
        if not self.date_field_id or not (date_from or date_to):
            return []
        field = self.date_field_id.name
        is_dt = self.date_field_id.ttype == "datetime"
        clause = []
        if date_from:
            clause.append((field, ">=", date_from))
        if date_to:
            # For datetime fields, include the whole end day instead of cutting
            # off at midnight.
            clause.append((field, "<=", "%s 23:59:59" % date_to if is_dt else date_to))
        return clause

    @staticmethod
    def _sm_num(value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def _sm_clean_label(self, label):
        if label is False or label is None:
            return _("Undefined")
        if isinstance(label, (list, tuple)):
            return str(label[-1]) if label else _("Undefined")
        return str(label)

    def _sm_jsonify_row(self, row):
        clean = {}
        for key, value in row.items():
            if isinstance(value, (datetime,)) or hasattr(value, "isoformat"):
                clean[key] = value.isoformat()
            elif isinstance(value, (int, float, str, bool)) or value is None:
                clean[key] = value
            else:
                clean[key] = str(value)
        return clean

    def sm_parse_domain(self):
        self.ensure_one()
        if not self.domain:
            return []
        try:
            value = safe_eval(self.domain, {"uid": self.env.uid})
        except Exception:
            value = ast.literal_eval(self.domain)
        if not isinstance(value, list):
            raise UserError(_("Domain must be a list."))
        return value

    def sm_validate_sql(self, query):
        forbidden = r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|copy|execute|call|do|vacuum|analyze|reindex|cluster|lock|comment|set|reset)\b"
        if not re.match(r"(?is)^\s*(select|with)\b", query):
            raise UserError(_("Only SELECT or WITH SQL queries are allowed."))
        if re.search(forbidden, query, re.I):
            raise UserError(_("SQL query contains a forbidden statement."))
        # Block stacked statements (e.g. "SELECT 1; DELETE ..."). A single
        # trailing ";" was already stripped by the caller.
        if ";" in query:
            raise UserError(_("Only a single SQL statement is allowed."))
        return True
