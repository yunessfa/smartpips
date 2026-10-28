import {chromium} from '/vercel/sandbox/node_modules/playwright/index.mjs';
import fs from 'node:fs';
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH || '/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const context=await browser.newContext({viewport:{width:1440,height:1100},timezoneId:'Asia/Tehran',reducedMotion:'reduce'});
await context.addInitScript(()=>{localStorage.setItem('smartpips_token','local-ui-fixture');localStorage.setItem('smartpips_user','Local test');localStorage.setItem('lang','fa');localStorage.setItem('sp_auto','0');localStorage.setItem('bx_mode','demo');localStorage.setItem('sp_balance','1000');});
const errors=[];let errorMode=false;let emptyMode=false;let orderCount=0;let block=false;let lastOrder=null;
const now=Math.floor(Date.now()/1000);
const candles=Array.from({length:180},(_,i)=>{const close=60000+Math.sin(i/11)*220+i*2;return {time:now-(180-i)*300,open:close-30,close,high:close+60,low:close-70,volume:100+i};});
const trades=Array.from({length:5000},(_,i)=>({id:i+1,symbol:['BTCUSDT','ETHUSDT','SOLUSDT'][i%3],source:'bitunix_demo',direction:i%2?'short':'long',entry_price:60000,exit_price:60020,size:10,leverage:5,pnl:i%2?-5:6,status:'closed',opened_at:new Date((now-i*900)*1000).toISOString(),closed_at:new Date((now-i*900+600)*1000).toISOString(),entry_snapshot:{},entry_snapshot_hash:''}));
const strategy={id:1,name:'Volume Profile Breakout',market:'crypto',direction:'both',description:'Local UI fixture — not a validated trading result',is_preset:false,is_active:true,timeframes:['1m','5m'],symbols:['BTCUSDT'],current:{version:1,rules:[],min_confidence:70,risk:{max_leverage:10}}};
await context.route('**/*',async route=>{
 const u=new URL(route.request().url());if(!['127.0.0.1','localhost'].includes(u.hostname))return route.abort();
 if(!u.pathname.startsWith('/api/'))return route.continue();
 const p=u.pathname;let data={};
 if(errorMode&&p.endsWith('/trades/analytics/'))return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Local test: analytics temporarily unavailable'})});
 if(p.endsWith('/auth/me/'))data={username:'Local test',is_admin:false};
 else if(p.endsWith('/prefs/risk_limits/'))data={max_leverage:20,max_position_usdt:500,max_open_positions:5,today_loss:0};
 else if(p.endsWith('/market_access/'))data={metals:true,spot:true,futures:true};
 else if(p.endsWith('/assets/quotes/'))data=emptyMode?[]:[{symbol:'BTCUSDT',name:'Bitcoin',price:.9857,change_percent:1.2,tradingview_symbol:'BINANCE:BTCUSDT',source:'Local UI fixture'},{symbol:'ETHUSDT',name:'Ethereum',price:2500,change_percent:-.4,tradingview_symbol:'BINANCE:ETHUSDT',source:'Local UI fixture'}];
 else if(p.endsWith('/market/metal/')||p.endsWith('/ticker/'))data={ok:true,price:.9857};
 else if(p.endsWith('/market/candles/'))data={candles,source:'Local test fixture — not live data'};
 else if(p.endsWith('/market/calendar/'))data={status:'ok',events:[],fetched_at:new Date().toISOString()};
 else if(p.endsWith('/chat/scalp/')){const body=route.request().postDataJSON();data={symbol:body.symbol,timeframe:body.timeframe,signal:'sell',score:72,confidence:'medium',data_quality:'candles',decision_id:'fixture-decision',explanation:'توضیح موتور برای تست رابط: این داده آزمایشی است و توصیه معاملاتی نیست.',summary:'نمونهٔ تست رابط؛ دادهٔ واقعی بازار نیست.',entry:.9857,stop_loss:.993888,take_profit:.962336,order_ticket:{quantity:3804.403,leverage:75,unit:'SUI',order_type:'market'},support:59950,resistance:60550,volume_profile:{poc:60100,val:59800,vah:60400},indicators:{KeyLevels:{PDH:60600,PDL:59600}},strategy_name:'Volume Profile • local test',strategy_version:1,generated_at:Date.now(),price_at_signal:60200};}
 else if(p.endsWith('/order/')){orderCount++;lastOrder=route.request().postDataJSON();if(block)return route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({error:'demo_available_margin; demo_daily_loss_cap',code:'demo_risk_blocked'})});data={mode:'demo',entryPrice:.9857,warnings:[{code:'leverage_above_recommended',leverage:75,recommended_max:10},{code:'demo_trade_risk_cap',estimated_risk_usdt:35.67,recommended_max_pct:.5},{code:'demo_total_stop_risk_cap',estimated_risk_usdt:35.67,recommended_max_pct:1.5}]};}
 else if(p.endsWith('/positions/'))data={positions:[],history:[],marginUsed:0};
 else if(p.endsWith('/bitunix/status/'))data={connected:false,configured:false,diagnostics:{}};
 else if(p.endsWith('/bitunix/account/'))data={account:{available:1000}};
 else if(p.endsWith('/trades/analytics/'))data={overall:{trades:emptyMode?0:199,total_reported_pnl:2464.2751,profit_factor:2.2783,expectancy_pnl:12.3833,max_drawdown_reported_pnl:487.2394,average_R:null,realized_R:{sample:0},verified_net_pnl:null}};
 else if(p.endsWith('/trades/stats/'))data={open:0,closed:emptyMode?0:5000,total_pnl:emptyMode?0:2500,win_rate:emptyMode?0:50};
 else if(p.endsWith('/trades/profile/'))data={total_trades:0};
 else if(p.endsWith('/trades/journal/'))data={enough:false,trades:0,min_trades:5};
 else if(p.endsWith('/trades/'))data=emptyMode?[]:trades;
 else if(p.endsWith('/exit_advice/'))data={advice:[]};
 else if(p.endsWith('/backtest/'))data={trades:0,symbol:'BTCUSDT',timeframe:'1m',candles_used:499,wins:0,losses:0,total_r:0,note:'No qualifying setups (fixture)',diagnostics:{bars_evaluated:438,base_engine_wait:438,strategy_veto:0,base_wait_reasons:{low_score:{count:438,example:'Fixture low score'}},strategy_veto_reasons:{}}};
 else if(p.endsWith('/strategy/strategies/'))data=emptyMode?[]:[strategy];
 else if(p.endsWith('/strategy/strategies/analytics/'))data=null;
 else if(p.endsWith('/strategy/vocabulary/'))data={blocks:[],operators:[]};
 else if(p.includes('/strategy/'))data=[];
 else if(p.endsWith('/watchlist/'))data=[];
 else if(p.endsWith('/depth/'))data={bids:[],asks:[]};
 else if(p.endsWith('/unread-count/'))data={unread:0};
 else if(p.endsWith('/notifications/'))data=[];
 return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});
});

