/* =========================================================
   오박사 공통 푸터 로더
   - 모든 HTML 페이지는 <div id="obaksa-footer"></div>만 둡니다.
   - 실제 푸터 내용은 /footer.html 한 곳에서만 관리합니다.
   - 푸터 삽입 후 세계 시계/날씨 스크립트를 자동 실행합니다.
   ========================================================= */
(function(){
  'use strict';

  var target = document.getElementById('obaksa-footer');
  if(!target) return;

  var footerSrc = target.getAttribute('data-footer-src') || 'footer.html';
  var worldScriptSrc = 'assets/js/obaksa-world-footer.js';

  function loadWorldFooterScript(){
    if(document.querySelector('script[data-obaksa-world-footer="loaded"]')){
      if(window.ObaksaWorldFooter && typeof window.ObaksaWorldFooter.init === 'function'){
        window.ObaksaWorldFooter.init();
      }
      return;
    }

    var script = document.createElement('script');
    script.src = worldScriptSrc;
    script.defer = true;
    script.setAttribute('data-obaksa-world-footer', 'loaded');
    document.body.appendChild(script);
  }

  function injectFooter(html){
    target.outerHTML = html;
    loadWorldFooterScript();
  }

  function fallbackFooter(){
    injectFooter(
      '<footer class="wrapper style1 align-center ob-footer">' +
        '<div class="inner">' +
          '<h2>오박사만능인테리어</h2>' +
          '<p>울산 생활 집수리, 욕실수리, 인테리어 보수 상담은 010-8284-5584로 문의해주세요.</p>' +
        '</div>' +
      '</footer>'
    );
  }

  fetch(footerSrc, { cache: 'no-store' })
    .then(function(res){
      if(!res.ok) throw new Error('footer load ' + res.status);
      return res.text();
    })
    .then(injectFooter)
    .catch(function(err){
      if(window.console) console.warn('[obaksa-footer-loader]', err);
      fallbackFooter();
    });
})();
