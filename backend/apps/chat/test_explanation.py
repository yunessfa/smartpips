from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase, SimpleTestCase
from django.core import signing
from rest_framework.test import APIClient
from apps.ai.models import AIProvider
from .scalp import engine_explanation


DECISION = {
    'signal':'wait','score':72,'reason':'Active strategy veto','data_quality':'candles',
    'support':59950,'resistance':60550,'entry':60200,'stop_loss':59000,'take_profit':63000,
    'strategy_name':'Fixture strategy','strategy_version':2,
    'indicators':{'EMA9':60120,'RSI':47,'VWAP':60110,'KeyLevels':{'PDH':60600},
                  'OrderFlow':{'delta':-2}},
    'strategy_evaluation':{'checks':[{'block':'rsi','label':'RSI','actual':47,
                                    'operator':'gte','value':50,'passed':False,'required':True}]},
    'session':{'name':'London'},'risk_settings_not_executed':['trailing_stop'],
}


class EngineExplanationTests(SimpleTestCase):
    def test_short_decision_first_text_without_indicator_dump(self):
        summary, text = engine_explanation('BTCUSDT','5m',DECISION)
        for fact in ('59,950','60,550','Fixture strategy','RSI'):
            self.assertIn(fact,text)
        # no indicator dump, no stale entry on a WAIT
        for noise in ('EMA9','MACD_hist','Stochastic','FVG_quality','60,120'):
            self.assertNotIn(noise,text)
        self.assertNotIn('ورود 60,200',text)
        self.assertIn('امتیاز، درصد برد نیست',text)
        self.assertIn('انتظار',summary)
        self.assertLessEqual(len(text.splitlines()), 10)

    def test_no_data_still_has_a_truthful_explanation(self):
        _,text=engine_explanation('BTCUSDT','5m',{'signal':'wait','data_quality':'none','score':0})
        self.assertIn('ناموجود',text)
        self.assertIn('دستور ورود نیستند',text)
        self.assertIn('سیگنال معتبر نیست',text)

    def test_brief_lines_and_active_limit(self):
        d={'signal':'buy','signal_source':'playbook','entry':100.5,'stop_loss':99,'take_profit':105,
           'risk_reward':3,'entry_plan':{'type':'limit','valid_for_bars':12},
           'brief':{'timeframe':'1h','facts':[{'key':'h4_trend','value':1,'state':'ok'},
                    {'key':'volatility','value':0.8,'need':0.4,'state':'ok'}],
                    'next':{'code':'limit_active','price':100.5,'valid_bars':12}}}
        summary,text=engine_explanation('BTCUSDT:PERP','1h',d)
        self.assertIn('لیمیت',summary)
        self.assertIn('✓ روند ۴ساعته: صعودی',text)
        self.assertIn('پلی‌بوک',text)
        self.assertIn('تارگت 105',text)


class ExplanationAPITests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user('explain')
        self.client=APIClient(); self.client.force_authenticate(self.user)

    def signal(self, **extra):
        data={'symbol':'BTCUSDT','timeframe':'5m','price':60200,'explain':False,
              'prepare_explanation':True, **extra}
        with patch('apps.strategy.decision.decide',return_value=dict(DECISION)):
            return self.client.post('/api/chat/scalp/',data,format='json')

    def test_fast_poll_quick_and_manual_always_include_engine_explanation(self):
        for data in ({'explain':False},{'explain':True},{'prepare_explanation':False}):
            r=self.signal(**data)
            self.assertEqual(r.status_code,200)
            self.assertTrue(r.data['explanation']); self.assertTrue(r.data['summary'])
            self.assertEqual(r.data['explanation_source'],'engine')

    def test_ai_timeout_or_empty_does_not_replace_engine_facts(self):
        AIProvider.objects.create(label='fixture',is_active=True)
        for raw in ('', '{"summary":"Summary only"}'):
            with patch('apps.chat.views.chat_completion',return_value=raw):
                r=self.signal(explain=True)
            self.assertTrue(r.data['explanation']); self.assertIn('59,950',r.data['explanation'])
            self.assertEqual(r.data['ai_explanation_status'],'empty')
        with patch('apps.chat.views.chat_completion',side_effect=RuntimeError('fixture')):
            with self.assertLogs('apps.chat.views',level='ERROR'):
                r=self.signal(explain=True)
        self.assertEqual(r.status_code,200); self.assertIn('59,950',r.data['explanation'])

    def test_explain_endpoint_uses_signed_same_decision_without_recomputing(self):
        AIProvider.objects.create(label='fixture',is_active=True)
        r=self.signal(); token=r.data['explanation_token']
        with patch('apps.strategy.decision.decide',side_effect=AssertionError('must not recalculate')), \
             patch('apps.chat.views.chat_completion',return_value='{"summary":"خلاصه","explanation":"توضیح تکمیلی همان تصمیم"}') as ai:
            explained=self.client.post('/api/chat/scalp/explain/',{'explanation_token':token},format='json')
        self.assertEqual(explained.status_code,200)
        self.assertEqual(explained.data['decision_id'],r.data['decision_id'])
        self.assertEqual(ai.call_args.kwargs['timeout'],20)
        for field in ('entry','stop_loss','take_profit','signal','explanation'):
            self.assertNotIn(field,explained.data)

    def test_snapshot_cannot_be_tampered_or_read_by_other_user(self):
        token=self.signal().data['explanation_token']
        self.assertEqual(self.client.post('/api/chat/scalp/explain/',{'explanation_token':token+'bad'}).status_code,400)
        self.client.force_authenticate(User.objects.create_user('other-explain'))
        self.assertEqual(self.client.post('/api/chat/scalp/explain/',{'explanation_token':token}).status_code,403)

    def test_expired_snapshot_is_rejected_without_engine_or_ai_call(self):
        token=signing.dumps({'user_id':self.user.pk,'decision':DECISION},salt='smartpips.scalp.explanation')
        with patch('django.core.signing.time.time',return_value=9999999999):
            self.assertEqual(self.client.post('/api/chat/scalp/explain/',{'explanation_token':token}).status_code,400)
