/* 오박사 시공 분야 아코디언
   - index.html의 #ob-service-accordion 안에서만 작동합니다.
   - 카드 전체 버튼을 누르면 상세 설명이 열리고 닫힙니다.
*/
(function(){
  function ready(fn){
    if(document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  ready(function(){
    var root = document.querySelector('#ob-service-accordion');
    if(!root) return;

    var cards = Array.prototype.slice.call(root.querySelectorAll('.ob-service-card'));
    cards.forEach(function(card){
      var btn = card.querySelector('.ob-service-toggle');
      if(!btn) return;

      btn.addEventListener('click', function(){
        var willOpen = !card.classList.contains('is-open');

        cards.forEach(function(other){
          if(other !== card){
            other.classList.remove('is-open');
            var otherBtn = other.querySelector('.ob-service-toggle');
            if(otherBtn) otherBtn.setAttribute('aria-expanded', 'false');
          }
        });

        card.classList.toggle('is-open', willOpen);
        btn.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
      });
    });
  });
})();
