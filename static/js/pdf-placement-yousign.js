'use strict';

/**
 * Aperçu PDF + choix de l'emplacement de signature Yousign (coordonnées API v3).
 * Nécessite pdf.js (pdfjsLib) chargé avant ce script.
 */
(function (global) {
  var SIG_W = 120;
  var SIG_H = 60;

  var state = {
    pdfDoc: null,
    currentPage: 1,
    totalPages: 0,
    scale: 1,
    pageViewport: null,
    placement: null,
    onChange: null,
  };

  function $(id) { return document.getElementById(id); }

  function emitChange() {
    if (typeof state.onChange === 'function') {
      state.onChange(!!state.placement);
    }
  }

  function setHiddenFields(page, x, y) {
    var fp = $('yousign_sig_page');
    var fx = $('yousign_sig_x');
    var fy = $('yousign_sig_y');
    var fw = $('yousign_sig_width');
    var fh = $('yousign_sig_height');
    if (fp) fp.value = String(page);
    if (fx) fx.value = String(Math.round(x));
    if (fy) fy.value = String(Math.round(y));
    if (fw) fw.value = String(SIG_W);
    if (fh) fh.value = String(SIG_H);
  }

  function clearHiddenFields() {
    ['yousign_sig_page', 'yousign_sig_x', 'yousign_sig_y'].forEach(function (id) {
      var el = $(id);
      if (el) el.value = '';
    });
  }

  function updateStatus() {
    var el = $('yousign-placement-status');
    if (!el) return;
    if (!state.placement) {
      el.textContent = 'Cliquez sur le document pour placer votre signature électronique.';
      el.style.color = 'var(--text-secondary)';
      return;
    }
    el.textContent = '✓ Page ' + state.placement.page + ' — position (' +
      state.placement.x + ', ' + state.placement.y + ')';
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

  function positionMarker(canvas, marker, pdfX, pdfY) {
    if (!state.pageViewport || !marker || !canvas) return;
    var scaleX = canvas.width / state.pageViewport.width;
    var scaleY = canvas.height / state.pageViewport.height;
    marker.style.display = 'flex';
    marker.style.left = (pdfX * scaleX) + 'px';
    marker.style.top = (pdfY * scaleY) + 'px';
    marker.style.width = (SIG_W * scaleX) + 'px';
    marker.style.height = (SIG_H * scaleY) + 'px';
  }

  function hideMarker() {
    var marker = $('yousign-sig-marker');
    if (marker) marker.style.display = 'none';
  }

  function clampField(x, y) {
    var maxX = Math.max(0, state.pageViewport.width - SIG_W);
    var maxY = Math.max(0, state.pageViewport.height - SIG_H);
    return {
      x: Math.min(Math.max(0, x), maxX),
      y: Math.min(Math.max(0, y), maxY),
    };
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
          positionMarker(canvas, $('yousign-sig-marker'), state.placement.x, state.placement.y);
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
    var topLeft = clampField(pdfX - SIG_W / 2, pdfY - SIG_H / 2);

    state.placement = {
      page: state.currentPage,
      x: Math.round(topLeft.x),
      y: Math.round(topLeft.y),
    };
    setHiddenFields(state.placement.page, state.placement.x, state.placement.y);
    positionMarker(canvas, $('yousign-sig-marker'), state.placement.x, state.placement.y);
    updateStatus();
    emitChange();
  }

  function resetPlacement() {
    state.placement = null;
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
      state.currentPage = 1;
      if (statusLoad) statusLoad.style.display = 'none';
      return renderPage(1);
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

  function init(options) {
    options = options || {};
    state.onChange = options.onChange || null;

    if (global.pdfjsLib) {
      global.pdfjsLib.GlobalWorkerOptions.workerSrc =
        'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
    }

    var canvas = $('yousign-pdf-canvas');
    if (canvas) {
      canvas.addEventListener('click', onCanvasClick);
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
