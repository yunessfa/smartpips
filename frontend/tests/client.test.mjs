import test from 'node:test';
import assert from 'node:assert/strict';
import { api, authApi, setUnauthorizedHandler } from '../src/api/client.js';
let store, loggedOut, refreshCount;
function setup(handler) {
  store = new Map([['smartpips_token', 'old-access']]); loggedOut = 0; refreshCount = 0;
  globalThis.localStorage = { getItem: k => store.get(k) ?? null, setItem: (k,v) => store.set(k,v), removeItem: k => store.delete(k) };
  globalThis.document = { cookie: 'csrftoken=test-csrf' };
  globalThis.window = { dispatchEvent() {} };
  globalThis.fetch = handler;
  setUnauthorizedHandler(() => { loggedOut++; });
}
function response(status, data = {}) { return { status, ok: status >= 200 && status < 300, json: async () => data, statusText: 'Error' }; }

test('concurrent 401s share one refresh and retry with new access', async () => {
  setup(async (url, options = {}) => {
    if (url.endsWith('/refresh/')) {
      if (options.method === 'POST') { refreshCount++; await new Promise(r => setTimeout(r, 10)); return response(200, {token: 'new-access'}); }
      return response(200);
    }
    return options.headers.Authorization === 'Token new-access' ? response(200, {ok: true}) : response(401);
  });
  const values = await Promise.all(Array.from({length: 8}, () => api.get('/protected/')));
  assert.equal(refreshCount, 1); assert.equal(loggedOut, 0); assert.ok(values.every(v => v.ok));
});
test('refresh server error preserves session', async () => {
  setup(async (url, o = {}) => url.endsWith('/refresh/') ? response(o.method ? 503 : 200) : response(401));
  await assert.rejects(api.get('/protected/'));
  assert.equal(loggedOut, 0); assert.equal(store.get('smartpips_token'), 'old-access');
});
test('refresh network error preserves session', async () => {
  setup(async url => { if (url.endsWith('/refresh/')) throw new TypeError('offline'); return response(401); });
  await assert.rejects(api.get('/protected/')); assert.equal(loggedOut, 0);
});
test('expired refresh triggers sign-out', async () => {
  setup(async (url, o = {}) => url.endsWith('/refresh/') ? response(o.method ? 401 : 200) : response(401));
  await assert.rejects(api.get('/protected/')); assert.equal(loggedOut, 1);
});
test('bad login never refreshes or attaches old access', async () => {
  setup(async (url, o) => { assert.equal(url, '/api/auth/login/'); assert.equal(o.headers.Authorization, undefined); return response(401, {error:'Bad credentials'}); });
  await assert.rejects(authApi.login('test', 'not-a-real-password'), /Bad credentials/);
  assert.equal(loggedOut, 0);
});
test('permission denial does not renew or sign out', async () => {
  setup(async url => { assert.equal(url, '/api/protected/'); return response(403); });
  await assert.rejects(api.get('/protected/')); assert.equal(loggedOut, 0);
});
test('a retried 401 cannot enter a refresh loop', async () => {
  setup(async (url, o = {}) => {
    if (url.endsWith('/refresh/')) { if (o.method) { refreshCount++; return response(200,{token:'new-access'}); } return response(200); }
    return response(401);
  });
  await assert.rejects(api.get('/protected/')); assert.equal(refreshCount, 1); assert.equal(loggedOut, 1);
});

test('late old 401 cannot log out a newer successful login', async () => {
  let release;
  setup(async (url, o = {}) => {
    if(o.headers.Authorization === 'Token newly-logged-in') return response(200, {ok:true});
    return new Promise(resolve => { release=resolve; });
  });
  const pending = api.get('/protected/');
  store.set('smartpips_token','newly-logged-in');
  release(response(401));
  assert.equal((await pending).ok,true);
  assert.equal(loggedOut,0);
});

test('CSRF bootstrap body supports refresh without reading CSRF cookie', async () => {
  setup(async (url,o={}) => {
    if(url.endsWith('/refresh/')) {
      if(o.method) {
        assert.equal(o.headers['X-CSRFToken'],'masked-from-bootstrap');
        return response(200,{token:'new-access'});
      }
      return response(200,{csrf_token:'masked-from-bootstrap'});
    }
    return o.headers.Authorization==='Token new-access' ? response(200,{ok:true}) : response(401);
  });
  document.cookie='';
  assert.equal((await api.get('/protected/')).ok,true);
});

test('failed CSRF bootstrap stops before refresh POST, without logout', async () => {
  let post=0;
  setup(async (url,o={}) => {
    if(url.endsWith('/refresh/')) { if(o.method) post++; return response(503); }
    return response(401);
  });
  await assert.rejects(api.get('/protected/'));
  assert.equal(post,0); assert.equal(loggedOut,0);
});
