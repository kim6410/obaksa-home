/**
 * Obaksa Haptic Feedback v2
 * - 주요 CTA/버튼/링크형 버튼 전체에 모바일 진동 피드백 적용
 * - 지원하지 않는 브라우저에서는 조용히 무시
 */
(function () {
  'use strict';

  function getVibrator() {
    return navigator.vibrate || navigator.webkitVibrate || navigator.mozVibrate || navigator.msVibrate;
  }

  function isHapticSupported() {
    return typeof getVibrator() === 'function';
  }

  function triggerHaptic(pattern) {
    if (!isHapticSupported()) return;
    try {
      getVibrator().call(navigator, pattern || 42);
    } catch (error) {
      // 미지원 기기에서는 아무 일도 하지 않습니다.
    }
  }

  function isInteractiveTarget(el) {
    if (!el || !el.matches) return false;
    return el.matches([
      'a.button',
      'button',
      '[role="button"]',
      '.button',
      '.ob-floating-call',
      '.ob-call-mini',
      '.ob-channel-list a',
      '.ob-big-links a',
      '.actions a',
      'a[href^="tel:"]',
      'a[href^="mailto:"]',
      'a[href*="kko.to"]',
      'a[href*="map.kakao"]',
      'a[href*="naver"]',
      'a[href*="instagram"]',
      'a[href*="daangn"]',
      'a[href*="litt.ly"]',
      'a[href*="google"]'
    ].join(','));
  }

  function bindHaptic() {
    document.addEventListener('pointerdown', function (event) {
      const target = event.target && event.target.closest ? event.target.closest('a, button, [role="button"], .button') : null;
      if (!target || !isInteractiveTarget(target)) return;
      triggerHaptic(38);
    }, { passive: true });

    document.addEventListener('click', function (event) {
      const target = event.target && event.target.closest ? event.target.closest('a, button, [role="button"], .button') : null;
      if (!target || !isInteractiveTarget(target)) return;
      triggerHaptic([18, 28]);
    }, { passive: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindHaptic, { once: true });
  } else {
    bindHaptic();
  }
})();
