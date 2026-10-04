const { test } = require('node:test');
const assert = require('node:assert/strict');
const { phase, events, create } = require('../ui-kit/motion.js');

const snapshot = overrides => ({case_no: 1138, camera_ok: true, pending: false, revealed: false, items: [], ...overrides});
const item = (n, overrides) => ({n, item: `Camera ${n}`, value_usd: n * 100, estimated: true, ...overrides});

function harness() {
  class Element {
    constructor(tag, ownerDocument) {
      this.tag = tag; this.ownerDocument = ownerDocument; this.dataset = {}; this.children = [];
      this.attributes = {}; this.textContent = ''; this.disabled = false; this.hidden = false;
      const classes = new Set();
      this.classList = {add: (...names) => names.forEach(n => classes.add(n)), remove: (...names) => names.forEach(n => classes.delete(n)),
        contains: name => classes.has(name), toggle: (name, value) => value ? classes.add(name) : classes.delete(name)};
      this.selectors = {};
    }
    setAttribute(key, value) { this.attributes[key] = value; }
    removeAttribute(key) { delete this.attributes[key]; }
    querySelector(selector) { return this.selectors[selector] ??= new Element('span', this.ownerDocument); }
    addEventListener() {}
    append(...nodes) { this.children.push(...nodes); }
    remove() { this.removed = true; }
  }
  const doc = {hidden: false, addEventListener() {}, removeEventListener() {}};
  doc.createElement = tag => new Element(tag, doc);
  doc.body = doc.createElement('body');
  const host = doc.createElement('div');
  const motion = create(host);
  return {host, doc, motion, notice: doc.body.children[0]};
}

test('connecting is distinct from confirmed empty state', () => {
  assert.equal(phase(null), 'connecting'); assert.equal(phase(snapshot()), 'empty');
  assert.equal(phase(snapshot({items: [item(1)]})), 'observing');
});
test('connection and camera failures override processing', () => {
  assert.equal(phase(snapshot({pending: true}), 'offline'), 'offline');
  assert.equal(phase(snapshot({pending: true, camera_ok: false})), 'camera-lost');
  assert.equal(phase(snapshot({pending: true})), 'analyzing');
});
test('debrief can remain available even when the camera is gone', () => {
  assert.equal(phase(snapshot({revealed: true, camera_ok: false})), 'debrief');
});
test('initial hydration and repeated polls do not announce existing findings', () => {
  const data = snapshot({items: [item(1)]});
  assert.deepEqual(events(null, data), []); assert.deepEqual(events(data, {...data}), []);
});
test('only fresh observations get a filing event, with value-based top-five context', () => {
  const before = snapshot({items: [item(1)]});
  const data = snapshot({items: [item(1), item(2)]});
  assert.equal(events(before, data).length, 1);
  assert.match(events(before, data)[0].text, /Top-five asset: Camera 2/);
  assert.equal(events(before, data)[0].n, 2);
});
test('exit observations do not receive a top-five asset callout', () => {
  const data = snapshot({items: [item(1, {category: 'exit', value_usd: 0})]});
  assert.match(events(snapshot(), data)[0].text, /^Observation filed:/);
});
test('case reset handles reused exhibit IDs as a reset, not a new asset', () => {
  const before = snapshot({items: [item(1)]});
  const data = snapshot({case_no: 1139, items: [item(1)]});
  assert.equal(events(before, data)[0].kind, 'reset');
});
test('debrief event only fires on the state edge', () => {
  const data = snapshot({revealed: true});
  assert.equal(events(snapshot(), data)[0].kind, 'debrief');
  assert.deepEqual(events(data, data), []);
});
test('slow processing timer survives identical snapshots, then stops on disconnection', t => {
  t.mock.timers.enable({apis: ['setTimeout', 'setInterval', 'Date'], now: 1000});
  const {host, motion} = harness();
  motion.update(snapshot({pending: true}));
  t.mock.timers.tick(11000);
  motion.update(snapshot({pending: true}));
  assert.match(host.querySelector('.motion-detail').textContent, /Still processing/);
  assert.equal(host.querySelector('.motion-elapsed').textContent, '11s elapsed');
  motion.setConnection('offline');
  assert.equal(host.querySelector('.motion-elapsed').textContent, '');
  motion.destroy();
});
test('remote asset names are text, and model/demo sources are explicit', () => {
  const {motion, notice, host} = harness();
  motion.update(snapshot());
  motion.update(snapshot({items: [item(1, {item: '<img onerror=alert(1)>', source: 'offline'})]}));
  assert.match(notice.children[0].textContent, /<img onerror=alert\(1\)>/);
  assert.equal(host.querySelector('.motion-source').textContent, 'DEMO CATALOG');
  motion.destroy();
});
test('an action is busy until a successful response and then restores its label', async () => {
  const {doc, motion, notice} = harness(); const button = doc.createElement('button');
  button.textContent = 'File'; let resolve;
  const pending = motion.action([button], () => new Promise(r => { resolve = r; }));
  assert.equal(button.disabled, true); assert.equal(button.attributes['aria-busy'], 'true');
  assert.equal(await motion.action([button], () => { throw new Error('duplicate'); }), false);
  resolve({ok: true}); assert.equal((await pending).ok, true);
  assert.equal(button.disabled, false); assert.equal(button.textContent, 'File');
  assert.equal(notice.dataset.tone, 'success'); motion.destroy();
});
test('failure restores controls and never paints a false success', async () => {
  const {doc, motion, notice} = harness(); const button = doc.createElement('button'); button.textContent = 'File';
  assert.equal(await motion.action([button], async () => ({ok: false, status: 503})), false);
  assert.equal(button.disabled, false); assert.equal(notice.dataset.tone, 'warning');
  assert.equal(button.classList.contains('action-confirmed'), false); motion.destroy();
});
test('timeout aborts a hung request and releases the control', async t => {
  t.mock.timers.enable({apis: ['setTimeout']});
  const {doc, motion, notice} = harness(); const button = doc.createElement('button'); let signal;
  const pending = motion.action([button], s => { signal = s; return new Promise(() => {}); });
  t.mock.timers.tick(12001);
  assert.equal(await pending, false); assert.equal(signal.aborted, true);
  assert.equal(button.disabled, false); assert.equal(notice.dataset.tone, 'warning'); motion.destroy();
});
