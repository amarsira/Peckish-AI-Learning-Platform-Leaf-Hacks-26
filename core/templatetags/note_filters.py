import re

from django import template
from django.utils.safestring import mark_safe


register = template.Library()


ICON_PATHS = {
    "arrow": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "book": '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5z"/>',
    "brain": '<path d="M9 3a3 3 0 0 0-3 3v1a3 3 0 0 0 0 6v1a4 4 0 0 0 4 4h1V3z"/><path d="M15 3a3 3 0 0 1 3 3v1a3 3 0 0 1 0 6v1a4 4 0 0 1-4 4h-1V3z"/>',
    "chip": '<rect x="7" y="7" width="10" height="10" rx="2"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3"/>',
    "compass": '<circle cx="12" cy="12" r="9"/><path d="m15 9-2 6-6 2 2-6 6-2z"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.12 2.12-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1 1.56V21h-3v-.78a1.7 1.7 0 0 0-1-1.56 1.7 1.7 0 0 0-1.88.34l-.06.06-2.12-2.12.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.56-1H2v-3h1.04a1.7 1.7 0 0 0 1.56-1 1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.12-2.12.06.06A1.7 1.7 0 0 0 8.26 5.4a1.7 1.7 0 0 0 1-1.56V3h3v.84a1.7 1.7 0 0 0 1 1.56 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.12 2.12-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.56 1H22v3h-1.04a1.7 1.7 0 0 0-1.56 1z"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 10v6"/><path d="M12 7h.01"/>',
    "key": '<circle cx="7.5" cy="14.5" r="3.5"/><path d="M10 12 21 1"/><path d="m16 6 2 2"/><path d="m14 8 2 2"/>',
    "leaf": '<path d="M20 4c-7 0-12 5-12 12a4 4 0 0 0 4 4c7 0 8-8 8-16z"/><path d="M8 16c2-4 5-7 10-10"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.07 0l2-2a5 5 0 0 0-7.07-7.07l-1.15 1.15"/><path d="M14 11a5 5 0 0 0-7.07 0l-2 2A5 5 0 0 0 12 20.07l1.15-1.15"/>',
    "map": '<path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6z"/><path d="M9 3v15"/><path d="M15 6v15"/>',
    "spark": '<path d="m12 2 1.6 6.4L20 10l-6.4 1.6L12 18l-1.6-6.4L4 10l6.4-1.6L12 2z"/><path d="m19 17 .6 2.4L22 20l-2.4.6L19 23l-.6-2.4L16 20l2.4-.6L19 17z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>',
}

ICON_ALIASES = {
    "alu": "gear",
    "arrow-right": "arrow",
    "bridge": "link",
    "calculate": "gear",
    "calculation": "gear",
    "circuit": "chip",
    "compass": "compass",
    "cpu": "chip",
    "decode": "map",
    "execute": "gear",
    "fetch": "arrow",
    "idea": "spark",
    "instruction": "arrow",
    "lens": "compass",
    "memory": "chip",
    "process": "gear",
    "register": "book",
    "sparkle": "spark",
    "thread": "link",
}


@register.filter
def note_points(value, limit=3):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return []

    raw_parts = re.split(r"(?:\s*[-*]\s+)|(?:[.;]\s+)|(?:\n+)", text)
    cleaned_parts = [part.strip(" -.;:") for part in raw_parts if part.strip(" -.;:")]
    points = []
    compact_note = ""
    max_points = int(limit)

    for part in cleaned_parts:
        is_tiny_fragment = len(part.split()) <= 4
        if is_tiny_fragment:
            compact_note = f"{compact_note}; {part}" if compact_note else part
            if len(compact_note) < 90:
                continue

        if compact_note:
            points.append(compact_note)
            compact_note = ""
            if len(points) >= max_points:
                break

        if not is_tiny_fragment:
            points.append(part)
            if len(points) >= max_points:
                break

    if compact_note and len(points) < max_points:
        points.append(compact_note)

    if points:
        return points[:max_points]

    for part in raw_parts:
        cleaned = part.strip(" -.;:")
        if cleaned:
            points.append(cleaned)
        if len(points) >= max_points:
            break
    return points or [text]


@register.filter
def mindmap_icon(value):
    raw_icon = re.sub(r"[^a-z0-9 -]", "", str(value or "").strip().lower())
    icon_key = ICON_ALIASES.get(raw_icon, raw_icon)

    if icon_key not in ICON_PATHS:
        for alias, mapped_icon in ICON_ALIASES.items():
            if alias in raw_icon:
                icon_key = mapped_icon
                break

    paths = ICON_PATHS.get(icon_key, ICON_PATHS["spark"])
    return mark_safe(
        '<svg class="mindmap-icon" viewBox="0 0 24 24" aria-hidden="true" '
        'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round">{paths}</svg>'
    )
