# apps/core/search.py
#
# Name search across the English canonical name and the Tamil display
# layer (name_ta / aliases). English stays the source of truth — this
# only helps users FIND the canonical record by any of its names.

import unicodedata

from django.db.models import Q


def normalize_text(value):
    """
    NFC-normalise, trim and collapse internal whitespace; '' for None.

    Tamil vowel signs can be typed as different code-point sequences
    (e.g. ொ as U+0BCA, or as U+0BC6 + U+0BBE) that look identical on
    screen. Normalising both stored values and queries to NFC makes
    them compare equal.
    """
    if value is None:
        return ''
    return ' '.join(unicodedata.normalize('NFC', str(value)).split())


def normalize_multiline(value):
    """Like normalize_text, but keeps line breaks (for the aliases field,
    which may be one alias per line)."""
    if value is None:
        return ''
    lines = (normalize_text(line) for line in str(value).splitlines())
    return '\n'.join(line for line in lines if line)


def search_by_name(queryset, query, name_field):
    """
    Case-insensitive match of `query` against the English name field
    (`name_field`, e.g. 'resource_name' on Resource, 'name' on Part),
    `name_ta` and `aliases`. An empty query returns the queryset as-is.

        search_by_name(Resource.objects.all(), 'தேக்கு', 'resource_name')
    """
    q = normalize_text(query)
    if not q:
        return queryset
    return queryset.filter(
        Q(**{f'{name_field}__icontains': q})
        | Q(name_ta__icontains=q)
        | Q(aliases__icontains=q)
    )
