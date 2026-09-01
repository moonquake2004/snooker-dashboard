/* ==========================================================================
   世界斯诺克巡回赛成绩看板 — 交互逻辑（原生 JS，无依赖）
   数据：window.SNOOKER_DATA（由 scripts/build_dashboard.py 生成）
   ========================================================================== */
(function () {
  'use strict';

  var D = window.SNOOKER_DATA;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  if (!D) {
    document.getElementById('loader').innerHTML =
      '<div class="loader-inner"><p>数据未加载：请先运行 build_dashboard.py<br>' +
      '<span class="en">Run build_dashboard.py first</span></p></div>';
    return;
  }

  /* ------------------------------------------------------------ 工具 */
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  /** 中英双语行：中文主行 + 英文副行 */
  function bi(cn, en, cls) {
    return '<span class="' + (cls || '') + '"><span class="cn">' + esc(cn) +
      '</span><span class="en">' + esc(en) + '</span></span>';
  }
  function nz(v) { return v == null || v === '' ? '—' : v; }
  function money(v) {
    if (v == null) return '—';
    return '£' + Number(v).toLocaleString('en-US');
  }
  function dateParts(ds) {
    // ds: "2026-08-30"
    if (!ds) return { d: '—', m: '', y: '' };
    var p = ds.split('-');
    var mon = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
               'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
    return { d: p[2] || '—', m: mon[parseInt(p[1], 10) - 1] || '', y: p[0] || '' };
  }
  function dateRange(a, b) {
    if (!a) return '';
    if (!b || a === b) return a;
    return a.slice(0, 10) + ' → ' + b.slice(0, 10);
  }
  function avatarUrl(p) { return p && p.photo ? p.photo : ''; }
  function avatar(p, cls, fallback) {
    var u = avatarUrl(p);
    if (u) {
      return '<span class="' + cls + '"><img src="' + esc(u) + '" alt="" loading="lazy" ' +
        'onerror="this.remove()"></span>';
    }
    var nm = (p && (p.name_zh || p.name_en)) || '';
    return '<span class="' + cls + '">' + esc(fallback || nm.slice(0, 1)) + '</span>';
  }
  var STATUS_ZH = { completed: '已结束', ongoing: '进行中', upcoming: '未开始' };
  var STATUS_EN = { completed: 'Done', ongoing: 'Live', upcoming: 'Upcoming' };

  var TYPE_ZH = { ranking: '排名赛', invitational: '邀请赛', qualifier: '资格赛' };
  var TYPE_EN = { ranking: 'Ranking', invitational: 'Invitational', qualifier: 'Qualifier' };

  function gbp(v) {
    return v == null ? '—' : '£' + Number(v).toLocaleString('en-US');
  }

  /** 赛事类型徽章：排名赛 / 邀请赛 / 资格赛，三大赛另加标记 */
  function typeBadge(t) {
    if (!t.type) return '';
    var cls = t.type === 'ranking' ? 'ranking'
      : (t.type === 'invitational' ? 'invitational' : 'qualifier');
    return '<span class="tbadge ' + cls + '">' +
      '<span class="cn">' + esc(TYPE_ZH[t.type] || t.type_zh) + '</span>' +
      '<span class="en">' + esc(TYPE_EN[t.type] || t.type_en) + '</span></span>';
  }

  function crownBadge(t) {
    if (!t.tripleCrown) return '';
    return '<span class="tbadge crown" title="Triple Crown 三大赛">★ ' +
      '<span class="cn">三大赛</span><span class="en">Triple Crown</span></span>';
  }

  /** 奖金行：总奖金 + 冠军奖金 */
  function prizeLine(t) {
    if (t.prizeTotal == null && t.prizeWinner == null) return '';
    return '<span class="prize-line">' +
      '<span class="prz"><i class="cn">总奖金</i><i class="en">Prize Fund</i>' +
      '<b>' + gbp(t.prizeTotal) + '</b></span>' +
      '<span class="prz win"><i class="cn">冠军</i><i class="en">Winner</i>' +
      '<b>' + gbp(t.prizeWinner) + '</b></span>' +
      '</span>';
  }

  /* ------------------------------------------------------------ 初始化 */
  function initMeta() {
    var m = D.meta, s = D.stats;
    $('#seasonValue').textContent = m.season;
    $('#heroUpdated').textContent = m.generatedAt;
    $('#heroWindow').textContent = m.seasonStart + ' → ' + m.seasonEnd;
    $('#footerStats').innerHTML =
      bi(s.tournamentTotal + ' 站赛事 · ' + s.matchCompleted + '/' + s.matchTotal + ' 场比赛 · ' +
         s.playerTotal + ' 名球员',
         s.tournamentTotal + ' events · ' + s.matchCompleted + '/' + s.matchTotal +
         ' matches · ' + s.playerTotal + ' players');
    document.title = m.season + ' 世界斯诺克巡回赛 · 成绩看板 | World Snooker Tour Dashboard';
  }

  /* ------------------------------------------------------------ KPI */
  function renderKPI() {
    var s = D.stats;
    var items = [
      { cn: '已完赛赛事', en: 'Events Done', v: s.tournamentFinished,
        sub: bi('共 ' + s.tournamentTotal + ' 站', s.tournamentTotal + ' total'), c: 'var(--ball-green)' },
      { cn: '已赛场次', en: 'Matches', v: s.matchCompleted,
        sub: bi('共 ' + s.matchTotal + ' 场', s.matchTotal + ' scheduled'), c: 'var(--ball-blue)' },
      { cn: '参赛球员', en: 'Players', v: s.playerTotal,
        sub: bi('来自 ' + s.countries + ' 个国家和地区', s.countries + ' nations'), c: 'var(--brass-400)' },
      { cn: '单杆破百', en: 'Centuries', v: s.centuryTotal,
        sub: bi('最高 ' + s.maxBreak + ' 分', 'Hi-break ' + s.maxBreak), c: 'var(--ball-red)' },
      { cn: '总对局数', en: 'Frames', v: s.frameTotal,
        sub: bi('逐局统计', 'Frame-by-frame'), c: 'var(--ball-pink)' },
      { cn: '中国球员', en: 'China', v: s.chinaPlayers,
        sub: bi('本赛季出场', 'On tour'), c: 'var(--ball-yellow)' },
      { cn: '赛季总奖金', en: 'Prize Fund',
        v: '£' + ((s.seasonPrize || 0) / 1e6).toFixed(1) + 'M',
        sub: bi(s.rankingEvents + ' 站排名赛 · ' + s.invitationalEvents + ' 站邀请赛',
                s.rankingEvents + ' ranking · ' + s.invitationalEvents + ' invitational'),
        c: 'var(--brass-300)' }
    ];
    $('#kpiGrid').innerHTML = items.map(function (k) {
      return '<div class="kpi" style="--accent:' + k.c + '">' +
        '<div class="kpi-label"><span class="cn">' + esc(k.cn) + '</span>' +
        '<span class="en">' + esc(k.en) + '</span></div>' +
        '<div class="kpi-value">' + k.v + '</div>' +
        '<div class="kpi-sub">' + k.sub + '</div></div>';
    }).join('');
  }

  /* ------------------------------------------------------------ 冠军墙 */
  function renderChampions() {
    var done = D.tournaments.filter(function (t) { return t.winner; });
    done.sort(function (a, b) { return b.startDate.localeCompare(a.startDate); });
    $('#champCount').innerHTML = bi(done.length + ' 站已产生冠军',
                                    done.length + ' champions crowned');
    $('#championWall').innerHTML = done.map(function (t) {
      var w = t.winner;
      return '<div class="champ-card" data-player="' + esc(w.id) + '">' +
        avatar(w, 'champ-avatar') +
        '<div class="champ-info">' +
          '<div class="champ-name"><span class="cn">' + esc(w.name_zh) + '</span>' +
          '<span class="en">' + esc(w.name_en) + '</span></div>' +
          '<div class="champ-ev"><span class="trophy">🏆</span> ' +
          '<span class="cn">' + esc(t.name_zh) + '</span>' +
          '<span class="en">' + esc(t.name_en) + '</span></div>' +
        '</div></div>';
    }).join('') || emptyChamp();
  }
  function emptyChamp() {
    return '<div class="empty-state"><span class="cn">赛季刚开始，还没有冠军产生</span>' +
      '<span class="en">No champions yet</span></div>';
  }

  /* ------------------------------------------------------------ 最新赛果 */
  function renderRecent() {
    var done = D.matches.filter(function (m) { return m.status === 'Completed'; });
    done.sort(function (a, b) {
      return (b.date + b.time).localeCompare(a.date + a.time);
    });
    var list = done.slice(0, 12);
    $('#recentList').innerHTML = list.map(function (m) {
      var hw = m.homeScore > m.awayScore;
      return '<div class="recent-row">' +
        '<div class="rr-player">' +
          '<span class="rr-name"><span class="cn">' + esc(m.home ? m.home.name_zh : 'TBD') + '</span>' +
          '<span class="en">' + esc(m.home ? m.home.name_en : 'TBD') + '</span></span>' +
          '<span class="rr-flag">' + esc(m.home ? m.home.country : '') + '</span>' +
        '</div>' +
        '<div class="rr-score">' +
          '<span class="' + (hw ? 'w' : 'l') + '">' + m.homeScore + '</span>' +
          '<span style="opacity:.5;margin:0 5px">-</span>' +
          '<span class="' + (hw ? 'l' : 'w') + '">' + m.awayScore + '</span>' +
        '</div>' +
        '<div class="rr-player right">' +
          '<span class="rr-name"><span class="cn">' + esc(m.away ? m.away.name_zh : 'TBD') + '</span>' +
          '<span class="en">' + esc(m.away ? m.away.name_en : 'TBD') + '</span></span>' +
          '<span class="rr-flag">' + esc(m.away ? m.away.country : '') + '</span>' +
        '</div>' +
        '<div class="rr-ev"><span class="cn">' + esc(m.tournament_zh) + ' · ' + esc(m.round_zh) +
        ' · ' + esc(m.date) + '</span>' +
        '<span class="en">' + esc(m.tournament_en) + ' · ' + esc(m.round_en) + '</span></div>' +
      '</div>';
    }).join('');
  }

  /* ------------------------------------------------------------ 破百条 */
  function renderCenturyStrip() {
    var top = D.centuries.slice(0, 12);
    $('#centuryStrip').innerHTML = top.map(function (c) {
      var gold = c.value >= 140;
      return '<div class="cb-card' + (gold ? ' gold' : '') + '">' +
        '<div class="cb-value">' + c.value + '</div>' +
        '<div class="cb-name"><span class="cn">' + esc(c.player_zh) + '</span>' +
        '<span class="en">' + esc(c.player) + '</span></div>' +
        '<div class="cb-meta">' + esc(c.tournament_zh) + '</div>' +
      '</div>';
    }).join('');
  }

  /* ------------------------------------------------------------ 赛程 */
  var schedFilter = 'all', schedQuery = '';

  function schedulePass(t) {
    if (schedFilter === 'main' && t.isQualifier) return false;
    if (schedFilter === 'ranking' && t.type !== 'ranking') return false;
    if (schedFilter === 'invitational' && t.type !== 'invitational') return false;
    if (schedFilter === 'completed' && t.status !== 'completed') return false;
    if (schedFilter === 'ongoing' && t.status !== 'ongoing') return false;
    if (schedFilter === 'upcoming' && t.status !== 'upcoming') return false;
    if (schedQuery) {
      var q = schedQuery.toLowerCase();
      var hay = (t.name_en + ' ' + t.name_zh + ' ' + t.city_en + ' ' + t.city_zh + ' ' +
                 t.country_en + ' ' + t.country_zh).toLowerCase();
      if (hay.indexOf(q) < 0) return false;
    }
    return true;
  }

  function renderSchedule() {
    var list = D.tournaments.filter(schedulePass);
    $('#scheduleEmpty').hidden = list.length > 0;
    $('#scheduleTimeline').innerHTML = list.map(function (t) {
      var dp = dateParts(t.startDate);
      var ep = dateParts(t.endDate);
      var cls = t.status === 'completed' ? 'done' : (t.status === 'ongoing' ? 'live' : '');
      var pct = t.matchCount ? Math.round(t.completedMatches / t.matchCount * 100) : 0;
      var city = [t.city_zh || t.city_en, t.country_zh || t.country_en]
        .filter(Boolean).join(' · ');
      var cityEn = [t.city_en, t.country_en].filter(Boolean).join(', ');

      return '<div class="tl-item ' + cls + '">' +
        '<div class="tl-card" data-event="' + esc(t.id) + '">' +
          '<div class="tl-date">' +
            '<span class="d">' + dp.d + (t.startDate !== t.endDate ? '–' + ep.d : '') + '</span>' +
            '<span class="m">' + dp.m + '</span>' +
            '<span class="y">' + dp.y + '</span>' +
          '</div>' +
          '<div class="tl-main">' +
            '<div class="tl-name"><span class="cn">' + esc(t.name_zh) + '</span>' +
            '<span class="en">' + esc(t.name_en) + '</span>' +
            typeBadge(t) + crownBadge(t) + '</div>' +
            '<div class="tl-meta">' +
              '<span class="tl-city">📍 <span class="cn">' + esc(city) + '</span>' +
              '<span class="en">' + esc(cityEn) + '</span></span>' +
              '<span class="tl-range">' + dateRange(t.startDate, t.endDate) + '</span>' +
              (t.matchCount ?               '<span class="tl-count">' + t.completedMatches + '/' +
               t.matchCount + '</span>' : '') +
            '</div>' +
            prizeLine(t) +
          '</div>' +
          '<div class="tl-side">' +
            '<span class="badge ' + t.status + '">' +
            '<span class="cn">' + STATUS_ZH[t.status] + '</span>' +
            '<span class="en">' + STATUS_EN[t.status] + '</span></span>' +
            (t.winner
              ? '<span class="tl-winner">🏆 <b class="cn">' + esc(t.winner.name_zh) + '</b>' +
                '<span class="en">' + esc(t.winner.name_en) + '</span></span>'
              : (t.matchCount ? '<div class="tl-progress"><i style="width:' + pct + '%"></i></div>' : '')) +
          '</div>' +
        '</div></div>';
    }).join('');
  }

  /* ------------------------------------------------------------ 赛果 */
  function renderResults() {
    var list = D.tournaments.slice().reverse();
    $('#resultsList').innerHTML = list.map(function (t) {
      var ms = D.matches.filter(function (m) { return m.tournamentId === t.id; });
      var rounds = {};
      var order = [];
      ms.forEach(function (m) {
        var k = m.round_en + '||' + m.round_zh;
        if (!rounds[k]) { rounds[k] = []; order.push(k); }
        rounds[k].push(m);
      });
      order.sort(function (a, b) {
        return (rounds[b][0].roundRank || 0) - (rounds[a][0].roundRank || 0);
      });

      var city = [t.city_zh || t.city_en, t.country_zh || t.country_en].filter(Boolean).join(' · ');
      var cityEn = [t.city_en, t.country_en].filter(Boolean).join(', ');

      var body = order.map(function (k) {
        var parts = k.split('||');
        var rows = rounds[k].sort(function (a, b) {
          return (a.date + a.time).localeCompare(b.date + b.time);
        }).map(matchRow).join('');
        return '<div class="round-block">' +
          '<div class="round-title"><span><span class="cn">' + esc(parts[1]) + '</span>' +
          '<span class="en">' + esc(parts[0]) + '</span></span>' +
          '<span class="round-count">' + rounds[k].length + '</span></div>' + rows +
        '</div>';
      }).join('') ||
        '<div class="empty-state"><span class="cn">对阵尚未公布</span>' +
        '<span class="en">Draw not published yet</span></div>';

      return '<div class="res-card" data-event="' + esc(t.id) + '">' +
        '<div class="res-head">' +
          '<div class="res-title">' +
            '<div class="res-name"><span class="cn">' + esc(t.name_zh) + '</span>' +
            '<span class="en">' + esc(t.name_en) + '</span>' +
            typeBadge(t) + crownBadge(t) + '</div>' +
            '<div class="res-meta">' +
              '<span>📍 <span class="cn">' + esc(city) + '</span>' +
              '<span class="en">' + esc(cityEn) + '</span></span>' +
              '<span>' + dateRange(t.startDate, t.endDate) + '</span>' +
              '<span class="tl-count">' + t.completedMatches + '/' + t.matchCount + '</span>' +
              '<span class="badge ' + t.status + '"><span class="cn">' + STATUS_ZH[t.status] +
              '</span><span class="en">' + STATUS_EN[t.status] + '</span></span>' +
            '</div>' +
            prizeLine(t) +
          '</div>' +
          '<div class="res-right">' +
            (t.winner
              ? '<div class="res-final"><span class="cn">冠军 ' + esc(t.winner.name_zh) +
                ' <b>' + esc(t.finalScore) + '</b> ' + esc(t.runnerUp.name_zh) + '</span>' +
                '<span class="en">Winner ' + esc(t.winner.name_en) + ' ' + esc(t.finalScore) +
                ' ' + esc(t.runnerUp.name_en) + '</span></div>'
              : '<div class="res-score">—</div>') +
            '<div class="res-toggle">▾</div>' +
          '</div>' +
        '</div>' +
        '<div class="res-body">' + body + '</div>' +
      '</div>';
    }).join('');
  }

  function matchRow(m) {
    var hw = m.homeScore > m.awayScore;
    var aw = m.awayScore > m.homeScore;
    var done = m.status === 'Completed';
    return '<div class="match-row">' +
      '<div class="mr-p ' + (done ? (hw ? 'win' : 'lose') : '') + '">' +
        '<span class="mr-flag">' + esc(m.home ? m.home.country : '') + '</span>' +
        '<span class="mr-name"><span class="cn">' + esc(m.home ? m.home.name_zh : '待定 TBD') + '</span>' +
        '<span class="en">' + esc(m.home ? m.home.name_en : 'TBD') + '</span></span>' +
      '</div>' +
      '<div class="mr-sc' + (done ? '' : ' pending') + '">' +
        (done ? m.homeScore + '-' + m.awayScore : esc(m.status_zh || '未开始')) + '</div>' +
      '<div class="mr-p r ' + (done ? (aw ? 'win' : 'lose') : '') + '">' +
        '<span class="mr-name"><span class="cn">' + esc(m.away ? m.away.name_zh : '待定 TBD') + '</span>' +
        '<span class="en">' + esc(m.away ? m.away.name_en : 'TBD') + '</span></span>' +
        '<span class="mr-flag">' + esc(m.away ? m.away.country : '') + '</span>' +
      '</div>' +
    '</div>';
  }

  /* ------------------------------------------------------------ 排名 */
  var rankIdx = 0, varIdx = 0, rankLimit = 30;

  function renderRankTabs() {
    $('#rankTabs').innerHTML = D.rankings.map(function (g, i) {
      return '<button class="seg' + (i === rankIdx ? ' active' : '') + '" data-r="' + i + '">' +
        '<span class="cn">' + esc(g.name_zh) + '</span>' +
        '<span class="en">' + esc(g.name_en) + '</span></button>';
    }).join('');
    renderVariantTabs();
  }

  function renderVariantTabs() {
    var g = D.rankings[rankIdx];
    var wrap = $('#rankVariant');
    if (!g || g.variants.length < 2) { wrap.innerHTML = ''; return; }
    wrap.innerHTML = g.variants.map(function (v, i) {
      return '<button class="seg' + (i === varIdx ? ' active' : '') + '" data-v="' + i + '">' +
        '<span class="cn">' + esc(v.label) + '</span>' +
        '<span class="en">' + esc(v.label_en) + '</span></button>';
    }).join('');
  }

  function metricOf(v, pos) {
    var t = v.type;
    if (t === 'centuriesCount') return { v: nz(pos.centuries), raw: pos.centuries || 0 };
    if (t === 'playerAst') return { v: pos.ast != null ? pos.ast + 's' : '—', raw: pos.ast || 0 };
    return { v: money(pos.prizeMoney), raw: pos.prizeMoney || 0 };
  }

  /** 排名页冠军数徽章：排名赛(R) + 非排名赛(NR) */
  function titlesCell(p) {
    var r = p.titlesRank || 0, nr = p.titlesNonRank || 0;
    if (!r && !nr) {
      return '<span class="tt-none">—</span>';
    }
    return '<span class="tt-cell">' +
      '<span class="tt-r" title="排名赛冠军 Ranking titles"><b>' + r + '</b><i>R</i></span>' +
      '<span class="tt-sep">·</span>' +
      '<span class="tt-nr" title="非排名赛冠军 Non-ranking titles（含邀请赛）"><b>' + nr + '</b><i>NR</i></span>' +
      '</span>';
  }

  function renderRankings() {
    var g = D.rankings[rankIdx];
    if (!g) return;
    var v = g.variants[Math.min(varIdx, g.variants.length - 1)];
    var isAst = v.type === 'playerAst';
    var metricLabel = isAst
      ? bi('平均出杆', 'Avg Shot')
      : (v.type === 'centuriesCount' ? bi('破百数', 'Centuries') : bi('奖金', 'Prize Money'));

    $('#rankTitle').innerHTML = '<span class="cn">' + esc(g.name_zh) + '</span>' +
      '<span class="en">' + esc(g.name_en) + ' · ' + esc(v.label_en) + '</span>';
    $('#rankDesc').innerHTML = '<span class="cn">' + esc(g.description) + '</span>' +
      '<span class="en">' + esc(g.name_en) + ' — ' + esc(v.label_en) + ' version</span>';
    $('#rankUpdated').innerHTML = v.updated
      ? bi('截止：' + v.updated, 'After: ' + v.updated) : '';
    $('#rankMetricTh').innerHTML = metricLabel;

    // 领奖台
    var pod = v.positions.slice(0, 3);
    $('#rankPodium').innerHTML = pod.map(function (p, i) {
      var mt = metricOf(v, p);
      return '<div class="podium p' + (i + 1) + '" data-player="' + esc(p.playerId) + '">' +
        '<div class="pod-crown">' + ['1st', '2nd', '3rd'][i] + '</div>' +
        avatar(p, 'pod-avatar', p.name_zh ? p.name_zh.slice(0, 1) : '?') +
        '<div class="pod-name"><span class="cn">' + esc(p.name_zh) + '</span>' +
        '<span class="en">' + esc(p.name_en) + '</span></div>' +
        '<div class="pod-metric">' + mt.v + '</div>' +
        '<div class="pod-sub"><span class="cn">' + esc(p.country_zh || p.country) + '</span>' +
        '<span class="en">' + esc(p.country_en || p.country) + '</span></div>' +
        '<div class="pod-titles">' + titlesCell(p) + '</div>' +
      '</div>';
    }).join('');

    // 表格
    var rows = v.positions.slice(0, rankLimit);
    $('#rankBody').innerHTML = rows.map(function (p) {
      var mt = metricOf(v, p);
      var cls = p.pos === 1 ? 'top1' : (p.pos <= 16 ? 'top16' : '');
      return '<tr class="' + cls + '" data-player="' + esc(p.playerId) + '">' +
        '<td class="c-pos">' + p.pos + '</td>' +
        '<td class="c-player"><div class="pl-cell">' +
          avatar(p, 'pl-avatar', p.name_zh ? p.name_zh.slice(0, 1) : '?') +
          '<span class="pl-name"><span class="cn">' + esc(p.name_zh) + '</span>' +
          '<span class="en">' + esc(p.name_en) + '</span></span></div></td>' +
        '<td class="c-country"><span class="nat"><span class="code">' + esc(p.country) + '</span>' +
          '<span class="cn">' + esc(p.country_zh) + '</span>' +
          '<span class="en">' + esc(p.country_en) + '</span></span></td>' +
        '<td class="c-titles">' + titlesCell(p) + '</td>' +
        '<td class="c-metric">' + mt.v + '</td>' +
      '</tr>';
    }).join('');

    var more = $('#rankMore');
    if (rankLimit < v.positions.length) {
      more.hidden = false;
      more.innerHTML = '<span class="cn">显示更多（' + rankLimit + '/' + v.positions.length +
        '）</span><span class="en">Show more (' + rankLimit + '/' + v.positions.length + ')</span>';
    } else if (rankLimit > 30) {
      more.hidden = false;
      more.innerHTML = '<span class="cn">收起</span><span class="en">Collapse</span>';
    } else {
      more.hidden = true;
    }
  }

  /* ------------------------------------------------------------ 球员 */
  var pCountry = 'ALL', pQuery = '', pSort = 'wins';

  function renderCountryFilter() {
    var counts = {};
    D.players.forEach(function (p) {
      var k = p.country || '—';
      counts[k] = (counts[k] || 0) + 1;
    });
    var keys = Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; });
    var top = keys.slice(0, 8);
    if (top.indexOf('CHN') < 0 && counts.CHN) top.unshift('CHN');
    var zh = {};
    D.players.forEach(function (p) { if (p.country) zh[p.country] = p.country_zh; });

    var html = '<button class="seg' + (pCountry === 'ALL' ? ' active' : '') + '" data-c="ALL">' +
      '<span class="cn">全部</span><span class="en">All</span></button>' +
      top.map(function (k) {
        return '<button class="seg' + (pCountry === k ? ' active' : '') + '" data-c="' + esc(k) + '">' +
          '<span class="cn">' + esc(zh[k] || k) + '</span>' +
          '<span class="en">' + esc(k) + ' ' + counts[k] + '</span></button>';
      }).join('');
    $('#countryFilter').innerHTML = html;
  }

  function renderPlayers() {
    var list = D.players.filter(function (p) {
      if (pCountry !== 'ALL' && p.country !== pCountry) return false;
      if (pQuery) {
        var q = pQuery.toLowerCase();
        if ((p.name_en + ' ' + p.name_zh + ' ' + (p.country_zh || '')).toLowerCase()
            .indexOf(q) < 0) return false;
      }
      return true;
    });

    if (pSort === 'name') {
      list.sort(function (a, b) { return a.name_en.localeCompare(b.name_en); });
    } else {
      list.sort(function (a, b) {
        return (b[pSort] || 0) - (a[pSort] || 0) || b.wins - a.wins;
      });
    }

    $('#playerCount').textContent = list.length + ' / ' + D.players.length;
    $('#playerEmpty').hidden = list.length > 0;

    $('#playerGrid').innerHTML = list.map(function (p) {
      var tot = p.wins + p.losses;
      var wp = tot ? Math.round(p.wins / tot * 100) : 0;
      return '<div class="player-card" data-player="' + esc(p.id) + '">' +
        '<div class="pc-top">' +
          avatar(p, 'pc-avatar', p.name_zh ? p.name_zh.slice(0, 1) : '?') +
          '<div class="pc-id">' +
            '<div class="pc-name"><span class="cn">' + esc(p.name_zh) + '</span>' +
            '<span class="en">' + esc(p.name_en) + '</span></div>' +
            '<div class="pc-tag">' +
              '<span class="code">' + esc(p.country) + '</span>' +
              '<span class="cn">' + esc(p.country_zh) + '</span>' +
              '<span class="en">' + esc(p.country_en) + '</span>' +
              (p.titles ? '<span class="trophy">🏆 ' + p.titles + '</span>' : '') +
            '</div>' +
          '</div>' +
        '</div>' +
        '<div class="pc-stats">' +
          '<div class="pc-stat"><b>' + p.wins + '</b><span><span class="cn">胜</span><span class="en">W</span></span></div>' +
          '<div class="pc-stat"><b>' + p.centuries + '</b><span><span class="cn">破百</span><span class="en">100+</span></span></div>' +
          '<div class="pc-stat"><b>' + p.fiftyPlus + '</b><span><span class="cn">50+</span><span class="en">50+</span></span></div>' +
          '<div class="pc-stat"><b>' + (p.highestBreak || '—') + '</b><span><span class="cn">最高</span><span class="en">Hi</span></span></div>' +
        '</div>' +
        '<div class="pc-bar"><i class="w" style="width:' + wp + '%"></i>' +
        '<i class="l" style="width:' + (100 - wp) + '%"></i></div>' +
        '<div class="pc-foot">' +
          '<span><span class="cn">' + p.wins + '胜 ' + p.losses + '负 · 胜率 ' + wp + '%</span>' +
          '<span class="en">' + p.wins + 'W ' + p.losses + 'L · ' + wp + '%</span></span>' +
          '<span><span class="cn">' + esc(p.bestRound || '—') + '</span>' +
          '<span class="en">Best</span></span>' +
        '</div>' +
      '</div>';
    }).join('');
  }

  /* ------------------------------------------------------------ 数据中心 */
  function renderLeaders() {
    var L = D.leaderboards;
    var defs = [
      { k: 'centuries', cn: '破百榜', en: 'Century Breaks', unit: '' },
      { k: 'highestBreak', cn: '最高单杆', en: 'Highest Break', unit: '' },
      { k: 'fiftyPlus', cn: '50+ 单杆数', en: '50+ Breaks', unit: '' },
      { k: 'wins', cn: '胜场榜', en: 'Most Wins', unit: '' },
      { k: 'titles', cn: '冠军数', en: 'Titles', unit: '' }
    ];
    $('#leaderGrid').innerHTML = defs.map(function (d) {
      var rows = (L[d.k] || []).slice(0, 10);
      if (!rows.length) return '';
      var max = Math.max.apply(null, rows.map(function (r) { return r.value || 0; })) || 1;
      return '<div class="leader-card">' +
        '<h4><span class="cn">' + d.cn + '</span><span class="en">' + d.en + '</span></h4>' +
        rows.map(function (r, i) {
          var pct = Math.round((r.value || 0) / max * 100);
          return '<div class="leader-row">' +
            '<span class="lr-rank">' + (i + 1) + '</span>' +
            '<span style="flex:1;min-width:0">' +
              '<div class="lr-name"><span class="cn">' + esc(r.name_zh) + '</span>' +
              '<span class="en">' + esc(r.name_en) + '</span></div>' +
              '<div class="lr-bar"><i style="width:' + pct + '%"></i></div>' +
            '</span>' +
            '<span class="lr-val">' + (r.value || 0) + '</span>' +
          '</div>';
        }).join('') +
      '</div>';
    }).join('');
  }

  var cFilter = 'all';
  function renderCenturies() {
    var list = D.centuries;
    if (cFilter === '147') list = list.filter(function (c) { return c.value >= 147; });
    else if (cFilter === '140') list = list.filter(function (c) { return c.value >= 140; });
    else if (cFilter === '130') list = list.filter(function (c) { return c.value >= 130; });

    var show = list.slice(0, 200);
    $('#centuryBody').innerHTML = show.map(function (c) {
      var cls = c.value >= 147 ? ' style="color:var(--brass-300);font-weight:700"' : '';
      return '<tr>' +
        '<td class="c-brk"' + cls + '>' + c.value + '</td>' +
        '<td><span class="pl-name"><span class="cn">' + esc(c.player_zh) + '</span>' +
        '<span class="en">' + esc(c.player) + '</span></span></td>' +
        '<td class="hide-sm"><span class="nat"><span class="code">' + esc(c.country) + '</span>' +
        '<span class="cn">' + esc(c.country_zh) + '</span>' +
        '<span class="en">' + esc(c.country_en) + '</span></span></td>' +
        '<td class="hide-sm"><span class="cn">' + esc(c.tournament_zh) + '</span>' +
        '<span class="en">' + esc(c.tournament_en) + '</span></td>' +
        '<td class="hide-md"><span class="cn">' + esc(c.round_zh) + '</span>' +
        '<span class="en">' + esc(c.round_en) + '</span></td>' +
        '<td class="hide-sm"><span class="cn">' + esc(c.opponent_zh) + '</span>' +
        '<span class="en">' + esc(c.opponent_en) + '</span></td>' +
        '<td class="c-date">' + esc(c.date) + '</td>' +
      '</tr>';
    }).join('') || '<tr><td colspan="7"><div class="empty-state">' +
      '<span class="cn">没有符合条件的记录</span>' +
      '<span class="en">No records</span></div></td></tr>';
  }

  /* ------------------------------------------------------------ 历史冠军榜 */
  var titleSort = 'ranking';
  var careerSlug2pid = {};   // 现役球员 slug → 球员ID
  var tbBySlug = {};         // 全部上榜球员 slug → 行数据（含名宿）
  function renderTitleBoard() {
    var tb = D.titleBoard;
    if (!tb || !tb.rows || !tb.rows.length) {
      $('#titleBody').innerHTML = '<tr><td colspan="9"><div class="empty-state">' +
        '<span class="cn">暂无生涯冠军数据</span>' +
        '<span class="en">No career title data</span></div></td></tr>';
      $('#titleNote').innerHTML = '';
      return;
    }
    var rows = tb.rows.slice().sort(function (a, b) {
      return (b[titleSort] || 0) - (a[titleSort] || 0) ||
             (b.total || 0) - (a.total || 0);
    });
    $('#titleBody').innerHTML = rows.map(function (r) {
      var crown = r.crown
        ? '<span class="crown-n">★ ' + r.crown + '</span>' : '—';
      return '<tr data-slug="' + esc(r.slug) + '" class="clickable">' +
        '<td class="c-rank">' + r.rank + '</td>' +
        '<td><span class="pl-name"><span class="cn">' + esc(r.name_zh) +
        '</span><span class="en">' + esc(r.name_en) + '</span></span></td>' +
        '<td class="hide-sm"><span class="nat"><span class="code">' + esc(r.country) +
        '</span><span class="cn">' + esc(r.country_zh) + '</span>' +
        '<span class="en">' + esc(r.country_en) + '</span></span></td>' +
        '<td class="c-num">' + r.ranking + '</td>' +
        '<td class="c-num hide-sm">' + r.nonRanking + '</td>' +
        '<td class="c-num"><b>' + r.total + '</b></td>' +
        '<td class="c-num">' + crown + '</td>' +
        '<td class="c-yr hide-md">' + (r.first || '—') + '</td>' +
        '<td class="c-yr hide-md">' + (r.last || '—') + '</td>' +
      '</tr>';
    }).join('');
    var m = tb.meta || {};
    $('#titleNote').innerHTML =
      '<span class="cn">数据来源 ' + esc(m.source || 'CueTracker') + '，截至 ' +
      esc((m.fetched || '').slice(0, 10)) + '。共 ' + (m.rows || 0) + ' 人上榜，' +
      '排名赛冠军合计 ' + (m.rankingTitles || 0) + ' 个、全部冠军 ' +
      (m.allTitles || 0) + ' 个。</span>' +
      '<span class="en">Source ' + esc(m.source || 'CueTracker') + ', as of ' +
      esc((m.fetched || '').slice(0, 10)) + '. ' + (m.rows || 0) + ' players, ' +
      (m.rankingTitles || 0) + ' ranking / ' + (m.allTitles || 0) +
      ' total titles.</span>';
    // 建立 slug → 行 映射（现役 + 名宿），供点击弹窗
    tbBySlug = {};
    rows.forEach(function (r) { tbBySlug[r.slug] = r; });
  }

  // 名宿（不在现役名单）点击 → 弹出「生涯冠军」明细
  function openLegacy(slug) {
    var r = tbBySlug[slug];
    if (!r) return;
    var items = (r.items || []).map(function (it) {
      return '<div class="md-row"><b><span class="cn">' + esc(it.zh) +
        '</span><span class="en">' + esc(it.en) + '</span></b>' +
        '<i><span class="cn">' + esc(it.year) + '</span>' +
        '<span class="en">' + esc(it.year) + '</span></i></div>';
    }).join('');
    var crown = r.crown ? '<span class="tbadge crown">★ ' + r.crown + '</span>' : '';
    var html =
      '<div class="md-head"><div>' +
        '<div class="md-name"><span class="cn">' + esc(r.name_zh) +
        '</span><span class="en">' + esc(r.name_en) + '</span></div>' +
        '<div class="md-tags"><span class="nat"><span class="code">' + esc(r.country) +
        '</span><span class="cn">' + esc(r.country_zh) + '</span>' +
        '<span class="en">' + esc(r.country_en) + '</span></span>' + crown + '</div>' +
      '</div></div>' +
      '<div class="md-grid">' +
        stat(r.ranking, '排名赛', 'Ranking') +
        stat(r.nonRanking, '非排名赛', 'Non-Ranking') +
        stat(r.total, '全部冠军', 'Total') +
        stat(r.crown, '三大赛', 'Triple Crown') +
        stat((r.first || '—') + '–' + (r.last || '—'), '首冠–末冠', 'First–Last') +
      '</div>' +
      '<div class="md-sec-title"><span class="cn">生涯冠军全记录（' +
        (r.items ? r.items.length : 0) + ' 冠）</span>' +
        '<span class="en">Career Titles (' + (r.items ? r.items.length : 0) +
        ')</span></div>' +
      (items ? '<div class="md-list">' + items + '</div>'
              : '<div class="empty-state"><span class="cn">暂无逐冠明细</span>' +
                '<span class="en">No detail</span></div>');
    $('#modalBody').innerHTML = html;
    $('#modal').hidden = false;
    document.body.style.overflow = 'hidden';
  }

  /* ------------------------------------------------------------ 弹层 */
  function openPlayer(pid) {
    var p = D.allPlayers.filter(function (x) { return x.id === pid; })[0];
    if (!p) return;

    // 世界排名（优先取实时版）
    var wr = null;
    var wrGroup = D.rankings.filter(function (g) { return g.name_en === 'World Rankings'; })[0];
    if (wrGroup) {
      var v = wrGroup.variants[0];
      wr = v.positions.filter(function (x) { return x.playerId === pid; })[0];
    }
    var myCenturies = D.centuries.filter(function (c) { return c.playerId === pid; });
    myCenturies.sort(function (a, b) { return b.value - a.value; });

    var tot = p.wins + p.losses;
    var wp = tot ? Math.round(p.wins / tot * 100) : 0;

    var html =
      '<div class="md-head">' +
        avatar(p, 'md-avatar', p.name_zh ? p.name_zh.slice(0, 1) : '?') +
        '<div>' +
          '<div class="md-name"><span class="cn">' + esc(p.name_zh) + '</span>' +
          '<span class="en">' + esc(p.name_en) + '</span></div>' +
          '<div class="md-tags">' +
            '<span><span class="cn">' + esc(p.country_zh || p.country) + '</span>' +
                  '<span class="en">' + esc(p.country_en || p.country) + '</span></span>' +
            (wr ? '<span><span class="cn">世界排名 第' + wr.pos + '位</span>' +
                  '<span class="en">World Rank ' + wr.pos + '</span></span>' : '') +
            (wr && wr.prizeMoney ? '<span><span class="cn">' + money(wr.prizeMoney) + '</span>' +
                  '<span class="en">Prize money</span></span>' : '') +
            (p.dob ? '<span><span class="cn">生于 ' + esc(p.dob) + '</span>' +
                  '<span class="en">Born ' + esc(p.dob) + '</span></span>' : '') +
            (p.turnedPro ? '<span><span class="cn">' + p.turnedPro + ' 年转职业</span>' +
                  '<span class="en">Pro since ' + p.turnedPro + '</span></span>' : '') +
            (p.nickname ? '<span><span class="cn">绰号 ' + esc(p.nickname) + '</span>' +
                  '<span class="en">"' + esc(p.nickname) + '"</span></span>' : '') +
            '<span><span class="cn">' + p.matches + ' 场出场</span>' +
                  '<span class="en">' + p.matches + ' matches</span></span>' +
          '</div>' +
        '</div>' +
      '</div>' +

      '<div class="md-grid">' +
        stat(p.matches, '出场', 'Matches') +
        stat(p.wins + '-' + p.losses, '胜负', 'W-L') +
        stat(wp + '%', '胜率', 'Win rate') +
        stat(p.centuries, '破百', '100+') +
        stat(p.fiftyPlus, '50+', '50+') +
        stat(p.highestBreak || '—', '最高单杆', 'Hi-break') +
        stat(p.titles, '冠军', 'Titles') +
        stat(p.bestRound || '—', '最好成绩', 'Best') +
      '</div>' +

      (p.career
        ? '<div class="md-sec-title"><span class="cn">生涯冠军（转职业以来）</span>' +
          '<span class="en">Career Titles · since turning pro</span></div>' +
          '<div class="md-career-stats">' +
            stat(p.career.ranking, '排名赛', 'Ranking') +
            stat(p.career.nonRanking, '非排名赛', 'Non-Rank') +
            stat(p.career.total, '全部冠军', 'All Titles') +
            stat(p.career.crown, '三大赛', 'Triple Crown') +
            stat((p.career.first || '—') + '–' + (p.career.last || '—'),
                 '首冠–末冠', 'First–Last') +
          '</div>' +
          '<div class="md-list">' +
            p.career.items.map(function (it) {
              return '<div class="md-row"><b><span class="cn">' + esc(it.z) +
                '</span><span class="en">' + esc(it.e) + '</span></b>' +
                '<i>' + (it.y || '') +
                (it.r ? ' · <span class="tag-rank">排名赛</span>' : '') +
                (it.c ? ' · <span class="tag-crown">★ 三大赛</span>' : '') + '</i></div>';
            }).join('') +
          '</div>'
        : '') +

      '<div class="md-sec-title"><span class="cn">本赛季逐站成绩</span>' +
      '<span class="en">Event By Event</span></div>' +
      '<div class="md-list">' +
        (p.tournaments.length
          ? p.tournaments.map(function (t) {
              return '<div class="md-row"><b><span class="cn">' + esc(t.name_zh) + '</span>' +
                '<span class="en">' + esc(t.name_en) + '</span></b>' +
                '<i><span class="cn">' + esc(t.bestRound) + '</span>' +
                '<span class="en">' + esc(t.bestRound_en) + '</span></i></div>';
            }).join('')
          : '<div class="md-row"><b><span class="cn">暂无出场记录</span>' +
            '<span class="en">No appearances</span></b></div>') +
      '</div>' +

      (myCenturies.length
        ? '<div class="md-sec-title"><span class="cn">破百记录（' + myCenturies.length + ' 杆）</span>' +
          '<span class="en">Centuries (' + myCenturies.length + ')</span></div>' +
          '<div class="md-list">' +
          myCenturies.slice(0, 30).map(function (c) {
            return '<div class="md-row"><b><span class="cn">' + esc(c.tournament_zh) +
              ' · ' + esc(c.round_zh) + '</span><span class="en">' + esc(c.tournament_en) +
              ' · ' + esc(c.round_en) + '</span></b>' +
              '<i><span class="cn">' + c.value + ' vs ' + esc(c.opponent_zh) + '</span>' +
              '<span class="en">' + c.value + ' vs ' + esc(c.opponent_en) + '</span></i></div>';
          }).join('') + '</div>'
        : '');

    $('#modalBody').innerHTML = html;
    $('#modal').hidden = false;
    document.body.style.overflow = 'hidden';
  }

  function stat(v, cn, en) {
    return '<div class="md-stat"><b>' + esc(v) + '</b><span><span class="cn">' + cn +
      '</span><span class="en">' + en + '</span></span></div>';
  }

  function openEvent(tid) {
    var t = D.tournaments.filter(function (x) { return x.id === tid; })[0];
    if (!t) return;
    var ms = D.matches.filter(function (m) { return m.tournamentId === tid; });
    var rounds = {}, order = [];
    ms.forEach(function (m) {
      var k = m.round_en + '||' + m.round_zh;
      if (!rounds[k]) { rounds[k] = []; order.push(k); }
      rounds[k].push(m);
    });
    order.sort(function (a, b) {
      return (rounds[b][0].roundRank || 0) - (rounds[a][0].roundRank || 0);
    });

    var city = [t.city_zh || t.city_en, t.country_zh || t.country_en].filter(Boolean).join(' · ');
    var cent = D.centuries.filter(function (c) { return c.tournamentId === tid; });
    cent.sort(function (a, b) { return b.value - a.value; });

    var html =
      '<div class="md-head"><div>' +
        '<div class="md-name"><span class="cn">' + esc(t.name_zh) + '</span>' +
        '<span class="en">' + esc(t.name_en) + '</span></div>' +
        '<div class="md-tags">' +
          '<span>📍 <span class="cn">' + esc(city) + '</span>' +
          '<span class="en">' + esc([t.city_en, t.country_en].filter(Boolean).join(', ')) +
          '</span></span>' +
          '<span>' + dateRange(t.startDate, t.endDate) + '</span>' +
          '<span><span class="cn">' + STATUS_ZH[t.status] + '</span>' +
          '<span class="en">' + STATUS_EN[t.status] + '</span></span>' +
          '<span><span class="cn">' + t.completedMatches + '/' + t.matchCount + ' 场</span>' +
          '<span class="en">' + t.completedMatches + '/' + t.matchCount + ' matches</span></span>' +
          (t.type ? '<span><span class="cn">' + esc(TYPE_ZH[t.type]) + '</span>' +
            '<span class="en">' + esc(TYPE_EN[t.type]) + '</span></span>' : '') +
          (t.tripleCrown ? '<span class="tbadge crown">★ <span class="cn">三大赛</span>' +
            '<span class="en">Triple Crown</span></span>' : '') +
          (t.prizeTotal != null ? '<span><span class="cn">总奖金 ' + gbp(t.prizeTotal) +
            '</span><span class="en">Prize fund ' + gbp(t.prizeTotal) + '</span></span>' : '') +
          (t.prizeWinner != null ? '<span><span class="cn">冠军奖金 ' + gbp(t.prizeWinner) +
            '</span><span class="en">Winner ' + gbp(t.prizeWinner) + '</span></span>' : '') +
        '</div>' +
      '</div></div>' +

      (t.winner
        ? '<div class="md-sec-title"><span class="cn">决赛</span><span class="en">Final</span></div>' +
          '<div class="md-row" style="justify-content:center;gap:20px;font-size:17px">' +
          '<b><span class="cn">🏆 ' + esc(t.winner.name_zh) + '</span>' +
          '<span class="en">' + esc(t.winner.name_en) + '</span></b>' +
          '<i style="font-size:20px">' + esc(t.finalScore) + '</i>' +
          '<b><span class="cn">' + esc(t.runnerUp.name_zh) + '</span>' +
          '<span class="en">' + esc(t.runnerUp.name_en) + '</span></b></div>'
        : '') +

      '<div class="md-sec-title"><span class="cn">完整对阵</span>' +
      '<span class="en">Full Draw</span></div>' +
      '<div class="md-list" style="max-height:340px">' +
        (order.length
          ? order.map(function (k) {
              var parts = k.split('||');
              var rows = rounds[k].sort(function (a, b) {
                return (a.date + a.time).localeCompare(b.date + b.time);
              }).map(matchRow).join('');
              return '<div class="round-block"><div class="round-title">' +
                '<span><span class="cn">' + esc(parts[1]) + '</span>' +
                '<span class="en">' + esc(parts[0]) + '</span></span>' +
                '<span class="round-count">' + rounds[k].length + '</span></div>' + rows + '</div>';
            }).join('')
          : '<div class="md-row"><b><span class="cn">对阵尚未公布</span>' +
            '<span class="en">Draw not published</span></b></div>') +
      '</div>' +

      (cent.length
        ? '<div class="md-sec-title"><span class="cn">本站破百（' + cent.length + ' 杆）</span>' +
          '<span class="en">Centuries (' + cent.length + ')</span></div>' +
          '<div class="md-list">' +
          cent.slice(0, 20).map(function (c) {
            return '<div class="md-row"><b><span class="cn">' + esc(c.player_zh) + '</span>' +
              '<span class="en">' + esc(c.player) + '</span></b><i>' + c.value + '</i></div>';
          }).join('') + '</div>'
        : '');

    $('#modalBody').innerHTML = html;
    $('#modal').hidden = false;
    document.body.style.overflow = 'hidden';
  }

  function closeModal() {
    $('#modal').hidden = true;
    document.body.style.overflow = '';
  }

  /* ------------------------------------------------------------ 语言模式 */
  var LANGS = ['both', 'cn', 'en'];

  function setLang(l) {
    if (LANGS.indexOf(l) < 0) l = 'both';
    document.documentElement.setAttribute('data-lang', l);
    try { localStorage.setItem('snooker-lang', l); } catch (e) { /* 忽略隐私模式 */ }
    $$('#langSwitch .lang-btn').forEach(function (b) {
      b.classList.toggle('active', b.dataset.l === l);
    });
  }

  function initLang() {
    var saved = 'both';
    try { saved = localStorage.getItem('snooker-lang') || 'both'; } catch (e) { /* noop */ }
    setLang(saved);
    $('#langSwitch').addEventListener('click', function (e) {
      var b = e.target.closest('.lang-btn');
      if (b) setLang(b.dataset.l);
    });
  }

  /* ------------------------------------------------------------ 导航 */
  function switchTab(name) {
    $$('.tab-panel').forEach(function (p) {
      p.classList.toggle('active', p.id === name);
    });
    $$('.nav-link').forEach(function (a) {
      a.classList.toggle('active', a.dataset.tab === name);
    });
    $('#mainNav').classList.remove('open');
    if (history.replaceState) history.replaceState(null, '', '#' + name);
  }

  function initNav() {
    $$('.nav-link').forEach(function (a) {
      a.addEventListener('click', function (e) {
        e.preventDefault();
        switchTab(a.dataset.tab);
      });
    });
    $('#navToggle').addEventListener('click', function () {
      $('#mainNav').classList.toggle('open');
    });
    window.addEventListener('hashchange', function () {
      var h = location.hash.replace('#', '');
      if (h && $('#' + h)) switchTab(h);
    });
    var h0 = location.hash.replace('#', '');
    if (h0 && $('#' + h0)) switchTab(h0);
  }

  /* ------------------------------------------------------------ 事件绑定 */
  function initEvents() {
    // 赛程筛选
    $('#scheduleFilter').addEventListener('click', function (e) {
      var b = e.target.closest('.seg');
      if (!b) return;
      $$('#scheduleFilter .seg').forEach(function (x) { x.classList.remove('active'); });
      b.classList.add('active');
      schedFilter = b.dataset.f;
      renderSchedule();
    });
    $('#scheduleSearch').addEventListener('input', function (e) {
      schedQuery = e.target.value.trim();
      renderSchedule();
    });

    // 赛果 / 赛程卡片 → 赛事详情
    document.addEventListener('click', function (e) {
      var card = e.target.closest('.res-head');
      if (card) {
        card.parentElement.classList.toggle('open');
        return;
      }
      var ev = e.target.closest('[data-event]');
      if (ev && !e.target.closest('.res-body')) {
        openEvent(ev.dataset.event);
        return;
      }
      var pl = e.target.closest('[data-player]');
      if (pl) { openPlayer(pl.dataset.player); return; }
    });

    // 排名榜切换
    $('#rankTabs').addEventListener('click', function (e) {
      var b = e.target.closest('.seg');
      if (!b) return;
      rankIdx = parseInt(b.dataset.r, 10);
      varIdx = 0; rankLimit = 30;
      renderRankTabs(); renderRankings();
    });
    $('#rankVariant').addEventListener('click', function (e) {
      var b = e.target.closest('.seg');
      if (!b) return;
      varIdx = parseInt(b.dataset.v, 10);
      renderVariantTabs(); renderRankings();
    });
    $('#rankMore').addEventListener('click', function () {
      var g = D.rankings[rankIdx];
      var len = g.variants[Math.min(varIdx, g.variants.length - 1)].positions.length;
      rankLimit = rankLimit >= len ? 30 : Math.min(len, rankLimit + 50);
      renderRankings();
    });

    // 球员筛选
    $('#countryFilter').addEventListener('click', function (e) {
      var b = e.target.closest('.seg');
      if (!b) return;
      pCountry = b.dataset.c;
      renderCountryFilter(); renderPlayers();
    });
    $('#playerSearch').addEventListener('input', function (e) {
      pQuery = e.target.value.trim();
      renderPlayers();
    });
    $('#playerSort').addEventListener('click', function (e) {
      var b = e.target.closest('.seg');
      if (!b) return;
      $$('#playerSort .seg').forEach(function (x) { x.classList.remove('active'); });
      b.classList.add('active');
      pSort = b.dataset.s;
      renderPlayers();
    });

    // 破百筛选
    $('#centuryFilter').addEventListener('click', function (e) {
      var b = e.target.closest('.seg');
      if (!b) return;
      $$('#centuryFilter .seg').forEach(function (x) { x.classList.remove('active'); });
      b.classList.add('active');
      cFilter = b.dataset.c;
      renderCenturies();
    });

    // 历史冠军榜排序
    $('#titleSort').addEventListener('click', function (e) {
      var b = e.target.closest('.seg');
      if (!b) return;
      $$('#titleSort .seg').forEach(function (x) { x.classList.remove('active'); });
      b.classList.add('active');
      titleSort = b.dataset.s;
      renderTitleBoard();
    });

    // 历史冠军榜行 → 打开对应球员（现役走球员弹窗，名宿走生涯明细）
    $('#titleBody').addEventListener('click', function (e) {
      var tr = e.target.closest('tr[data-slug]');
      if (!tr) return;
      var slug = tr.dataset.slug;
      var pid = careerSlug2pid[slug];
      if (pid) openPlayer(pid);
      else if (tbBySlug[slug]) openLegacy(slug);
    });

    // 弹层
    document.addEventListener('click', function (e) {
      if (e.target.closest('[data-close]')) closeModal();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeModal();
    });

    // 面板内链接跳转
    $$('[data-goto]').forEach(function (a) {
      a.addEventListener('click', function (e) {
        e.preventDefault();
        switchTab(a.dataset.goto);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });
  }

  /* ------------------------------------------------------------ 启动 */
  function boot() {
    initLang();
    initMeta();
    renderKPI();
    renderChampions();
    renderRecent();
    renderCenturyStrip();
    renderSchedule();
    renderResults();
    renderRankTabs();
    renderRankings();
    renderCountryFilter();
    renderPlayers();
    renderLeaders();
    renderCenturies();
    // 建立 生涯slug → 球员ID 映射，供历史冠军榜点击跳转
    D.allPlayers.forEach(function (p) {
      if (p.career && p.career.slug) careerSlug2pid[p.career.slug] = p.id;
    });
    renderTitleBoard();
    initNav();
    initEvents();
    $('#loader').hidden = true;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
