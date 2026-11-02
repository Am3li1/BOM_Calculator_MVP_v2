from decimal import Decimal

from django.test import TestCase

from apps.products.models import Product
from apps.resources.models import Resource
from apps.bom.models import WoodPart


class WoodPartCalculatedQuantityTests(TestCase):
    """
    Regression tests for the CFT (solid_wood) / SFT (sheet) formula
    split introduced when material_type was added to Resource.
    Locks in the exact numbers verified manually during development —
    if any of these change, the formula has regressed.
    """

    @classmethod
    def setUpTestData(cls):
        cls.product = Product.objects.create(
            product_code='TEST-01', product_name='Test Product'
        )
        cls.teak = Resource.objects.create(
            resource_name='Teak Wood', category='Carpentry Materials',
            material_type='solid_wood', unit='cft', rate=Decimal('1000'),
        )
        cls.ply = Resource.objects.create(
            resource_name='Plywood 6mm', category='Carpentry Materials',
            material_type='sheet', unit='sqft', rate=Decimal('80'),
        )
        cls.other = Resource.objects.create(
            resource_name='Fevicol', category='Miscellaneous',
            material_type='other', unit='kg', rate=Decimal('300'),
        )

    def test_solid_wood_cft_formula(self):
        # (2in * 2in * 8ft * 4pcs) / 144 = 0.888888...
        wp = WoodPart(
            product=self.product, resource=self.teak, part_name='Leg',
            width=2, width_unit='in',
            breadth=2, breadth_unit='in',
            length=8, length_unit='ft',
            pieces=4,
        )
        expected = (Decimal('2') * Decimal('2') * Decimal('8') * Decimal('4')) / Decimal('144')
        self.assertAlmostEqual(
            float(wp.calculated_quantity), float(expected), places=6
        )

    def test_solid_wood_unit_conversion_is_equivalent(self):
        # Same physical dimensions expressed in mm/cm must match the
        # inches/feet version exactly — proves conversion isn't a no-op.
        wp_in = WoodPart(
            product=self.product, resource=self.teak, part_name='Leg A',
            width=2, width_unit='in', breadth=2, breadth_unit='in',
            length=8, length_unit='ft', pieces=4,
        )
        wp_mm = WoodPart(
            product=self.product, resource=self.teak, part_name='Leg B',
            width=50.8, width_unit='mm',    # 50.8mm = 2in
            breadth=5.08, breadth_unit='cm', # 5.08cm = 2in
            length=8, length_unit='ft', pieces=4,
        )
        self.assertAlmostEqual(
            float(wp_in.calculated_quantity),
            float(wp_mm.calculated_quantity),
            places=6,
        )

    def test_sheet_sft_formula_uses_width_times_breadth(self):
        # 1.25ft * 1.25ft * 4pcs = 6.25 — matches the real spreadsheet
        # row this was validated against. No divisor for sheet goods.
        wp = WoodPart(
            product=self.product, resource=self.ply, part_name='Panel',
            width=1.25, width_unit='ft',
            breadth=1.25, breadth_unit='ft',
            length=99, length_unit='ft',   # deliberately absurd — must be ignored
            pieces=4,
        )
        self.assertAlmostEqual(float(wp.calculated_quantity), 6.25, places=6)

    def test_sheet_ignores_length_changes(self):
        # Changing Length must NOT change the result for sheet goods —
        # this is the exact bug (Width x Length) that was caught and fixed.
        base_kwargs = dict(
            product=self.product, resource=self.ply, part_name='Panel',
            width=4, width_unit='ft', breadth=8, breadth_unit='ft', pieces=1,
        )
        wp_a = WoodPart(length=1, length_unit='ft', **base_kwargs)
        wp_b = WoodPart(length=500, length_unit='ft', **base_kwargs)
        self.assertEqual(wp_a.calculated_quantity, wp_b.calculated_quantity)
        self.assertAlmostEqual(float(wp_a.calculated_quantity), 32.0, places=6)

    def test_other_material_type_uses_legacy_unit_naive_formula(self):
        # Unclassified resources keep the old raw-number/divisor formula
        # (no unit conversion) — deliberate, so reclassifying nothing
        # doesn't silently change existing costs.
        wp = WoodPart(
            product=self.product, resource=self.other, part_name='Misc',
            width=10, breadth=10, length=10, height=0, pieces=1,
            formula_type='standard',
        )
        expected = (Decimal('10') * Decimal('10') * Decimal('1') * Decimal('10') * Decimal('1')) / Decimal('144')
        self.assertAlmostEqual(
            float(wp.calculated_quantity), float(expected), places=6
        )


