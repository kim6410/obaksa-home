/**
 * Haptic Feedback for Obaksa
 * Provides mobile device vibration feedback on button clicks
 */

(function() {
  'use strict';

  // Check if Vibration API is available
  const isHapticSupported = () => {
    return !!navigator.vibrate || !!navigator.webkitVibrate || !!navigator.mozVibrate || !!navigator.msVibrate;
  };

  // Trigger haptic feedback
  const triggerHaptic = (duration = 50) => {
    if (!isHapticSupported()) return;
    
    const vibrator = navigator.vibrate || navigator.webkitVibrate || navigator.mozVibrate || navigator.msVibrate;
    try {
      if (vibrator && typeof vibrator.call === 'function') {
        vibrator.call(navigator, duration);
      } else if (vibrator && typeof vibrator === 'function') {
        vibrator(duration);
      }
    } catch (e) {
      // Silently fail if vibration is not supported
    }
  };

  // Initialize haptic feedback for buttons
  const initHapticButtons = () => {
    const buttons = document.querySelectorAll(
      'a.button[href^="tel:"], a.button[href*="naver.com"], a.button[href*="instagram"], a.button[href*="blog.naver"], a.button[href*="booking"], a.button[href*="daangn"], a.button[href*="litt.ly"]'
    );

    buttons.forEach(button => {
      button.addEventListener('click', () => {
        triggerHaptic(50);
      });
    });
  };

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initHapticButtons);
  } else {
    initHapticButtons();
  }
})();
