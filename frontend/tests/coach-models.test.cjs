const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

// Exercise the hook without adding a browser or test framework dependency.
const source = fs.readFileSync(path.join(__dirname, '../src/coach-models.ts'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
function harness(t) {
  const originalFetch = global.fetch;
  const originalStorage = global.localStorage;
  global.localStorage = { getItem: () => null, setItem: () => {} };
  t.after(() => { global.fetch = originalFetch; global.localStorage = originalStorage; });
  const slots = [];
  let cursor = 0;
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initial;
      return [slots[index], value => { slots[index] = value; }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = { current: initial };
      return slots[index];
    },
    useEffect() {},
    useCallback(fn) { return fn; },
  };
  const exports = {};
  new Function('require', 'exports', compiled)(name => {
    assert.equal(name, 'react');
    return react;
  }, exports);
  return {
    exports,
    render() { cursor = 0; return exports.useCoachModels(true, 0, 'fictional-user'); },
  };
}

test('coach displays the safe server diagnosis instead of asking for reconnect for every failure', async t => {
  const app = harness(t);
  global.fetch = async () => new Response(JSON.stringify({detail: 'Limite ChatGPT atteinte. Réessaye plus tard.'}), {status: 429});
  await app.render().loadModels();
  assert.equal(app.render().modelsError, 'Limite ChatGPT atteinte. Réessaye plus tard.');
  assert.equal(app.render().model, '');
});

test('HTML proxy errors and invalid detail shapes get a usable fallback', async t => {
  const {exports} = harness(t);
  for (const body of ['<html>proxy failure</html>', JSON.stringify({detail: ['unexpected']})]) {
    const error = await exports.modelResponseError(new Response(body, {status: 502}));
    assert.match(error, /Catalogue ChatGPT indisponible/);
    assert.doesNotMatch(error, /proxy failure|unexpected/);
  }
  assert.equal(await exports.modelResponseError(new Response('{}', {status: 401})), 'Reconnecte ton espace.');
});

test('successful connection check supplies models and wins over an older failed request', async t => {
  const app = harness(t);
  let finish;
  let signal;
  global.fetch = (_, options) => {
    signal = options.signal;
    return new Promise(resolve => { finish = resolve; });
  };
  const pending = app.render().loadModels();
  app.render().applyModels([{id: 'test-astra', name: 'Astra'}, {id: 'test-sol', name: 'Sol'}]);
  assert.equal(signal.aborted, true);
  finish(new Response(JSON.stringify({detail: 'Old failure'}), {status: 503}));
  await pending;
  const result = app.render();
  assert.equal(result.model, 'test-sol');
  assert.equal(result.models.length, 2);
  assert.equal(result.modelsError, '');
  assert.equal(result.modelsLoading, false);
});

test('a failed refresh clears unavailable choices rather than allowing a stale model to send', async t => {
  const app = harness(t);
  app.render().applyModels([{id: 'test-sol', name: 'Sol'}]);
  global.fetch = async () => new Response(JSON.stringify({detail: 'OpenAI refuse l’accès ChatGPT (403).'}), {status: 503});
  await app.render().loadModels();
  assert.deepEqual(app.render().models, []);
  assert.equal(app.render().model, '');
  assert.match(app.render().modelsError, /403/);
});
