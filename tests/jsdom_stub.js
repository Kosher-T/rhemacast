// Minimal DOM stub so a display script can be evaluated under node (used by
// tests/test_display_js.py). Only what display.js / display_view.py touch at
// load time and in the render path.
function makeEl(id) {
  const _attrs = {};
  const _toAttr = (k) => "data-" + String(k).replace(/[A-Z]/g, (c) => "-" + c.toLowerCase());
  const el = {
    _attrs: _attrs,
    dataset: new Proxy({}, {
      get(t, k) { const a = _attrs[_toAttr(k)]; return a === undefined ? undefined : a; },
      set(t, k, v) { _attrs[_toAttr(k)] = String(v); return true; },
      deleteProperty(t, k) { delete _attrs[_toAttr(k)]; return true; },
    }),
    getAttribute(n) { return Object.prototype.hasOwnProperty.call(_attrs, n) ? _attrs[n] : null; },
    setAttribute(n, v) { _attrs[String(n)] = String(v); },
    removeAttribute(n) { delete _attrs[String(n)]; },
    id: id || "",
    innerHTML: "",
    textContent: "",
    style: {
      _props: {},
      setProperty(k, v) { this._props[k] = v; },
      removeProperty(k) { delete this._props[k]; },
      getPropertyValue(k) { return this._props[k] || ""; },
    },
    classList: { _s: new Set(), add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
                  contains(c) { return this._s.has(c); }, toggle() {} },
    className: "",
    children: [],
    appendChild(c) {
      const idx = this.children.indexOf(c);
      if (idx !== -1) this.children.splice(idx, 1);
      this.children.push(c);
      c.parentElement = this;
      return c;
    },
    insertBefore(newChild, refChild) {
      const curIdx = this.children.indexOf(newChild);
      if (curIdx !== -1) this.children.splice(curIdx, 1);
      const idx = this.children.indexOf(refChild);
      if (idx !== -1) {
        this.children.splice(idx, 0, newChild);
      } else {
        this.children.push(newChild);
      }
      newChild.parentElement = this;
      return newChild;
    },
    insertAdjacentHTML(_pos, html) { this.innerHTML += html; },
    addEventListener() {},
    removeEventListener() {},
    remove() {},

    animate(keyframes, options) {
      return {
        finished: Promise.resolve(),
        cancel() {},
        play() {},
        pause() {},
        addEventListener(type, cb) { if (type === "finish") setTimeout(cb, 0); },
        removeEventListener() {},
        onfinish: null,
      };
    },
    getBoundingClientRect() { return { top: 0, left: 0, width: 100, height: 20, right: 100, bottom: 20 }; },
    getClientRects() { return []; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    focus() {},
    scrollIntoView() {},
  };
  return el;
}

const _els = {};
globalThis.document = {
  documentElement: makeEl("html"),
  body: makeEl("body"),
  head: makeEl("head"),
  readyState: "complete",
  fonts: {
    ready: Promise.resolve(),
    addEventListener() {},
    removeEventListener() {},
    check() { return true; },
    load() { return Promise.resolve([]); },
    forEach() {},
  },
  getElementById(id) { return _els[id] || (_els[id] = makeEl(id)); },
  createElement(tag) {
    const el = makeEl(tag);
    if (tag === "canvas") {
      el.getContext = () => ({
        set font(v) {}, get font() { return ""; },
        measureText() {
          return { width: 0, actualBoundingBoxAscent: 0,
                   actualBoundingBoxDescent: 0, actualBoundingBoxLeft: 0 };
        },
      });
    }
    return el;
  },
  createElementNS(_ns, tag) { return makeEl(tag); },
  createTreeWalker() { return { nextNode() { return null; } }; },
  createRange() {
    return {
      setStart() {}, setEnd() {},
      getClientRects() { return []; },
      getBoundingClientRect() { return { top: 0, left: 0, width: 0, height: 0 }; },
    };
  },
  addEventListener() {},
  removeEventListener() {},
  querySelector() { return null; },
  querySelectorAll() { return []; },
};
globalThis.window = globalThis;
globalThis.window.addEventListener = () => {};
globalThis.window.removeEventListener = () => {};
globalThis.window.setTimeout = setTimeout;
globalThis.window.setInterval = () => 0;
globalThis.window.clearTimeout = () => {};
globalThis.window.clearInterval = () => {};
globalThis.window.devicePixelRatio = 1;
globalThis.window.innerWidth = 1920;
globalThis.window.innerHeight = 1080;
globalThis.location = { hostname: "127.0.0.1", search: "" };
globalThis.navigator = { userAgent: "node" };
globalThis.getComputedStyle = () => ({
  getPropertyValue: () => "",
  fontSize: "40px",
});
globalThis.requestAnimationFrame = (fn) => setTimeout(fn, 0);
globalThis.WebSocket = class { constructor() { this.close = () => {}; } send() {} };
globalThis.ResizeObserver = class { observe() {} disconnect() {} };
globalThis.matchMedia = () => ({ matches: false, addEventListener() {} });
// Outline conversion needs these at *evaluation* time only; without layout
// every measurement is empty and conversion cleanly no-ops.
globalThis.NodeFilter = { SHOW_TEXT: 4, SHOW_ELEMENT: 1 };
const _stg = _els["stage"] = makeEl("stage");
const _cnt = _els["container"] = makeEl("container");
const _vc = _els["verse-content"] = makeEl("verse-content");
const _vt = _els["verse-text"] = makeEl("verse-text");
const _vr = _els["verse-ref"] = makeEl("verse-ref");
const _vrt = _els["verse-ref-text"] = makeEl("verse-ref-text");
const _vrtr = _els["verse-ref-translation"] = makeEl("verse-ref-translation");
_stg.appendChild(_cnt);
_cnt.appendChild(_vc);
_vc.appendChild(_vt);
_vc.appendChild(_vr);
_vr.appendChild(_vrt);
_vr.appendChild(_vrtr);
globalThis.__els = _els;