class WoodPartFormulaPrecedenceTests(TestCase):
    """
    Regression tests for WoodPart.formula_expression, the only
    custom-formula tier that exists (resource-level formula_expression
    was removed — see CLAUDE.md / migration 0008 in the resources app).
    Precedence is: WoodPart.formula_expression, if set, else the
    built-in material_type formula.
    """

    @classmethod
    def setUpTestData(cls):
        cls.product = Product.objects.create(
            product_code='TEST-WP', product_name='WoodPart Formula Product'
        )
        cls.plain_sheet = Resource.objects.create(
            resource_name='Plain Sheet', category='Carpentry Materials',
            material_type='sheet', unit='sqft', rate=Decimal('60'),
        )

    def test_woodpart_formula_overrides_material_type_default(self):
        # material_type='sheet' default (W x B) would ignore Length.
        # The custom formula uses Length instead, proving the override
        # takes priority: 4 * 8 * 1 / 4 = 8
        wp = WoodPart(
            product=self.product, resource=self.plain_sheet,
            part_name='Panel',
            width=4, width_unit='ft', breadth=999, breadth_unit='ft',
            length=8, length_unit='ft', pieces=1,
            formula_expression='width_ft * length_ft * pieces / 4',
        )
        self.assertAlmostEqual(float(wp.calculated_quantity), 8.0, places=6)
        self.assertEqual(wp.formula_source, 'woodpart_custom')

    def test_blank_woodpart_formula_falls_back_to_material_type_default(self):
        # No WoodPart-level formula set -> falls straight through to
        # the built-in sheet SFT formula (W x B, Length ignored).
        wp = WoodPart(
            product=self.product, resource=self.plain_sheet,
            part_name='Panel',
            width=4, width_unit='ft', breadth=8, breadth_unit='ft',
            length=999, length_unit='ft', pieces=1,
        )
        self.assertAlmostEqual(float(wp.calculated_quantity), 32.0, places=6)
        self.assertEqual(wp.formula_source, 'material_type_default')

    def test_bad_woodpart_formula_raises_loudly(self):
        from apps.core.safe_eval import FormulaError

        wp = WoodPart(
            product=self.product, resource=self.plain_sheet,
            part_name='Panel',
            width=1, width_unit='ft', breadth=1, breadth_unit='ft',
            length=1, length_unit='ft', pieces=1,
            formula_expression='width_ft * nonsense_variable',
        )
        with self.assertRaises(FormulaError):
            wp.calculated_quantity

    def test_no_divisor_variable_available(self):
        # 'divisor' was removed as a formula variable entirely —
        # referencing it must raise, not silently resolve to 144.
        from apps.core.safe_eval import FormulaError

        wp = WoodPart(
            product=self.product, resource=self.plain_sheet,
            part_name='Panel',
            width=1, width_unit='ft', breadth=1, breadth_unit='ft',
            length=1, length_unit='ft', pieces=1,
            formula_expression='width_ft * breadth_ft * pieces / divisor',
        )
        with self.assertRaises(FormulaError):
            wp.calculated_quantity


