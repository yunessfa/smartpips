import test from 'node:test';
import assert from 'node:assert/strict';
import { journalContext } from '../src/lib/journalContext.js';
import { buildCsvBlob, buildXlsxBlob } from '../src/lib/export.js';

test('entry attribution reaches CSV and XLSX, including Persian and zero score', async () => {
  const values = journalContext({strategy_name:'استراتژی تست',strategy_version:2,
    timeframe:'5m',confidence:0,exit_reason:'sl',fees_paid:0,funding_paid:-1,net_pnl:12});
  assert.equal(values.confidence,0);
  assert.equal(values.fees_paid,0);
  const columns = Object.keys(values).map(key => ({key,label:key}));
  const csv = await buildCsvBlob(columns,[values]).text();
  assert.match(csv,/استراتژی تست/);
  assert.match(csv,/5m/);
  const xlsx = await buildXlsxBlob('Trades',columns,[values]).arrayBuffer();
  // Writer uses uncompressed ZIP members, so worksheet UTF-8 is directly readable.
  const xml = new TextDecoder().decode(xlsx);
  assert.match(xml,/استراتژی تست/);
  assert.match(xml,/5m/);
  assert.match(xml,/>sl</);
});
test('unknown costs/metadata are blank rather than invented zero values', () => {
  const row = journalContext({});
  assert.equal(row.net_pnl,'');
  assert.equal(row.fees_paid,'');
  assert.equal(row.strategy_name,'');
  assert.equal(row.execution_verified,'unverified');
});