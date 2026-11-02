# apps/bom/services.py
#
# Validation + write path shared by every "staged" way of adding BOM
# data: carpenter submissions (approved in views_submissions.py) and the
# voice assistant draft (assistant_commit in views.py). Both stage raw
# values first and only call apply_lines() once a human has confirmed.

from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.resources.models import Resource, DIMENSIONAL_UNIT_CODES

from .models import BOMItem, WoodPart, Part


class LineError(ValueError):
    """A single staged line failed validation. Message is user-facing."""


def _decimal(value, label, required=True, allow_zero=False):
    if value in (None, ''):
        if required:
            raise LineError(f'{label} is required.')
        return Decimal('0')
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise LineError(f'{label} must be a number.')
    if not number.is_finite() or number < 0 or (number == 0 and not allow_zero):
        raise LineError(f'{label} must be greater than zero.')
    return number


def _resource(resource_id):
    try:
        return Resource.objects.get(pk=int(resource_id), active=True)
    except (Resource.DoesNotExist, TypeError, ValueError):
        raise LineError('Please choose a material from the list.')


def _unit(value):
    unit = (value or 'in').strip()
    if unit not in DIMENSIONAL_UNIT_CODES:
        raise LineError(f'"{unit}" is not a valid unit.')
    return unit


def clean_bom_line(resource_id, quantity):
    """Standard BOM line → {'type': 'bom', 'resource', 'quantity'}."""
    return {
        'type': 'bom',
        'resource': _resource(resource_id),
        'quantity': _decimal(quantity, 'Quantity'),
    }


def clean_dimension_line(resource_id, part_name, width, breadth, length, pieces,
                         height=None, width_unit='in', breadth_unit='in',
                         height_unit='in', length_unit='in'):
    """Dimension line → dict with the same fields as WoodPart."""
    part_name = ' '.join((part_name or '').split())
    if not part_name:
        raise LineError('Part name is required.')
    try:
        pieces = int(str(pieces).strip())
    except (TypeError, ValueError):
        raise LineError('Pieces must be a whole number.')
    if pieces < 1:
        raise LineError('Pieces must be at least 1.')

    return {
        'type': 'dimension',
        'resource': _resource(resource_id),
        'part_name': part_name[:200],
        'width':   _decimal(width, 'Width'),
        'breadth': _decimal(breadth, 'Breadth'),
        'height':  _decimal(height, 'Height', required=False, allow_zero=True),
        'length':  _decimal(length, 'Length'),
        'width_unit':   _unit(width_unit),
        'breadth_unit': _unit(breadth_unit),
        'height_unit':  _unit(height_unit),
        'length_unit':  _unit(length_unit),
        'pieces': pieces,
    }


@transaction.atomic
def apply_lines(product, lines):
    """
    Writes cleaned lines into the real BOM. Standard lines upsert on
    (product, resource) — the same rule as the BOM import — so a
    resource already in the BOM gets its quantity replaced, not a
    duplicate row. Dimension lines always create a new WoodPart.

    Returns (bom_added, bom_updated, dimensions_added).
    """
    bom_added = bom_updated = dims_added = 0

    for line in lines:
        if line['type'] == 'bom':
            _, created = BOMItem.objects.update_or_create(
                product=product,
                resource=line['resource'],
                defaults={'quantity': line['quantity']},
            )
            if created:
                bom_added += 1
            else:
                bom_updated += 1
        else:
            part_obj, _ = Part.objects.get_or_create(name=line['part_name'])
            WoodPart.objects.create(
                product=product,
                resource=line['resource'],
                part=part_obj,
                part_name=part_obj.name,
                width=line['width'],
                breadth=line['breadth'],
                height=line['height'],
                length=line['length'],
                pieces=line['pieces'],
                width_unit=line['width_unit'],
                breadth_unit=line['breadth_unit'],
                height_unit=line['height_unit'],
                length_unit=line['length_unit'],
            )
            dims_added += 1

    return bom_added, bom_updated, dims_added


def describe_result(bom_added, bom_updated, dims_added):
    parts = []
    if bom_added:
        parts.append(f'{bom_added} BOM item{"s" if bom_added != 1 else ""} added')
    if bom_updated:
        parts.append(f'{bom_updated} BOM quantit{"ies" if bom_updated != 1 else "y"} updated')
    if dims_added:
        parts.append(f'{dims_added} dimension entr{"ies" if dims_added != 1 else "y"} added')
    return ', '.join(parts) or 'Nothing to add'
