# apps/bom/reviewer.py
#
# AI BOM reviewer. Checks a carpenter's list before it is sent and asks
# about likely mistakes: a material similar products always use but this
# list lacks, a quantity far from what similar products use, a
# measurement that looks like a unit slip.
#
# Three layers (see the plan in CLAUDE.md → AI BOM Reviewer):
#   1. Statistics learned from every approved BOM: similar products
#      (nearest neighbours), "used together" rules, quantity ranges.
#      Recomputed on every check, so each approval "retrains" it.
#   2. An LLM (reviewer_llm.py) reasoning over the same evidence.
#   3. Feedback: SubmissionFinding rows record what was flagged, what the
#      carpenter answered and what the admin approved. Rules the
#      carpenter and admin keep overruling are suppressed.
#
# Quantities and measurements only — never rates or costs (CLAUDE.md
# Security rule 3). Nothing here writes to the BOM.

import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from decimal import Decimal, InvalidOperation

from apps.core.units import to_inches
from apps.products.models import Product

from .models import BOMItem, WoodPart

MAX_REFERENCES = 5
MIN_REFERENCE_SCORE = 0.15
MISSING_SHARE = 0.6            # weighted share of references that use a material
MAX_MISSING = 6
COMPANION_CONFIDENCE = 0.8
COMPANION_SUPPORT = 3          # products that use both
MAX_COMPANIONS = 4
QUANTITY_FACTOR = Decimal('2.5')
DIMENSION_FACTOR = Decimal('3')
MAX_SANE_INCHES = Decimal('144')   # 12 ft — longer than any sheet or plank
SUPPRESS_AFTER = 3             # dismissals upheld by an admin
UNIT_SLIPS = [10, 12, 100, 1000]

_STOPWORDS = {'with', 'and', 'the', 'for', 'of', 'in', 'a', 'an', 'new', 'type', 'model'}
_DIM_NAMES = {
    'width':   {'en': 'width',   'ta': 'அகலம்'},
    'breadth': {'en': 'breadth', 'ta': 'கனம்'},
    'length':  {'en': 'length',  'ta': 'நீளம்'},
}

MESSAGES = {
    'en': {
        'missing': '{n} of {m} similar products use {material} (usually {qty} {unit}). Did you forget it?',
        'missing_one': '{ref} uses {material} ({qty} {unit}), but it is not in your list. Did you forget it?',
        'companion': 'Products that use {trigger} usually also use {material} ({qty} {unit}). Is it needed here?',
        'quantity': 'You entered {qty} {unit} of {material}. Similar products use about {typical} {unit}. '
                    'Is {qty} correct?',
        'unit_slip': ' It may have been entered in a different unit.',
        'dimension': '{part}: the {dim} is {value}, but in similar products it is about {typical}. '
                     'Please check the measurement.',
        'too_big': '{part}: the {dim} is {value}, which is more than 12 feet. Please check the unit.',
        'pieces': '{part}: {pieces} pieces, but similar products use {typical}. Is that correct?',
    },
    'ta': {
        'missing': '{m} ஒத்த பொருட்களில் {n} இல் {material} பயன்படுகிறது (பொதுவாக {qty} {unit}). '
                   'அதைச் சேர்க்க மறந்துவிட்டீர்களா?',
        'missing_one': '{ref} இல் {material} ({qty} {unit}) உள்ளது, ஆனால் உங்கள் பட்டியலில் இல்லை. '
                       'சேர்க்க மறந்துவிட்டீர்களா?',
        'companion': '{trigger} பயன்படுத்தும் பொருட்களில் பொதுவாக {material} ({qty} {unit}) உம் இருக்கும். '
                     'இங்கே தேவையா?',
        'quantity': 'நீங்கள் {material} {qty} {unit} என உள்ளிட்டுள்ளீர்கள். ஒத்த பொருட்களில் சுமார் '
                    '{typical} {unit} தான். {qty} சரியா?',
        'unit_slip': ' வேறு அலகில் உள்ளிடப்பட்டிருக்கலாம்.',
        'dimension': '{part}: {dim} {value}, ஆனால் ஒத்த பொருட்களில் சுமார் {typical}. அளவைச் சரிபார்க்கவும்.',
        'too_big': '{part}: {dim} {value} — இது 12 அடிக்கு மேல். அலகைச் சரிபார்க்கவும்.',
        'pieces': '{part}: {pieces} எண்ணிக்கை, ஆனால் ஒத்த பொருட்களில் {typical}. இது சரியா?',
    },
}


