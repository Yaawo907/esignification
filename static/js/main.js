/* ═══════════════════════════════════════════════════
   e-Signification Bénin — JS Principal
   Sécurité : pas d'innerHTML avec données brutes,
   échappement systématique, CSRF sur chaque requête
   ═══════════════════════════════════════════════════ */

'use strict';

/* ── Utilitaires sécurité ── */
function getCookie(name) {
  let value = null;
  document.cookie.split(';').forEach(function(c) {
    const trimmed = c.trim();
    if (trimmed.startsWith(name + '=')) {
      value = decodeURIComponent(trimmed.slice(name.length + 1));
    }
  });
  return value;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/* ── Spinner global (navigation) ── */
const spinnerGlobal = document.getElementById('spinner-global');

function showSpinner() {
  if (spinnerGlobal) spinnerGlobal.style.display = 'flex';
}

function hideSpinner() {
  if (spinnerGlobal) spinnerGlobal.style.display = 'none';
}

/* Déclenche le spinner sur tous les liens .spinner-link */
document.addEventListener('DOMContentLoaded', function() {

  /* Spinner sur liens de navigation */
  document.querySelectorAll('a.spinner-link').forEach(function(link) {
    link.addEventListener('click', function(e) {
      const href = link.getAttribute('href');
      if (!href || href.startsWith('#') || href.startsWith('javascript')) return;
      if (link.getAttribute('target') === '_blank') return;
      showSpinner();
    });
  });

  /* Masquer le spinner si retour navigateur */
  window.addEventListener('pageshow', function(e) {
    if (e.persisted) hideSpinner();
  });
  window.addEventListener('popstate', hideSpinner);

  /* ── Spinner sur boutons de formulaire (btn-spinner) ── */
  document.querySelectorAll('form').forEach(function(form) {
    form.addEventListener('submit', function() {
      const btn = form.querySelector('.btn-spinner');
      if (btn && !btn.disabled) {
        const loadingText = btn.getAttribute('data-loading') || 'Chargement…';
        const textEl = btn.querySelector('.btn-text');
        const loaderEl = btn.querySelector('.btn-loader');
        if (textEl) textEl.style.display = 'none';
        if (loaderEl) {
          loaderEl.style.display = 'inline-flex';
          loaderEl.innerHTML = '<svg class="spin-icon" viewBox="0 0 24 24" width="14" height="14"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" opacity="0.3"/><path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" stroke-width="3" fill="none" stroke-linecap="round"><animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="0.8s" repeatCount="indefinite"/></path></svg> ' + escapeHtml(loadingText);
        }
        btn.disabled = true;
      }
    });
  });

  /* ── Spinner sur boutons de téléchargement ── */
  document.querySelectorAll('a[data-loading]').forEach(function(link) {
    link.addEventListener('click', function() {
      const original = link.innerHTML;
      const loadingText = link.getAttribute('data-loading') || 'Téléchargement…';
      link.innerHTML = '<span class="dl-spin"></span> ' + escapeHtml(loadingText);
      link.style.pointerEvents = 'none';
      /* Réactiver après 8 secondes (sécurité) */
      setTimeout(function() {
        link.innerHTML = original;
        link.style.pointerEvents = '';
      }, 8000);
    });
  });

  /* ── Fermeture automatique des messages après 5s ── */
  setTimeout(function() {
    const container = document.getElementById('messages-container');
    if (container) {
      container.style.transition = 'opacity .5s';
      container.style.opacity = '0';
      setTimeout(function() { if (container) container.remove(); }, 500);
    }
  }, 5000);

  /* ── Protection XSS : nettoyer les champs texte à la soumission ── */
  document.querySelectorAll('form input[type=text], form input[type=email]').forEach(function(input) {
    input.addEventListener('blur', function() {
      this.value = this.value.trim();
    });
  });

  /* ── Accessibilité : focus trap sur modales éventuelles ── */
  document.querySelectorAll('[role=dialog]').forEach(function(modal) {
    trapFocus(modal);
  });

});

/* ── Requête AJAX sécurisée (avec CSRF) ── */
function fetchSecure(url, options) {
  const defaults = {
    headers: {
      'X-CSRFToken': getCookie('csrftoken'),
      'X-Requested-With': 'XMLHttpRequest',
    },
    credentials: 'same-origin',
  };
  const merged = Object.assign({}, defaults, options);
  if (options && options.headers) {
    merged.headers = Object.assign({}, defaults.headers, options.headers);
  }
  return fetch(url, merged);
}

/* ── Focus trap accessibilité ── */
function trapFocus(element) {
  const focusable = element.querySelectorAll('a, button, input, textarea, select, [tabindex]:not([tabindex="-1"])');
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  element.addEventListener('keydown', function(e) {
    if (e.key !== 'Tab') return;
    if (e.shiftKey) {
      if (document.activeElement === first) { last.focus(); e.preventDefault(); }
    } else {
      if (document.activeElement === last) { first.focus(); e.preventDefault(); }
    }
  });
}

/* ── Utilitaire pour construire des éléments DOM sans innerHTML ── */
function buildSearchItem(uuid, nom, email, npi, ifu, onSelect) {
  const div = document.createElement('div');
  div.className = 'search-item';
  div.setAttribute('role', 'option');
  div.setAttribute('tabindex', '0');

  const nomEl = document.createElement('strong');
  nomEl.textContent = nom;
  div.appendChild(nomEl);

  div.appendChild(document.createTextNode(' — ' + email));

  if (npi) {
    const npiEl = document.createTextNode(' | NPI: ' + npi);
    div.appendChild(npiEl);
  }
  if (ifu) {
    const ifuEl = document.createTextNode(' | IFU: ' + ifu);
    div.appendChild(ifuEl);
  }

  div.addEventListener('click', function() { onSelect(uuid, nom, email); });
  div.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' || e.key === ' ') { onSelect(uuid, nom, email); }
  });
  return div;
}

