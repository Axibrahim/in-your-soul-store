/*
 * PWA glue: registers the service worker, shows an offline notice, and shows a small
 * "add to Home Screen" hint (iPhone Safari has no install button, so people need to be told how;
 * Android/Chrome gets a real Install button). No inline scripts and no innerHTML, so it works under
 * the strict script-src 'self' policy.
 */
(function () {
  'use strict';

  var root = document.documentElement;
  var standalone =
    window.navigator.standalone === true ||
    (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches);
  if (standalone) root.classList.add('is-standalone');

  /* ---------- 1. service worker ---------- */
  if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost')) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function () { /* not fatal */ });
    });
  }

  /* ---------- small helpers ---------- */
  var SVG_NS = 'http://www.w3.org/2000/svg';
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
  }
  function icon(pathData, size) {
    var svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('width', size || 18);
    svg.setAttribute('height', size || 18);
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    var path = document.createElementNS(SVG_NS, 'path');
    path.setAttribute('d', pathData);
    svg.appendChild(path);
    return svg;
  }
  var SHARE_ICON = 'M12 3v12M8 7l4-4 4 4M5 11v9h14v-9';
  var CLOSE_ICON = 'M6 6l12 12M18 6L6 18';

  var store = {
    get: function (k) { try { return window.localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { window.localStorage.setItem(k, v); } catch (e) { /* private mode */ } }
  };

  /* ---------- 2. offline notice ---------- */
  var toast = null;
  function setOffline(isOffline) {
    if (isOffline && !toast) {
      toast = el('div', 'pwa-toast', 'You are offline. Check your connection.');
      toast.setAttribute('role', 'status');
      toast.setAttribute('aria-live', 'polite');
      document.body.appendChild(toast);
    } else if (!isOffline && toast) {
      toast.remove();
      toast = null;
    }
  }
  window.addEventListener('offline', function () { setOffline(true); });
  window.addEventListener('online', function () { setOffline(false); });
  if (navigator.onLine === false) setOffline(true);

  /* ---------- 3. install hint ---------- */
  if (standalone) return;

  var path = location.pathname;
  var quiet = ['/admin', '/auth', '/cart', '/checkout'];
  for (var i = 0; i < quiet.length; i++) if (path.indexOf(quiet[i]) === 0) return;

  var DAY = 86400000;
  var snoozedUntil = parseInt(store.get('iys.install.until') || '0', 10);
  if (Date.now() < snoozedUntil) return;

  // Only ask on the 2nd visit or later: nobody wants a pop-up before they have seen the shop.
  var visits = parseInt(store.get('iys.visits') || '0', 10) + 1;
  store.set('iys.visits', String(visits));
  if (visits < 2) return;

  var ua = navigator.userAgent || '';
  var isIOS = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  var isIOSSafari = isIOS && /Safari/.test(ua) &&
    !/CriOS|FxiOS|EdgiOS|OPiOS|OPT\/|GSA|Instagram|FBAN|FBAV|Line\/|TikTok|Snapchat/.test(ua);

  var banner = null;
  var deferredPrompt = null;

  function hide(days) {
    store.set('iys.install.until', String(Date.now() + days * DAY));
    if (banner) { banner.remove(); banner = null; }
  }

  function show(buildAction) {
    if (banner) return;
    banner = el('div', 'pwa-install');
    banner.setAttribute('role', 'dialog');
    banner.setAttribute('aria-label', 'Add IN YOUR SOUL to your Home Screen');

    var img = el('img', 'pwa-install__icon');
    img.src = '/static/images/icons/icon-192.png';
    img.alt = '';
    img.width = 44;
    img.height = 44;

    var text = el('div', 'pwa-install__text');
    text.appendChild(el('strong', '', 'Add IN YOUR SOUL to your Home Screen'));
    text.appendChild(buildAction());

    var close = el('button', 'pwa-install__close');
    close.type = 'button';
    close.setAttribute('aria-label', 'Dismiss');
    close.appendChild(icon(CLOSE_ICON, 16));
    close.addEventListener('click', function () { hide(14); });

    banner.appendChild(img);
    banner.appendChild(text);
    banner.appendChild(close);
    document.body.appendChild(banner);
  }

  if (isIOSSafari) {
    setTimeout(function () {
      show(function () {
        var line = el('span');
        line.appendChild(document.createTextNode('Tap '));
        var share = el('span', 'pwa-install__share');
        share.appendChild(icon(SHARE_ICON, 16));
        line.appendChild(share);
        line.appendChild(document.createTextNode(' then \u201CAdd to Home Screen\u201D'));
        return line;
      });
    }, 4000);
  }

  // Chrome / Edge / Samsung Internet on Android and desktop
  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    deferredPrompt = e;
    setTimeout(function () {
      show(function () {
        var btn = el('button', 'pwa-install__btn', 'Install app');
        btn.type = 'button';
        btn.addEventListener('click', function () {
          if (!deferredPrompt) return;
          deferredPrompt.prompt();
          deferredPrompt.userChoice.then(function () { deferredPrompt = null; hide(14); });
        });
        return btn;
      });
    }, 4000);
  });
  window.addEventListener('appinstalled', function () { hide(365); });
})();