@dataclass
class Finding:
    kind: str                       # SubmissionFinding.KIND_*
    message_en: str
    message_ta: str
    source: str = 'stats'           # 'stats' | 'ai'
    resource_id: int = None
    resource_name: str = ''
    part_name: str = ''
    suggested: str = ''             # suggested quantity, plain number string
    current: str = ''               # what the carpenter entered
    evidence: str = ''              # English, for the admin
    line_index: int = None          # index among dimension lines (dimension findings)

    @property
    def key(self):
        group = 'missing' if self.kind in ('missing', 'companion') else self.kind
        return (group, self.resource_id, self.part_name.lower())

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        names = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in names})


@dataclass
class Reference:
    """A similar product's list, used as evidence."""
    product_id: int
    name: str
    score: float
    bom: dict = field(default_factory=dict)    # resource_id → Decimal qty
    dims: list = field(default_factory=list)   # dicts with *_in measurements


# ── Helpers ──────────────────────────────────────────────────────────

def number(value):
    """Decimal → short plain string: 2.5, 100, 0.33."""
    if value in (None, ''):
        return ''
    value = Decimal(value)
    if value >= 10:
        value = value.quantize(Decimal('1')) if value == value.to_integral() else value.quantize(Decimal('0.1'))
    else:
        value = value.quantize(Decimal('0.01'))
    return format(value.normalize(), 'f')


def name_tokens(name):
    words = re.findall(r'[\w-]+', (name or '').lower())
    return {w for w in words if len(w) > 1 and w not in _STOPWORDS}


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _median(values):
    return Decimal(str(statistics.median(values)))


def _inches(value, unit):
    try:
        return to_inches(value, unit)
    except (ValueError, InvalidOperation, TypeError):
        return None


def _display_name(resource, lang):
    if lang == 'ta' and resource.name_ta:
        return resource.name_ta
    return resource.resource_name


def _messages(key, **params):
    """Both languages of one message. `params` values may be dicts with
    'en' / 'ta' variants (e.g. material names)."""
    out = {}
    for lang in ('en', 'ta'):
        values = {k: (v[lang] if isinstance(v, dict) else v) for k, v in params.items()}
        out[lang] = MESSAGES[lang][key].format(**values)
    return out['en'], out['ta']


def _names(resource):
    return {'en': resource.resource_name, 'ta': _display_name(resource, 'ta')}


# ── Learned data: product profiles ───────────────────────────────────

def product_profiles():
    """
    Every active product's BOM quantities and measurements — the data the
    reviewer learns from. Returns {product_id: Reference} (score 0).
    """
    profiles = {
        p.pk: Reference(product_id=p.pk, name=p.product_name, score=0.0)
        for p in Product.active_products()
    }
    for product_id, resource_id, quantity in (
        BOMItem.objects.filter(product_id__in=profiles, resource__active=True)
        .values_list('product_id', 'resource_id', 'quantity')
    ):
        profiles[product_id].bom[resource_id] = quantity

    for wp in (
        WoodPart.objects.filter(product_id__in=profiles, resource__active=True)
        .values('product_id', 'resource_id', 'part_name', 'width', 'width_unit',
                'breadth', 'breadth_unit', 'length', 'length_unit', 'pieces')
    ):
        profiles[wp['product_id']].dims.append({
            'resource_id': wp['resource_id'],
            'part': (wp['part_name'] or '').strip().lower(),
            'width': _inches(wp['width'], wp['width_unit']),
            'breadth': _inches(wp['breadth'], wp['breadth_unit']),
            'length': _inches(wp['length'], wp['length_unit']),
            'pieces': wp['pieces'],
        })

    return {pk: p for pk, p in profiles.items() if p.bom or p.dims}


def _line_resources(lines):
    return {line['resource'].pk for line in lines}


def find_similar_products(product_name, lines, product=None, based_on=None,
                          profiles=None, k=MAX_REFERENCES):
    """
    Nearest-neighbour search over product_profiles(): the product's own
    current BOM and the product it was copied from score highest, then
    shared name words ("wardrobe", "3-door") and shared materials.
    """
    profiles = product_profiles() if profiles is None else profiles
    tokens = name_tokens(product_name)
    submitted = _line_resources(lines)
    pinned = {p.pk for p in (product, based_on) if p is not None}

    scored = []
    for profile in profiles.values():
        materials = set(profile.bom) | {d['resource_id'] for d in profile.dims}
        score = (2.0 * _jaccard(tokens, name_tokens(profile.name))
                 + 1.0 * _jaccard(submitted, materials))
        if profile.product_id in pinned:
            score += 3.0
        if score >= MIN_REFERENCE_SCORE:
            scored.append(Reference(profile.product_id, profile.name, score,
                                    profile.bom, profile.dims))

    scored.sort(key=lambda r: (-r.score, r.name))
    return scored[:k]


