# -*- coding: utf-8 -*-

import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SmAnalyticsDashboard(models.Model):
    _name = "sm.analytics.dashboard"
    _description = "SM Analytics Dashboard"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, name"

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    user_ids = fields.Many2many("res.users", string="Shared Users")
    theme_color = fields.Char(default="#0E2D59")
    accent_color = fields.Char(default="#fbaf3d")
    refresh_interval = fields.Integer(
        default=0,
        help="Auto-refresh the dashboard every N seconds. 0 disables auto-refresh.",
    )
    enable_date_filter = fields.Boolean(
        string="Date Filter",
        help="Show a date range filter in the dashboard header. Analyses with a "
             "Date Field configured are constrained by the selected range.",
    )
    email_enabled = fields.Boolean(
        string="Scheduled Email",
        help="Email a KPI summary of this dashboard to the recipients on a schedule.",
    )
    email_frequency = fields.Selection(
        [("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")],
        default="weekly", string="Frequency",
    )
    email_user_ids = fields.Many2many(
        "res.users", "sm_dashboard_email_user_rel", "dashboard_id", "user_id",
        string="Email Recipients",
    )
    email_last_sent = fields.Datetime(string="Last Emailed", readonly=True, copy=False)
    block_ids = fields.One2many("sm.analytics.block", "dashboard_id", string="Blocks", copy=True)
    block_count = fields.Integer(compute="_compute_block_count")

    @api.depends("block_ids")
    def _compute_block_count(self):
        for dashboard in self:
            dashboard.block_count = len(dashboard.block_ids)

    def action_sm_open_dashboard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "sm_dynamic_analytics_dashboard",
            "name": self.name,
            "params": {"dashboard_id": self.id},
        }

    def action_sm_duplicate(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.copy({"name": _("%s (Copy)") % self.name}).id,
            "view_mode": "form",
            "target": "current",
        }

    def action_sm_export_json(self):
        self.ensure_one()
        payload = self.sm_export_payload()
        attachment = self.env["ir.attachment"].create({
            "name": "%s.json" % self.name.replace("/", "-"),
            "type": "binary",
            "raw": json.dumps(payload, indent=2).encode(),
            "mimetype": "application/json",
            "res_model": self._name,
            "res_id": self.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    # ------------------------------------------------------------------
    # Prebuilt templates
    # ------------------------------------------------------------------
    # Each template lists blocks by model + field NAMES. They are resolved at
    # build time against the running database, so a template silently skips
    # blocks whose app is not installed instead of failing.
    _SM_TEMPLATES = {
        "sales": {
            "name": "Sales Overview",
            "model": "sale.order",
            "blocks": [
                {"name": "Orders", "type": "kpi", "icon": "fa-shopping-cart", "width": "third"},
                {"name": "Revenue", "type": "kpi", "icon": "fa-money", "width": "third",
                 "agg": "sum", "measure": "amount_total"},
                {"name": "Orders by Status", "type": "bar", "icon": "fa-bar-chart",
                 "width": "half", "groupby": "state"},
                {"name": "Revenue by Month", "type": "area", "icon": "fa-line-chart",
                 "width": "full", "agg": "sum", "measure": "amount_total",
                 "groupby": "date_order", "date": "date_order"},
            ],
        },
        "crm": {
            "name": "CRM Pipeline",
            "model": "crm.lead",
            "blocks": [
                {"name": "Leads", "type": "kpi", "icon": "fa-filter", "width": "third"},
                {"name": "Expected Revenue", "type": "kpi", "icon": "fa-money", "width": "third",
                 "agg": "sum", "measure": "expected_revenue"},
                {"name": "By Stage", "type": "bar", "icon": "fa-bar-chart",
                 "width": "half", "groupby": "stage_id"},
                {"name": "By Salesperson", "type": "doughnut", "icon": "fa-pie-chart",
                 "width": "half", "groupby": "user_id"},
            ],
        },
        "invoicing": {
            "name": "Invoicing",
            "model": "account.move",
            "domain": "[('move_type', '=', 'out_invoice')]",
            "blocks": [
                {"name": "Customer Invoices", "type": "kpi", "icon": "fa-file-text", "width": "third"},
                {"name": "Invoiced", "type": "kpi", "icon": "fa-money", "width": "third",
                 "agg": "sum", "measure": "amount_total"},
                {"name": "By Status", "type": "bar", "icon": "fa-bar-chart",
                 "width": "half", "groupby": "state"},
                {"name": "Invoiced by Month", "type": "area", "icon": "fa-line-chart",
                 "width": "full", "agg": "sum", "measure": "amount_total",
                 "groupby": "invoice_date", "date": "invoice_date"},
            ],
        },
        "inventory": {
            "name": "Inventory Operations",
            "model": "stock.picking",
            "blocks": [
                {"name": "Transfers", "type": "kpi", "icon": "fa-truck", "width": "third"},
                {"name": "By Status", "type": "doughnut", "icon": "fa-pie-chart",
                 "width": "half", "groupby": "state"},
                {"name": "By Operation Type", "type": "bar", "icon": "fa-bar-chart",
                 "width": "half", "groupby": "picking_type_id"},
            ],
        },
        "contacts": {
            "name": "Contacts & Users",
            "model": "res.partner",
            "blocks": [
                {"name": "Contacts", "type": "kpi", "icon": "fa-users", "width": "third"},
                {"name": "By Country", "type": "bar", "icon": "fa-globe",
                 "width": "half", "groupby": "country_id"},
                {"name": "Companies vs Individuals", "type": "pie", "icon": "fa-pie-chart",
                 "width": "half", "groupby": "company_type"},
            ],
        },
    }

    @api.model
    def sm_template_options(self):
        return [(key, tpl["name"]) for key, tpl in self._SM_TEMPLATES.items()]

    @api.model
    def sm_build_template(self, key):
        """Create a ready-to-use dashboard from a named template. Returns the
        new dashboard record."""
        tpl = self._SM_TEMPLATES.get(key)
        if not tpl:
            raise UserError(_("Unknown template."))
        if tpl["model"] not in self.env:
            raise UserError(_(
                "This template needs a model (%s) that is not installed in this "
                "database. Install the related app first."
            ) % tpl["model"])
        dashboard = self.create({"name": tpl["name"]})
        Analysis = self.env["sm.analytics.analysis"]
        Block = self.env["sm.analytics.block"]
        model = tpl["model"]
        domain = tpl.get("domain", "[]")
        sequence = 10
        for spec in tpl["blocks"]:
            analysis = self._sm_template_analysis(model, spec, domain, tpl["name"])
            if not analysis:
                continue
            Block.create({
                "dashboard_id": dashboard.id,
                "analysis_id": analysis.id,
                "name": spec["name"],
                "block_type": spec["type"],
                "width": spec.get("width", "half"),
                "icon": spec.get("icon", "fa-bar-chart"),
                "sequence": sequence,
            })
            sequence += 10
        return dashboard

    def _sm_template_analysis(self, model, spec, domain, tpl_name):
        """Build one analysis for a template block, resolving fields by name and
        self-healing so it never violates the measure/aggregate constraint."""
        Field = self.env["ir.model.fields"]

        def field_id(fname):
            return Field._get(model, fname).id if fname else False

        groupby = field_id(spec.get("groupby")) if spec.get("groupby") else False
        date = field_id(spec.get("date")) if spec.get("date") else False
        aggregate = spec.get("agg", "count")
        measure = False
        if aggregate != "count":
            mf = Field._get(model, spec.get("measure")) if spec.get("measure") else False
            if mf and mf.ttype in ("integer", "float", "monetary"):
                measure = mf.id
            else:
                aggregate = "count"  # fall back rather than break the constraint
        return self.env["sm.analytics.analysis"].create({
            "name": "%s - %s" % (tpl_name, spec["name"]),
            "source_type": "model",
            "model_id": self.env["ir.model"]._get_id(model),
            "domain": domain,
            "aggregate": aggregate,
            "measure_field_id": measure,
            "groupby_field_id": groupby,
            "date_field_id": date,
            "limit": 12,
        })

    def sm_export_payload(self):
        self.ensure_one()
        return {
            "name": self.name,
            "theme_color": self.theme_color,
            "accent_color": self.accent_color,
            "refresh_interval": self.refresh_interval,
            "enable_date_filter": self.enable_date_filter,
            "blocks": [block.sm_export_payload() for block in self.block_ids],
        }

    @api.model
    def sm_import_payload(self, payload):
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            raise UserError(_("Invalid dashboard payload."))
        dashboard = self.create({
            "name": payload.get("name") or _("Imported Dashboard"),
            "theme_color": payload.get("theme_color") or "#0E2D59",
            "accent_color": payload.get("accent_color") or "#fbaf3d",
            "refresh_interval": payload.get("refresh_interval") or 0,
            "enable_date_filter": payload.get("enable_date_filter") or False,
        })
        for block_data in payload.get("blocks", []):
            self.env["sm.analytics.block"].create({
                "dashboard_id": dashboard.id,
                "name": block_data.get("name"),
                "block_type": block_data.get("block_type") or "kpi",
                "sequence": block_data.get("sequence") or 10,
                "width": block_data.get("width") or "half",
                "color": block_data.get("color") or "#0E2D59",
                "icon": block_data.get("icon") or "fa-bar-chart",
                "value_prefix": block_data.get("value_prefix") or False,
                "value_suffix": block_data.get("value_suffix") or False,
                "decimals": block_data.get("decimals") or 0,
                "target_value": block_data.get("target_value") or 0,
                "show_trend": block_data.get("show_trend") or False,
                "compare_mode": block_data.get("compare_mode") or "previous",
                "warn_below": block_data.get("warn_below") or 0,
                "good_above": block_data.get("good_above") or 0,
                "grid_x": block_data.get("grid_x") or 0,
                "grid_y": block_data.get("grid_y") or 0,
                "grid_w": block_data.get("grid_w") or 0,
                "grid_h": block_data.get("grid_h") or 0,
            })
        return dashboard

    # ------------------------------------------------------------------
    # Scheduled email delivery
    # ------------------------------------------------------------------
    _FREQ_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}

    @api.model
    def sm_cron_send_emails(self):
        """Cron entry point: email a KPI summary for every due dashboard."""
        now = fields.Datetime.now()
        for dashboard in self.search([("email_enabled", "=", True), ("email_user_ids", "!=", False)]):
            due_days = self._FREQ_DAYS.get(dashboard.email_frequency, 7)
            last = dashboard.email_last_sent
            if last and (now - last).total_seconds() < due_days * 86400:
                continue
            try:
                dashboard.sm_send_email()
            except Exception:  # never let one broken dashboard stop the batch
                self.env.cr.rollback()

    def sm_send_email(self):
        self.ensure_one()
        recipients = self.email_user_ids.filtered("email")
        if not recipients:
            return False
        self.env["mail.mail"].create({
            "subject": _("%s - Analytics Summary") % self.name,
            "body_html": self.sm_email_body(),
            "email_to": ",".join(recipients.mapped("email")),
            "auto_delete": True,
        }).send()
        self.email_last_sent = fields.Datetime.now()
        return True

    def sm_email_body(self):
        """Compact HTML table of every KPI/gauge block's current value."""
        self.ensure_one()
        rows = []
        for block in self.block_ids.sorted("sequence"):
            if block.block_type not in ("kpi", "gauge") or not block.analysis_id:
                continue
            total = block.analysis_id.sm_get_data().get("total", 0)
            value = "%s%s%s" % (
                block.value_prefix or "",
                ("{:,.%df}" % (block.decimals or 0)).format(total),
                block.value_suffix or "",
            )
            rows.append(
                "<tr><td style='padding:8px 14px;border-bottom:1px solid #eee'>%s</td>"
                "<td style='padding:8px 14px;border-bottom:1px solid #eee;text-align:right;"
                "font-weight:700'>%s</td></tr>" % (block.name, value)
            )
        body = "".join(rows) or (
            "<tr><td style='padding:8px 14px'>No KPI blocks to report.</td></tr>")
        return (
            "<div style='font-family:Arial,sans-serif;color:#1f2937'>"
            "<h2 style='color:%s'>%s</h2>"
            "<table style='border-collapse:collapse;min-width:320px'>%s</table>"
            "<p style='color:#888;font-size:12px;margin-top:16px'>"
            "Sent by Dynamic Analytics Dashboard.</p></div>"
        ) % (self.theme_color or "#0E2D59", self.name, body)

    @api.model
    def sm_get_dashboard_payload(self, dashboard_id=False, date_from=False, date_to=False):
        dashboard = self.browse(dashboard_id).exists() if dashboard_id else self.search([], limit=1)
        if not dashboard:
            return {"dashboard": False, "blocks": []}
        if dashboard.user_ids and self.env.user not in dashboard.user_ids:
            raise UserError(_("You are not allowed to open this dashboard."))
        return {
            "dashboard": {
                "id": dashboard.id,
                "name": dashboard.name,
                "theme_color": dashboard.theme_color,
                "accent_color": dashboard.accent_color,
                "refresh_interval": dashboard.refresh_interval or 0,
                "enable_date_filter": dashboard.enable_date_filter,
                "can_edit": self.env["sm.analytics.block"].has_access("write"),
            },
            "blocks": [
                block.sm_get_render_payload(date_from, date_to)
                for block in dashboard.block_ids.sorted("sequence")
            ],
        }

    @api.model
    def sm_save_layout(self, dashboard_id, layout):
        """Persist the drag/resize grid coordinates for a dashboard's blocks.

        `layout` is a list of {id, x, y, w, h}. Write access is enforced by the
        ORM: users without it get an AccessError, so read-only viewers cannot
        rearrange a shared dashboard.
        """
        dashboard = self.browse(dashboard_id).exists()
        if not dashboard:
            return False
        allowed = set(dashboard.block_ids.ids)
        for item in layout or []:
            block = self.env["sm.analytics.block"].browse(int(item.get("id", 0)))
            if block.id not in allowed:
                continue
            block.write({
                "grid_x": int(item.get("x", 0)),
                "grid_y": int(item.get("y", 0)),
                "grid_w": max(1, int(item.get("w", 1))),
                "grid_h": max(1, int(item.get("h", 1))),
            })
        return True