# ════════════════════════════════════════════════════════════════════
# Voice assistant (apps/bom/assistant.py) — the OpenAI-compatible
# client is always mocked; these tests never call a real provider.
# ════════════════════════════════════════════════════════════════════

import json
from unittest import mock

import openai
from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse
from openai.types.chat import ChatCompletion

from apps.bom import assistant
from apps.bom.models import BOMItem


def _completion(message, finish_reason='stop'):
    return ChatCompletion.model_validate({
        'id': 'chatcmpl-test', 'object': 'chat.completion', 'created': 0, 'model': 'gemini-2.5-flash',
        'choices': [{'index': 0, 'finish_reason': finish_reason, 'message': {'role': 'assistant', **message}}],
    })


def _tool_call(name, args, call_id='call_1', raw_arguments=None):
    return _completion({
        'content': None,
        'tool_calls': [{
            'id': call_id, 'type': 'function',
            'function': {'name': name, 'arguments': raw_arguments if raw_arguments is not None else json.dumps(args)},
            # Gemini's thought signature — must survive the round trip.
            'extra_content': {'google': {'thought_signature': 'sig'}},
        }],
    }, finish_reason='tool_calls')


def _text(text):
    return _completion({'content': text})


def _fake_client(*responses):
    client = mock.Mock()
    client.chat.completions.create.side_effect = list(responses)
    return client


def _rate_limit_error():
    response = mock.Mock(status_code=429, headers={}, request=mock.Mock())
    return openai.RateLimitError('Resource has been exhausted', response=response, body=None)


