const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]')?.content;

// ── NAV SCROLL EFFECT ──────────────────────────
const navbar = document.getElementById('navbar');
if (navbar) {
  window.addEventListener('scroll', () => {
    navbar.classList.toggle('scrolled', window.scrollY > 50);
  }, { passive: true });
}

// ── MOBILE BURGER ──────────────────────────────
const burger = document.getElementById('burger');
const mobileMenu = document.getElementById('mobile-menu');
const mobileBackdrop = document.getElementById('mobile-backdrop');

let scrollLockY = 0;

function setMobileMenu(open) {
  burger.classList.toggle('active', open);
  mobileMenu.classList.toggle('open', open);
  if (mobileBackdrop) mobileBackdrop.classList.toggle('open', open);
  burger.setAttribute('aria-expanded', open ? 'true' : 'false');

  if (open) {
    scrollLockY = window.scrollY;
    document.body.style.top = `-${scrollLockY}px`;
    document.body.classList.add('nav-open');
  } else {
    document.body.classList.remove('nav-open');
    document.body.style.top = '';
    window.scrollTo(0, scrollLockY);
  }
}
if (burger && mobileMenu) {
  burger.setAttribute('aria-expanded', 'false');

  burger.addEventListener('click', () => {
    setMobileMenu(!mobileMenu.classList.contains('open'));
  });

  // Close as soon as a link is tapped, so navigation doesn't leave it open mid-transition
  mobileMenu.querySelectorAll('.nav-mobile-link').forEach(link => {
    link.addEventListener('click', () => setMobileMenu(false));
  });

  if (mobileBackdrop) {
    mobileBackdrop.addEventListener('click', () => setMobileMenu(false));
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') setMobileMenu(false);
  });

  // Swipe down anywhere on the open panel to dismiss it
  let touchStartY = null;
  let touchStartX = null;

  mobileMenu.addEventListener('touchstart', (e) => {
    if (!mobileMenu.classList.contains('open')) return;
    touchStartY = e.touches[0].clientY;
    touchStartX = e.touches[0].clientX;
  }, { passive: true });

  mobileMenu.addEventListener('touchmove', (e) => {
    // Block the page underneath from scrolling while we're mid-swipe,
    // otherwise the browser treats this as a scroll gesture instead of
    // a close gesture and the panel just sits there "stuck".
    if (mobileMenu.classList.contains('open') && touchStartY !== null) {
      e.preventDefault();
    }
  }, { passive: false });

  mobileMenu.addEventListener('touchend', (e) => {
    if (touchStartY === null) return;
    const deltaY = e.changedTouches[0].clientY - touchStartY;
    const deltaX = Math.abs(e.changedTouches[0].clientX - touchStartX);
    // Mostly-vertical downward swipe past ~50px closes it
    if (deltaY > 50 && deltaY > deltaX) {
      setMobileMenu(false);
    }
    touchStartY = null;
    touchStartX = null;
  });
}


// ── CART COUNT ─────────────────────────────────
async function updateCartCount() {
  try {
    const res = await fetch('/cart/count');
    const data = await res.json();
    const badge = document.getElementById('cart-badge');
    if (badge) {
      badge.textContent = data.count;
      badge.classList.toggle('zero', data.count === 0);
    }
  } catch (e) {}
}
updateCartCount();


// ── CLOSE SERVER-RENDERED FLASH MESSAGES ───────
document.querySelectorAll('.flash-close').forEach(btn => {
  btn.addEventListener('click', () => btn.closest('.flash').remove());
});


// ── INSTAPAY QR TOGGLE ──────────────────────────
const instapayDetails = document.getElementById('instapay-details');

function updateInstapay() {
  const selected = document.querySelector('input[name="payment_method"]:checked');
  if (!instapayDetails) return;
  if (selected && selected.value === 'instapay') {
    instapayDetails.classList.add('visible');
  } else {
    instapayDetails.classList.remove('visible');
  }
}

document.querySelectorAll('input[name="payment_method"]').forEach(input => {
  input.addEventListener('change', updateInstapay);
});

updateInstapay();


