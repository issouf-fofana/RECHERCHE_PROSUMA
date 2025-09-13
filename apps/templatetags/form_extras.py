# apps/templatetags/form_extras.py
from django import template
register = template.Library()

@register.filter
def add_class(field, css):
    existing = field.field.widget.attrs.get("class", "")
    field.field.widget.attrs["class"] = (existing + " " + css).strip()
    return field
