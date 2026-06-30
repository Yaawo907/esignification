'use strict';

/**
 * Aperçu PDF + choix de l'emplacement de signature Yousign (coordonnées API v3).
 * Nécessite pdf.js (pdfjsLib) chargé avant ce script.
 */
(function (global) {
  var DEFAULT_SIG_W = 120;
  var DEFAULT_SIG_H = 60;
  var MIN_SIG_W = 85;
  var MIN_SIG_H = 37;
  var MAX_SIG_W = 2000;
  var MAX_SIG_H = 1000;

  var state = {
    pdfDoc: null,
    currentPage: 1,
    totalPages: 0,
    scale: 1,
    pageViewport: null,
    placement: null,
    onChange: null,
    drag: null,
    defaultWidth: DEFAULT_SIG_W,
    defaultHeight: DEFAULT_SIG_H,
  };

  function $(id) { return document.getElementById(id); }

  function emitChange() {
    if (typeof state.onChange === 'function') {
      state.onChange(!!state.placement);
    }
  }

  function setHiddenFields(placement) {
    var fp = $('yousign_sig_page');
    var fx = $('yousign_sig_x');
    var fy = $('yousign_sig_y');
    var fw = $('yousign_sig_width');
    var fh = $('yousign_sig_height');
    if (fp) fp.value = String(placement.page);
    if (fx) fx.value = String(Math.round(placement.x));
    if (fy) fy.value = String(Math.round(placement.y));
    if (fw) fw.value = String(Math.round(placement.width));
    if (fh) fh.value = String(Math.round(placement.height));
  }

  function clearHiddenFields() {
    ['yousign_sig_page', 'yousign_sig_x', 'yousign_sig_y'].forEach(function (id) {
      var el = $(id);
      if (el) el.value = '';
    });
    var fw = $('yousign_sig_width');
    var fh = $('yousign_sig_height');
    if (fw) fw.value = String(state.defaultWidth);
    if (fh) fh.value = String(state.defaultHeight);
  }

  function updateStatus() {
    var el = $('yousign-placement-status');
    if (!el) return;
    if (!state.placement) {
      el.textContent = 'Cliquez sur le document pour placer votre signature électronique.';
      el.style.color = 'var(--text-secondary)';
      return;
    }
    var p = state.placement;
    el.textContent = '✓ Page ' + p.page + ' — (' + p.x + ', ' + p.y + ') · ' +
      p.width + ' × ' + p.height + ' pt';
    el.style.color = '#134e3a';
  }

  function updatePager() {
    var info = $('yousign-page-info');
    var prev = $('yousign-page-prev');
    var next = $('yousign-page-next');
    if (info) {
      info.textContent = state.totalPages > 0
        ? 'Page ' + state.currentPage + ' / ' + state.totalPages
        : '—';
    }
    if (prev) prev.disabled = state.currentPage <= 1;
    if (next) next.disabled = state.currentPage >= state.totalPages;
  }

  function clampPosition(x, y, w, h) {
    var maxX = Math.max(0, state.pageViewport.width - w);
    var maxY = Math.max(0, state.pageViewport.height - h);
    return {
      x: Math.min(Math.max(0, x), maxX),
      y: Math.min(Math.max(0, y), maxY),
    };
  }

  function clampSize(w, h, x, y) {
    var maxW = Math.min(MAX_SIG_W, state.pageViewport.width - x);
    var maxH = Math.min(MAX_SIG_H, state.pageViewport.height - y);
    return {
      width: Math.min(Math.max(MIN_SIG_W, w), maxW),
      height: Math.min(Math.max(MIN_SIG_H, h), maxH),
    };
  }

  function positionMarker() {
    if (!state.placement || !state.pageViewport) return;
    var canvas = $('yousign-pdf-canvas');
    var marker = $('yousign-sig-marker');
    if (!canvas || !marker) return;
    var p = state.placement;
    var scaleX = canvas.width / state.pageViewport.width;
    var scaleY = canvas.height / state.pageViewport.height;
    marker.style.display = 'flex';
    marker.style.left = (p.x * scaleX) + 'px';
    marker.style.top = (p.y * scaleY) + 'px';
    marker.style.width = (p.width * scaleX) + 'px';
    marker.style.height = (p.height * scaleY) + 'px';
  }

  function hideMarker() {
    var marker = $('yousign-sig-marker');
    if (marker) marker.style.display = 'none';
  }

  function screenToPdfDelta(deltaX, deltaY) {
    var canvas = $('yousign-pdf-canvas');
    if (!canvas || !state.pageViewport) return { x: 0, y: 0 };
    var rect = canvas.getBoundingClientRect();
    return {
      x: deltaX * (state.pageViewport.width / rect.width),
      y: deltaY * (state.pageViewport.height / rect.height),
    };
  }

  function onDragMove(e) {
    if (!state.drag || !state.placement) return;
    var p = state.placement;
    var delta = screenToPdfDelta(e.clientX - state.drag.startX, e.clientY - state.drag.startY);

    if (state.drag.type === 'resize') {
      var size = clampSize(
        state.drag.startW + delta.x,
        state.drag.startH + delta.y,
        p.x,
        p.y
      );
      p.width = Math.round(size.width);
      p.height = Math.round(size.height);
    } else if (state.drag.type === 'move') {
      var pos = clampPosition(
        state.drag.startPdfX + delta.x,
        state.drag.startPdfY + delta.y,
        p.width,
        p.height
      );
      p.x = Math.round(pos.x);
      p.y = Math.round(pos.y);
    }

    positionMarker();
    setHiddenFields(p);
    updateStatus();
  }

  function onDragEnd() {
    state.drag = null;
    document.removeEventListener('mousemove', onDragMove);
    document.removeEventListener('mouseup', onDragEnd);
    emitChange();
  }

  function startDrag(type, e, extra) {
    e.preventDefault();
    e.stopPropagation();
    if (!state.placement) return;
    state.drag = {
      type: type,
      startX: e.clientX,
      startY: e.clientY,
      startW: state.placement.width,
      startH: state.placement.height,
      startPdfX: state.placement.x,
      startPdfY: state.placement.y,
    };
    if (extra) {
      Object.keys(extra).forEach(function (k) { state.drag[k] = extra[k]; });
    }
    document.addEventListener('mousemove', onDragMove);
    document.addEventListener('mouseup', onDragEnd);
  }

  function onResizeStart(e) {
    startDrag('resize', e);
  }

  function onMoveStart(e) {
    if (e.target.classList.contains('yousign-sig-resize-handle')) return;
    startDrag('move', e);
  }

  function renderPage(pageNum) {
    if (!state.pdfDoc) return Promise.resolve();
    return state.pdfDoc.getPage(pageNum).then(function (page) {
      var wrap = $('yousign-pdf-wrap');
      var canvas = $('yousign-pdf-canvas');
      if (!wrap || !canvas) return;

      var baseViewport = page.getViewport({ scale: 1 });
      var maxWidth = wrap.clientWidth || 640;
      var scale = Math.min(maxWidth / baseViewport.width, 2);
      var viewport = page.getViewport({ scale: scale });
      state.scale = scale;
      state.pageViewport = baseViewport;

      var ctx = canvas.getContext('2d');
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      canvas.style.width = viewport.width + 'px';
      canvas.style.height = viewport.height + 'px';

      return page.render({ canvasContext: ctx, viewport: viewport }).promise.then(function () {
        state.currentPage = pageNum;
        updatePager();
        if (state.placement && state.placement.page === pageNum) {
          positionMarker();
        } else {
          hideMarker();
        }
      });
    });
  }

  function onCanvasClick(e) {
    if (!state.pageViewport) return;
    var canvas = $('yousign-pdf-canvas');
    if (!canvas) return;
    var rect = canvas.getBoundingClientRect();
    var clickX = (e.clientX - rect.left) * (canvas.width / rect.width);
    var clickY = (e.clientY - rect.top) * (canvas.height / rect.height);
    var pdfX = clickX / state.scale;
    var pdfY = clickY / state.scale;
    var topLeft = clampPosition(
      pdfX - state.defaultWidth / 2,
      pdfY - state.defaultHeight / 2,
      state.defaultWidth,
      state.defaultHeight
    );

    state.placement = {
      page: state.currentPage,
      x: Math.round(topLeft.x),
      y: Math.round(topLeft.y),
      width: state.defaultWidth,
      height: state.defaultHeight,
    };
    setHiddenFields(state.placement);
    positionMarker();
    updateStatus();
    emitChange();
  }

  function resetPlacement() {
    state.placement = null;
    state.drag = null;
    clearHiddenFields();
    hideMarker();
    updateStatus();
    emitChange();
  }

  function loadPdfFromFile(file) {
    var section = $('yousign-placement-section');
    if (!file || file.type !== 'application/pdf') {
      if (section) section.style.display = 'none';
      state.pdfDoc = null;
      resetPlacement();
      return Promise.resolve();
    }

    if (section) section.style.display = 'block';
    resetPlacement();

    var statusLoad = $('yousign-pdf-loading');
    if (statusLoad) statusLoad.style.display = 'block';

    return file.arrayBuffer().then(function (buf) {
      if (!global.pdfjsLib) {
        throw new Error('pdf.js non chargé');
      }
      return global.pdfjsLib.getDocument({ data: buf }).promise;
    }).then(function (pdf) {
      state.pdfDoc = pdf;
      state.totalPages = pdf.numPages;
      var lastPage = pdf.numPages;
      state.currentPage = lastPage;
      if (statusLoad) statusLoad.style.display = 'none';
      return renderPage(lastPage);
    }).catch(function () {
      if (statusLoad) statusLoad.style.display = 'none';
      state.pdfDoc = null;
      var st = $('yousign-placement-status');
      if (st) {
        st.textContent = 'Impossible de lire ce PDF. Vérifiez le fichier.';
        st.style.color = '#b91c1c';
      }
      emitChange();
    });
  }

  function clampDefaultSize(w, h) {
    return {
      width: Math.min(Math.max(MIN_SIG_W, Math.round(w)), MAX_SIG_W),
      height: Math.min(Math.max(MIN_SIG_H, Math.round(h)), MAX_SIG_H),
    };
  }

  function init(options) {
    options = options || {};
    state.onChange = options.onChange || null;
    var dims = clampDefaultSize(
      options.defaultWidth || DEFAULT_SIG_W,
      options.defaultHeight || DEFAULT_SIG_H
    );
    state.defaultWidth = dims.width;
    state.defaultHeight = dims.height;

    if (global.pdfjsLib) {
      global.pdfjsLib.GlobalWorkerOptions.workerSrc =
        'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
    }

    var canvas = $('yousign-pdf-canvas');
    if (canvas) {
      canvas.addEventListener('click', onCanvasClick);
    }

    var marker = $('yousign-sig-marker');
    if (marker) {
      marker.addEventListener('mousedown', onMoveStart);
    }

    var handle = document.querySelector('.yousign-sig-resize-handle');
    if (handle) {
      handle.addEventListener('mousedown', onResizeStart);
    }

    var prev = $('yousign-page-prev');
    var next = $('yousign-page-next');
    if (prev) {
      prev.addEventListener('click', function () {
        if (state.currentPage > 1) {
          renderPage(state.currentPage - 1);
        }
      });
    }
    if (next) {
      next.addEventListener('click', function () {
        if (state.currentPage < state.totalPages) {
          renderPage(state.currentPage + 1);
        }
      });
    }

    var fileInput = $('fichier_acte');
    if (fileInput) {
      fileInput.addEventListener('change', function () {
        var f = fileInput.files && fileInput.files[0];
        loadPdfFromFile(f);
      });
    }

    updatePager();
    updateStatus();
  }

  global.YousignPdfPlacement = {
    init: init,
    hasPlacement: function () { return !!state.placement; },
    reset: resetPlacement,
  };
})(window);