// ── AUTO-DISMISS FLASH ─────────────────────────
setTimeout(() => {
  document.querySelectorAll('.flash').forEach(el => {
    el.style.transition = 'opacity 0.5s, transform 0.5s';
    el.style.opacity = '0';
    el.style.transform = 'translateX(100%)';
    setTimeout(() => el.remove(), 500);
  });
}, 4000);

// ── SCROLL REVEAL ──────────────────────────────
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach((entry, i) => {
    if (entry.isIntersecting) {
      setTimeout(() => entry.target.classList.add('visible'), i * 80);
      revealObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.1 });

document.querySelectorAll('.reveal').forEach(el => revealObserver.observe(el));

// ── CYBER RAIN CANVAS (Matrix / hero bg) ───────
function initCyberRain(canvasId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  function resize() {
    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;
  }
  resize();
  window.addEventListener('resize', resize, { passive: true });

  const chars = 'ΔΣΩΨΦΞΛΘαβγδεζηθιKΠΠΡΣΤΥΦΧΨΩ01'.split('');
  const fontSize = 13;
  let cols = Math.floor(canvas.width / fontSize);
  let drops = Array(cols).fill(1);

  function draw() {
    ctx.fillStyle = 'rgba(4,8,4,0.05)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.font = `${fontSize}px "Space Mono", monospace`;

    drops.forEach((y, i) => {
      const char = chars[Math.floor(Math.random() * chars.length)];
      const bright = Math.random() > 0.95;
      ctx.fillStyle = bright ? '#76ff03' : '#1a3a1a';
      ctx.fillText(char, i * fontSize, y * fontSize);

      if (y * fontSize > canvas.height && Math.random() > 0.975) {
        drops[i] = 0;
      }
      drops[i]++;
    });
  }

  let animId = setInterval(draw, 55);

  // Pause when hidden
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) clearInterval(animId);
    else animId = setInterval(draw, 55);
  });
}

initCyberRain('cyber-canvas');

// ── PRODUCT GALLERY THUMBS ─────────────────────
document.querySelectorAll('.product-thumb').forEach(thumb => {
  thumb.addEventListener('click', () => {
    const src = thumb.dataset.src;
    const mainImg = document.getElementById('main-product-img');
    if (mainImg && src) {
      mainImg.src = src;
      document.querySelectorAll('.product-thumb').forEach(t => t.classList.remove('active'));
      thumb.classList.add('active');
    }
  });
});

// ── SIZE SELECTOR ──────────────────────────────
document.querySelectorAll('.size-btn').forEach(btn => {
  if (btn.disabled) return;
  btn.addEventListener('click', () => {
    document.querySelectorAll('.size-btn').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
    const sizeInput = document.getElementById('selected-size');
    if (sizeInput) sizeInput.value = btn.dataset.size;
  });
});

// ── ADD TO CART ────────────────────────────────
const addToCartForm = document.getElementById('add-to-cart-form');
if (addToCartForm) {
  addToCartForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const sizeInput = document.getElementById('selected-size');
    if (!sizeInput?.value) {
      showToast('Please select a size.', 'danger');
      return;
    }

    const btn = addToCartForm.querySelector('[type="submit"]');
    btn.disabled = true;
    const originalText = btn.innerHTML;
    btn.innerHTML = '<span>ADDING...</span>';

    try {
      const formData = new FormData(addToCartForm);
      const res = await fetch('/cart/add', { method: 'POST', body: formData });
      const data = await res.json();

      if (data.success) {
        showToast(data.message, 'success');
        updateCartCount();
        btn.innerHTML = '<span>ADDED ✓</span>';
        setTimeout(() => { btn.innerHTML = originalText; btn.disabled = false; }, 2000);
      } else {
        showToast(data.message, 'danger');
        btn.innerHTML = originalText;
        btn.disabled = false;
      }
    } catch {
      showToast('Something went wrong.', 'danger');
      btn.innerHTML = originalText;
      btn.disabled = false;
    }
  });
}