/* ── Recherche AJAX justiciable (dans le formulaire d'envoi) ── */
(function() {
  const searchInput = document.getElementById('search-just');
  const resultsDiv = document.getElementById('search-results');
  const uuidField = document.getElementById('just-uuid');
  if (!searchInput || !resultsDiv || !uuidField) return;

  let timeout;

  searchInput.addEventListener('input', function() {
    clearTimeout(timeout);
    const q = this.value.trim();
    if (q.length < 2) { resultsDiv.style.display = 'none'; resultsDiv.innerHTML = ''; return; }
    timeout = setTimeout(function() {
      fetchSecure('/api/justiciables/rechercher/?q=' + encodeURIComponent(q))
        .then(function(r) { return r.json(); })
        .then(function(data) {
          resultsDiv.innerHTML = '';
          if (!data.resultats || !data.resultats.length) {
            resultsDiv.style.display = 'none';
            return;
          }
          data.resultats.forEach(function(j) {
            const item = buildSearchItem(j.uuid, j.nom, j.email, j.npi, j.ifu, function(uuid, nom, email) {
              uuidField.value = uuid;
              searchInput.value = nom + ' — ' + email;
              resultsDiv.style.display = 'none';
              resultsDiv.innerHTML = '';
            });
            resultsDiv.appendChild(item);
          });
          resultsDiv.style.display = 'block';
        })
        .catch(function() { resultsDiv.style.display = 'none'; });
    }, 300);
  });

  /* Fermer si clic ailleurs */
  document.addEventListener('click', function(e) {
    if (!searchInput.contains(e.target) && !resultsDiv.contains(e.target)) {
      resultsDiv.style.display = 'none';
    }
  });

  /* Keyboard nav dans la liste */
  searchInput.addEventListener('keydown', function(e) {
    if (e.key === 'ArrowDown') {
      const first = resultsDiv.querySelector('.search-item');
      if (first) first.focus();
      e.preventDefault();
    }
  });
})();

/* ── Export pour usage inline dans les templates ── */
window.fetchSecure = fetchSecure;
window.escapeHtml = escapeHtml;
window.getCookie = getCookie;
window.showSpinner = showSpinner;
window.hideSpinner = hideSpinner;