# ── Checks ───────────────────────────────────────────────────────────

def _resources_by_id(ids):
    from apps.resources.models import Resource
    return Resource.objects.in_bulk(set(ids))


def missing_materials(lines, refs):
    """Materials most similar products use that this list lacks."""
    if not refs:
        return []
    present = _line_resources(lines)
    total_weight = sum(r.score for r in refs)
    weight, users = defaultdict(float), defaultdict(list)
    for ref in refs:
        for resource_id in ref.bom:
            weight[resource_id] += ref.score
            users[resource_id].append(ref)

    candidates = []
    for resource_id, w in weight.items():
        if resource_id in present:
            continue
        share = w / total_weight
        if share >= MISSING_SHARE and (len(users[resource_id]) >= 2 or len(refs) == 1):
            candidates.append((share, resource_id))
    candidates.sort(key=lambda c: -c[0])
    candidates = candidates[:MAX_MISSING]

    resources = _resources_by_id(rid for _, rid in candidates)
    findings = []
    for share, resource_id in candidates:
        resource = resources.get(resource_id)
        if resource is None:
            continue
        refs_using = users[resource_id]
        qty = number(_median([r.bom[resource_id] for r in refs_using]))
        if len(refs) == 1:
            en, ta = _messages('missing_one', ref=refs[0].name, material=_names(resource),
                               qty=qty, unit=resource.unit)
        else:
            en, ta = _messages('missing', n=len(refs_using), m=len(refs), material=_names(resource),
                               qty=qty, unit=resource.unit)
        findings.append(Finding(
            kind='missing', message_en=en, message_ta=ta,
            resource_id=resource.pk, resource_name=resource.resource_name,
            suggested=qty,
            evidence=f'Used by {len(refs_using)} of {len(refs)} similar products: '
                     + ', '.join(r.name for r in refs_using[:4]),
        ))
    return findings


def companion_rules(lines, profiles, exclude=()):
    """
    Association rules mined from every BOM: "products with X almost
    always also have Y". Fires when X is in the list and Y is not.
    """
    present = _line_resources(lines)
    baskets = [set(p.bom) for p in profiles.values()]
    if len(baskets) < COMPANION_SUPPORT:
        return []

    item_count = Counter()
    pair_count = Counter()
    for basket in baskets:
        item_count.update(basket)
        for x in basket & present:
            for y in basket - present:
                pair_count[(x, y)] += 1

    best = {}
    for (x, y), both in pair_count.items():
        if y in exclude or both < COMPANION_SUPPORT:
            continue
        confidence = both / item_count[x]
        if confidence >= COMPANION_CONFIDENCE and confidence > best.get(y, (0,))[0]:
            best[y] = (confidence, x, both)

    chosen = sorted(best.items(), key=lambda kv: -kv[1][0])[:MAX_COMPANIONS]
    resources = _resources_by_id([y for y, _ in chosen] + [v[1] for _, v in chosen])
    findings = []
    for y, (confidence, x, both) in chosen:
        target, trigger = resources.get(y), resources.get(x)
        if target is None or trigger is None:
            continue
        qty = number(_median([p.bom[y] for p in profiles.values() if y in p.bom and x in p.bom]))
        en, ta = _messages('companion', trigger=_names(trigger), material=_names(target),
                           qty=qty, unit=target.unit)
        findings.append(Finding(
            kind='companion', message_en=en, message_ta=ta,
            resource_id=target.pk, resource_name=target.resource_name, suggested=qty,
            evidence=f'{both} of {item_count[x]} products with {trigger.resource_name} '
                     f'also use {target.resource_name}',
        ))
    return findings


def _unit_slip(ratio):
    for factor in UNIT_SLIPS:
        for r in (ratio, 1 / ratio if ratio else 0):
            if r and abs(r - factor) / factor <= 0.1:
                return True
    return False


