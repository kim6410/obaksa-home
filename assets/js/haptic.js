/**
 * Haptic Feedback for Obaksa
 * 모든 주요 버튼/링크에 모바일 햅틱 피드백을 적용합니다.
 * 지원하지 않는 브라우저에서는 조용히 무시됩니다.
 */
(function () {
  "use strict";

  function isHapticSupported() {
    return typeof navigator !== "undefined" && typeof navigator.vibrate === "function";
  }

  function triggerHaptic(duration) {
    if (!isHapticSupported()) return;
    try {
      navigator.vibrate(duration || 22);
    } catch (e) {
      // 지원하지 않거나 브라우저가 차단하면 아무 작업도 하지 않습니다.
    }
  }

  function isPrimaryPointerEvent(event) {
    if (!event) return true;
    if (event.pointerType && event.pointerType !== "touch" && event.pointerType !== "pen") return false;
    return true;
  }

  function bindHaptic() {
    var selector = [
      "a.button",
      "button",
      ".button",
      ".ob-nav a",
      ".ob-call-mini",
      ".ob-floating-call",
      ".ob-channel-list a",
      ".ob-big-links a",
      "a[href^='tel:']",
      "a[href^='sms:']",
      "a[href*='naver']",
      "a[href*='instagram']",
      "a[href*='daangn']",
      "a[href*='litt.ly']",
      "a[href*='google']"
    ].join(",");

    var targets = document.querySelectorAll(selector);

    targets.forEach(function (el) {
      if (el.dataset.obHapticBound === "1") return;
      el.dataset.obHapticBound = "1";

      el.addEventListener("pointerdown", function (event) {
        if (!isPrimaryPointerEvent(event)) return;
        triggerHaptic(18);
      }, { passive: true });

      el.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          triggerHaptic(12);
        }
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindHaptic);
  } else {
    bindHaptic();
  }

  window.ObaksaHaptic = {
    trigger: triggerHaptic,
    refresh: bindHaptic
  };
})();
