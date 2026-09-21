// Latest Hits — centered swipe carousel (latest_products_swipe_cards)
// Loaded by templates/partials/latest_products_swipe_cards.html.
// External file on purpose: the site CSP is script-src 'self' (no inline JS).
(() => {
  'use strict';

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
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

    let active = -1;
    let ticking = false;

    const slideCenter = (i) => slides[i].offsetLeft + slides[i].offsetWidth / 2;

    function goTo(i, instant) {
      const index = clamp(i, 0, slides.length - 1);
      track.scrollTo({
        left: slideCenter(index) - track.clientWidth / 2,
        behavior: instant || reduceMotion ? 'auto' : 'smooth',
      });
    }

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

      if (best !== active) {
        active = best;
        slides.forEach((s, i) => s.classList.toggle('is-active', i === best));
        dots.forEach((d, i) => {
          d.classList.toggle('is-active', i === best);
          if (i === best) d.setAttribute('aria-current', 'true');
          else d.removeAttribute('aria-current');
        });
        if (prev) prev.disabled = best === 0;
        if (next) next.disabled = best === slides.length - 1;
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

    update();

    // ── POP ────────────────────────────────────────────────
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