def quantity_outliers(lines, refs):
    """Quantities far from what similar products use."""
    findings = []
    for line in lines:
        if line['type'] != 'bom':
            continue
        resource = line['resource']
        values = [r.bom[resource.pk] for r in refs if resource.pk in r.bom]
        if not values:
            continue
        typical = _median(values)
        qty = line['quantity']
        if typical <= 0 or (typical / QUANTITY_FACTOR <= qty <= typical * QUANTITY_FACTOR):
            continue
        key = 'quantity'
        en, ta = _messages(key, qty=number(qty), unit=resource.unit, material=_names(resource),
                           typical=number(typical))
        if _unit_slip(float(qty / typical)):
            en += MESSAGES['en']['unit_slip']
            ta += MESSAGES['ta']['unit_slip']
        findings.append(Finding(
            kind='quantity', message_en=en, message_ta=ta,
            resource_id=resource.pk, resource_name=resource.resource_name,
            suggested=number(typical), current=format(qty.normalize(), 'f'),
            evidence=f'Similar products: {", ".join(number(v) for v in values)} {resource.unit}',
        ))
    return findings


def _dim_text(value, unit):
    return f'{number(value)} {unit}'


def dimension_outliers(lines, refs):
    """Measurements far from the same part in similar products, or
    longer than any sheet / plank (usually inches typed as feet)."""
    by_part = defaultdict(list)
    for ref in refs:
        for d in ref.dims:
            by_part[d['part']].append(d)

    findings = []
    dim_lines = [line for line in lines if line['type'] == 'dimension']
    for index, line in enumerate(dim_lines):
        part = line['part_name']
        resource = line['resource']
        # Sheet materials (plywood / MDF) have no breadth — skip blank sizes.
        current = ' × '.join(_dim_text(line[d], line[f'{d}_unit']) for d in _DIM_NAMES if line[d]) + \
            f' × {line["pieces"]}'
        common = dict(kind='dimension', resource_id=resource.pk,
                      resource_name=resource.resource_name, part_name=part,
                      current=current, line_index=index)

        found = None
        for dim, names in _DIM_NAMES.items():
            if not line[dim]:
                continue
            inches = _inches(line[dim], line[f'{dim}_unit'])
            if inches is None:
                continue
            value = _dim_text(line[dim], line[f'{dim}_unit'])
            if inches > MAX_SANE_INCHES:
                en, ta = _messages('too_big', part=part, dim=names, value=value)
                found = Finding(message_en=en, message_ta=ta,
                                evidence=f'{dim} = {number(inches)} in', **common)
                break
            similar = [d[dim] for d in by_part.get(part.lower(), []) if d[dim]]
            if not similar:
                continue
            typical = _median(similar)
            if typical and not (typical / DIMENSION_FACTOR <= inches <= typical * DIMENSION_FACTOR):
                en, ta = _messages('dimension', part=part, dim=names, value=value,
                                   typical=f'{number(typical)} in')
                found = Finding(message_en=en, message_ta=ta,
                                evidence=f'{part} {dim} in similar products: '
                                         + ', '.join(f'{number(v)} in' for v in similar),
                                **common)
                break

        if found is None:
            pieces = [d['pieces'] for d in by_part.get(part.lower(), []) if d['pieces']]
            if pieces:
                typical = _median(pieces)
                if line['pieces'] > typical * DIMENSION_FACTOR:
                    en, ta = _messages('pieces', part=part, pieces=line['pieces'],
                                       typical=number(typical))
                    found = Finding(message_en=en, message_ta=ta, suggested=number(typical),
                                    evidence=f'{part} pieces in similar products: '
                                             + ', '.join(str(p) for p in pieces),
                                    **common)
        if found:
            findings.append(found)
    return findings


# ── Feedback loop ────────────────────────────────────────────────────

def suppressed_resources(product_name, resource_ids):
    """
    Resources whose "missing" question the carpenter dismissed and the
    admin agreed with (left out of the approved BOM) at least
    SUPPRESS_AFTER times on products with similar names. The reviewer
    stops asking about them.
    """
    from apps.carpenter.models import SubmissionFinding

    tokens = name_tokens(product_name)
    counts = Counter()
    rows = (
        SubmissionFinding.objects
        .filter(resource_id__in=resource_ids,
                kind__in=['missing', 'companion'],
                carpenter_response=SubmissionFinding.RESPONSE_DISMISSED,
                admin_outcome=SubmissionFinding.OUTCOME_REJECTED)
        .values_list('resource_id', 'submission__product__product_name',
                     'submission__new_product_name')
    )
    for resource_id, product, new_name in rows:
        if not tokens or tokens & name_tokens(product or new_name):
            counts[resource_id] += 1
    return {rid for rid, n in counts.items() if n >= SUPPRESS_AFTER}


