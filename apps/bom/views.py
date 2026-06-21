from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from apps.products.models import Product
from .models import BOMItem


@login_required
def bom_list(request, product_pk):
    from .models import WoodPart

    product = get_object_or_404(Product, pk=product_pk, is_deleted=False)

    bom_items  = BOMItem.objects.filter(product=product).select_related('resource')
    wood_parts = WoodPart.objects.filter(product=product).select_related('resource')

    total_bom_cost  = sum(item.cost for item in bom_items)
    total_wood_cost = sum(part.cost for part in wood_parts)
    grand_total     = total_bom_cost + total_wood_cost

    context = {
        'page_title': f'BOM — {product.product_code}',
        'product': product,
        'bom_items': bom_items,
        'wood_parts': wood_parts,
        'total_bom_cost': total_bom_cost,
        'total_wood_cost': total_wood_cost,
        'grand_total': grand_total,
    }
    return render(request, 'bom/list.html', context)


@login_required
def bom_add(request, product_pk):
    from apps.resources.models import Resource

    product = get_object_or_404(Product, pk=product_pk, is_deleted=False)

    existing_resource_ids = BOMItem.objects.filter(
        product=product
    ).values_list('resource_id', flat=True)

    available_resources = Resource.objects.filter(
        active=True
    ).exclude(id__in=existing_resource_ids)

    if request.method == 'POST':
        resource_id = request.POST.get('resource')
        quantity = request.POST.get('quantity')

        if not resource_id or not quantity:
            messages.error(request, 'Please select a resource and enter a quantity.')
        else:
            try:
                resource = Resource.objects.get(pk=resource_id, active=True)
                qty = float(quantity)
                if qty <= 0:
                    raise ValueError("Quantity must be positive.")

                BOMItem.objects.create(
                    product=product,
                    resource=resource,
                    quantity=qty,
                )
                messages.success(request, f'"{resource.resource_name}" added to BOM.')
                return redirect('bom:list', product_pk=product.pk)

            except Resource.DoesNotExist:
                messages.error(request, 'Invalid resource selected.')
            except ValueError as e:
                messages.error(request, f'Invalid quantity: {e}')

    context = {
        'page_title': f'Add BOM Item — {product.product_code}',
        'product': product,
        'available_resources': available_resources,
    }
    return render(request, 'bom/bom_add.html', context)


@login_required
def bom_remove(request, pk):
    bom_item = get_object_or_404(BOMItem, pk=pk)
    product_pk = bom_item.product.pk

    if request.method == 'POST':
        resource_name = bom_item.resource.resource_name
        bom_item.delete()
        messages.success(request, f'"{resource_name}" removed from BOM.')

    return redirect('bom:list', product_pk=product_pk)


@login_required
def bom_edit_quantity(request, pk):
    bom_item = get_object_or_404(BOMItem, pk=pk)
    product_pk = bom_item.product.pk

    if request.method == 'POST':
        quantity = request.POST.get('quantity')
        try:
            qty = float(quantity)
            if qty <= 0:
                raise ValueError("Must be positive.")
            bom_item.quantity = qty
            bom_item.save()
            messages.success(request, 'Quantity updated.')
        except (TypeError, ValueError) as e:
            messages.error(request, f'Invalid quantity: {e}')

    return redirect('bom:list', product_pk=product_pk)

@login_required
def woodpart_add(request, product_pk):
    """
    Adds a WoodPart to a product.
    User enters dimensions — system calculates quantity and cost.
    """
    from apps.resources.models import Resource
    from apps.core.models import SystemConfig

    product = get_object_or_404(Product, pk=product_pk, is_deleted=False)

    # Only show Wood/Ply/MDF resources — those are the only valid material types
    # for cut parts. Filter by category so the dropdown isn't cluttered.
    wood_resources = Resource.objects.filter(
        active=True,
        category__in=['Wood', 'Ply', 'MDF']
    )

    # Get the current divisor so we can show it on the form
    config = SystemConfig.get_config()

    if request.method == 'POST':
        resource_id  = request.POST.get('resource')
        part_name    = request.POST.get('part_name', '').strip()
        width        = request.POST.get('width')
        breadth      = request.POST.get('breadth')
        length       = request.POST.get('length')
        pieces       = request.POST.get('pieces')

        # Validate that nothing is blank
        if not all([resource_id, part_name, width, breadth, length, pieces]):
            messages.error(request, 'All fields are required.')
        else:
            try:
                from .models import WoodPart

                resource = Resource.objects.get(pk=resource_id, active=True)

                WoodPart.objects.create(
                    product  = product,
                    resource = resource,
                    part_name = part_name,
                    width    = float(width),
                    breadth  = float(breadth),
                    length   = float(length),
                    pieces   = int(pieces),
                )
                messages.success(
                    request,
                    f'Wood part "{part_name}" added successfully.'
                )
                return redirect('bom:list', product_pk=product.pk)

            except Resource.DoesNotExist:
                messages.error(request, 'Invalid resource selected.')
            except ValueError:
                messages.error(request, 'Please enter valid numbers for all dimensions.')

    context = {
        'page_title': f'Add Wood Part — {product.product_code}',
        'product': product,
        'wood_resources': wood_resources,
        'divisor': config.wood_divisor,
    }
    return render(request, 'bom/woodpart_add.html', context)


@login_required
def woodpart_remove(request, pk):
    """
    Removes a WoodPart. POST only for safety.
    """
    from .models import WoodPart

    wood_part = get_object_or_404(WoodPart, pk=pk)
    product_pk = wood_part.product.pk

    if request.method == 'POST':
        part_name = wood_part.part_name
        wood_part.delete()
        messages.success(request, f'Wood part "{part_name}" removed.')

    return redirect('bom:list', product_pk=product_pk)