// ── NEW: BUY NOW ─────────────────────────────────
const buyNowBtn = document.getElementById('buy-now-btn');
if (buyNowBtn) {
  buyNowBtn.addEventListener('click', async () => {
    const sizeInput = document.getElementById('selected-size');
    if (!sizeInput?.value) {
      showToast('Please select a size.', 'danger');
      return;
    }

    buyNowBtn.disabled = true;
    const originalText = buyNowBtn.innerHTML;
    buyNowBtn.innerHTML = '<span>ADDING...</span>';

    try {
      const formData = new FormData();
      formData.append('product_id', buyNowBtn.dataset.productId);
      formData.append('size', sizeInput.value);
      formData.append('quantity', 1);
      formData.append('csrf_token', CSRF_TOKEN);

      const res = await fetch('/cart/add', { method: 'POST', body: formData });
      const data = await res.json();

      if (data.success) {
        window.location.href = '/cart/checkout';
      } else {
        showToast(data.message, 'danger');
        buyNowBtn.innerHTML = originalText;
        buyNowBtn.disabled = false;
      }
    } catch {
      showToast('Something went wrong.', 'danger');
      buyNowBtn.innerHTML = originalText;
      buyNowBtn.disabled = false;
    }
  });
}

// ── TOAST ──────────────────────────────────────
function showToast(message, type = 'success') {
  const container = document.getElementById('flash-container') || (() => {
    const el = document.createElement('div');
    el.id = 'flash-container';
    el.className = 'flash-container';
    document.body.appendChild(el);
    return el;
  })();

  const flash = document.createElement('div');
  flash.className = `flash flash--${type}`;
const span = document.createElement('span');
span.textContent = message;
const closeBtn = document.createElement('button');
closeBtn.textContent = '✕';
closeBtn.addEventListener('click', () => flash.remove());
flash.appendChild(span);
flash.appendChild(closeBtn);  
container.appendChild(flash);

  setTimeout(() => {
    flash.style.opacity = '0';
    flash.style.transform = 'translateX(100%)';
    flash.style.transition = 'opacity 0.4s, transform 0.4s';
    setTimeout(() => flash.remove(), 400);
  }, 3000);
}

// ── ADMIN PRODUCT TOGGLE ───────────────────────
document.querySelectorAll('.toggle-product-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const productId = btn.dataset.id;
    try {
   const res = await fetch(`/admin/products/${productId}/toggle`, {
    method: 'POST',
    headers: { 'X-CSRFToken': CSRF_TOKEN }
        });
      const data = await res.json();
      if (data.success) {
        const badge = btn.closest('tr').querySelector('.product-status-badge');
        if (badge) {
          badge.textContent = data.is_active ? 'ACTIVE' : 'INACTIVE';
          badge.className = `badge ${data.is_active ? 'badge--success' : 'badge--muted'} product-status-badge`;
        }
        btn.textContent = data.is_active ? 'Deactivate' : 'Activate';
        showToast(`Product ${data.is_active ? 'activated' : 'deactivated'}.`);
      }
    } catch {
      showToast('Failed to update product.', 'danger');
    }
  });
});

// ── ADMIN USER TOGGLE ──────────────────────────
document.querySelectorAll('.toggle-admin-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const userId = btn.dataset.id;
    try {
      const res = await fetch(`/admin/users/${userId}/toggle-admin`, {
        method: 'POST',
        headers: { 'X-CSRFToken': CSRF_TOKEN }
      });
      const data = await res.json();
      if (data.success) {
        btn.textContent = data.is_admin ? 'Remove Admin' : 'Make Admin';
        showToast('User role updated.');
      }
    } catch {
      showToast('Failed to update user.', 'danger');
    }
  });
});

// ── SET DEFAULT ADDRESS ────────────────────────
document.querySelectorAll('.set-default-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const addrId = btn.dataset.id;
    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
    try {
      const res = await fetch(`/account/addresses/${addrId}/set-default`, {
        method: 'POST',
        headers: {
          'X-CSRFToken': csrfToken
        }
      });
      const data = await res.json();
      if (data.success) {
        document.querySelectorAll('.default-badge').forEach(b => b.remove());
        btn.insertAdjacentHTML('beforebegin', '<span class="badge badge--success default-badge">DEFAULT</span>');
        showToast('Default address updated.');
      }
    } catch {
      showToast('Failed to update.', 'danger');
    }
  });
});

