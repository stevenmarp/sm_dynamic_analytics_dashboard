# -*- coding: utf-8 -*-

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)

EMPTY = {"labels": [], "values": [], "rows": [], "domains": [], "total": 0}


class SmAnalyticsBlock(models.Model):
    _name = "sm.analytics.block"
    _description = "SM Analytics Dashboard Block"
    _order = "sequence, id"

    name = fields.Char(string="Block Title", required=True, help="Label shown in the block header on the dashboard.")
    dashboard_id = fields.Many2one("sm.analytics.dashboard", required=True, ondelete="cascade")
    analysis_id = fields.Many2one(
        "sm.analytics.analysis", string="Data Source", ondelete="set null",
        help="The analysis that feeds data into this block. Create one under Analyses menu first.",
    )
    block_type = fields.Selection([
        ("kpi", "KPI (Single Number)"),
        ("bar", "Bar Chart"),
        ("line", "Line Chart"),
        ("area", "Area Chart"),
        ("pie", "Pie Chart"),
        ("doughnut", "Doughnut Chart"),
        ("radar", "Radar Chart"),
        ("polar", "Polar / Radial Chart"),
        ("scatter", "Scatter Chart"),
        ("sparkline", "Sparkline"),
        ("gauge", "Gauge (vs Target)"),
        ("funnel", "Funnel"),
        ("pivot", "Pivot Table"),
        ("heatmap", "Heatmap"),
        ("table", "Data Table"),
    ], default="kpi", required=True, string="Display As",
        help="How this block is rendered on the dashboard.")
    sequence = fields.Integer(default=10)
    width = fields.Selection(
        [("third", "Small (1/3)"), ("half", "Medium (1/2)"), ("full", "Full Width")],
        default="half", string="Initial Size",
        help="Starting width for new blocks. You can also drag-resize on the dashboard.",
    )
    color = fields.Char(default="#0E2D59", string="Block Color", help="Accent color used for the icon badge, chart bars, and progress fill.")
    icon = fields.Char(
        default="fa-bar-chart", string="Icon",
        help="FontAwesome icon class, e.g. fa-dollar, fa-users, fa-shopping-cart. "
             "Browse icons at fontawesome.com/v4/icons.",
    )
    grid_x = fields.Integer(default=0)
    grid_y = fields.Integer(default=0)
    grid_w = fields.Integer(default=0)
    grid_h = fields.Integer(default=0)
    value_prefix = fields.Char(
        string="Prefix",
        help="Text before the value, e.g. '$' or 'Rp '. Useful for currency.",
    )
    value_suffix = fields.Char(
        string="Suffix",
        help="Text after the value, e.g. '%%', ' units', ' kg'.",
    )
    decimals = fields.Integer(
        default=0, string="Decimal Places",
        help="Number of decimals shown. 0 = whole numbers, 2 = e.g. 1,234.56.",
    )
    target_value = fields.Float(
        string="Goal / Target",
        help="Set a target number. KPI blocks show a progress bar towards this goal.",
    )
    show_trend = fields.Boolean(
        string="Compare Period",
        help="Show an up/down trend badge comparing current vs a baseline period. "
             "Only works on KPI blocks when a date filter is active.",
    )
    compare_mode = fields.Selection(
        [("previous", "Previous Period"), ("year", "Same Period Last Year")],
        default="previous", string="Compare With",
        help="Baseline for the trend badge: the immediately preceding period, "
             "or the same range one year earlier (year over year).",
    )
    warn_below = fields.Float(
        string="Warn Below",
        help="Conditional formatting: KPI value and table rows turn red when "
             "the value is below this threshold. Leave 0 to disable.",
    )
    good_above = fields.Float(
        string="Good Above",
        help="Conditional formatting: KPI value and table rows turn green when "
             "the value is at or above this threshold. Leave 0 to disable.",
    )

    def sm_export_payload(self):
        self.ensure_one()
        return {
            "name": self.name,
            "block_type": self.block_type,
            "sequence": self.sequence,
            "width": self.width,
            "color": self.color,
            "icon": self.icon,
            "value_prefix": self.value_prefix,
            "value_suffix": self.value_suffix,
            "decimals": self.decimals,
            "target_value": self.target_value,
            "show_trend": self.show_trend,
            "compare_mode": self.compare_mode,
            "warn_below": self.warn_below,
            "good_above": self.good_above,
            "grid_x": self.grid_x,
            "grid_y": self.grid_y,
            "grid_w": self.grid_w,
            "grid_h": self.grid_h,
        }

    # 12-column defaults derived from the legacy `width` field and block type.
    _WIDTH_TO_W = {"third": 4, "half": 6, "full": 12}

    def _sm_grid(self):
        self.ensure_one()
        if self.grid_w > 0:
            return {"x": self.grid_x, "y": self.grid_y, "w": self.grid_w, "h": self.grid_h or 4, "auto": False}
        default_h = 3 if self.block_type in ("kpi", "table") else 5
        return {"x": 0, "y": 0, "w": self._WIDTH_TO_W.get(self.width, 6), "h": default_h, "auto": True}

    def sm_get_render_payload(self, date_from=False, date_to=False):
        self.ensure_one()
        data = dict(EMPTY)
        trend = False
        error = False
        if self.analysis_id:
            # Isolate each block in a savepoint: a single misconfigured analysis
            # (e.g. avg() on a date field) must not 500 the whole dashboard.
            try:
                with self.env.cr.savepoint():
                    if self.block_type in ("pivot", "heatmap"):
                        data = self.analysis_id.sm_get_matrix_data(date_from, date_to)
                    else:
                        data = self.analysis_id.sm_get_data(date_from, date_to)
            except Exception as exc:
                _logger.warning(
                    "SM Analytics: block %s (%s) failed to load: %s",
                    self.id, self.name, exc,
                )
                data = dict(EMPTY)
                error = True
            if not error and self.show_trend and self.block_type in ("kpi", "gauge"):
                trend = self.analysis_id.sm_get_trend(
                    date_from, date_to, mode=self.compare_mode or "previous")
        return {
            "id": self.id,
            "name": self.name,
            "type": self.block_type,
            "width": self.width,
            "color": self.color,
            "icon": self.icon,
            "value_prefix": self.value_prefix or "",
            "value_suffix": self.value_suffix or "",
            "decimals": self.decimals or 0,
            "target_value": self.target_value or 0,
            "warn_below": self.warn_below or 0,
            "good_above": self.good_above or 0,
            "trend": trend,
            "grid": self._sm_grid(),
            "error": error,
            "data": data,
        }
