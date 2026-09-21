"""Small presentation helpers used across the templates."""

import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def initials(value):
    parts = [p for p in str(value).split() if p]
    if not parts:
        return "?"
    return "".join(part[0] for part in parts[:2]).upper()


@register.filter
def currency(value):
    """Render a money amount with thousands separators."""
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        return value
    return "{:,.2f}".format(amount)


@register.filter
def percent_of(value, total):
    try:
        value = float(value or 0)
        total = float(total or 0)
    except (TypeError, ValueError):
        return 0
    if not total:
        return 0
    return round(value * 100 / total, 1)


@register.filter(is_safe=True)
def markdownish(value):
    """Render the small markdown subset the assistant produces.

    Supports **bold**, *italic*, `code`, bullet lists and paragraphs. Input is
    escaped first, so model output can never inject HTML.
    """
    if not value:
        return ""

    text = escape(str(value))
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text, flags=re.S)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text, flags=re.S)
    text = re.sub(r"_(?!_)(.+?)_", r"<em>\1</em>", text, flags=re.S)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)

    blocks = []
    for chunk in re.split(r"\n\s*\n", text.strip()):
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        if not lines:
            continue
        if all(re.match(r"^[-*\u2022]\s+", line) for line in lines):
            items = "".join(
                "<li>%s</li>" % re.sub(r"^[-*\u2022]\s+", "", line) for line in lines
            )
            blocks.append("<ul class='mb-2'>%s</ul>" % items)
        elif all(re.match(r"^\d+[.)]\s+", line) for line in lines):
            items = "".join(
                "<li>%s</li>" % re.sub(r"^\d+[.)]\s+", "", line) for line in lines
            )
            blocks.append("<ol class='mb-2'>%s</ol>" % items)
        else:
            blocks.append("<p class='mb-2'>%s</p>" % "<br>".join(lines))

    return mark_safe("".join(blocks))


@register.simple_tag
def query_replace(request, **kwargs):
    """Rebuild the query string with some parameters replaced -- used by paginators."""
    params = request.GET.copy()
    for key, value in kwargs.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = value
    return params.urlencode()
