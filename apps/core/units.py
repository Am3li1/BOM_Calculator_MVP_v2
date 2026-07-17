# apps/core/units.py  (new file)
"""
Length-unit conversion for WoodPart dimension fields.

Only length units are meaningful here — 'sqft', 'cft', and 'nos' are
NOT convertible lengths (they're area/volume/count), so they're
intentionally excluded from LENGTH_TO_INCHES. If a WoodPart dimension
somehow has one of those units, that's a data-entry error upstream —
convert_to() raises rather than guessing.
"""
from decimal import Decimal

# Every supported length unit expressed in inches (exact, not approximate,
# to keep Decimal precision — avoid float literals here).
LENGTH_TO_INCHES = {
    'mm': Decimal('1') / Decimal('25.4'),
    'cm': Decimal('1') / Decimal('2.54'),
    'm':  Decimal('39.3700787401575'),   # 1 m = 39.37... in — see note below
    'in': Decimal('1'),
    'ft': Decimal('12'),
}


def to_inches(value, unit):
    """Convert a dimension value in `unit` to inches, as Decimal."""
    value = Decimal(str(value))
    if unit not in LENGTH_TO_INCHES:
        raise ValueError(
            f"'{unit}' is not a convertible length unit "
            f"(got dimension unit, expected one of {list(LENGTH_TO_INCHES)})"
        )
    return value * LENGTH_TO_INCHES[unit]


def to_feet(value, unit):
    """Convert a dimension value in `unit` to feet, as Decimal."""
    return to_inches(value, unit) / Decimal('12')