"""Report renderer — Jinja2 template engine + matplotlib chart generation (M3-T2).

Renders ReportTemplate instances into ReportInstance objects by:
1. Substituting Jinja2 template variables in section bodies
2. Generating matplotlib chart images (base64-encoded PNG)
3. Assembling the final HTML/Markdown/text output

Usage:
    renderer = ReportRenderer()
    instance = renderer.render(template, variables={"title": "Sales Report"})
    print(instance.content[:200])
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Any

from agents.data_agent.report_models import (
    ChartSpec,
    ChartType,
    ReportFormat,
    ReportInstance,
    ReportSection,
    ReportTemplate,
)

logger = logging.getLogger("fde.data.report_renderer")

__all__ = ["ReportRenderer", "create_default_templates", "get_renderer"]


# ══════════════════════════════════════════════════════════════════
# Jinja2 Integration (graceful degradation if not installed)
# ══════════════════════════════════════════════════════════════════

try:
    from jinja2 import BaseLoader, Environment, StrictUndefined

    _JINJA_AVAILABLE = True
except ImportError:
    _JINJA_AVAILABLE = False
    logger.warning("jinja2 not installed; falling back to str.format rendering")

# ══════════════════════════════════════════════════════════════════
# Matplotlib Integration (graceful degradation)
# ══════════════════════════════════════════════════════════════════

try:
    import matplotlib

    matplotlib.use("Agg")  # Non-interactive backend
    import matplotlib.pyplot as plt

    _MPL_AVAILABLE = True
except ImportError:
    _MPL_AVAILABLE = False
    logger.warning("matplotlib not installed; chart rendering will be skipped")


# ══════════════════════════════════════════════════════════════════
# Singleton
# ══════════════════════════════════════════════════════════════════

_renderer: ReportRenderer | None = None


def get_renderer() -> ReportRenderer:
    """Get the singleton ReportRenderer instance."""
    global _renderer
    if _renderer is None:
        _renderer = ReportRenderer()
    return _renderer


# ══════════════════════════════════════════════════════════════════
# ReportRenderer
# ══════════════════════════════════════════════════════════════════


class ReportRenderer:
    """Renders ReportTemplate instances into ReportInstance objects.

    Supports:
    - Jinja2 template substitution (with str.format fallback)
    - matplotlib chart generation (bar, line, pie, scatter, table)
    - HTML, Markdown, and plain text output formats
    """

    def __init__(self) -> None:
        self._jinja_env: Any = None
        if _JINJA_AVAILABLE:
            self._jinja_env = Environment(
                loader=BaseLoader(),
                undefined=StrictUndefined,
                autoescape=True,
            )

    def render(
        self,
        template: ReportTemplate,
        variables: dict[str, Any] | None = None,
    ) -> ReportInstance:
        """Render a template into a report instance.

        Args:
            template: The report template to render.
            variables: Variables for Jinja2 substitution.

        Returns:
            ReportInstance with rendered content and chart images.
        """
        variables = variables or {}
        self._validate_required_variables(template, variables)

        chart_images: dict[str, str] = {}
        sorted_sections = sorted(template.sections, key=lambda s: s.order)

        rendered_sections: list[str] = []
        for section in sorted_sections:
            rendered_body = self._render_template_string(section.body_template, variables)
            chart_html = self._render_charts(section, chart_images)
            rendered_sections.append(
                self._format_section(section.title, rendered_body, chart_html, template.format)
            )

        title = self._render_template_string(template.name, variables)
        content = self._assemble(title, rendered_sections, template.format)

        return ReportInstance(
            template_id=template.id,
            title=title,
            format=template.format,
            content=content,
            chart_images=chart_images,
            variables_used=variables,
        )

    def _validate_required_variables(
        self,
        template: ReportTemplate,
        variables: dict[str, Any],
    ) -> None:
        """Validate that all required template variables are provided."""
        missing = [
            var.name
            for var in template.variables
            if var.required and var.name not in variables and var.default is None
        ]
        if missing:
            raise ValueError(f"Missing required template variables: {missing}")

    def _render_template_string(self, template_str: str, variables: dict[str, Any]) -> str:
        """Render a Jinja2 template string with variables.

        Falls back to str.format if Jinja2 is not available.
        """
        if not template_str:
            return ""

        if _JINJA_AVAILABLE and self._jinja_env is not None:
            try:
                tmpl = self._jinja_env.from_string(template_str)
                return str(tmpl.render(**variables))
            except Exception as e:
                logger.warning("Jinja2 render failed: %s; falling back to format", e)

        try:
            return template_str.format(**variables)
        except (KeyError, IndexError, ValueError):
            return template_str

    def _render_charts(
        self,
        section: ReportSection,
        chart_images: dict[str, str],
    ) -> str:
        """Render all charts in a section, return HTML/Markdown for embedding.

        Args:
            section: The report section containing charts.
            chart_images: Dict to populate with base64-encoded images.

        Returns:
            String representation of embedded charts.
        """
        if not section.charts:
            return ""

        parts: list[str] = []
        for chart in section.charts:
            img_b64 = self._generate_chart(chart)
            if img_b64:
                chart_images[chart.id] = img_b64
                parts.append(
                    f'<img alt="{chart.title}" '
                    f'src="data:image/png;base64,{img_b64}" '
                    f'style="max-width:{chart.width}px;" />'
                )
            else:
                parts.append(f"[Chart: {chart.title} (rendering skipped)]")
        return "\n".join(parts)

    def _generate_chart(self, spec: ChartSpec) -> str | None:
        """Generate a matplotlib chart and return base64-encoded PNG.

        Returns None if matplotlib is unavailable or rendering fails.
        """
        if not _MPL_AVAILABLE or not spec.data:
            return None

        try:
            fig, ax = plt.subplots(figsize=(spec.width / 100, spec.height / 100), dpi=100)

            _drawers = {
                ChartType.BAR: self._draw_bar,
                ChartType.LINE: self._draw_line,
                ChartType.PIE: self._draw_pie,
                ChartType.SCATTER: self._draw_scatter,
                ChartType.TABLE: self._draw_table,
            }
            drawer = _drawers.get(spec.chart_type)
            if drawer is not None:
                drawer(ax, spec)
            else:
                ax.text(0.5, 0.5, f"Unknown: {spec.chart_type}", ha="center")

            if spec.title:
                ax.set_title(spec.title)
            if spec.x_label:
                ax.set_xlabel(spec.x_label)
            if spec.y_label:
                ax.set_ylabel(spec.y_label)

            buf = io.BytesIO()
            fig.tight_layout()
            fig.savefig(buf, format="png", dpi=100)
            plt.close(fig)
            buf.seek(0)
            return base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception as e:
            logger.error("Chart generation failed for '%s': %s", spec.title, e)
            plt.close("all")
            return None

    def _draw_bar(self, ax: Any, spec: ChartSpec) -> None:
        labels = [str(d.get("label", d.get("x", ""))) for d in spec.data]
        values = [float(d.get("value", d.get("y", 0))) for d in spec.data]
        ax.bar(labels, values)

    def _draw_line(self, ax: Any, spec: ChartSpec) -> None:
        labels = [str(d.get("label", d.get("x", ""))) for d in spec.data]
        values = [float(d.get("value", d.get("y", 0))) for d in spec.data]
        ax.plot(labels, values, marker="o")

    def _draw_pie(self, ax: Any, spec: ChartSpec) -> None:
        labels = [str(d.get("label", "")) for d in spec.data]
        values = [float(d.get("value", 0)) for d in spec.data]
        ax.pie(values, labels=labels, autopct="%1.1f%%")

    def _draw_scatter(self, ax: Any, spec: ChartSpec) -> None:
        xs = [float(d.get("x", 0)) for d in spec.data]
        ys = [float(d.get("y", 0)) for d in spec.data]
        ax.scatter(xs, ys)

    def _draw_table(self, ax: Any, spec: ChartSpec) -> None:
        ax.axis("off")
        if spec.data:
            cols = list(spec.data[0].keys())
            rows = [[str(d.get(c, "")) for c in cols] for d in spec.data]
            ax.table(cellText=rows, colLabels=cols, loc="center")

    def _format_section(
        self,
        title: str,
        body: str,
        chart_html: str,
        fmt: ReportFormat,
    ) -> str:
        """Format a section according to the output format."""
        if fmt == ReportFormat.HTML:
            parts = [f"<h2>{title}</h2>"]
            if body:
                parts.append(f"<div>{body}</div>")
            if chart_html:
                parts.append(f"<div>{chart_html}</div>")
            return "\n".join(parts)
        elif fmt == ReportFormat.MARKDOWN:
            parts = [f"## {title}", ""]
            if body:
                parts.append(body)
            if chart_html:
                parts.append(f"\n{chart_html}\n")
            return "\n".join(parts)
        else:  # TEXT
            parts = [f"=== {title} ===", ""]
            if body:
                parts.append(body)
            if chart_html:
                parts.append("[Chart embedded]")
            return "\n".join(parts)

    def _assemble(
        self,
        title: str,
        sections: list[str],
        fmt: ReportFormat,
    ) -> str:
        """Assemble the final report content."""
        if fmt == ReportFormat.HTML:
            return f"<html><body><h1>{title}</h1>\n{''.join(sections)}\n</body></html>"
        elif fmt == ReportFormat.MARKDOWN:
            return f"# {title}\n\n{''.join(sections)}"
        else:  # TEXT
            return f"{title}\n{'=' * len(title)}\n\n{''.join(sections)}"


# ══════════════════════════════════════════════════════════════════
# Default Templates
# ══════════════════════════════════════════════════════════════════


def create_default_templates() -> dict[str, ReportTemplate]:
    """Create a set of default report templates.

    Returns:
        Dict mapping template name to ReportTemplate.
    """
    from agents.data_agent.report_models import TemplateVariable

    data_summary = ReportTemplate(
        name="Data Collection Summary",
        description="Summary of data collection pipeline results",
        format=ReportFormat.HTML,
        sections=[
            ReportSection(
                title="Overview",
                body_template=(
                    "<p>This report summarizes the data collection from "
                    "<strong>{{ source }}</strong> on {{ date }}.</p>"
                    "<p>Total items collected: <b>{{ total_items }}</b>, "
                    "valid items: <b>{{ valid_items }}</b>.</p>"
                ),
                order=0,
            ),
            ReportSection(
                title="Quality Metrics",
                body_template=(
                    "<ul>"
                    "<li>Completeness: {{ completeness_avg | default('N/A') }}</li>"
                    "<li>Uniqueness: {{ uniqueness_avg | default('N/A') }}</li>"
                    "<li>Validity: {{ validity_avg | default('N/A') }}</li>"
                    "</ul>"
                ),
                order=1,
            ),
        ],
        variables=[
            TemplateVariable(name="source", description="Data source name"),
            TemplateVariable(name="date", description="Report date"),
            TemplateVariable(name="total_items", description="Total collected"),
            TemplateVariable(name="valid_items", description="Valid after cleaning"),
            TemplateVariable(
                name="completeness_avg",
                description="Completeness score",
                required=False,
                default="N/A",
            ),
            TemplateVariable(
                name="uniqueness_avg",
                description="Uniqueness score",
                required=False,
                default="N/A",
            ),
            TemplateVariable(
                name="validity_avg",
                description="Validity score",
                required=False,
                default="N/A",
            ),
        ],
    )

    return {data_summary.name: data_summary}
