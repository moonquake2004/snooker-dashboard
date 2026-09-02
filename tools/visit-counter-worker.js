/**
 * 看板访问统计后端 —— Cloudflare Worker + KV
 *   真正的按客户端 IP 去重，24 小时滚动窗口，跨部署域名（GitHub Pages / 分享站）共享同一份数据。
 *
 * 部署步骤（免费额度足够个人站点）：
 *   1. Cloudflare → Workers & Pages → 创建 Worker，把本文件内容整段粘进去，部署。
 *   2. 同页面 Settings → Variables → KV Namespace Bindings → 绑定一个命名空间，变量名填 VISITS。
 *   3. （可选）加一个环境变量（Secret）ADMIN_TOKEN，用于 ?stats 导出接口鉴权。
 *   4. 把 Worker 地址填到 index.html 的 window.VISIT_API，重新部署前端即可。
 *
 * 接口：
 *   POST /          计一次访问，返回 {uv, pv}
 *   GET  /?stats&token=xxx   导出明细（需配置 ADMIN_TOKEN）
 *
 * 说明：KV 为最终一致、无原子自增，高并发下 PV 可能少计几个；且单 key 上限 25 MB
 *      （约可存百万级 IP）。个人看板量级完全够用，量大了再换 D1 / Durable Objects。
 */

const DAY = 86400000; // 24 小时窗口

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Content-Type': 'application/json; charset=utf-8',
  'Cache-Control': 'no-store'
};

const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), { status, headers: CORS });

function ymd(ts) {
  return new Date(ts).toISOString().slice(0, 10); // YYYY-MM-DD
}

async function load(env, key) {
  const raw = await env.VISITS.get(key);
  if (!raw) return { pv: 0, ips: {} };
  try {
    const o = JSON.parse(raw);
    return { pv: o.pv | 0, ips: o.ips || {} };
  } catch (e) {
    return { pv: 0, ips: {} };
  }
}

const save = (env, key, val) => env.VISITS.put(key, JSON.stringify(val));

// 清掉窗口外的 IP，避免单 key 无限膨胀
function prune(day, now) {
  let changed = false;
  for (const ip in day.ips) {
    if (now - day.ips[ip] > DAY) { delete day.ips[ip]; changed = true; }
  }
  return changed;
}

// 合并两天表，统计仍在 24 小时窗口内的独立 IP
function countUV(a, b, now) {
  const seen = new Set();
  for (const ip in a.ips) if (now - a.ips[ip] <= DAY) seen.add(ip);
  for (const ip in b.ips) if (now - b.ips[ip] <= DAY) seen.add(ip);
  return seen.size;
}

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') return new Response(null, { headers: CORS });

    const now = Date.now();
    const today = ymd(now);
    const yest = ymd(now - DAY);

    const ip =
      request.headers.get('CF-Connecting-IP') ||
      (request.headers.get('X-Forwarded-For') || '').split(',')[0].trim() ||
      '0.0.0.0';

    const [d0, d1, total] = await Promise.all([
      load(env, today), load(env, yest), load(env, 'total')
    ]);

    // ---- 导出明细
    if (new URL(request.url).searchParams.has('stats')) {
      if (env.ADMIN_TOKEN &&
          new URL(request.url).searchParams.get('token') !== env.ADMIN_TOKEN) {
        return json({ error: 'forbidden' }, 403);
      }
      return json({
        uv: countUV(d0, d1, now),
        pv: (total && total.pv) | 0,
        today: d0,
        yesterday: d1
      });
    }

    // ---- 计数
    prune(d0, now);
    prune(d1, now);
    d0.ips[ip] = now;
    d0.pv = (d0.pv | 0) + 1;
    const nextTotal = { pv: ((total && total.pv) | 0) + 1 };

    // 不阻塞响应：写完再返回，个人站点量级下耗时可忽略
    await Promise.all([
      save(env, today, d0),
      save(env, yest, d1),
      save(env, 'total', nextTotal)
    ]);

    return json({ uv: countUV(d0, d1, now), pv: nextTotal.pv });
  }
};
