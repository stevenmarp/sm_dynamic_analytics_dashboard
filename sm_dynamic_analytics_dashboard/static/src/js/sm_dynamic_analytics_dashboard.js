/** @odoo-module **/
/* global Chart, GridStack */

const { Component } = owl;
const { onWillStart, onWillUnmount, useRef, useState } = owl.hooks;

import { loadAssets } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { useEffect, useService } from "@web/core/utils/hooks";

const GRIDSTACK_JS = "/sm_dynamic_analytics_dashboard/static/lib/gridstack/gridstack-all.js";
const GRIDSTACK_CSS = "/sm_dynamic_analytics_dashboard/static/lib/gridstack/gridstack.min.css";

const FALLBACK_PALETTE = [
    "#0E2D59", "#fbaf3d", "#2f9e44", "#e8590c", "#7048e8",
    "#1098ad", "#e64980", "#f08c00", "#37b24d", "#4263eb",
];

const CHART_TYPES = {
    bar: "bar",
    line: "line",
    area: "line",
    pie: "pie",
    doughnut: "doughnut",
    radar: "radar",
    polar: "polarArea",
    scatter: "scatter",
    sparkline: "line",
};

const SM_CHART_KINDS = Object.keys(CHART_TYPES);

// ──────────────────────────────────────────────────
// Color utilities
// ──────────────────────────────────────────────────
function hexToRgb(hex) {
    const v = (hex || "#0E2D59").replace("#", "");
    if (v.length !== 6) return { r: 14, g: 45, b: 89 };
    return { r: parseInt(v.slice(0, 2), 16), g: parseInt(v.slice(2, 4), 16), b: parseInt(v.slice(4, 6), 16) };
}

function rgbToHsl(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    let h = 0, s = 0;
    const l = (max + min) / 2;
    if (max !== min) {
        const d = max - min;
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
        else if (max === g) h = ((b - r) / d + 2) / 6;
        else h = ((r - g) / d + 4) / 6;
    }
    return [Math.round(h * 360), Math.round(s * 100), Math.round(l * 100)];
}

function hslToHex(h, s, l) {
    s /= 100; l /= 100;
    const a = s * Math.min(l, 1 - l);
    const f = (n) => {
        const k = (n + h / 30) % 12;
        const color = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
        return Math.round(255 * color).toString(16).padStart(2, "0");
    };
    return `#${f(0)}${f(8)}${f(4)}`;
}

