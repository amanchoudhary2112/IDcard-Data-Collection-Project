from django import template

register = template.Library()

@register.filter(name='get_item')
def get_item(dictionary, key):
    """Allows accessing dictionary keys with variables in templates."""
    return dictionary.get(key)

@register.filter(name='is_list')
def is_list(value):
    """Checks if a value is a list."""
    return isinstance(value, list)