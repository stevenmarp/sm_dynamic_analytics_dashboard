# -*- coding: utf-8 -*-
# Copyright 2026 Steven Marp
{
    "name": "Analytics Dashboard",
    "version": "18.0.3.1.0",
    "category": "Reporting",
    "summary": "Build live KPI, chart, table, and SQL dashboards with drill-down in Odoo",
    "description": """
Analytics Dashboard
===========================

Create dynamic analytics dashboards from Odoo models or safe SQL queries.

Features
--------
* Dashboard builder with blocks
* KPI, bar, line, area, pie, doughnut, and table blocks
* Real interactive charts powered by Chart.js
* Click-through drill-down from any chart, KPI, or table row to the records
* Live auto-refresh at a configurable interval
* Global date range filter with per-analysis date field
* KPI trend comparison versus the previous period
* KPI value formatting (prefix, suffix, decimals) and goal/target progress
* Model-based analytics with domain, measure, group by, and aggregation
* Read-only, single-statement, time-capped SQL analytics
* Dashboard JSON export and import
* Per-dashboard user sharing and company-aware dashboards
* Pivot table and heatmap blocks from a second group-by dimension
* Gauge and funnel blocks
* Conditional formatting: warn-below and good-above thresholds
* Year-over-year trend comparison, not just previous period
* Scheduled email delivery of a KPI summary (daily, weekly, monthly)
* Download any chart block as a PNG image
* Add blocks straight from the dashboard, no round trip to a form
* SQL analytics restricted to managers, never leaking across companies
* Lightweight OWL frontend
    """,
    "author": "Steven Marp",
    "website": "https://apps.odoo.com/apps/modules/browse?author=Steven Marp",
    "license": "OPL-1",
    "depends": ["web", "mail"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/sm_cron.xml",
        "data/sm_analytics_demo.xml",
        "views/sm_analytics_views.xml",
        "views/sm_analytics_menu.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sm_dynamic_analytics_dashboard/static/src/scss/sm_dynamic_analytics_dashboard.scss",
            "sm_dynamic_analytics_dashboard/static/src/xml/sm_dynamic_analytics_dashboard.xml",
            "sm_dynamic_analytics_dashboard/static/src/js/sm_dynamic_analytics_dashboard.js",
        ],
        # GridStack 11.5.1 (MIT) is lazy-loaded on the dashboard via loadJS/loadCSS,
        # so it is not bundled into every backend page.
    },
    "images": [
        "static/description/banner.gif",
        "static/description/ss-command-center.png",
        "static/description/ss-invoicing.png",
        "static/description/ss-inventory.png",
        "static/description/ss-crm.png",
        "static/description/ss-edit-layout.png",
        "static/description/ss-templates.png",
        "static/description/icon.png",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
    "price": 98.00,
    "currency": "USD",
}