// ── PRODUCT CARD PULSE EFFECT ──────────────────
document.querySelectorAll('.product-card').forEach((card, i) => {
  // Staggered entrance
  card.style.animationDelay = `${i * 0.05}s`;

  // Alive hover glow pulse
  card.addEventListener('mouseenter', () => {
    card.style.boxShadow = '0 0 30px rgba(118,255,3,0.2), 0 0 80px rgba(118,255,3,0.05)';
  });
  card.addEventListener('mouseleave', () => {
    card.style.boxShadow = '';
  });
});


// ── CLICKABLE PRODUCT CARDS ─────────────────────
document.querySelectorAll('.product-card[data-href]').forEach(card => {
  card.addEventListener('click', (e) => {
    if (e.target.closest('a')) return; // let the real link handle its own click
    window.location.href = card.dataset.href;
  });
});

// ── NEW: HOMEPAGE HERO LOGO FADE + CLICKABLE CARDS ──
(() => {
  const hero = document.querySelector('.hero');
  const logo = document.querySelector('.hero-background-logo');
  const cards = document.querySelectorAll('.product-card--clickable');

  const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

  const updateHeroLogo = () => {
    if (!hero || !logo) return;
    const rect = hero.getBoundingClientRect();
    const fadeDistance = Math.max(hero.offsetHeight * 0.65, window.innerHeight * 0.65);
    const progress = clamp((-rect.top) / fadeDistance, 0, 1);
    logo.style.opacity = String(0.13 * (1 - progress));
  };

  let heroTicking = false;
  const onHeroScroll = () => {
    if (heroTicking) return;
    heroTicking = true;
    window.requestAnimationFrame(() => {
      updateHeroLogo();
      heroTicking = false;
    });
  };

  updateHeroLogo();
  window.addEventListener('scroll', onHeroScroll, { passive: true });
  window.addEventListener('resize', updateHeroLogo);

  cards.forEach((card) => {
    const url = card.dataset.productUrl;
    if (!url) return;
    card.addEventListener('click', (event) => {
      if (event.target.closest('a, button, input, select, textarea')) return;
      window.location.href = url;
    });
    card.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      if (event.target.closest('a, button, input, select, textarea')) return;
      event.preventDefault();
      window.location.href = url;
    });
  });
})();