function hexAlpha(hex, alpha) {
    const { r, g, b } = hexToRgb(hex);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function buildPalette(themeHex, accentHex) {
    const theme = themeHex || FALLBACK_PALETTE[0];
    const accent = accentHex || FALLBACK_PALETTE[1];
    const { r, g, b } = hexToRgb(theme);
    const [baseH] = rgbToHsl(r, g, b);
    const palette = [theme, accent];
    const GOLDEN = 137.508;
    for (let i = 1; i <= 8; i++) {
        const h = (baseH + i * GOLDEN) % 360;
        const s = 50 + (i % 3) * 10;
        const l = 42 + (i % 2) * 12;
        palette.push(hslToHex(h, s, l));
    }
    return palette;
}

/**
 * One Chart.js canvas for a single block. Owns its own lifecycle so each canvas
 * creates on mount, rebuilds when its data changes, and destroys on unmount.
 * Chart.js v2 is responsive, so it follows the GridStack item as it resizes.
 */
export class SmAnalyticsChart extends Component {

    setup() {
        this.canvasRef = useRef("canvas");
        this.chart = null;
        useEffect(
            () => {
                this.renderChart();
                return () => this.destroyChart();
            },
            () => [this.props.block.data],
        );
    }

    destroyChart() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }

    renderChart() {
        const canvas = this.canvasRef.el;
        if (!canvas || typeof Chart === "undefined") {
            return;
        }
        this.destroyChart();
        const block = this.props.block;
        const pal = this.props.palette || FALLBACK_PALETTE;
        const data = block.data || {};
        const labels = data.labels || [];
        const values = data.values || [];
        const kind = block.type;                       // semantic type
        const type = CHART_TYPES[kind] || "bar";        // Chart.js type
        const colors = labels.map((_l, i) => pal[i % pal.length]);
        const base = block.color || pal[0];

        const multiColor = ["pie", "doughnut", "polar"].includes(kind);
        const isLine = ["line", "area", "sparkline"].includes(kind);
        const isSpark = kind === "sparkline";
        const cartesian = ["bar", "line", "area", "scatter", "sparkline"].includes(kind);

        const dataset = { label: block.name || "" };
        if (kind === "scatter") {
            dataset.data = values.map((v, i) => ({ x: i, y: Number(v) || 0 }));
            dataset.backgroundColor = hexAlpha(base, 0.7);
            dataset.pointRadius = 6;
            dataset.pointHoverRadius = 8;
        } else {
            dataset.data = values;
            if (multiColor) {
                dataset.backgroundColor = kind === "polar" ? colors.map((c) => hexAlpha(c, 0.72)) : colors;
                dataset.borderColor = "transparent";
                dataset.borderWidth = 2;
            } else if (kind === "radar") {
                dataset.backgroundColor = hexAlpha(base, 0.2);
                dataset.borderColor = base;
                dataset.borderWidth = 2;
                dataset.pointBackgroundColor = base;
                dataset.pointRadius = 3;
            } else if (isLine) {
                dataset.borderColor = base;
                dataset.backgroundColor = hexAlpha(base, isSpark ? 0.25 : 0.18);
                dataset.fill = kind === "area" || isSpark;
                dataset.tension = 0.4;
                dataset.pointRadius = isSpark ? 0 : 3;
                dataset.pointBackgroundColor = base;
                dataset.borderWidth = 2;
            } else { // bar
                dataset.backgroundColor = colors;
                dataset.borderWidth = 0;
                dataset.borderRadius = 6;
            }
        }

        const isDark = document.documentElement.getAttribute("data-color-scheme") === "dark"
            || document.body.classList.contains("o_dark");
        const gridColor = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.06)";
        const tickColor = isDark ? "#9ca3af" : "#64748b";

        const scales = cartesian ? {
            yAxes: [{
                ticks: { beginAtZero: true, display: !isSpark, fontColor: tickColor },
                gridLines: { color: gridColor, display: !isSpark }
            }],
            xAxes: [{
                ticks: { display: !isSpark, fontColor: tickColor },
                gridLines: { color: gridColor, display: !isSpark }
            }]
        } : {};

        this.chart = new Chart(canvas, {
            type,
            data: { labels, datasets: [dataset] },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                onClick: (ev, elements) => {
                    if (elements && elements.length) {
                        const firstElem = elements[0];
                        const idx = firstElem.index !== undefined ? firstElem.index : firstElem._index;
                        if (idx !== undefined) {
                            this.props.onDrill(block, idx);
                        }
                    }
                },
                legend: { display: multiColor, position: "right", labels: { fontColor: tickColor } },
                tooltips: { enabled: !isSpark },
                scales,
            },
        });
    }
}
SmAnalyticsChart.template = "sm_dynamic_analytics_dashboard.Chart";
SmAnalyticsChart.props = { block: Object, onDrill: Function, palette: { type: Array, optional: true } };

