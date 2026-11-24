# apps/bom/reviewer_llm.py
#
# The LLM half of the AI BOM reviewer (see reviewer.py). It gets the
# carpenter's list, the most similar real BOMs and what the statistics
# already flagged, and is asked what else looks wrong — the kind of thing
# counting can't see ("a 3-door wardrobe with 2 handles").
#
# Guard rails:
#   - The payload is an explicit whitelist: names, units, quantities and
#     measurements. Never rate, effective_rate, supplier or cost
#     (CLAUDE.md Security rule 3).
#   - Every material the model names must resolve to a real active
#     Resource, or the finding is dropped — it cannot invent materials.
#   - Any failure (no key, timeout, 429, bad JSON) returns [] and the
#     carpenter just sees the statistical findings.

import json
import logging
import re
from decimal import Decimal, InvalidOperation

from django.conf import settings

from apps.core.search import search_by_name
from apps.resources.models import Resource

from .reviewer import Finding, number

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 12
MAX_AI_FINDINGS = 5
KINDS = {'missing', 'quantity', 'dimension', 'other'}

SYSTEM_PROMPT = """\
You check a furniture carpenter's material list (Bill of Materials) for one \
product before it is sent to the office. Compare it with the reference lists \
of similar products from the same workshop, and use your carpentry knowledge.

Look for real, likely mistakes only:
- a material the product clearly needs but the list lacks (screws for hinges, \
edge band for ply, handles for doors or drawers, polish for wood);
- a quantity that does not fit the product (2 handles on a 3-door wardrobe);
- a measurement that looks like a unit or typing slip.

The "already_flagged" questions will be asked anyway: do not repeat them. \
If nothing else looks wrong, return no findings. At most {max_findings}.

Reply with JSON only, no other text:
{{"findings": [{{"kind": "missing" | "quantity" | "dimension" | "other",
  "material": "exact English material name from the list or references",
  "part_name": "part name for dimension findings, else empty",
  "suggested_value": "number or empty",
  "question_en": "one short, polite question to the carpenter, in simple English",
  "question_ta": "the same question in simple Tamil",
  "reason": "why, in a few words, for the office"}}]}}
"""


def is_configured():
    return bool(getattr(settings, 'BOM_ASSISTANT_API_KEY', ''))


def _client():
    from openai import OpenAI
    return OpenAI(
        api_key=settings.BOM_ASSISTANT_API_KEY,
        base_url=settings.BOM_ASSISTANT_BASE_URL,
        timeout=TIMEOUT_SECONDS,
        max_retries=0,
    )


def _plain(value):
    if value in (None, ''):
        return ''
    return format(Decimal(value).normalize(), 'f')


def _resource_json(resource, quantity):
    return {'material': resource.resource_name, 'category': resource.category,
            'unit': resource.unit, 'quantity': _plain(quantity)}


def build_payload(product_name, lines, refs, stats_findings, corrections):
    """Everything the model sees. Explicit fields only — no rates."""
    resource_ids = set()
    for ref in refs:
        resource_ids |= set(ref.bom) | {d['resource_id'] for d in ref.dims}
    names = Resource.objects.in_bulk(resource_ids)

    def ref_json(ref):
        return {
            'product': ref.name,
            'materials': [_resource_json(names[rid], qty) for rid, qty in ref.bom.items() if rid in names],
            'parts': [
                {'part': d['part'], 'material': names[d['resource_id']].resource_name,
                 'width_in': _plain(d['width']), 'breadth_in': _plain(d['breadth']),
                 'length_in': _plain(d['length']), 'pieces': d['pieces']}
                for d in ref.dims if d['resource_id'] in names
            ],
        }

    materials, parts = [], []
    for line in lines:
        if line['type'] == 'bom':
            materials.append(_resource_json(line['resource'], line['quantity']))
        else:
            parts.append({
                'part': line['part_name'], 'material': line['resource'].resource_name,
                # Sheet materials (plywood / MDF) have no breadth.
                **{d: f"{_plain(line[d])} {line[f'{d}_unit']}"
                   for d in ('width', 'breadth', 'length') if line[d]},
                'pieces': line['pieces'],
            })

    return {
        'product': product_name or 'New product',
        'list': {'materials': materials, 'parts': parts},
        'similar_products': [ref_json(r) for r in refs],
        'already_flagged': [f.message_en for f in stats_findings],
        'past_corrections': corrections,
    }


