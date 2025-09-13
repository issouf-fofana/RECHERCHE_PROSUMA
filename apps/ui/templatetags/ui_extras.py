from django import template

register = template.Library()

@register.filter(name="add_class")
def add_class(field, css):
    """
    Ajoute des classes CSS à un widget de formulaire.
    Usage: {{ form.field|add_class:"form-control" }}
    """
    existing = field.field.widget.attrs.get("class", "")
    merged = f"{existing} {css}".strip()
    return field.as_widget(attrs={**field.field.widget.attrs, "class": merged})

@register.filter(name="get_item")
def get_item(obj, key):
    """
    Récupère une valeur dynamiquement:
      - dict: obj.get(key)
      - objet: getattr(obj, key, "")
      - list/tuple avec key numérique: index
      - sinon: ""
    Usage: {{ row|get_item:c }}
    """
    if obj is None or key is None:
        return ""
    # dict-like
    if isinstance(obj, dict):
        return obj.get(key, "")
    # list/tuple + index numérique
    if isinstance(obj, (list, tuple)):
        try:
            i = int(key)
            return obj[i]
        except Exception:
            return ""
    # objet avec attribut
    try:
        return getattr(obj, key, "")
    except Exception:
        return ""