@override_settings(BOM_ASSISTANT_API_KEY='test-key', BOM_ASSISTANT_MODEL='gemini-2.5-flash')
class AssistantTurnTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.product = Product.objects.create(product_code='TABLE-01', product_name='Coffee Table')
        cls.teak = Resource.objects.create(
            resource_name='Teak Wood', name_ta='தேக்கு', category='Carpentry Materials',
            material_type='solid_wood', unit='cft', rate=Decimal('1000'),
        )
        cls.hinge = Resource.objects.create(
            resource_name='Hinge', category='Hardware', unit='nos', rate=Decimal('50'),
        )

    def test_tool_loop_stages_a_row_and_returns_reply(self):
        client = _fake_client(
            _tool_call('search_resources', {'query': 'hinges'}, 'call_1'),
            _tool_call('stage_material', {'resource_id': self.hinge.pk, 'quantity': 8}, 'call_2'),
            _text('Added 8 hinges.'),
        )
        state = assistant.new_state()
        with mock.patch.object(assistant, '_client', return_value=client):
            reply = assistant.run_turn(self.product, state, 'eight hinges')

        self.assertEqual(reply, 'Added 8 hinges.')
        self.assertEqual(state['draft'][0]['resource_id'], self.hinge.pk)
        self.assertEqual(state['draft'][0]['quantity'], '8')
        # user, assistant(tool call), tool, assistant(tool call), tool, assistant(text)
        self.assertEqual([m['role'] for m in state['messages']],
                         ['user', 'assistant', 'tool', 'assistant', 'tool', 'assistant'])
        self.assertEqual(state['messages'][2]['tool_call_id'], 'call_1')
        # Provider extras on tool calls are passed back unchanged.
        self.assertEqual(state['messages'][1]['tool_calls'][0]['extra_content'],
                         {'google': {'thought_signature': 'sig'}})
        # The assistant never writes to the BOM itself.
        self.assertFalse(BOMItem.objects.exists())

        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs['model'], 'gemini-2.5-flash')
        self.assertEqual(kwargs['messages'][0]['role'], 'system')
        self.assertEqual(kwargs['tools'][0]['type'], 'function')
        # Search results reach the model without rates.
        self.assertNotIn('rate', state['messages'][2]['content'])

    def test_tool_calls_with_stop_finish_reason_still_run(self):
        # Some providers report "stop" even when they return tool calls.
        call = _tool_call('stage_material', {'resource_id': self.hinge.pk, 'quantity': 2})
        call.choices[0].finish_reason = 'stop'
        state = assistant.new_state()
        with mock.patch.object(assistant, '_client', return_value=_fake_client(call, _text('Done.'))):
            assistant.run_turn(self.product, state, 'two hinges')
        self.assertEqual(len(state['draft']), 1)

    def test_malformed_tool_arguments_go_back_to_the_model(self):
        client = _fake_client(
            _tool_call('stage_material', None, 'call_1', raw_arguments='{"resource_id": 5, "quantity": '),
            _tool_call('stage_material', {'resource_id': self.hinge.pk, 'quantity': 'eight'}, 'call_2'),
            _tool_call('stage_material', {'quantity': 3}, 'call_3'),
            _tool_call('stage_material', ['not', 'an', 'object'], 'call_4'),
            _tool_call('drop_table', {}, 'call_5'),
            _text('Which material did you mean?'),
        )
        state = assistant.new_state()
        with mock.patch.object(assistant, '_client', return_value=client), \
                mock.patch.object(assistant, 'MAX_TOOL_ROUNDS', 10):
            reply = assistant.run_turn(self.product, state, 'eight hinges')

        self.assertEqual(reply, 'Which material did you mean?')
        self.assertEqual(state['draft'], [])
        errors = [json.loads(m['content'])['error'] for m in state['messages'] if m['role'] == 'tool']
        self.assertEqual(len(errors), 5)
        self.assertIn('not valid JSON', errors[0])
        self.assertIn('quantity must be a number', errors[1])
        self.assertIn('resource_id is required', errors[2])
        self.assertIn('must be a JSON object', errors[3])
        self.assertIn('Unknown tool', errors[4])

    def test_string_numbers_are_accepted(self):
        args, error = assistant.parse_arguments(
            'stage_dimension',
            json.dumps({'resource_id': str(self.teak.pk), 'part_name': 'Leg', 'width': '2',
                        'width_unit': 'IN', 'breadth': 2, 'breadth_unit': 'in', 'length': '2.5',
                        'length_unit': 'ft', 'pieces': '4.0'}),
        )
        self.assertIsNone(error)
        self.assertEqual(args['resource_id'], self.teak.pk)
        self.assertEqual(args['pieces'], 4)
        self.assertEqual(args['width_unit'], 'in')

        _, error = assistant.parse_arguments('remove_staged_row', '{"row_number": 0}')
        self.assertIn('at least 1', error)
        _, error = assistant.parse_arguments('stage_dimension', json.dumps({
            'resource_id': self.teak.pk, 'part_name': 'Leg', 'width': 2, 'width_unit': 'yards',
            'breadth': 2, 'breadth_unit': 'in', 'length': 2, 'length_unit': 'ft', 'pieces': 1,
        }))
        self.assertIn('width_unit must be one of', error)

    def test_search_falls_back_to_individual_words(self):
        # Speech adds extra words; the whole phrase matches nothing, so
        # per-word matching has to find "Hinge".
        result, is_error = assistant.execute_tool(
            'search_resources', {'query': 'steel hinge pieces'}, self.product, assistant.new_state()
        )
        self.assertFalse(is_error)
        self.assertEqual(result['matches'][0]['id'], self.hinge.pk)
        self.assertNotIn('rate', result['matches'][0])

    def test_search_matches_tamil_name(self):
        result, _ = assistant.execute_tool(
            'search_resources', {'query': 'தேக்கு'}, self.product, assistant.new_state()
        )
        self.assertEqual(result['matches'][0]['id'], self.teak.pk)

    def test_invalid_stage_is_reported_to_the_model(self):
        state = assistant.new_state()
        result, is_error = assistant.execute_tool(
            'stage_material', {'resource_id': 99999, 'quantity': 2}, self.product, state
        )
        self.assertTrue(is_error)
        self.assertEqual(state['draft'], [])

    def test_same_material_cannot_be_staged_twice(self):
        state = assistant.new_state()
        args = {'resource_id': self.hinge.pk, 'quantity': 2}
        assistant.execute_tool('stage_material', args, self.product, state)
        _, is_error = assistant.execute_tool('stage_material', args, self.product, state)
        self.assertTrue(is_error)
        self.assertEqual(len(state['draft']), 1)

    def test_stage_dimension_and_remove(self):
        state = assistant.new_state()
        _, is_error = assistant.execute_tool('stage_dimension', {
            'resource_id': self.teak.pk, 'part_name': 'Leg', 'width': 2, 'width_unit': 'in',
            'breadth': 2, 'breadth_unit': 'in', 'length': 2.5, 'length_unit': 'ft', 'pieces': 4,
        }, self.product, state)
        self.assertFalse(is_error)
        self.assertEqual(state['draft'][0]['part_name'], 'Leg')

        _, is_error = assistant.execute_tool('remove_staged_row', {'row_number': 1}, self.product, state)
        self.assertFalse(is_error)
        self.assertEqual(state['draft'], [])

    def test_content_filter_rolls_back_the_turn(self):
        blocked = _completion({'content': None}, finish_reason='content_filter')
        state = assistant.new_state()
        with mock.patch.object(assistant, '_client', return_value=_fake_client(blocked)):
            with self.assertRaises(assistant.AssistantError):
                assistant.run_turn(self.product, state, 'something odd')
        self.assertEqual(state['messages'], [])

    def test_rate_limit_gives_busy_message_and_keeps_earlier_turns(self):
        state = assistant.new_state()
        with mock.patch.object(assistant, '_client', return_value=_fake_client(_text('Hi.'))):
            assistant.run_turn(self.product, state, 'hello')
        before = list(state['messages'])

        with mock.patch.object(assistant, '_client', return_value=_fake_client(_rate_limit_error())):
            with self.assertRaisesMessage(assistant.AssistantError, assistant.BUSY_MESSAGE):
                assistant.run_turn(self.product, state, 'eight hinges')
        self.assertEqual(state['messages'], before)

    def test_network_error_gives_busy_message(self):
        failing = mock.Mock()
        failing.chat.completions.create.side_effect = openai.APIConnectionError(request=mock.Mock())
        state = assistant.new_state()
        with mock.patch.object(assistant, '_client', return_value=failing):
            with self.assertRaisesMessage(assistant.AssistantError, assistant.BUSY_MESSAGE):
                assistant.run_turn(self.product, state, 'eight hinges')
        self.assertEqual(state['messages'], [])

    def test_running_out_of_tool_rounds_rolls_back(self):
        calls = [_tool_call('get_draft', {}, f'call_{i}') for i in range(assistant.MAX_TOOL_ROUNDS)]
        state = assistant.new_state()
        with mock.patch.object(assistant, '_client', return_value=_fake_client(*calls)):
            with self.assertRaises(assistant.AssistantError):
                assistant.run_turn(self.product, state, 'loop forever')
        self.assertEqual(state['messages'], [])

    def test_empty_reply_is_stored_as_okay(self):
        state = assistant.new_state()
        with mock.patch.object(assistant, '_client', return_value=_fake_client(_text(''))):
            reply = assistant.run_turn(self.product, state, 'hello')
        self.assertEqual(reply, 'Okay.')
        self.assertEqual(state['messages'][-1]['content'], 'Okay.')

    def test_old_session_format_keeps_draft_and_restarts_conversation(self):
        old = {'messages': [{'role': 'assistant', 'content': [{'type': 'text', 'text': 'Hi'}]}],
               'draft': [{'type': 'bom'}]}
        state = assistant.load_state(old)
        self.assertEqual(state['messages'], [])
        self.assertEqual(state['draft'], [{'type': 'bom'}])
        self.assertEqual(state['format'], assistant.STATE_FORMAT)


