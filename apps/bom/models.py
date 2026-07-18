# apps/bom/models.py
from decimal import Decimal
from apps.core.units import to_inches, to_feet
from django.db import models
from apps.products.models import Product
from apps.resources.models import Resource

# Divisor used ONLY by the two built-in material_type formulas
# (solid_wood CFT / 'other' legacy) below. This replaced
# SystemConfig.wood_divisor — it is no longer a user-editable system
# setting. Anyone who needs a different divisor writes it as a literal
# in a custom formula (WoodPart.formula_expression or
# Resource.formula_expression), e.g. ".../166".
_BUILTIN_DIVISOR = Decimal('144')


class Part(models.Model):
    """
    A named component of a product (e.g. 'Table Top', 'Leg 1').
    Exists only to organize WoodPart entries in the BOM — no
    standalone CRUD page. Managed via the Parts sheet import
    and inline from the WoodPart add/edit forms.
    """
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='parts',
    )
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ['name']
        unique_together = [['product', 'name']]

    def __str__(self):
        return f'{self.product.product_code} — {self.name}'

class BOMItem(models.Model):
    """
    Standard Bill of Materials line item.
    
    Represents: "Product X needs Y units of Resource Z"
    
    Example:
        3-Door Wardrobe needs 12.5 SFT of Teak Wood
    
    Key design decision:
        'rate' and 'cost' are NOT stored here.
        Cost = quantity × resource.rate  (always calculated live)
        This ensures rate changes reflect immediately everywhere.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,       # if product deleted, its BOM items go too
        related_name='bom_items',       # lets us do: product.bom_items.all()
        help_text="The product this BOM line belongs to."
    )

    resource = models.ForeignKey(
        Resource,
        on_delete=models.PROTECT,       # PROTECT: don't allow deleting a resource
        related_name='bom_items',       # that's still in use in a BOM
        help_text="The resource/material being consumed."
    )

    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        help_text="How many units of this resource does this product need?"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['resource__category', 'resource__resource_name']
        verbose_name = "BOM Item"
        verbose_name_plural = "BOM Items"
        # A resource should appear only once per product in standard BOM
        unique_together = [['product', 'resource']]

    def __str__(self):
        return f"{self.product.product_code} | {self.resource.resource_name} × {self.quantity}"

    # ── Calculated Properties ───────────────────────────────────────
    @property
    def rate(self):
        """
        Live rate from the resource's effective rate.
        Uses preferred supplier rate, lowest supplier rate,
        or resource master rate — in that priority order.
        """
        return self.resource.effective_rate

    @property
    def cost(self):
        """
        Calculated automatically. Never stored. Never editable.
        Cost = Quantity × Rate
        """
        return self.quantity * self.rate


class WoodPart(models.Model):
    """
    A dimensional entry for a product.
    Captures physical measurements and calculates material quantity.

    Units are stored per-dimension so that mixed-unit products
    (e.g. width in inches, length in feet) are supported.
    """

    UNIT_CHOICES = [
        ('in',   'Inches'),
        ('ft',   'Feet'),
        ('sqft', 'Square Feet'),
        ('cft',  'Cubic Feet'),
        ('mm',   'Millimeters'),
        ('cm',   'Centimeters'),
        ('m',    'Meters'),
        ('nos',  'Numbers'),
    ]

    FORMULA_CHOICES = [
        ('standard', 'Standard (W × B × L × Pcs ÷ Divisor)'),
        ('area',     'Area (W × L × Pcs ÷ Divisor)'),
        ('custom',   'Custom'),
    ]

    product  = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='wood_parts',
    )
    resource = models.ForeignKey(
        'resources.Resource',
        on_delete=models.PROTECT,
        related_name='wood_parts',
    )

    part_name = models.CharField(max_length=200)

    part = models.ForeignKey(
        Part,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='wood_parts',
    )

    # Dimensions
    width   = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    breadth = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    height  = models.DecimalField(
        max_digits=10, decimal_places=4,
        default=0, blank=True,
        help_text="Optional. Use for 3D parts."
    )
    length  = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    pieces  = models.PositiveIntegerField(default=1)

    # Units per dimension
    width_unit   = models.CharField(
        max_length=10, choices=UNIT_CHOICES, default='in'
    )
    breadth_unit = models.CharField(
        max_length=10, choices=UNIT_CHOICES, default='in'
    )
    height_unit  = models.CharField(
        max_length=10, choices=UNIT_CHOICES, default='in'
    )
    length_unit  = models.CharField(
        max_length=10, choices=UNIT_CHOICES, default='in'
    )

    formula_type = models.CharField(
        max_length=20,
        choices=FORMULA_CHOICES,
        default='standard',
    )

    # ── Per-line custom formula ─────────────────────────────────────
    formula_expression = models.CharField(
        max_length=500,
        blank=True,
        help_text=(
            "Optional. A custom formula for THIS dimension entry only "
            "— takes priority over the resource's formula and the "
            "built-in Material Type formula. E.g. "
            "\"width_in * breadth_in * length_ft * pieces / 166\". "
            "Leave blank to fall back to the resource's custom formula "
            "(if any), then the built-in formula. Evaluated with a "
            "safe expression parser — no arbitrary code execution."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['part_name']

    def __str__(self):
        return f'{self.product.product_code} — {self.part_name}'

    @property
    def rate(self):
        """
        Live rate from the resource's effective rate.
        """
        return self.resource.effective_rate

    @property
    def cost(self):
        """Calculated cost — never stored."""
        return self.calculated_quantity * self.rate

    def _formula_variables(self):
        """
        Builds the variable dict available to a custom
        WoodPart.formula_expression or Resource.formula_expression.
        Unit-conversion variables (_in / _ft) are omitted (not
        KeyError'd) if the stored unit for that dimension isn't a
        convertible length unit (e.g. 'sqft'/'cft'/'nos') —
        referencing a missing one in a formula surfaces as a clear
        "Unknown variable" FormulaError rather than crashing here.

        Note: there is no 'divisor' variable. If a formula needs to
        divide by something (144, 166, 1728...), the user types that
        number directly in the expression — there's no implicit
        system-wide value to fall back on.
        """
        def _try(dim_value, dim_unit, converter):
            try:
                return float(converter(dim_value, dim_unit))
            except ValueError:
                return None

        variables = {
            'width':   float(self.width or 0),
            'breadth': float(self.breadth or 0),
            'height':  float(self.height or 0),
            'length':  float(self.length or 0),
            'pieces':  float(self.pieces or 0),
        }

        for dim_name, dim_value, dim_unit in [
            ('width', self.width, self.width_unit),
            ('breadth', self.breadth, self.breadth_unit),
            ('height', self.height, self.height_unit),
            ('length', self.length, self.length_unit),
        ]:
            in_val = _try(dim_value, dim_unit, to_inches)
            if in_val is not None:
                variables[f'{dim_name}_in'] = in_val
            ft_val = _try(dim_value, dim_unit, to_feet)
            if ft_val is not None:
                variables[f'{dim_name}_ft'] = ft_val

        return variables

    @property
    def calculated_quantity(self):
        """
        Quantity resolution order:

          1. self.formula_expression, if set — a custom formula for
             THIS WoodPart line only.
          2. Built-in formula by resource.material_type:
               solid_wood -> CFT = (W_in × B_in × L_ft × pieces) / 144
               sheet      -> SFT = W_ft × B_ft × pieces   (Length unused)
               other      -> legacy formula_type-based calculation
                             (unchanged behaviour for anything not yet
                             classified and without a custom formula)

        (Resource-level formula_expression was removed — there is no
        longer a per-resource formula tier. Custom formulas are set
        per WoodPart line only.)

        The custom-formula tier is evaluated safely via
        apps/core/safe_eval.py (see _formula_variables for the
        available variable set). There is no 'divisor' variable; any
        division constant goes directly in the formula text.
        """
        woodpart_formula = (self.formula_expression or '').strip()

        if woodpart_formula:
            from apps.core.safe_eval import evaluate_formula, FormulaError

            variables = self._formula_variables()
            try:
                result = evaluate_formula(woodpart_formula, variables)
            except FormulaError as e:
                raise FormulaError(f'Formula error (this dimension entry): {e}')
            return Decimal(str(result))

        material_type = self.resource.material_type
        pieces = Decimal(str(self.pieces))

        if material_type == 'solid_wood':
            w_in = to_inches(self.width, self.width_unit)
            b_in = to_inches(self.breadth, self.breadth_unit)
            l_ft = to_feet(self.length, self.length_unit)
            return (w_in * b_in * l_ft * pieces) / _BUILTIN_DIVISOR

        if material_type == 'sheet':
            w_ft = to_feet(self.width, self.width_unit)
            b_ft = to_feet(self.breadth, self.breadth_unit)
            return w_ft * b_ft * pieces

        # material_type == 'other' -> legacy behaviour, unit-naive
        # (kept as-is so unclassified resources don't silently change cost)
        w = Decimal(str(self.width))
        b = Decimal(str(self.breadth))
        h = Decimal(str(self.height)) if self.height else Decimal('1')
        l = Decimal(str(self.length))

        if self.formula_type == 'area':
            return (w * l * pieces) / _BUILTIN_DIVISOR
        else:
            effective_h = h if h > 0 else Decimal('1')
            return (w * b * effective_h * l * pieces) / _BUILTIN_DIVISOR

    @property
    def formula_source(self):
        """
        Which tier actually produced calculated_quantity — for UI
        badges ("this entry" / "built-in") and debugging. Mirrors the
        precedence in calculated_quantity; keep the two in sync if
        that logic ever changes.
        """
        if (self.formula_expression or '').strip():
            return 'woodpart_custom'
        return 'material_type_default'