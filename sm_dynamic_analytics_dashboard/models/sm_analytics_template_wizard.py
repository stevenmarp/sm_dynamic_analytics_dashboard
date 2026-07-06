# -*- coding: utf-8 -*-

from odoo import fields, models


class SmAnalyticsTemplateWizard(models.TransientModel):
    _name = "sm.analytics.template.wizard"
    _description = "Create Dashboard from Template"

    template = fields.Selection(
        selection="_sm_template_selection",
        required=True,
        default="sales",
        string="Template",
    )

    def _sm_template_selection(self):
        return self.env["sm.analytics.dashboard"].sm_template_options()

    def action_create(self):
        self.ensure_one()
        dashboard = self.env["sm.analytics.dashboard"].sm_build_template(self.template)
        return {
            "type": "ir.actions.act_window",
            "name": dashboard.name,
            "res_model": "sm.analytics.dashboard",
            "res_id": dashboard.id,
            "view_mode": "form",
            "target": "current",
        }
