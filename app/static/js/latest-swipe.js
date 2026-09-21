// Latest Hits — centered swipe carousel (latest_products_swipe_cards)
// Loaded by templates/partials/latest_products_swipe_cards.html.
// External file on purpose: the site CSP is script-src 'self' (no inline JS).
(() => {
  'use strict';

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  const clamp = (v, min, max) => Math.min(Math.max(v, min), max);

  document.querySelectorAll('[data-latest-swipe]').forEach(initSection);

  function initSection(section) {
    const track = section.querySelector('[data-ls-track]');
    const slides = Array.from(section.querySelectorAll('.ls-slide'));
    if (!track || !slides.length) return;

    const dots = Array.from(section.querySelectorAll('[data-ls-dot]'));
    const prev = section.querySelector('[data-ls-prev]');
    const next = section.querySelector('[data-ls-next]');
    const video = section.querySelector('video.ls-bg-media');

    // position of each card, used by the CSS to stagger the entry pop (--ls-i)
    slides.forEach((slide, i) => slide.style.setProperty('--ls-i', i));

    let active = -1;
    let ticking = false;
    let punchTimer = 0;

    const slideCenter = (i) => slides[i].offsetLeft + slides[i].offsetWidth / 2;

    function goTo(i, instant) {
      const index = clamp(i, 0, slides.length - 1);
      track.scrollTo({
        left: slideCenter(index) - track.clientWidth / 2,
        behavior: instant || reduceMotion ? 'auto' : 'smooth',
      });
    }

    // ── POP ON SWIPE ───────────────────────────────────────
    // Restarts the "punch" (scale overshoot + ring) on the card that just landed
    // in the middle. Removed again when its animation ends.
    function punch(slide) {
      slide.classList.remove('ls-punch');
      void slide.offsetWidth;                 // restart the animation
      slide.classList.add('ls-punch');
      window.setTimeout(() => slide.classList.remove('ls-punch'), 1000);   // safety net
    }

    slides.forEach((slide) => {
      slide.addEventListener('animationend', (e) => {
        if (e.animationName === 'ls-punch') slide.classList.remove('ls-punch');
      });
    });

    // Runs on every scroll frame: the closer a card is to the middle, the
    // bigger / brighter / flatter it gets (CSS reads --ls-d and --ls-s).
    function update() {
      ticking = false;
      const mid = track.scrollLeft + track.clientWidth / 2;
      const gap = parseFloat(getComputedStyle(track).columnGap) || 0;
      let best = 0;
      let bestDist = Infinity;

      slides.forEach((slide, i) => {
        const dist = slideCenter(i) - mid;
        const offset = dist / (slide.offsetWidth + gap);
        slide.style.setProperty('--ls-d', clamp(Math.abs(offset), 0, 2).toFixed(3));
        slide.style.setProperty('--ls-s', offset < 0 ? -1 : 1);
        if (Math.abs(dist) < bestDist) {
          bestDist = Math.abs(dist);
          best = i;
        }
      });

      // how far the whole row is scrolled (0..1) - the background drifts with it
      const maxScroll = track.scrollWidth - track.clientWidth;
      section.style.setProperty('--ls-p', maxScroll > 0 ? (track.scrollLeft / maxScroll).toFixed(3) : '0.5');

      if (best !== active) {
        const firstRun = active === -1;
        active = best;
        slides.forEach((s, i) => s.classList.toggle('is-active', i === best));
        dots.forEach((d, i) => {
          d.classList.toggle('is-active', i === best);
          if (i === best) d.setAttribute('aria-current', 'true');
          else d.removeAttribute('aria-current');
        });
        if (prev) prev.disabled = best === 0;
        if (next) next.disabled = best === slides.length - 1;

        // pop the card once the swipe settles on it (not on page load, not mid-fling)
        window.clearTimeout(punchTimer);
        if (!firstRun && !reduceMotion && section.classList.contains('is-in')) {
          const landed = slides[best];
          punchTimer = window.setTimeout(() => {
            if (slides[active] === landed) punch(landed);
          }, 140);
        }
      }
    }

    function requestUpdate() {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(update);
    }

    track.addEventListener('scroll', requestUpdate, { passive: true });
    window.addEventListener('resize', requestUpdate);
    window.addEventListener('load', requestUpdate);

    if (prev) prev.addEventListener('click', () => goTo(active - 1));
    if (next) next.addEventListener('click', () => goTo(active + 1));
    dots.forEach((dot, i) => dot.addEventListener('click', () => goTo(i)));

    track.addEventListener('keydown', (e) => {
      if (e.target !== track) return;           // let cards handle their own Enter/Space
      if (e.key === 'ArrowLeft') { e.preventDefault(); goTo(active - 1); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); goTo(active + 1); }
      else if (e.key === 'Home') { e.preventDefault(); goTo(0); }
      else if (e.key === 'End') { e.preventDefault(); goTo(slides.length - 1); }
    });

    // Tapping a side card brings it to the middle first; tapping the centered
    // card opens it (handled by the existing .product-card--clickable code in main.js).
    track.addEventListener('click', (e) => {
      const slide = e.target.closest('.ls-slide');
      if (!slide) return;
      const i = slides.indexOf(slide);
      if (i !== active) {
        e.preventDefault();
        e.stopPropagation();
        goTo(i);
      }
    }, true);

    // ── GLASS TILT (mouse only) ────────────────────────────
    // While hovering a card it tilts toward the cursor and a soft glare follows it.
    // CSS reads --ls-rx / --ls-ry (tilt) and --mx / --my (glare position).
    if (finePointer && !reduceMotion) {
      slides.forEach((slide) => {
        const card = slide.querySelector('.product-card');
        if (!card) return;
        let frame = 0;
        let lastEvent = null;

        const reset = () => {
          if (frame) { window.cancelAnimationFrame(frame); frame = 0; }
          ['--ls-rx', '--ls-ry', '--mx', '--my'].forEach((p) => card.style.removeProperty(p));
        };

        card.addEventListener('pointermove', (e) => {
          if (e.pointerType && e.pointerType !== 'mouse') return;
          lastEvent = e;
          if (frame) return;
          frame = window.requestAnimationFrame(() => {
            frame = 0;
            const r = card.getBoundingClientRect();
            if (!r.width || !r.height) return;
            const px = clamp((lastEvent.clientX - r.left) / r.width, 0, 1);
            const py = clamp((lastEvent.clientY - r.top) / r.height, 0, 1);
            card.style.setProperty('--ls-ry', ((px - 0.5) * 14).toFixed(2) + 'deg');
            card.style.setProperty('--ls-rx', ((0.5 - py) * 14).toFixed(2) + 'deg');
            card.style.setProperty('--mx', (px * 100).toFixed(1) + '%');
            card.style.setProperty('--my', (py * 100).toFixed(1) + '%');
          });
        });

        card.addEventListener('pointerleave', reset);
      });
    }

    update();

    // ── POP ON ENTRY ───────────────────────────────────────
    // Adds .is-in when the section scrolls into view and removes it once it is
    // fully off-screen, so the pop replays every time you come back to it.
    section.classList.add('ls-ready');

    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.intersectionRatio >= 0.2) {
            section.classList.add('is-in');
          } else if (entry.intersectionRatio === 0) {
            section.classList.remove('is-in');
          }
          if (video) {
            if (entry.isIntersecting && !reduceMotion) video.play().catch(() => {});
            else video.pause();
          }
        });
      }, { threshold: [0, 0.2] });
      observer.observe(section);
    } else {
      section.classList.add('is-in');
      if (video && !reduceMotion) video.play().catch(() => {});
    }
  }
})();