def _resolve(name, candidates):
    """Material name → active Resource. Prefers resources from the list /
    references, then an unambiguous search."""
    name = (name or '').strip()
    if not name:
        return None
    lowered = name.lower()
    for resource in candidates:
        if resource.resource_name.lower() == lowered:
            return resource
    matches = list(search_by_name(Resource.objects.filter(active=True), name, 'resource_name')[:2])
    return matches[0] if len(matches) == 1 else None


def _parse_json(text):
    text = (text or '').strip()
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text)
    start, end = text.find('{'), text.rfind('}')
    if start == -1 or end <= start:
        raise ValueError('no JSON object')
    return json.loads(text[start:end + 1])


def parse_findings(text, lines, refs):
    """Model reply → validated Finding list. Anything malformed or
    pointing at an unknown material is dropped."""
    data = _parse_json(text)
    items = data.get('findings') if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []

    in_list = {line['resource'].pk: line for line in lines if line['type'] == 'bom'}
    dim_lines = [line for line in lines if line['type'] == 'dimension']
    ref_ids = set()
    for ref in refs:
        ref_ids |= set(ref.bom)
    candidates = [line['resource'] for line in lines] + \
        list(Resource.objects.filter(pk__in=ref_ids, active=True))

    findings = []
    for item in items:
        if not isinstance(item, dict) or len(findings) >= MAX_AI_FINDINGS:
            continue
        kind = str(item.get('kind', '')).strip().lower()
        question_en = str(item.get('question_en') or '').strip()[:400]
        question_ta = str(item.get('question_ta') or '').strip()[:400] or question_en
        if kind not in KINDS or not question_en:
            continue

        resource = _resolve(item.get('material'), candidates)
        suggested = ''
        try:
            value = Decimal(str(item.get('suggested_value') or '').strip())
            if value.is_finite() and value > 0:
                suggested = number(value)
        except InvalidOperation:
            pass

        finding = Finding(kind=kind, message_en=question_en, message_ta=question_ta, source='ai',
                          suggested=suggested, evidence=str(item.get('reason') or '')[:300])
        if kind == 'missing':
            if resource is None or resource.pk in in_list:
                continue
        elif kind == 'quantity':
            if resource is None or resource.pk not in in_list:
                continue
            finding.current = _plain(in_list[resource.pk]['quantity'])
        elif kind == 'dimension':
            part = str(item.get('part_name') or '').strip().lower()
            index = next((i for i, l in enumerate(dim_lines) if l['part_name'].lower() == part), None)
            if index is None:
                continue
            finding.line_index = index
            finding.part_name = dim_lines[index]['part_name']
            resource = dim_lines[index]['resource']
            finding.suggested = ''
        if resource is not None:
            finding.resource_id = resource.pk
            finding.resource_name = resource.resource_name
        findings.append(finding)
    return findings


def ai_findings(product_name, lines, refs, stats_findings, corrections):
    if not is_configured():
        return []
    payload = build_payload(product_name, lines, refs, stats_findings, corrections)
    try:
        response = _client().chat.completions.create(
            model=settings.BOM_ASSISTANT_MODEL,
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT.format(max_findings=MAX_AI_FINDINGS)},
                {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.1,
            max_tokens=4096,      # thinking models spend part of this budget
        )
        text = response.choices[0].message.content if response.choices else ''
        return parse_findings(text, lines, refs)
    except Exception:
        # Busy provider, timeout, odd output: the statistical findings
        # still stand on their own.
        logger.warning('AI BOM reviewer: LLM check skipped', exc_info=True)
        return []
