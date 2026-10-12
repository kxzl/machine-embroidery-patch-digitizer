/* Digitize Patch web UI: Region map and Stitch plan.
 *
 * Every path and every JSON field name used here is fixed by
 * docs/design/webui.md, section "Interfaces / HTTP API". Do not invent
 * fields: the Flask server (T2) is written against the same list.
 */
(function () {
  'use strict';

  var POLL_MS = 1000;
  var MIN_SCALE = 0.02;
  var MAX_SCALE = 40;
  var DRAG_PX = 3;

  var SVG_NS = 'http://www.w3.org/2000/svg';
  var INKSTITCH_NS = 'http://inkstitch.org/namespace';

  /* D3: only fill and satinized Regions are clickable. */
  var LOCKED_KINDS = { outline: 1, border: 1, gradient: 1, run: 1 };
  var KIND_WORDS = { outline: 'Outline', border: 'Border', gradient: 'Gradient', run: 'Run' };

  var OVERRIDE_STATUSES = ['pending', 'applied', 'refused', 'orphaned', 'shadowed'];

  var state = {
    options: null,
    status: null,
    overrides: [],            /* [{at_px: [x, y], type: 'fill'|'satin'}] */
    regions: null,            /* parsed <base>.regions.json of the drawn Slice */
    reported: false,          /* true while regions.json still describes the list */
    svg: null,                /* the inlined Region map <svg> element */
    mapKey: null,             /* slice.svg_url currently drawn */
    fitKey: null,             /* picture url the view was fitted to */
    fitted: false,
    pictureKind: '',
    yamlText: '',
    hasPalette: false,
    actionError: '',
    planView: 'stitchplan',
    view: { x: 0, y: 0, s: 1 },
    popover: null             /* {path, at: [x, y]} */
  };

  var pollTimer = null;
  var drag = null;
  var suppressClick = false;

  /* ---- small helpers ---- */

  function $(id) { return document.getElementById(id); }

  function clearNode(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }

  function show(node) { node.classList.remove('hidden'); }
  function hide(node) { node.classList.add('hidden'); }

  function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }

  function make(tag, className, label) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (label !== undefined && label !== null) { node.textContent = label; }
    return node;
  }

  function radio(name, value, label, checked) {
    var wrap = make('label');
    var input = document.createElement('input');
    input.type = 'radio';
    input.name = name;
    input.value = value;
    input.checked = !!checked;
    wrap.appendChild(input);
    wrap.appendChild(document.createTextNode(label));
    return wrap;
  }

  function checkedValue(name) {
    var input = document.querySelector('input[name="' + name + '"]:checked');
    return input ? input.value : null;
  }

  function isBusy() {
    var s = state.status ? state.status.state : 'idle';
    return s === 'slicing' || s === 'exporting';
  }

  /* ---- server calls ---- */

  function api(path, options) {
    return fetch(path, options).then(function (res) {
      return res.text().then(function (text) {
        var body = null;
        if (text) { try { body = JSON.parse(text); } catch (err) { body = null; } }
        if (!res.ok) {
          var msg = (body && body.error) ? body.error : path + ' failed (' + res.status + ')';
          throw new Error(msg);
        }
        return body || {};
      });
    });
  }

  function postJson(path, payload) {
    return api(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  }

  function showError(message) {
    var box = $('prog-error');
    if (!message) { box.textContent = ''; hide(box); return; }
    box.textContent = message;
    show(box);
  }

  /* ---- options (GET /api/options) ---- */

  function loadOptions() {
    return api('/api/options').then(function (options) {
      state.options = options;

      var hoops = $('hoop-radios');
      clearNode(hoops);
      (options.hoops || []).forEach(function (hoop, i) {
        hoops.appendChild(radio('hoop', String(i), hoop[0] + ' x ' + hoop[1] + ' mm', i === options.default_hoop));
      });

      var colors = $('color-radios');
      clearNode(colors);
      (options.colors || []).forEach(function (n) {
        colors.appendChild(radio('color', String(n), String(n), n === options.default_colors));
      });

      $('in-size').value = options.default_size_mm;
      renderPaletteNote();
    });
  }

  /* ---- picture (POST /api/picture) ---- */

  function uploadPicture(file) {
    var form = new FormData();
    form.append('picture', file);
    return api('/api/picture', { method: 'POST', body: form }).then(function (body) {
      state.pictureKind = body.kind || '';
      state.regions = null;
      state.reported = false;
      hidePopover();

      var note = $('picture-note');
      note.textContent = body.width + ' x ' + body.height + ' px, ' + (body.kind || 'unknown').replace(/_/g, ' ');

      var advice = $('picture-advice');
      clearNode(advice);
      (body.advice || []).forEach(function (line) {
        advice.appendChild(make('li', null, line));
      });

      renderKeyBackground();
      /* E5: a different picture clears every override. */
      state.overrides = [];
      renderOverrides();
      return afterAction();
    });
  }

  function renderKeyBackground() {
    var plain = state.pictureKind === 'plain_background';
    var label = $('label-keybg');
    if (plain) { show(label); } else { hide(label); $('in-keybg').checked = false; }
  }

  function keyBackground() {
    if (state.pictureKind !== 'plain_background') { return false; }
    return $('in-keybg').checked;
  }

  /* ---- config (POST /api/yaml) ---- */

  function loadYaml(file) {
    return file.text().then(function (yamlText) {
      state.yamlText = yamlText;
      return postJson('/api/yaml', { yaml_text: yamlText });
    }).then(function (body) {
      var note = $('yaml-note');
      if (!body.ok) {
        note.textContent = 'Not loaded: ' + (body.error || 'the YAML did not parse');
        note.classList.add('error');
        state.hasPalette = false;
        renderPaletteNote();
        return;
      }
      note.classList.remove('error');
      note.textContent = 'loaded (' + (file.name || 'config') + ')';
      state.hasPalette = !!body.has_palette;
      renderPaletteNote();
      var fromYaml = normaliseOverrides(body.stitch_overrides || []);
      if (fromYaml.length) {
        state.overrides = fromYaml;
        state.reported = false;
        renderOverrides();
      }
      return afterAction();
    });
  }

  function clearConfig() {
    state.yamlText = '';
    state.hasPalette = false;
    var note = $('yaml-note');
    note.classList.remove('error');
    note.textContent = 'No config loaded';
    renderPaletteNote();
  }

  function renderPaletteNote() {
    var note = $('palette-note');
    if (state.hasPalette) {
      show(note);
      Array.prototype.forEach.call($('color-radios').querySelectorAll('input'), function (input) {
        input.disabled = true;
      });
    } else {
      hide(note);
      Array.prototype.forEach.call($('color-radios').querySelectorAll('input'), function (input) {
        input.disabled = false;
      });
    }
  }

  /* ---- actions (POST /api/slice, /api/stitchplan, /api/cancel) ---- */

  function sliceBody() {
    var hoops = (state.options && state.options.hoops) || [];
    var hoopIndex = checkedValue('hoop');
    var hoop = hoopIndex === null ? null : hoops[Number(hoopIndex)];
    var size = null;
    if (!$('in-fill-hoop').checked) {
      var value = Number($('in-size').value);
      if ($('in-size').value !== '' && isFinite(value) && value > 0) { size = value; }
    }
    return {
      hoop: hoop,
      size_mm: size,
      colors: Number(checkedValue('color')),
      key_background: keyBackground(),
      yaml_text: state.yamlText,
      overrides: state.overrides.map(function (o) {
        return { at_px: [o.at_px[0], o.at_px[1]], type: o.type };
      })
    };
  }

  function runAction(promise) {
    state.actionError = '';
    return promise.then(function () {
      return afterAction();
    }).catch(function (err) {
      state.actionError = err.message;
      return afterAction();
    });
  }

  function afterAction() {
    return refreshStatus().then(function () {
      startPolling();
    });
  }

  function doSlice() {
    hidePopover();
    return runAction(postJson('/api/slice', sliceBody()));
  }

  function doStitchplan() {
    return runAction(api('/api/stitchplan', { method: 'POST' }));
  }

  function doCancel() {
    return runAction(postJson('/api/cancel', {}));
  }

  /* ---- status (GET /api/status) ---- */

  function refreshStatus() {
    return api('/api/status').then(function (status) {
      state.status = status;
      renderStatus();
      return status;
    });
  }

  function startPolling() {
    stopPolling();
    if (isBusy()) { pollTimer = setInterval(function () { refreshStatus(); }, POLL_MS); }
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  function renderStatus() {
    var status = state.status;
    var busy = isBusy();
    if (!busy) { stopPolling(); }

    $('prog-state').textContent = status.state;
    $('prog-stage').textContent = status.stage || '';
    $('prog-elapsed').textContent = (status.elapsed_s === null || status.elapsed_s === undefined)
      ? '' : status.elapsed_s.toFixed(1) + ' s';
    $('prog-log').textContent = (status.log_tail || []).join('\n');
    showError(status.error || state.actionError);

    renderButtons(busy);
    renderPicture(status.picture);
    renderOverrides();
    renderPlan(status.stitchplan, status.slice);

    var slice = status.slice;
    if (!slice) {
      var host = $('content-regionmap');
      if (state.svg || state.mapKey) {
        clearNode(host);
        host.appendChild(make('p', 'placeholder', 'No Slice yet'));
      }
      state.svg = null;
      state.mapKey = null;
      state.regions = null;
      hidePopover();
    } else {
      drawRegionMap(slice, status.picture);
    }
  }

  function renderButtons(busy) {
    var status = state.status;
    $('btn-slice').disabled = busy || !status.picture;
    $('btn-stitchplan').disabled = busy || !status.slice;
    $('btn-cancel').disabled = !busy;
    $('in-picture').disabled = busy;
  }

  /* ---- picture pane ---- */

  function pictureSize(picture) {
    if (picture && picture.width && picture.height) { return [picture.width, picture.height]; }
    return null;
  }

  function renderPicture(picture) {
    var host = $('content-picture');
    var size = pictureSize(picture);
    var url = picture ? picture.url : null;

    if (!url) {
      if (!host.querySelector('.placeholder')) {
        clearNode(host);
        host.appendChild(make('p', 'placeholder', 'No picture yet'));
      }
      state.fitKey = null;
      return;
    }

    var img = host.querySelector('img');
    if (!img) {
      clearNode(host);
      img = document.createElement('img');
      img.alt = 'Picture';
      host.appendChild(img);
    }
    if (img.getAttribute('src') !== url) { img.setAttribute('src', url); }
    if (size) {
      img.style.width = size[0] + 'px';
      img.style.height = size[1] + 'px';
    }

    if (!size) { return; }
    var key = url + '|' + size.join('x');
    if (state.fitKey !== key) {
      state.fitKey = key;
      state.fitted = true;
      fitView();
    }
  }

  /* ---- Region map pane ---- */

  function drawRegionMap(slice, picture) {
    if (state.mapKey === slice.svg_url) { return; }
    state.mapKey = slice.svg_url;

    var wanted = slice.svg_url;
    fetch(wanted).then(function (res) {
      if (!res.ok) { throw new Error('the Region map did not load (' + res.status + ')'); }
      return res.text();
    }).then(function (svgText) {
      return readRegions(slice).then(function (regions) {
        /* A newer Slice arrived while this one was loading: drop the stale draw. */
        if (state.mapKey !== wanted) { return; }
        mountRegionMap(svgText, regions, picture);
        renderOverrides();
      });
    }).catch(function (err) {
      if (state.mapKey !== wanted) { return; }
      state.actionError = err.message;
      showError(state.actionError);
    });
  }

  function readRegions(slice) {
    if (!slice.regions_url) { return Promise.resolve(null); }
    return fetch(slice.regions_url).then(function (res) {
      if (!res.ok) { return null; }
      return res.json();
    }).catch(function () { return null; });
  }

  function mountRegionMap(svgText, regions, picture) {
    var doc = new DOMParser().parseFromString(svgText, 'image/svg+xml');
    if (doc.getElementsByTagName('parsererror').length) {
      throw new Error('the Region map SVG did not parse');
    }
    var svg = document.importNode(doc.documentElement, true);
    if (svg.nodeName.toLowerCase() !== 'svg') {
      throw new Error('the Region map file is not an SVG');
    }

    var size = pictureSize(picture);
    if (!size) {
      var box = (svg.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
      size = (box.length === 4 && box[2] > 0 && box[3] > 0) ? [box[2], box[3]] : [1000, 1000];
    }
    /* Same pixel grid as the picture pane (D12): size in pixels, viewBox kept. */
    svg.setAttribute('width', String(size[0]));
    svg.setAttribute('height', String(size[1]));
    svg.classList.add('rmap');

    var kinds = null;
    if (regions && regions.objects) {
      kinds = {};
      regions.objects.forEach(function (object) { kinds[object.id] = object.kind; });
    }

    Array.prototype.forEach.call(svg.querySelectorAll('path'), function (path) {
      var kind = (kinds && kinds[path.id]) ? kinds[path.id] : kindFromSvg(path);
      path.setAttribute('data-kind', kind);
      path.classList.add('region');
      path.classList.add('kind-' + kind);
      if (LOCKED_KINDS[kind]) { path.classList.add('locked'); }
    });

    var overlay = document.createElementNS(SVG_NS, 'g');
    overlay.setAttribute('class', 'overrides');
    svg.appendChild(overlay);

    var host = $('content-regionmap');
    clearNode(host);
    host.appendChild(svg);
    host.style.width = size[0] + 'px';
    host.style.height = size[1] + 'px';
    state.svg = svg;
    state.regions = regions;
    state.reported = !!regions;
  }

  /* The rule for reading object kinds from the SVG when there is no regions.json. */
  function kindFromSvg(path) {
    var group = parentGroupId(path);
    if (group === 'border') { return 'border'; }
    if (group === 'outlines') { return 'outline'; }

    var style = path.getAttribute('style') || '';
    if (/fill\s*:\s*url\(/.test(style)) { return 'gradient'; }

    if ((path.hasAttributeNS(INKSTITCH_NS, 'satin_column') ||
        path.getAttribute('inkstitch:satin_column') !== null) && /^color\d+$/.test(group)) {
      return 'satinized';
    }
    /* Emitted ids are f{idx}, s{idx}, r{idx}; r* is a run. */
    if (/^r\d/.test(path.id || '')) { return 'run'; }
    return 'fill';
  }

  function parentGroupId(node) {
    var parent = node.parentNode;
    while (parent && parent.nodeType === 1) {
      if (parent.id) { return parent.id; }
      parent = parent.parentNode;
    }
    return '';
  }

  /* ---- override markers inside the Region map ---- */

  function renderMarkers() {
    if (!state.svg) { return; }
    var overlay = state.svg.querySelector('g.overrides');
    if (!overlay) { return; }
    clearNode(overlay);

    state.overrides.forEach(function (override) {
      var info = overrideInfo(override);
      var circle = document.createElementNS(SVG_NS, 'circle');
      circle.setAttribute('cx', String(override.at_px[0]));
      circle.setAttribute('cy', String(override.at_px[1]));
      circle.setAttribute('r', '9');
      circle.setAttribute('class', 'ov-' + info.status);

      var title = document.createElementNS(SVG_NS, 'title');
      title.textContent = override.type + ' at ' + override.at_px[0] + ', ' + override.at_px[1] +
        ': ' + info.status + (info.reason ? ' (' + info.reason + ')' : '');
      circle.appendChild(title);

      overlay.appendChild(circle);
    });
    sizeMarkers();
  }

  function sizeMarkers() {
    if (!state.svg) { return; }
    var r = 9 / state.view.s;
    Array.prototype.forEach.call(state.svg.querySelectorAll('g.overrides circle'), function (circle) {
      circle.setAttribute('r', r.toFixed(2));
    });
  }

  /* Status and reason come from the last Slice's regions.json when present.
   Overrides that Slice never saw (E8, or a config that brought its own) are pending. */
  function overrideInfo(override) {
    var list = (state.reported && state.regions && state.regions.overrides) || [];
    var found = findReported(list, override);
    if (!found) { return { status: 'pending', reason: '' }; }
    return {
      status: OVERRIDE_STATUSES.indexOf(found.status) >= 0 ? found.status : 'pending',
      reason: found.reason || ''
    };
  }

  function findReported(list, override) {
    var i;
    for (i = 0; i < list.length; i++) {
      if (sameAt(list[i].at_px, override.at_px) && list[i].type === override.type) { return list[i]; }
    }
    for (i = 0; i < list.length; i++) {
      if (sameAt(list[i].at_px, override.at_px)) { return list[i]; }
    }
    return null;
  }

  function sameAt(a, b) {
    return Array.isArray(a) && Array.isArray(b) && a.length === 2 && b.length === 2 &&
      Number(a[0]) === Number(b[0]) && Number(a[1]) === Number(b[1]);
  }

  /* ---- overrides list in the sidebar ---- */

  function normaliseOverrides(raw) {
    if (!Array.isArray(raw)) { return []; }
    return raw.filter(function (entry) {
      return entry && Array.isArray(entry.at_px) && entry.at_px.length === 2 &&
        isFinite(Number(entry.at_px[0])) && isFinite(Number(entry.at_px[1])) &&
        (entry.type === 'fill' || entry.type === 'satin');
    }).map(function (entry) {
      return {
        at_px: [Math.round(Number(entry.at_px[0])), Math.round(Number(entry.at_px[1]))],
        type: entry.type
      };
    });
  }

  function renderOverrides() {
    var list = $('override-list');
    clearNode(list);

    state.overrides.forEach(function (override, index) {
      var info = overrideInfo(override);
      var row = make('div', 'override');

      var what = make('span', 'what');
      what.appendChild(make('span', 'at', override.at_px[0] + ', ' + override.at_px[1]));
      what.appendChild(document.createTextNode(' ' + override.type + ' '));
      what.appendChild(make('span', 'status status-' + info.status, info.status));
      if (info.reason) { what.appendChild(make('span', 'why', info.reason)); }
      row.appendChild(what);

      var remove = make('button', 'ghost', 'Remove');
      remove.type = 'button';
      remove.addEventListener('click', function () {
        state.overrides.splice(index, 1);
        afterOverrideChange();
      });
      row.appendChild(remove);
      list.appendChild(row);
    });

    $('override-empty').classList.toggle('hidden', state.overrides.length > 0);
    if (overridesAreStale()) { show($('stale-note')); } else { hide($('stale-note')); }
    renderMarkers();
  }

  /* E8: the page's override list differs from what the last Slice was sent. */
  function overridesAreStale() {
    var status = state.status;
    if (!status || !status.slice || !Array.isArray(status.slice.overrides)) { return false; }
    var sent = status.slice.overrides;
    if (sent.length !== state.overrides.length) { return true; }
    return sent.some(function (entry, i) {
      var mine = state.overrides[i];
      return !mine || !sameAt(entry.at_px, mine.at_px) || entry.type !== mine.type;
    });
  }

  function afterOverrideChange() {
    hidePopover();
    renderOverrides();
  }

  /* ---- clicking a Region ---- */

  function pointInRegion(path, at) {
    try {
      return path.isPointInFill(new DOMPoint(at[0], at[1]));
    } catch (err) {
      return false;
    }
  }

  /* E1: one override per Region: drop the ones whose point is inside this path. */
  function setOverride(path, at, type) {
    state.overrides = state.overrides.filter(function (override) { return !pointInRegion(path, override.at_px); });
    state.overrides.push({ at_px: at, type: type });
    afterOverrideChange();
  }

  function clearRegion(path) {
    state.overrides = state.overrides.filter(function (override) { return !pointInRegion(path, override.at_px); });
    afterOverrideChange();
  }

  function onRegionClick(event) {
    if (suppressClick) { suppressClick = false; return; }
    var target = event.target;
    if (!target || !target.closest) { return; }
    if (target.closest('g.overrides')) { return; }

    var path = target.closest('path.region');
    if (!path || !state.svg || !state.svg.getScreenCTM) { hidePopover(); return; }
    var ctm = state.svg.getScreenCTM();
    if (!ctm) { hidePopover(); return; }

    var point = new DOMPoint(event.clientX, event.clientY).matrixTransform(ctm.inverse());
    var at = [Math.round(point.x), Math.round(point.y)];
    var kind = path.getAttribute('data-kind') || 'fill';

    if (LOCKED_KINDS[kind]) {
      showNote(KIND_WORDS[kind] + ' is drawn but locked: it cannot be overridden',
        event.clientX, event.clientY);
      return;
    }
    openPopover(path, at, event.clientX, event.clientY);
  }

  function openPopover(path, at, clientX, clientY) {
    state.popover = { path: path, at: at, clientX: clientX, clientY: clientY };
    var popover = $('popover');
    $('popover-at').textContent = 'Region at ' + at[0] + ', ' + at[1];
    show(popover.querySelector('.popover-actions'));
    show(popover);
    positionPopover(clientX, clientY);
  }

  /* The popover follows the click in screen coordinates, so it stays put while zooming. */
  function positionPopover(clientX, clientY) {
    if (!state.popover) { return; }
    if (clientX === undefined) { clientX = state.popover.clientX; }
    if (clientY === undefined) { clientY = state.popover.clientY; }
    var popover = $('popover');
    var stage = document.querySelector('.stage').getBoundingClientRect();
    var x = clamp(clientX - stage.left + 12, 8, Math.max(8, stage.width - popover.offsetWidth - 8));
    var y = clamp(clientY - stage.top + 12, 8, Math.max(8, stage.height - popover.offsetHeight - 8));
    popover.style.left = x + 'px';
    popover.style.top = y + 'px';
  }

  function showNote(text, clientX, clientY) {
    var popover = $('popover');
    state.popover = { path: null, at: null, clientX: clientX, clientY: clientY };
    $('popover-at').textContent = text;
    hide(popover.querySelector('.popover-actions'));
    show(popover);
    positionPopover(clientX, clientY);
  }

  function hidePopover() {
    state.popover = null;
    hide($('popover'));
  }

  /* ---- pan and zoom, one transform state for both panes ---- */

  function applyView() {
    var transform = 'translate(' + state.view.x + 'px,' + state.view.y + 'px) scale(' + state.view.s + ')';
    $('content-picture').style.transform = transform;
    $('content-regionmap').style.transform = transform;
    sizeMarkers();
  }

  function contentSize() {
    var size = pictureSize(state.status ? state.status.picture : null);
    if (size) { return size; }
    if (state.svg) {
      var box = (state.svg.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
      if (box.length === 4 && box[2] > 0 && box[3] > 0) { return [box[2], box[3]]; }
    }
    return null;
  }

  function fitView() {
    var viewport = $('viewport-regionmap');
    var size = contentSize();
    if (!size || !viewport.clientWidth || !viewport.clientHeight) { return; }
    var scale = Math.min(viewport.clientWidth / size[0], viewport.clientHeight / size[1]) * 0.98;
    state.view.s = clamp(scale, MIN_SCALE, MAX_SCALE);
    state.view.x = (viewport.clientWidth - size[0] * state.view.s) / 2;
    state.view.y = (viewport.clientHeight - size[1] * state.view.s) / 2;
    state.fitted = true;
    applyView();
  }

  function onWheel(event) {
    var size = contentSize();
    if (!size) { return; }
    event.preventDefault();
    var rect = event.currentTarget.getBoundingClientRect();
    var cx = event.clientX - rect.left;
    var cy = event.clientY - rect.top;
    var next = clamp(state.view.s * Math.pow(1.0015, -event.deltaY), MIN_SCALE, MAX_SCALE);
    if (next === state.view.s) { return; }
    var ratio = next / state.view.s;
    state.view.x = cx - (cx - state.view.x) * ratio;
    state.view.y = cy - (cy - state.view.y) * ratio;
    state.view.s = next;
    state.fitted = false;
    applyView();
  }

  function onPointerDown(event) {
    if (event.button !== 0) { return; }
    drag = {
      x: event.clientX,
      y: event.clientY,
      viewX: state.view.x,
      viewY: state.view.y,
      moved: false,
      /* Only a drag that started in the Region map can swallow a Region click. */
      overMap: event.currentTarget === $('viewport-regionmap')
    };
  }

  function onPointerMove(event) {
    if (!drag) { return; }
    var dx = event.clientX - drag.x;
    var dy = event.clientY - drag.y;
    if (!drag.moved && Math.abs(dx) + Math.abs(dy) < DRAG_PX) { return; }
    drag.moved = true;
    state.fitted = false;
    state.view.x = drag.viewX + dx;
    state.view.y = drag.viewY + dy;
    $('viewport-picture').classList.add('dragging');
    $('viewport-regionmap').classList.add('dragging');
    applyView();
  }

  function onPointerUp() {
    if (!drag) { return; }
    /* Same spot down and up is a click, not a drag. */
    suppressClick = drag.overMap && drag.moved;
    drag = null;
    $('viewport-picture').classList.remove('dragging');
    $('viewport-regionmap').classList.remove('dragging');
  }

  /* ---- stitch plan tab (D12: its own scale, not synced) ---- */

  function renderPlan(plan, slice) {
    var image = $('plan-image');
    var numbers = $('plan-numbers');
    var warnings = $('plan-warnings');
    var removed = $('plan-removed');
    var download = $('plan-download');
    clearNode(numbers); clearNode(warnings); clearNode(removed); clearNode(download);

    if (!plan) {
      if (!image.querySelector('.placeholder')) {
        clearNode(image);
        image.appendChild(make('p', 'placeholder', 'No stitch plan yet'));
      }
      hide($('plan-stale'));
      return;
    }

    var url = state.planView === 'coverage' ? plan.coverage_url : plan.stitchplan_url;
    if (url) {
      clearNode(image);
      var img = document.createElement('img');
      img.alt = state.planView === 'coverage' ? 'Coverage' : 'Stitch plan';
      img.setAttribute('src', url);
      image.appendChild(img);
    }

    addFact(numbers, 'Stitches', plan.stitches === null || plan.stitches === undefined ? '' : String(plan.stitches));
    if (plan.width_mm !== null && plan.width_mm !== undefined &&
        plan.height_mm !== null && plan.height_mm !== undefined) {
      addFact(numbers, 'Size', plan.width_mm + ' x ' + plan.height_mm + ' mm');
    }
    addFact(numbers, 'Threads', plan.threads ? plan.threads.join(', ') : '');

    if (plan.warnings && plan.warnings.length) {
      warnings.appendChild(make('p', 'stale', 'Warnings'));
      var list = make('ul');
      plan.warnings.forEach(function (line) { list.appendChild(make('li', null, line)); });
      warnings.appendChild(list);
    }
    if (plan.removed_by_precheck && plan.removed_by_precheck.length) {
      removed.appendChild(make('p', 'stale', 'Removed by the satin precheck'));
      var ids = make('ul');
      plan.removed_by_precheck.forEach(function (id) { ids.appendChild(make('li', null, id)); });
      removed.appendChild(ids);
    }
    if (plan.vp3_url) {
      var link = make('a', null, 'Download VP3');
      link.href = plan.vp3_url;
      download.appendChild(link);
    }

    /* E7: the Stitch plan belongs to an older Slice. */
    if (!slice || slice.slice_id !== plan.slice_id) { show($('plan-stale')); } else { hide($('plan-stale')); }
  }

  function addFact(table, name, value) {
    if (value === '' || value === null || value === undefined) { return; }
    var row = document.createElement('tr');
    row.appendChild(make('td', null, name));
    row.appendChild(make('td', null, value));
    table.appendChild(row);
  }

  /* ---- wiring ---- */

  function switchTab(name) {
    Array.prototype.forEach.call(document.querySelectorAll('#tabs .tab'), function (button) {
      button.classList.toggle('active', button.getAttribute('data-tab') === name);
    });
    $('view-regionmap').classList.toggle('hidden', name !== 'regionmap');
    $('view-stitchplan').classList.toggle('hidden', name !== 'stitchplan');
    if (name === 'regionmap') { positionPopover(); }
  }

  function wire() {
    $('in-picture').addEventListener('change', function (event) {
      var file = event.target.files && event.target.files[0];
      if (file) { runAction(uploadPicture(file)); }
    });
    $('in-fill-hoop').addEventListener('change', function () {
      $('in-size').disabled = $('in-fill-hoop').checked;
    });
    $('in-yaml').addEventListener('change', function (event) {
      var file = event.target.files && event.target.files[0];
      if (file) { runAction(loadYaml(file)); }
    });
    $('btn-clear-config').addEventListener('click', clearConfig);
    $('btn-slice').addEventListener('click', doSlice);
    $('btn-stitchplan').addEventListener('click', doStitchplan);
    $('btn-cancel').addEventListener('click', doCancel);
    $('btn-fit').addEventListener('click', fitView);

    Array.prototype.forEach.call(document.querySelectorAll('#tabs .tab'), function (button) {
      button.addEventListener('click', function () { switchTab(button.getAttribute('data-tab')); });
    });
    Array.prototype.forEach.call(document.querySelectorAll('#plan-switch .tab'), function (button) {
      button.addEventListener('click', function () {
        state.planView = button.getAttribute('data-plan');
        Array.prototype.forEach.call(document.querySelectorAll('#plan-switch .tab'), function (other) {
          other.classList.toggle('active', other === button);
        });
        renderPlan(state.status ? state.status.stitchplan : null, state.status ? state.status.slice : null);
      });
    });

    var viewport = $('viewport-regionmap');
    viewport.addEventListener('wheel', onWheel, { passive: false });
    viewport.addEventListener('mousedown', onPointerDown);
    viewport.addEventListener('click', onRegionClick);
    $('viewport-picture').addEventListener('wheel', onWheel, { passive: false });
    $('viewport-picture').addEventListener('mousedown', onPointerDown);
    window.addEventListener('mousemove', onPointerMove);
    window.addEventListener('mouseup', onPointerUp);

    $('pop-fill').addEventListener('click', function () {
      if (state.popover && state.popover.path) { setOverride(state.popover.path, state.popover.at, 'fill'); }
    });
    $('pop-satin').addEventListener('click', function () {
      if (state.popover && state.popover.path) { setOverride(state.popover.path, state.popover.at, 'satin'); }
    });
    $('pop-clear').addEventListener('click', function () {
      if (state.popover && state.popover.path) { clearRegion(state.popover.path); }
    });

    document.addEventListener('click', function (event) {
      if (event.target.closest && event.target.closest('.rmap')) { return; }
      hidePopover();
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') { hidePopover(); }
    });
    window.addEventListener('resize', function () {
      if (state.fitted) { fitView(); }
      positionPopover();
    });
  }

  wire();
  loadOptions().catch(function (err) { showError(err.message); });
  afterAction().catch(function (err) { showError(err.message); });
}());