const page=await context.newPage(); page.on('pageerror',e=>errors.push(e.message));
const checks=[];
for(const width of [390,1440]){
 await page.setViewportSize({width,height:width===390?844:1100});
 async function open(){
  await page.goto('http://127.0.0.1:5174/app/scalp?symbol=SUIUSDT&tf=1m');
  await page.getByRole('button',{name:'گرفتن سیگنال هوش مصنوعی',exact:true}).click();
  await page.getByRole('button',{name:'فروش شورت',exact:true}).click();
  await page.getByRole('button',{name:'دمو',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'تأیید سفارش'});await dialog.waitFor();
  await dialog.locator('input[min="1"][step="1"]').fill('75');
  await dialog.getByPlaceholder('مارجینی که درگیر می‌کنی (USDT)').fill('50');
  return dialog;
 }
 block=false;let dialog=await open();
 const submit=dialog.getByRole('button',{name:'ثبت سفارش دمو — فروش شورت',exact:true});
 if(!await submit.isEnabled())throw Error('Advisory blocked submit');
 await submit.scrollIntoViewIfNeeded();
 if(!await dialog.getByText(/زیان تخمینی تا استاپ/).isVisible())throw Error('Missing stop risk estimate');
 await page.screenshot({path:`qa/demo-risk/confirm-${width}.png`});
 await submit.click();await dialog.waitFor({state:'hidden'});
 await page.getByRole('status').getByText(/مجموع ریسک باز دمو/).waitFor();
 const status=await page.getByRole('status').innerText();
 if(status.includes('demo_trade_risk_cap')||!status.includes('مانع سفارش نیست'))throw Error('Untranslated warning');
 if(lastOrder.leverage!==75||Math.abs(lastOrder.qty-3804.403)>.002)throw Error('Screenshot sizing changed');
 await page.getByRole('status').scrollIntoViewIfNeeded();
 await page.screenshot({path:`qa/demo-risk/success-${width}.png`});
 block=true;dialog=await open();await dialog.getByRole('button',{name:'ثبت سفارش دمو — فروش شورت',exact:true}).click();
 await dialog.getByText(/موجودی آزاد دمو برای مارجین/).waitFor();
 await dialog.getByText(/موجودی آزاد دمو برای مارجین/).scrollIntoViewIfNeeded();
 await page.screenshot({path:`qa/demo-risk/blocked-${width}.png`});
 if((await dialog.innerText()).includes('demo_available_margin'))throw Error('Raw hard error code');
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Horizontal overflow');
 checks.push({width,margin:50,leverage:75,qty:lastOrder.qty,advisorySubmit:true,successWarningsReadable:true,hardErrorsReadable:true,horizontalOverflow:false});
}
if(errors.length)throw Error(errors.join('\n'));
fs.writeFileSync('qa/demo-risk/results.json',JSON.stringify({fixtureOnly:true,nonLocalNetworkBlocked:true,simulatedOrders:orderCount,errors,checks},null,2));
await browser.close();console.log('BROWSER_DEMO_RISK_PASS');
