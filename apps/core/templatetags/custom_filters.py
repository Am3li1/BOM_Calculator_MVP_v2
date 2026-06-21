# apps/core/templatetags/custom_filters.py

from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """
    Allows dictionary lookups in templates using a variable key.

    Django templates can do {{ mydict.fixed_key }} but NOT
    {{ mydict.variable_key }} — this filter bridges that gap.

    Usage in template:
        {{ my_dict|get_item:my_variable }}
    """
    return dictionary.get(key, 0)