export class SmDynamicAnalyticsDashboard extends Component {

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.refreshTimer = null;
        this.grid = null;
        this.gridRef = useRef("grid");
        this.shellRef = useRef("shell");
        this.state = useState({
            loading: true,
            dashboard: false,
            blocks: [],
            error: false,
            dateFrom: "",
            dateTo: "",
            editMode: false,
            fullscreen: false,
            dirty: false,
        });
        onWillStart(async () => {
            await loadAssets({
                jsLibs: [
                    "/web/static/lib/Chart/Chart.js",
                    GRIDSTACK_JS
                ],
                cssLibs: [
                    GRIDSTACK_CSS
                ]
            });
            await this.smLoad();
        });
        // (Re)build the grid whenever the set of blocks changes (reload, add,
        // delete). Data-only refreshes keep the same ids, so the grid is left
        // intact and only the block contents repaint.
        useEffect(
            () => {
                this._initGrid();
                return () => this._destroyGrid();
            },
            () => [this._gridSignature()],
        );
        useEffect(
            () => { this._applyTheme(); },
            () => [this.state.dashboard],
        );
        onWillUnmount(() => {
            this._clearRefresh();
            this._destroyGrid();
        });
    }

    // ------------------------------------------------------------------
    // Dynamic palette (passed to chart children as prop)
    // ------------------------------------------------------------------
    get palette() {
        const d = this.state.dashboard;
        if (!d) return FALLBACK_PALETTE;
        return buildPalette(d.theme_color, d.accent_color);
    }

    // ------------------------------------------------------------------
    // Theme CSS variables
    // ------------------------------------------------------------------
    _applyTheme() {
        const el = this.shellRef.el;
        const d = this.state.dashboard;
        if (!el || !d) return;
        const theme = d.theme_color || "#0E2D59";
        const accent = d.accent_color || "#fbaf3d";
        el.style.setProperty("--sm-theme", theme);
        el.style.setProperty("--sm-accent", accent);
        const tRgb = hexToRgb(theme);
        el.style.setProperty("--sm-theme-rgb", `${tRgb.r}, ${tRgb.g}, ${tRgb.b}`);
        const aRgb = hexToRgb(accent);
        el.style.setProperty("--sm-accent-rgb", `${aRgb.r}, ${aRgb.g}, ${aRgb.b}`);
    }

    _gridSignature() {
        // Include `loading`: a non-silent reload (manual Refresh, date filter)
        // swaps the grid DOM out for the skeleton and back, so the grid must be
        // re-initialised on the fresh nodes even when the block ids are unchanged.
        return (this.state.blocks || []).map((b) => b.id).join(",") + "|" + this.state.loading;
    }

    // ------------------------------------------------------------------
    // Loading
    // ------------------------------------------------------------------
    async smLoad(silent = false) {
        if (this.state.editMode) {
            return;
        }
        if (!silent) {
            this.state.loading = true;
        }
        this.state.error = false;
        try {
            const payload = await this.orm.call(
                "sm.analytics.dashboard",
                "sm_get_dashboard_payload",
                [this._dashboardId(), this.state.dateFrom || false, this.state.dateTo || false],
            );
            this.state.dashboard = payload.dashboard;
            this.state.blocks = payload.blocks || [];
            this._scheduleRefresh();
        } catch (error) {
            this.state.error = error.message || String(error);
        } finally {
            this.state.loading = false;
        }
    }

    _dashboardId() {
        return (this.state.dashboard && this.state.dashboard.id) || (this.props.action && this.props.action.params && this.props.action.params.dashboard_id) || false;
    }

    _scheduleRefresh() {
        this._clearRefresh();
        const seconds = (this.state.dashboard && this.state.dashboard.refresh_interval) || 0;
        if (seconds > 0) {
            this.refreshTimer = setInterval(() => this.smLoad(true), seconds * 1000);
        }
    }

    _clearRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }
    }

    // ------------------------------------------------------------------
    // GridStack layout
    // ------------------------------------------------------------------
    _initGrid() {
        const el = this.gridRef.el;
        if (!el || typeof GridStack === "undefined" || !this.state.blocks.length) {
            return;
        }
        this._destroyGrid();
        this.grid = GridStack.init(
            {
                column: 12,
                cellHeight: 70,
                margin: 8,
                float: true,
                staticGrid: !this.state.editMode,
                handle: ".sm_analytics_block_head",
            },
            el,
        );
        this.grid.on("change", (ev, items) => this._onGridChange(items));
    }

    _destroyGrid() {
        if (this.grid) {
            try {
                this.grid.destroy(false);
            } catch (error) {
                // ignore teardown races
            }
            this.grid = null;
        }
    }

    _onGridChange(items) {
        for (const item of items || []) {
            const id = Number(item.el && item.el.getAttribute("gs-id"));
            const block = this.state.blocks.find((b) => b.id === id);
            if (block) {
                block.grid = { ...block.grid, x: item.x, y: item.y, w: item.w, h: item.h, auto: false };
            }
        }
        this.state.dirty = true;
    }

    smToggleEdit() {
        this.state.editMode = !this.state.editMode;
        if (this.grid) {
            this.grid.setStatic(!this.state.editMode);
        }
        if (this.state.editMode) {
            this._clearRefresh();
        } else {
            this._scheduleRefresh();
        }
    }

    smToggleFullscreen() {
        this.state.fullscreen = !this.state.fullscreen;
        setTimeout(() => {
            if (this.grid) {
                this.grid.compact();
            }
            window.dispatchEvent(new Event("resize"));
        }, 50);
    }

    async smSaveLayout() {
        const layout = this.state.blocks.map((b) => ({
            id: b.id,
            x: b.grid.x,
            y: b.grid.y,
            w: b.grid.w,
            h: b.grid.h,
        }));
        try {
            await this.orm.call("sm.analytics.dashboard", "sm_save_layout", [this._dashboardId(), layout]);
            this.state.dirty = false;
            this.state.editMode = false;
            if (this.grid) {
                this.grid.setStatic(true);
            }
            this._scheduleRefresh();
            this.notification.add("Layout saved", { type: "success" });
        } catch (error) {
            this.notification.add(error.message || String(error), { type: "danger" });
        }
    }

    // ------------------------------------------------------------------
    // Date filter
    // ------------------------------------------------------------------
    smApplyDates() {
        this.smLoad();
    }

    smClearDates() {
        this.state.dateFrom = "";
        this.state.dateTo = "";
        this.smLoad();
    }

    // ------------------------------------------------------------------
    // Rendering helpers
    // ------------------------------------------------------------------
    smIsChart(block) {
        return SM_CHART_KINDS.includes(block.type);
    }

    smFormat(block, value) {
        const decimals = block.decimals || 0;
        const number = Number(value || 0);
        const formatted = new Intl.NumberFormat(undefined, {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
        }).format(number);
        return `${block.value_prefix || ""}${formatted}${block.value_suffix || ""}`;
    }

    smTargetPercent(block) {
        const target = Number(block.target_value || 0);
        if (!target) {
            return 0;
        }
        const ratio = (Number((block.data && block.data.total) || 0) / target) * 100;
        return Math.max(0, Math.min(100, ratio));
    }

    // Conditional formatting: green at/above good_above, red below warn_below.
    smValueClass(block, value) {
        const v = Number(value || 0);
        if (block.good_above && v >= block.good_above) {
            return "sm_analytics_good";
        }
        if (block.warn_below && v < block.warn_below) {
            return "sm_analytics_warn";
        }
        return "";
    }

    // ---- Funnel: each stage width relative to the largest value ----
    smFunnelPct(block, value) {
        const values = (block.data && block.data.values) || [];
        const max = Math.max(1, ...values.map((n) => Number(n) || 0));
        return Math.max(4, (Number(value || 0) / max) * 100);
    }

    smFunnelStages(block) {
        const labels = (block.data && block.data.labels) || [];
        const values = (block.data && block.data.values) || [];
        return labels.map((label, i) => ({ label, value: values[i] || 0, idx: i }));
    }

    // ---- Heatmap: cell opacity scales with value ----
    smMatrixMax(block) {
        const matrix = (block.data && block.data.matrix) || [];
        let max = 0;
        for (const line of matrix) {
            for (const cell of line) {
                if (Number(cell) > max) {
                    max = Number(cell);
                }
            }
        }
        return max || 1;
    }

    smHeatStyle(block, value) {
        const ratio = Math.min(1, Number(value || 0) / this.smMatrixMax(block));
        const base = block.color || "#0E2D59";
        return `background:${hexAlpha(base, 0.12 + ratio * 0.8)};` +
            `color:${ratio > 0.55 ? "#fff" : "inherit"}`;
    }

    // ---- Export a chart block to PNG (#3) ----
    smDownloadBlock(block) {
        const canvas = this.gridRef.el &&
            this.gridRef.el.querySelector(`.grid-stack-item[gs-id="${block.id}"] canvas`);
        if (!canvas) {
            this.notification.add("This block type cannot be exported as an image.", { type: "warning" });
            return;
        }
        const link = document.createElement("a");
        link.download = `${(block.name || "chart").replace(/[^\w-]+/g, "_")}.png`;
        link.href = canvas.toDataURL("image/png");
        link.click();
    }

    // ---- Add a block straight from the dashboard (#8) ----
    async smAddBlock() {
        const dashboardId = this._dashboardId();
        if (!dashboardId) {
            return;
        }
        await this.action.doAction(
            {
                type: "ir.actions.act_window",
                name: "New Block",
                res_model: "sm.analytics.block",
                view_mode: "form",
                views: [[false, "form"]],
                target: "new",
                context: { default_dashboard_id: dashboardId },
            },
            { onClose: () => this.smLoad() },
        );
    }

    // ------------------------------------------------------------------
    // Drill-down
    // ------------------------------------------------------------------
    smDrill(block, index) {
        if (this.state.editMode) {
            return;
        }
        const domains = (block.data && block.data.domains) || [];
        this._openRecords(block, domains[index] || (block.data && block.data.base_domain));
    }

    smDrillTotal(block) {
        if (this.state.editMode) {
            return;
        }
        this._openRecords(block, block.data && block.data.base_domain);
    }

    _openRecords(block, domain) {
        const model = block.data && block.data.model;
        if (!model || !domain) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: block.name,
            res_model: model,
            domain,
            views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }

    smOpenConfig() {
        this.action.doAction("sm_dynamic_analytics_dashboard.action_sm_analytics_dashboard");
    }
}
SmDynamicAnalyticsDashboard.template = "sm_dynamic_analytics_dashboard.Dashboard";
SmDynamicAnalyticsDashboard.components = { SmAnalyticsChart };

registry.category("actions").add("sm_dynamic_analytics_dashboard", SmDynamicAnalyticsDashboard);
