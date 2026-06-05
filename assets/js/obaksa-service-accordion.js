/* =========================================================
   오박사 시공 분야 아코디언
   - 한 번에 하나의 카드만 펼쳐져서 모바일 화면이 길어지지 않도록 관리합니다.
   - details/summary 기본 기능을 사용하므로 스크립트가 꺼져도 내용 확인은 가능합니다.
   ========================================================= */
(function(){
  'use strict';

  var cards = Array.prototype.slice.call(document.querySelectorAll('.ob-service-accordion .ob-service-card'));
  if(!cards.length) return;

  cards.forEach(function(card){
    card.addEventListener('toggle', function(){
      if(!card.open) return;
      cards.forEach(function(other){
        if(other !== card) other.open = false;
      });
    });
  });
})();
