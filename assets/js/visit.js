/* ==========================================================================
   访问统计 —— 按 IP 去重
   三种工作模式，自动切换：
     1) 自建接口（推荐）：在 index.html 里设 window.VISIT_API = 'https://xxx.workers.dev'
        真正按客户端 IP 去重、可跨部署域名共享、数据可导出。
        服务端实现见 tools/visit-counter-worker.js（Cloudflare Worker，免费额度够用）。
     2) 不蒜子 busuanzi（默认）：零配置，UV 按访客/IP 去重，PV 计页面浏览。
     3) 本地预览：只记本机次数，不污染线上数据。
   不阻塞页面渲染，任何一环失败都优雅降级，不影响看板主功能。
   ========================================================================== */
(function () {
  'use strict';

  var API = (window.VISIT_API || '').replace(/\/+$/, '');
  var uvEl = document.getElementById('visitUv');
  var pvEl = document.getElementById('visitPv');
  var noteEl = document.getElementById('visitNote');
  if (!uvEl || !pvEl) return;

  var h = location.hostname || '';
  var LOCAL = !window.VISIT_FORCE_ONLINE && (location.protocol === 'file:' ||
    h === 'localhost' || h === '::1' || h === '[::1]' || h === '0.0.0.0' ||
    /^127\./.test(h) || /^192\.168\./.test(h) || /^10\./.test(h) ||
    /(^|\.)local$/.test(h) || /(^|\.)internal$/.test(h));

  /* ------------------------------------------------------------ 工具 */
  function fmt(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }

  function setNum(el, to) {
    if (isNaN(to)) { el.textContent = '—'; return; }
    var from = parseInt(String(el.textContent).replace(/[^\d]/g, ''), 10) || 0;
    if (from === to || to - from > 1e7) { el.textContent = fmt(to); return; }
    var dur = 760, t0 = null;
    function step(ts) {
      if (t0 === null) t0 = ts;
      var p = Math.min(1, (ts - t0) / dur);
      var e = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(Math.round(from + (to - from) * e));
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  function setNote(cn, en) {
    if (!noteEl) return;
    noteEl.innerHTML = '<span class="cn">' + cn + '</span><span class="en">' + en + '</span>';
  }

  function offline(msg) {
    uvEl.textContent = '—';
    pvEl.textContent = '—';
    setNote(msg || '统计服务暂时不可用', 'Counter unavailable');
  }

  /* -------------------------------------------- 模式 3：本地预览 */
  function localMode() {
    var KEY = 'snooker_dashboard_visit';
    var d = { pv: 0 };
    try { d = JSON.parse(localStorage.getItem(KEY) || '') || d; } catch (e) { }
    d.pv = (d.pv | 0) + 1;
    d.last = Date.now();
    try { localStorage.setItem(KEY, JSON.stringify(d)); } catch (e) { }
    uvEl.textContent = '1';
    setNum(pvEl, d.pv);
    setNote('本地预览：仅记录本机打开次数，不计入线上统计', 'Local preview · not counted online');
  }

  /* -------------------------------------------- 模式 1：自建接口 */
  function apiMode(fail) {
    var ctrl = 'AbortController' in window ? new AbortController() : null;
    var opt = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ p: location.pathname || '/', t: document.title || '' })
    };
    if (ctrl) opt.signal = ctrl.signal;
    var timer = setTimeout(function () { if (ctrl) ctrl.abort(); }, 6000);
    fetch(API + '/', opt).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function (j) {
      clearTimeout(timer);
      if (!j || typeof j.uv === 'undefined') throw new Error('bad payload');
      setNum(uvEl, j.uv | 0);
      setNum(pvEl, j.pv | 0);
      setNote('按独立 IP 地址去重统计 · 24 小时窗口', 'Unique IP · 24h rolling window');
    }).catch(function () {
      clearTimeout(timer);
      fail();
    });
  }

  /* -------------------------------------------- 模式 2：不蒜子 */
  var BSZ = [
    'https://busuanzi.ibruce.info/busuanzi/2.3/busuanzi.pure.mini.js',
    'https://busuanzi.9420.ltd/busuanzi/2.3/busuanzi.pure.mini.js'
  ];

  function busuanziMode(idx) {
    idx = idx || 0;
    if (idx >= BSZ.length) { offline(); return; }

    // 不蒜子脚本会写 inline display，故用父容器隐藏，避免样式被覆盖
    var host = document.getElementById('bszHost');
    if (!host) {
      host = document.createElement('div');
      host.id = 'bszHost';
      host.setAttribute('aria-hidden', 'true');
      host.style.cssText = 'position:absolute;left:-9999px;top:0;width:0;height:0;overflow:hidden;opacity:0;pointer-events:none';
      host.innerHTML =
        '<span id="busuanzi_container_site_uv"><span id="busuanzi_value_site_uv"></span></span>' +
        '<span id="busuanzi_container_site_pv"><span id="busuanzi_value_site_pv"></span></span>';
      document.body.appendChild(host);
    }

    var s = document.createElement('script');
    s.async = true;
    s.src = BSZ[idx];
    s.onerror = function () { s.remove(); busuanziMode(idx + 1); };
    document.head.appendChild(s);

    var tries = 0;
    var timer = setInterval(function () {
      var u = document.getElementById('busuanzi_value_site_uv');
      var p = document.getElementById('busuanzi_value_site_pv');
      var uv = u ? parseInt(String(u.textContent).replace(/[^\d]/g, ''), 10) : NaN;
      if (!isNaN(uv) && uv > 0) {
        clearInterval(timer);
        var pv = p ? parseInt(String(p.textContent).replace(/[^\d]/g, ''), 10) : NaN;
        setNum(uvEl, uv);
        setNum(pvEl, isNaN(pv) ? uv : pv);
        setNote('按访客 IP 去重，PV 为累计页面浏览', 'Unique visitors / total page views');
        return;
      }
      if (++tries > 35) {              // 约 7 秒未返回 → 换备用节点
        clearInterval(timer);
        s.remove();
        busuanziMode(idx + 1);
      }
    }, 200);
  }

  /* ------------------------------------------------------------ 启动 */
  function start() {
    if (LOCAL) { localMode(); return; }
    if (API) { apiMode(function () { busuanziMode(0); }); return; }
    busuanziMode(0);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
