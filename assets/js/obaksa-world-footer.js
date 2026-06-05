/* =========================================================
   오박사 공통 푸터 · 세계 시계 / 날씨 위젯
   관리자 설정은 이 상단 영역에서만 수정하면 됩니다.
   ========================================================= */
(function(){
  'use strict';

  const CONFIG = {
    weatherApiKey: '892368a2bd0f493aa603c7d62a049df2',
    refreshMinutes: 10,
    cities: [
      { id:'ulsan', label:'대한민국 울산', tz:'Asia/Seoul', lat:35.5384, lon:129.3114 },
      { id:'hanoi', label:'베트남 하노이', tz:'Asia/Ho_Chi_Minh', lat:21.0278, lon:105.8342 },
      { id:'london', label:'영국 런던', tz:'Europe/London', lat:51.5072, lon:-0.1276 },
      { id:'washington', label:'미국 워싱턴 D.C.', tz:'America/New_York', lat:38.9072, lon:-77.0369 },
      { id:'tehran', label:'이란 테헤란', tz:'Asia/Tehran', lat:35.6892, lon:51.3890 },
      { id:'jerusalem', label:'이스라엘 예루살렘', tz:'Asia/Jerusalem', lat:31.7683, lon:35.2137 }
    ]
  };

  const roots = Array.from(document.querySelectorAll('.ob-world-footer'));
  if(!roots.length) return;

  function pad(n){ return String(n).padStart(2,'0'); }

  function timeParts(tz){
    const parts = new Intl.DateTimeFormat('en-GB', {
      timeZone:tz, hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false
    }).formatToParts(new Date());
    const map = {};
    parts.forEach(function(p){ if(p.type !== 'literal') map[p.type] = p.value; });
    return { h:Number(map.hour), m:Number(map.minute), s:Number(map.second) };
  }

  function timeText(tz){
    const t = timeParts(tz);
    return pad(t.h) + ':' + pad(t.m) + ':' + pad(t.s);
  }

  function dateText(tz){
    return new Intl.DateTimeFormat('ko-KR', {
      timeZone:tz, year:'numeric', month:'2-digit', day:'2-digit', weekday:'short'
    }).format(new Date());
  }

  function safeNum(v){
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  function codeToLabel(code){
    if(code == null) return '상태 확인 중';
    if(code >= 200 && code <= 299) return '천둥번개';
    if(code >= 300 && code <= 399) return '이슬비';
    if(code >= 500 && code <= 599) return '비';
    if(code >= 600 && code <= 699) return '눈';
    if(code >= 700 && code <= 799) return '안개';
    if(code === 800) return '맑음';
    if(code === 801) return '구름 조금';
    if(code === 802) return '흩어진 구름';
    if(code === 803) return '부분 흐림';
    if(code === 804) return '흐림';
    return '날씨 코드 ' + code;
  }

  function codeToIcon(code){
    if(code == null) return '·';
    if(code >= 200 && code <= 299) return '⚡';
    if(code >= 300 && code <= 399) return '☂';
    if(code >= 500 && code <= 599) return '☔';
    if(code >= 600 && code <= 699) return '❄';
    if(code >= 700 && code <= 799) return '≋';
    if(code === 800) return '☀';
    if(code === 801) return '◐';
    if(code === 802) return '☁';
    if(code === 803) return '☁';
    if(code === 804) return '☁';
    return '·';
  }

  function makeCard(city){
    return [
      '<article class="ob-world-card" data-city="'+city.id+'">',
        '<div class="ob-world-clock" aria-hidden="true">',
          '<span class="ob-world-hand hour" data-hand="hour"></span>',
          '<span class="ob-world-hand min" data-hand="min"></span>',
          '<span class="ob-world-hand sec" data-hand="sec"></span>',
        '</div>',
        '<div class="ob-world-meta">',
          '<div class="ob-world-city"><span>'+city.label+'</span><span class="ob-world-tz">'+city.tz+'</span></div>',
          '<div class="ob-world-time-row"><div class="ob-world-time" data-time>--:--:--</div><span class="ob-world-mobile-wx" data-mobile-wx title="현재 날씨">·</span></div>',
          '<div class="ob-world-date" data-date>----</div>',
          '<div class="ob-world-weather">',
            '<span class="ob-world-pill ob-world-cond" data-cond>상태 확인 중</span>',
            '<span class="ob-world-pill">기온 <strong data-temp>--</strong>℃</span>',
            '<span class="ob-world-pill">습도 <strong data-hum>--</strong>%</span>',
            '<span class="ob-world-pill">풍속 <strong data-wind>--</strong>m/s</span>',
          '</div>',
        '</div>',
      '</article>'
    ].join('');
  }

  function mount(root){
    const grid = root.querySelector('[data-ob-world-grid]');
    if(grid && !grid.children.length){
      grid.innerHTML = CONFIG.cities.map(makeCard).join('');
    }
  }

  function tick(){
    roots.forEach(function(root){
      CONFIG.cities.forEach(function(city){
        const card = root.querySelector('[data-city="'+city.id+'"]');
        if(!card) return;
        const t = timeParts(city.tz);
        const secDeg = (t.s / 60) * 360;
        const minDeg = ((t.m + t.s / 60) / 60) * 360;
        const hourDeg = (((t.h % 12) + t.m / 60 + t.s / 3600) / 12) * 360;
        const timeEl = card.querySelector('[data-time]');
        const dateEl = card.querySelector('[data-date]');
        const hourEl = card.querySelector('[data-hand="hour"]');
        const minEl = card.querySelector('[data-hand="min"]');
        const secEl = card.querySelector('[data-hand="sec"]');
        if(timeEl) timeEl.textContent = timeText(city.tz);
        if(dateEl) dateEl.textContent = dateText(city.tz);
        if(hourEl) hourEl.style.transform = 'translate(-50%,-100%) rotate('+hourDeg+'deg)';
        if(minEl) minEl.style.transform = 'translate(-50%,-100%) rotate('+minDeg+'deg)';
        if(secEl) secEl.style.transform = 'translate(-50%,-100%) rotate('+secDeg+'deg)';
      });
    });
  }

  function applyWeatherToAll(city, data){
    const code = safeNum(data && data.weather && data.weather[0] && data.weather[0].id);
    const temp = safeNum(data && data.main && data.main.temp);
    const hum = safeNum(data && data.main && data.main.humidity);
    const wind = safeNum(data && data.wind && data.wind.speed);
    roots.forEach(function(root){
      const card = root.querySelector('[data-city="'+city.id+'"]');
      if(!card) return;
      const cond = card.querySelector('[data-cond]');
      const tempEl = card.querySelector('[data-temp]');
      const humEl = card.querySelector('[data-hum]');
      const windEl = card.querySelector('[data-wind]');
      const mobileWx = card.querySelector('[data-mobile-wx]');
      if(cond) cond.textContent = codeToLabel(code);
      if(mobileWx){
        mobileWx.textContent = codeToIcon(code);
        mobileWx.setAttribute('aria-label', codeToLabel(code));
        mobileWx.setAttribute('title', codeToLabel(code));
      }
      if(tempEl) tempEl.textContent = temp == null ? '--' : String(Math.round(temp));
      if(humEl) humEl.textContent = hum == null ? '--' : String(Math.round(hum));
      if(windEl) windEl.textContent = wind == null ? '--' : String(Math.round(wind));
    });
  }

  function syncLabel(text){
    roots.forEach(function(root){
      const el = root.querySelector('[data-ob-world-sync]');
      if(el) el.textContent = text;
    });
  }

  async function fetchWeather(city){
    const url = 'https://api.openweathermap.org/data/2.5/weather?lat=' + encodeURIComponent(city.lat) +
      '&lon=' + encodeURIComponent(city.lon) + '&appid=' + encodeURIComponent(CONFIG.weatherApiKey) + '&units=metric&lang=kr';
    const res = await fetch(url, { cache:'no-store' });
    if(!res.ok) throw new Error('weather ' + res.status + ' ' + city.label);
    return res.json();
  }

  async function refreshWeather(){
    if(!CONFIG.weatherApiKey){
      syncLabel('날씨 API 키가 설정되지 않았습니다.');
      return;
    }
    syncLabel('날씨 데이터 갱신 중');
    try{
      const results = await Promise.all(CONFIG.cities.map(function(city){
        return fetchWeather(city).then(function(data){ return { city:city, data:data }; });
      }));
      results.forEach(function(item){ applyWeatherToAll(item.city, item.data); });
      syncLabel('날씨 업데이트: ' + new Intl.DateTimeFormat('ko-KR', { hour:'2-digit', minute:'2-digit', second:'2-digit' }).format(new Date()));
    }catch(err){
      syncLabel('날씨 업데이트 오류. 잠시 후 다시 확인합니다.');
      if(window.console) console.warn('[obaksa-world-footer]', err);
    }
  }

  roots.forEach(function(root){
    mount(root);
    const btn = root.querySelector('[data-ob-world-refresh]');
    if(btn) btn.addEventListener('click', refreshWeather);
  });
  tick();
  setInterval(tick, 1000);
  refreshWeather();
  setInterval(refreshWeather, CONFIG.refreshMinutes * 60 * 1000);
})();
