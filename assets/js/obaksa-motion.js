/*
  오박사만능인테리어 반응형 스크롤 모션
  - PC와 모바일 모두 IntersectionObserver로 가볍게 동작
  - IntersectionObserver 기반이라 가볍게 동작
*/
(function () {
  'use strict';

  var canAnimate = window.matchMedia && window.matchMedia('(min-width: 320px)').matches;
  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  if (!canAnimate || reduceMotion) return;

  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  }

  ready(function () {
    document.body.classList.add('ob-motion-ready');

    var selectors = [
      '.wrapper > .inner > h2',
      '.wrapper > .inner > h3',
      '.wrapper > .inner > p',
      '.wrapper > .inner > .major',
      '.wrapper > .inner > .actions',
      '.spotlight .content',
      '.spotlight .image',
      '.items.style1 > section',
      '.items.style1 > *',
      '.ob-card-grid > div',
      '.ob-channel-list > li',
      '.gallery article',
      '.ob-real-case-slider article',
      '.ob-real-gallery .major',
      '.ob-contact-card',
      '.ob-map-wrap',
      'form',
      'table'
    ];

    var nodes = Array.prototype.slice.call(document.querySelectorAll(selectors.join(',')));
    var filtered = nodes.filter(function (el, index, arr) {
      if (!el || el.closest('.ob-site-header') || el.closest('.ob-hero') || el.closest('.ob-subhero')) return false;
      return arr.indexOf(el) === index;
    });

    filtered.forEach(function (el, index) {
      el.classList.add('ob-reveal');
      el.style.setProperty('--ob-reveal-delay', Math.min((index % 6) * 70, 350) + 'ms');
    });

    if (!('IntersectionObserver' in window)) {
      filtered.forEach(function (el) { el.classList.add('is-visible'); });
      return;
    }

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    }, {
      root: null,
      threshold: 0.14,
      rootMargin: '0px 0px -7% 0px'
    });

    filtered.forEach(function (el) { observer.observe(el); });
  });
})();