// ── SMOOTH ANCHOR SCROLL ───────────────────────
document.querySelectorAll('a[href^="#"]').forEach(link => {
  link.addEventListener('click', e => {
    const target = document.querySelector(link.getAttribute('href'));
    if (target) {
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
});

// ── CHECKOUT ADDRESS TOGGLE ────────────────────
const savedAddressRadio = document.getElementById('use-saved-address');
const newAddressRadio = document.getElementById('use-new-address');
const savedSection = document.getElementById('saved-address-section');
const newSection = document.getElementById('new-address-section');

// The new-address fields carry `required` in the HTML so the form still
// validates correctly for stores with no saved addresses (where this toggle
// doesn't render at all and the fields are always visible). But when the
// toggle IS present and "USE SAVED ADDRESS" is selected, #new-address-section
// is hidden via display:none while its inputs are still required - the
// browser then refuses to submit (native validation tries to focus a hidden
// field and can't), silently blocking checkout for anyone with a saved
// address. Keep `required` in sync with which section is actually visible.
function setNewAddressRequired(isRequired) {
  if (!newSection) return;
  newSection.querySelectorAll('input[name]').forEach(input => {
    if (['street', 'building', 'floor', 'district', 'governorate'].includes(input.name)) {
      input.required = isRequired;
    }
  });
}

if (savedAddressRadio && newAddressRadio) {
  savedAddressRadio.addEventListener('change', () => {
    if (savedSection) savedSection.style.display = '';
    if (newSection) newSection.style.display = 'none';
    setNewAddressRequired(false);
  });
  newAddressRadio.addEventListener('change', () => {
    if (savedSection) savedSection.style.display = 'none';
    if (newSection) newSection.style.display = '';
    setNewAddressRequired(true);
  });
  // Sync on load to match whichever radio is checked by default
  // (USE SAVED ADDRESS, which is why this was broken on first load).
  setNewAddressRequired(newAddressRadio.checked);
}


// ── QUANTITY CONTROLS (cart) ───────────────────
document.querySelectorAll('.qty-form').forEach(form => {
  const input = form.querySelector('.qty-value-input');
  const display = form.querySelector('.qty-value');
  const minusBtn = form.querySelector('.qty-minus');
  const plusBtn = form.querySelector('.qty-plus');

  if (!input) return;

  function syncDisplay() {
    if (display) display.textContent = input.value;
  }

  minusBtn?.addEventListener('click', () => {
    const val = parseInt(input.value) - 1;
    if (val >= 0) { input.value = val; syncDisplay(); form.submit(); }
  });

  plusBtn?.addEventListener('click', () => {
    input.value = parseInt(input.value) + 1;
    syncDisplay();
    form.submit();
  });
});

// ── ADMIN IMAGE PREVIEW ────────────────────────
document.querySelectorAll('input[type="file"][accept*="image"]').forEach(input => {
  input.addEventListener('change', () => {
    const previewId = input.dataset.preview;
    if (!previewId) return;
    const preview = document.getElementById(previewId);
    const file = input.files[0];
    if (file && preview) {
      const reader = new FileReader();
      reader.onload = e => { preview.src = e.target.result; preview.style.display = 'block'; };
      reader.readAsDataURL(file);
    }
  });
});

// ── LIVING HEARTBEAT (ambient page pulse) ─────
// Subtle scanline sweep on panels
let scanPos = -200;
function scanSweep() {
  scanPos = (scanPos + 0.3) % (window.innerHeight + 400);
  const scanLine = document.getElementById('scan-line');
  if (scanLine) scanLine.style.top = `${scanPos}px`;
  requestAnimationFrame(scanSweep);
}
// Only run if reduced-motion not preferred
if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
  const scanLine = document.createElement('div');
  scanLine.id = 'scan-line';
  scanLine.style.cssText = `
    position: fixed; left: 0; right: 0; height: 1px;
    background: linear-gradient(90deg, transparent, rgba(118,255,3,0.04), transparent);
    pointer-events: none; z-index: 9998;
    mix-blend-mode: screen;
  `;
  document.body.appendChild(scanLine);
  scanSweep();
}

// ── CONFIRM-BEFORE-SUBMIT (delete buttons, etc.) ───────────────
document.querySelectorAll('form[data-confirm]').forEach((form) => {
  form.addEventListener('submit', (e) => {
    if (!confirm(form.dataset.confirm)) {
      e.preventDefault();
    }
  });
});

// ── HIDE IMAGE IF IT FAILS TO LOAD ─────────────────────────────
document.querySelectorAll('img[data-hide-on-error]').forEach((img) => {
  img.addEventListener('error', () => {
    img.style.display = 'none';
  });
});

// ── ADMIN MOBILE NAV DROPDOWN ──────────────────
(function () {
  var adminBurger = document.getElementById('admin-burger');
  var adminSidebar = document.getElementById('admin-sidebar');
  var adminBackdrop = document.getElementById('admin-sidebar-backdrop');
  if (!adminBurger || !adminSidebar) return;

  function setAdminMenu(open) {
    adminBurger.classList.toggle('active', open);
    adminSidebar.classList.toggle('open', open);
    if (adminBackdrop) adminBackdrop.classList.toggle('open', open);
    document.body.classList.toggle('nav-open', open);
    adminBurger.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  adminBurger.addEventListener('click', function () {
    setAdminMenu(!adminSidebar.classList.contains('open'));
  });

  adminSidebar.querySelectorAll('.admin-nav-item').forEach(function (link) {
    link.addEventListener('click', function () { setAdminMenu(false); });
  });

  if (adminBackdrop) {
    adminBackdrop.addEventListener('click', function () { setAdminMenu(false); });
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') setAdminMenu(false);
  });
})();