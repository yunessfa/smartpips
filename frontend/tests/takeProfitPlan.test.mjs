import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createRequire} from 'node:module';
import {takeProfitPlan,analysisTargetLevels,exitSlices,chartPriceFormat} from '../src/lib/takeProfitPlan.js';
const require=createRequire(import.meta.url), parser=require('@babel/parser');
const long={entry:100,signal:'buy',take_profit:102,tp_levels:[{price:101,pct:40},{price:102,pct:35},{price:103.2,pct:25}]};
test('long and short engine levels remain unchanged',()=>{
 assert.deepEqual(takeProfitPlan(long).map(l=>l.price),[101,102,103.2]);
 assert.deepEqual(takeProfitPlan({...long,signal:'sell',tp_levels:long.tp_levels.map(l=>({...l,price:200-l.price}))}).map(l=>l.price),[99,98,96.8]);
});
test('slices use ORIGINAL position quantity and percentages total100',()=>{
 const slices=exitSlices(takeProfitPlan(long),10);assert.deepEqual(slices.map(l=>l.quantity),[4,3.5,2.5]);
 assert.equal(slices.reduce((s,l)=>s+l.quantity,0),10);
});
test('missing ladder does not fabricate closer targets',()=>{
 assert.deepEqual(takeProfitPlan({...long,tp_levels:null}),[]);
 assert.deepEqual(analysisTargetLevels({...long,tp_levels:null}),[['Signal TP',102,'#72bc8f']]);
});
test('invalid duplicate opposite-side or nonfinite levels rejected',()=>{
 for(const levels of [[],[{price:101,pct:40},{price:101,pct:60}],[{price:99,pct:40},{price:102,pct:60}],[{price:101,pct:20},{price:102,pct:20}],[{price:Infinity,pct:40},{price:102,pct:60}]]) assert.deepEqual(takeProfitPlan({...long,tp_levels:levels}),[]);
});
test('wait signal never plots executable targets',()=>{assert.deepEqual(analysisTargetLevels({...long,signal:'wait'}),[]);});
test('journal shape supported without changing levels',()=>{assert.equal(takeProfitPlan({entry_price:100,direction:'long',tp_levels:long.tp_levels}).length,3);});
test('chart plots TP1 TP2 TP3 with original percentage labels',()=>{assert.deepEqual(analysisTargetLevels(long).map(l=>l[0]),['TP1 · 40%','TP2 · 35%','TP3 · 25%']);});
test('no raw unicode escape text in JSX children or static attributes',()=>{
 const issues=[];
 function walk(node,file){if(!node||typeof node!=='object')return;
  if(node.type==='JSXText'&&/\\[uU][0-9a-fA-F]{4}/.test(node.value))issues.push(file);
  if(node.type==='JSXAttribute'&&node.value?.type==='StringLiteral'&&/\\[uU][0-9a-fA-F]{4}/.test(node.value.value))issues.push(file);
  for(const[k,v]of Object.entries(node))if(k!=='loc'&&k!=='extra'){if(Array.isArray(v))v.forEach(n=>walk(n,file));else if(v&&typeof v==='object')walk(v,file);}
 }
 function scan(dir){for(const ent of fs.readdirSync(dir,{withFileTypes:true})){const p=`${dir}/${ent.name}`;if(ent.isDirectory())scan(p);else if(p.endsWith('.jsx'))walk(parser.parse(fs.readFileSync(p,'utf8'),{sourceType:'module',plugins:['jsx']}),p);}}
 scan(new URL('../src',import.meta.url).pathname);assert.deepEqual(issues,[]);
});

test('chart precision preserves sub-dollar and micro-coin targets',()=>{
 assert.equal(chartPriceFormat(.9857).precision,7);
 assert.equal(chartPriceFormat(.000005).precision,10);
 assert.equal(chartPriceFormat(60200).precision,2);
 assert.equal(chartPriceFormat(null).precision,2);
});
