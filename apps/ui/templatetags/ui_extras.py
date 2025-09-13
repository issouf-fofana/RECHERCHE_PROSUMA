from django import template
register = template.Library()

@register.filter
def get_item(d, key):
    try:
        return d.get(key, "")
    except AttributeError:
        try:
            return d[key]
        except Exception:
            return ""

@register.filter
def split(value, sep=","):
    """Retourne value.split(sep)."""
    if value is None:
        return []
    return str(value).split(sep)