def recent_corrections(limit=10):
    """Confirmed findings, for the LLM as worked examples."""
    from apps.carpenter.models import SubmissionFinding

    rows = (
        SubmissionFinding.objects
        .filter(admin_outcome=SubmissionFinding.OUTCOME_CONFIRMED)
        .select_related('submission__product')
        .order_by('-id')[:limit]
    )
    return [
        f'{(r.submission.product.product_name if r.submission.product else r.submission.new_product_name)}: '
        f'{r.message}'
        for r in rows
    ]


# ── Entry point ──────────────────────────────────────────────────────

def review(lines, product_name, product=None, based_on=None, use_ai=False):
    """
    Checks cleaned lines (clean_bom_line / clean_dimension_line output).
    Returns a list of Finding, statistics first, then AI extras.
    """
    profiles = product_profiles()
    refs = find_similar_products(product_name, lines, product=product,
                                 based_on=based_on, profiles=profiles)

    missing = missing_materials(lines, refs)
    findings = list(missing)
    findings += companion_rules(lines, profiles, exclude={f.resource_id for f in missing})
    findings += quantity_outliers(lines, refs)
    findings += dimension_outliers(lines, refs)

    candidates = [f.resource_id for f in findings if f.kind in ('missing', 'companion')]
    if candidates:
        hidden = suppressed_resources(product_name, candidates)
        findings = [f for f in findings
                    if not (f.kind in ('missing', 'companion') and f.resource_id in hidden)]

    if use_ai:
        from . import reviewer_llm
        seen = {f.key for f in findings}
        for extra in reviewer_llm.ai_findings(product_name, lines, refs, findings,
                                              recent_corrections()):
            if extra.key not in seen:
                seen.add(extra.key)
                findings.append(extra)

    return findings


def lines_from_submission(submission):
    """SubmissionLine rows → the cleaned-line dicts review() takes."""
    lines = []
    for line in submission.lines.select_related('resource').order_by('line_type', 'id'):
        if line.line_type == 'bom':
            lines.append({'type': 'bom', 'resource': line.resource, 'quantity': line.quantity})
        else:
            lines.append({
                'type': 'dimension', 'resource': line.resource, 'part_name': line.part_name,
                'width': line.width, 'breadth': line.breadth, 'height': line.height,
                'length': line.length, 'width_unit': line.width_unit,
                'breadth_unit': line.breadth_unit, 'height_unit': line.height_unit,
                'length_unit': line.length_unit, 'pieces': line.pieces,
            })
    return lines


def submission_product_name(submission):
    if submission.product:
        return submission.product.product_name
    return submission.new_product_name or (submission.based_on.product_name if submission.based_on else '')


def record_outcomes(submission, approved_lines):
    """
    After approval: label each finding with whether the approved BOM
    agreed with it. This is the feedback loop's training signal.
    """
    from apps.carpenter.models import SubmissionFinding

    approved_bom = {l['resource'].pk: l['quantity'] for l in approved_lines if l['type'] == 'bom'}
    approved_dims = {
        (l['resource'].pk, l['part_name'].lower()):
            ' × '.join(_dim_text(l[d], l[f'{d}_unit']) for d in _DIM_NAMES) + f' × {l["pieces"]}'
        for l in approved_lines if l['type'] == 'dimension'
    }
    present = set(approved_bom) | {rid for rid, _ in approved_dims}

    for finding in submission.findings.all():
        outcome = ''
        if finding.kind in (SubmissionFinding.KIND_MISSING, SubmissionFinding.KIND_COMPANION):
            if finding.resource_id:
                outcome = 'confirmed' if finding.resource_id in present else 'rejected'
        elif finding.kind == SubmissionFinding.KIND_QUANTITY:
            approved = approved_bom.get(finding.resource_id)
            if approved is not None and finding.current_value:
                try:
                    changed = approved != Decimal(finding.current_value)
                except InvalidOperation:
                    changed = False
                outcome = 'confirmed' if changed else 'rejected'
        elif finding.kind == SubmissionFinding.KIND_DIMENSION:
            approved = approved_dims.get((finding.resource_id, finding.part_name.lower()))
            if approved is not None and finding.current_value:
                outcome = 'confirmed' if approved != finding.current_value else 'rejected'
        if outcome != finding.admin_outcome:
            finding.admin_outcome = outcome
            finding.save(update_fields=['admin_outcome'])
