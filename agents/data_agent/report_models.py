"""Report models — Pydantic data contracts for report generation (M3-T2).

Defines:
- ReportTemplate: Jinja2 template definition with metadata
- ReportSection: A single section within a report
- ChartSpec: Chart generation specification (matplotlib)
- ReportInstance: A rendered report ready for delivery
- PushTarget: Delivery target (email, IM, webhook)
- PushResult: Delivery outcome
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from shared.utils.ids import new_uuid

__all__ = [
    "ChartSpec",
    "ChartType",
    "PushChannel",
    "PushResult",
    "PushTarget",
    "ReportFormat",
    "ReportInstance",
    "ReportSection",
    "ReportTemplate",
    "TemplateVariable",
]


# ══════════════════════════════════════════════════════════════════
# Enums
# ══════════════════════════════════════════════════════════════════


class ReportFormat(StrEnum):
    """Supported output formats for rendered reports."""

    HTML = "html"
    MARKDOWN = "markdown"
    TEXT = "text"


class ChartType(StrEnum):
    """Supported chart types for matplotlib rendering."""

    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    SCATTER = "scatter"
    TABLE = "table"


class PushChannel(StrEnum):
    """Supported push delivery channels."""

    EMAIL = "email"
    IM = "im"
    WEBHOOK = "webhook"


# ══════════════════════════════════════════════════════════════════
# Template Models
# ══════════════════════════════════════════════════════════════════


class TemplateVariable(BaseModel):
    """A variable that can be substituted in a template.

    Attributes:
        name: Variable name (used as Jinja2 placeholder key).
        description: Human-readable description.
        var_type: Python type hint for validation.
        default: Default value if not provided.
        required: Whether the variable must be provided.
    """

    name: str = Field(description="Variable name")
    description: str = Field(default="", description="Human-readable description")
    var_type: str = Field(default="str", description="Python type hint")
    default: Any = Field(default=None, description="Default value")
    required: bool = Field(default=True, description="Whether the variable is required")


class ReportTemplate(BaseModel):
    """A reusable report template definition.

    Attributes:
        id: Unique template identifier.
        name: Human-readable template name.
        description: Template purpose description.
        format: Output format (html, markdown, text).
        sections: Ordered list of report sections.
        variables: Template variables for Jinja2 substitution.
        created_at: Template creation timestamp.
    """

    id: str = Field(default_factory=new_uuid, description="Unique template ID")
    name: str = Field(description="Template name")
    description: str = Field(default="", description="Template purpose")
    format: ReportFormat = Field(default=ReportFormat.HTML, description="Output format")
    sections: list[ReportSection] = Field(
        default_factory=list,
        description="Ordered report sections",
    )
    variables: list[TemplateVariable] = Field(
        default_factory=list,
        description="Template variables for Jinja2 substitution",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Template creation timestamp",
    )


class ReportSection(BaseModel):
    """A single section within a report template.

    Attributes:
        title: Section heading.
        body_template: Jinja2 template string for the section body.
        charts: Chart specifications to embed in this section.
        order: Display order (0 = first).
    """

    title: str = Field(description="Section heading")
    body_template: str = Field(default="", description="Jinja2 template for section body")
    charts: list[ChartSpec] = Field(default_factory=list, description="Charts to embed")
    order: int = Field(default=0, ge=0, description="Display order")


class ChartSpec(BaseModel):
    """Specification for generating a chart image.

    Attributes:
        id: Unique chart identifier within the report.
        title: Chart title displayed above the image.
        chart_type: Type of chart (bar, line, pie, scatter, table).
        data: Chart data — list of dicts or 2D array.
        x_label: X-axis label.
        y_label: Y-axis label.
        width: Image width in pixels.
        height: Image height in pixels.
    """

    id: str = Field(default_factory=new_uuid, description="Chart ID")
    title: str = Field(default="", description="Chart title")
    chart_type: ChartType = Field(default=ChartType.BAR, description="Chart type")
    data: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Chart data as list of dicts",
    )
    x_label: str = Field(default="", description="X-axis label")
    y_label: str = Field(default="", description="Y-axis label")
    width: int = Field(default=800, ge=100, le=4000, description="Image width (px)")
    height: int = Field(default=400, ge=100, le=4000, description="Image height (px)")


# ══════════════════════════════════════════════════════════════════
# Report Instance (Rendered Output)
# ══════════════════════════════════════════════════════════════════


class ReportInstance(BaseModel):
    """A rendered report ready for delivery.

    Attributes:
        id: Unique report instance ID.
        template_id: Source template ID.
        title: Report title (rendered).
        format: Output format.
        content: Rendered content (HTML/Markdown/text string).
        chart_images: Base64-encoded chart images keyed by chart ID.
        generated_at: Generation timestamp.
        variables_used: Variables provided for rendering.
    """

    id: str = Field(default_factory=new_uuid, description="Report instance ID")
    template_id: str = Field(description="Source template ID")
    title: str = Field(default="", description="Rendered report title")
    format: ReportFormat = Field(default=ReportFormat.HTML, description="Output format")
    content: str = Field(default="", description="Rendered content")
    chart_images: dict[str, str] = Field(
        default_factory=dict,
        description="Base64-encoded chart images keyed by chart ID",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Generation timestamp",
    )
    variables_used: dict[str, Any] = Field(
        default_factory=dict,
        description="Variables provided for rendering",
    )


# ══════════════════════════════════════════════════════════════════
# Push Delivery Models
# ══════════════════════════════════════════════════════════════════


class PushTarget(BaseModel):
    """A delivery target for a report push.

    Attributes:
        channel: Push channel (email, im, webhook).
        address: Target address (email address, IM user/group ID, webhook URL).
        metadata: Channel-specific metadata (subject, sender, etc.).
    """

    channel: PushChannel = Field(description="Push channel")
    address: str = Field(description="Target address")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Channel-specific metadata",
    )


class PushResult(BaseModel):
    """Outcome of a single push delivery attempt.

    Attributes:
        target: The push target that was attempted.
        success: Whether the delivery succeeded.
        message: Status or error message.
        delivered_at: Delivery timestamp (None if failed).
    """

    target: PushTarget = Field(description="Push target")
    success: bool = Field(default=False, description="Whether delivery succeeded")
    message: str = Field(default="", description="Status or error message")
    delivered_at: datetime | None = Field(
        default=None,
        description="Delivery timestamp (None if failed)",
    )