@override_settings(BOM_ASSISTANT_API_KEY='test-key')
class AssistantViewTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.product = Product.objects.create(product_code='TABLE-01', product_name='Coffee Table')
        cls.hinge = Resource.objects.create(
            resource_name='Hinge', category='Hardware', unit='nos', rate=Decimal('50'),
        )

    def setUp(self):
        admin = User.objects.create_user(username='admin1', password='x', is_staff=True)
        self.client.force_login(admin, backend='django.contrib.auth.backends.ModelBackend')

    def _turn(self, text, *responses):
        with mock.patch.object(assistant, '_client', return_value=_fake_client(*responses)):
            return self.client.post(
                reverse('bom:assistant_turn', args=[self.product.pk]),
                data={'text': text}, content_type='application/json',
            )

    def _stage_hinges(self):
        return self._turn(
            'eight hinges',
            _tool_call('stage_material', {'resource_id': self.hinge.pk, 'quantity': 8}),
            _text('Added 8 hinges.'),
        )

    def test_turn_returns_reply_and_draft(self):
        data = self._stage_hinges().json()
        self.assertEqual(data['reply'], 'Added 8 hinges.')
        self.assertEqual(len(data['draft']), 1)

        page = self.client.get(reverse('bom:list', args=[self.product.pk]))
        self.assertEqual(page.context['assistant_initial']['log'],
                         [{'role': 'user', 'text': 'eight hinges'},
                          {'role': 'assistant', 'text': 'Added 8 hinges.'}])

    def test_voice_is_english_only(self):
        page = self.client.get(reverse('bom:list', args=[self.product.pk]))
        self.assertContains(page, "recognition.lang = 'en-IN'")
        self.assertNotContains(page, 'ta-IN')

    def test_rate_limit_shows_busy_message_not_500(self):
        self._stage_hinges()
        response = self._turn('two more', _rate_limit_error())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['reply'], assistant.BUSY_MESSAGE)
        self.assertEqual(len(data['draft']), 1)   # draft survives the failed turn

    def test_commit_writes_draft_and_clears_it(self):
        BOMItem.objects.create(product=self.product, resource=self.hinge, quantity=Decimal('2'))
        self._stage_hinges()
        self.client.post(reverse('bom:assistant_commit', args=[self.product.pk]))
        self.assertEqual(BOMItem.objects.get().quantity, Decimal('8'))   # upserted, not duplicated
        self.assertNotIn(str(self.product.pk), self.client.session.get('bom_assistant', {}))

    def test_commit_with_stale_row_writes_nothing(self):
        self._stage_hinges()
        Resource.objects.filter(pk=self.hinge.pk).update(active=False)
        self.client.post(reverse('bom:assistant_commit', args=[self.product.pk]))
        self.assertFalse(BOMItem.objects.exists())

    def test_remove_row_and_reset(self):
        self._stage_hinges()
        data = self.client.post(
            reverse('bom:assistant_remove_row', args=[self.product.pk]),
            data={'index': 0}, content_type='application/json',
        ).json()
        self.assertEqual(data['draft'], [])
        self.client.post(reverse('bom:assistant_reset', args=[self.product.pk]))
        self.assertNotIn(str(self.product.pk), self.client.session.get('bom_assistant', {}))

    def test_empty_text_is_rejected(self):
        response = self.client.post(
            reverse('bom:assistant_turn', args=[self.product.pk]),
            data={'text': '  '}, content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(BOM_ASSISTANT_API_KEY='')
    def test_hidden_when_api_key_unset(self):
        page = self.client.get(reverse('bom:list', args=[self.product.pk]))
        self.assertNotContains(page, 'Voice Assistant')
        self.assertNotContains(page, 'assistant-panel')
        response = self.client.post(
            reverse('bom:assistant_turn', args=[self.product.pk]),
            data={'text': 'hi'}, content_type='application/json',
        )
        self.assertEqual(response.status_code, 503)
