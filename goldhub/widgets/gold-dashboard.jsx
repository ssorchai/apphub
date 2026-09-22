import { run } from 'uebersicht';

// ============================================================================
// Gold Dashboard — การ์ดรวม 3 ตัวที่เคยแยกกัน (22 ก.ย. 26)
//   กรอบหลัก = cme-putcall · มุมขวาบน = gold-update · แปะซ้าย = cme-ticker (ยาวขึ้นเป็น ~24 แถว)
// โหลดข้อมูลรอบเดียวต่อ 5 วินาที: /api/state (cme + ราคาสด) + /api/ticker จาก goldhub daemon
// API ยิงไม่ได้ใน 2 วิ -> อ่านไฟล์ /tmp ทั้งสามแบบเดิม (footer ขึ้น "· file")
// การ์ดเดิมสามตัวเก็บไว้ใน repo (goldhub/widgets/) เผื่อถอยกลับ
// ============================================================================

const USE_API = true;            // false = โหมดไฟล์อย่างเดียว (สวิตช์ถอยกลับ)
const API = 'http://127.0.0.1:8787';
const API_TIMEOUT = 2000;
const TICKER_STATE = '$HOME/Library/Application Support/apphub/goldhub/state/ticker_state.json';
const CMD = "cat /tmp/cme_putcall.json 2>/dev/null; echo; echo '@@LIVE@@'; cat /tmp/gold_data.json 2>/dev/null;"
  + " echo; echo '@@TICK@@'; cat /tmp/cme_ticker.json 2>/dev/null";

const parse = (t) => { try { return JSON.parse(t); } catch (e) { return null; } };
const fetchJson = (url) => Promise.race([
  fetch(url).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }),
  new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), API_TIMEOUT)),
]);

const load = (dispatch) => {
  const viaFile = () => run(CMD).then((out) => {
    const [a, rest = ''] = String(out).split('@@LIVE@@');
    const [b, c = ''] = rest.split('@@TICK@@');
    dispatch({ type: 'DATA', cme: parse(a), live: parse(b), tick: parse(c), src: 'file' });
  });
  if (!USE_API) return viaFile();
  return Promise.all([
    fetchJson(API + '/api/state?fields=cme,live'),
    // ticker ยังไม่มี (503 ช่วงเพิ่ง start) ต้องไม่ลากทั้งการ์ดตกไปโหมดไฟล์
    fetchJson(API + '/api/ticker').catch(() => null),
  ]).then(([s, t]) => dispatch({ type: 'DATA', cme: s.cme, live: s.live, tick: t, src: 'api' }))
    .catch(viaFile);
};

export const command = load;
export const refreshFrequency = 5000;

// ค่าที่ผู้ใช้เลือกในกราฟ จำใน localStorage (ใช้ key เดิมของ cme-putcall ให้ค่าที่เลือกไว้ติดมาด้วย)
const PREF_KEY = 'cme-putcall.prefs';
const pref = (k, dflt) => {
  try { const v = (JSON.parse(localStorage.getItem(PREF_KEY)) || {})[k]; return v != null ? v : dflt; } catch (e) { return dflt; }
};
const savePref = (k, v) => {
  try {
    const all = JSON.parse(localStorage.getItem(PREF_KEY)) || {};
    all[k] = v;
    localStorage.setItem(PREF_KEY, JSON.stringify(all));
  } catch (e) { /* localStorage ใช้ไม่ได้ก็แค่ไม่จำ */ }
};

export const initialState = {
  cme: null, live: null, tick: null, src: null,
  refreshing: false, hover: null, hold: 0, resetting: false,
  chartMode: pref('chartMode', 'id'), sdMode: pref('sdMode', 'open'), dMode: pref('dMode', 'off'),
};
export const updateState = (event, prev) => {
  switch (event.type) {
    // command เป็นฟังก์ชัน Übersicht จะยิง UB/COMMAND_RAN เองแบบไม่มี output -- ไม่ใช้ event นั้นเลย
    case 'DATA': return { ...prev, cme: event.cme, live: event.live, tick: event.tick, src: event.src };
    case 'REFRESH_START': return { ...prev, refreshing: true };
    case 'REFRESH_DONE': return { ...prev, refreshing: false };
    case 'CHART_MODE': return { ...prev, chartMode: event.mode };
    case 'SD_MODE': return { ...prev, sdMode: event.mode };
    case 'DELTA_MODE': return { ...prev, dMode: event.mode };
    case 'HOVER': return { ...prev, hover: event.k };
    case 'HOLD_TICK': return { ...prev, hold: event.pct };
    case 'HOLD_END': return { ...prev, hold: 0 };
    case 'RESET_START': return { ...prev, hold: 0, resetting: true };
    case 'RESET_DONE': return { ...prev, resetting: false };
    default: return prev;
  }
};

// ---- palette เดียวทั้งการ์ด (ของ cme-putcall / gold-update) ----
// ห้ามใช้ backdrop-filter (กระพริบใน Übersicht ทุกรอบ re-render)
const macos = {
  material: 'rgba(24, 26, 33, 0.55)',
  border: '0.5px solid rgba(255, 255, 255, 0.16)',
  radius: '22px',
  shadow: '0 10px 28px rgba(0, 0, 0, 0.32)',
  font: '-apple-system, "SF Pro Display", "SF Pro Text", "Helvetica Neue", sans-serif',
  mono: '"SF Mono", ui-monospace, Menlo, monospace',
  label: '#ffffff',
  secondary: 'rgba(255, 255, 255, 0.78)',
  tertiary: 'rgba(255, 255, 255, 0.58)',
  divider: 'rgba(255, 255, 255, 0.18)',
  green: '#30d158',
  red: '#ff453a',
  blue: '#64d2ff',
  yellow: '#ffd60a',
  orange: '#ffb340',
};

// ---- ขนาด ----
const PAD = 16;
const TICK_W = 258;      // เนื้อหาคอลัมน์ ticker (เท่าการ์ดเดิม)
const MAIN_W = 960;      // เนื้อหากรอบหลัก (กราฟกว้างเท่านี้)
const GOLD_W = 236;      // บล็อกราคาสดมุมขวาบน
const COL_GAP = 16;      // ระยะแต่ละฝั่งของเส้นคั่น ticker | หลัก
const CARD_W = PAD + TICK_W + COL_GAP * 2 + MAIN_W + PAD;
const CHART_H = 400;
const TICKER_ROWS = 24;
const ACTIVE_ROWS = 5;
const HOLD_MS = 5000;

const fmt = (v) => (v == null ? '--' : Number(v).toLocaleString());
const num = (v) => (typeof v === 'number' ? v : parseFloat(String(v).replace(/[,%+]/g, '')) || 0);
const fmt2 = (v, d = 2) => num(v).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
const secTitle = {
  fontSize: '10px', color: macos.secondary, fontWeight: '600',
  letterSpacing: '0.4px', textTransform: 'uppercase',
};
const vline = { borderLeft: `0.5px solid ${macos.divider}` };

// ⌥-drag ย้ายทั้งการ์ด — ตำแหน่งเก็บ localStorage (ค่าเริ่มต้น = ที่เดิมของ cme-putcall)
const POS_KEY = 'gold-dashboard.pos';
const savedPos = () => {
  try { return JSON.parse(localStorage.getItem(POS_KEY)) || {}; } catch (e) { return {}; }
};
const altDrag = (e) => {
  if (!e.altKey) return;
  e.preventDefault();
  e.stopPropagation();
  const el = e.currentTarget;
  const sx = e.clientX, sy = e.clientY;
  const rect = el.getBoundingClientRect();
  const left0 = rect.left, bottom0 = window.innerHeight - rect.bottom;
  const move = (ev) => {
    const pos = { left: `${left0 + ev.clientX - sx}px`, bottom: `${bottom0 - (ev.clientY - sy)}px` };
    el.style.left = pos.left;
    el.style.bottom = pos.bottom;
    localStorage.setItem(POS_KEY, JSON.stringify(pos));
  };
  const up = () => {
    window.removeEventListener('mousemove', move);
    window.removeEventListener('mouseup', up);
  };
  window.addEventListener('mousemove', move);
  window.addEventListener('mouseup', up);
};

// ============================================================================
// ส่วน cme-putcall
// ============================================================================
const PcRow = ({ title, pc }) => {
  if (!pc) return null;
  const total = pc.put + pc.call;
  const putShare = total > 0 ? (pc.put / total) * 100 : 50;
  return (
    <div style={{ marginTop: '10px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={secTitle}>{title}</span>
        <span style={{ fontSize: '13px', fontWeight: '600' }}>
          <span style={{ color: macos.orange }}>P {fmt(pc.put)}</span>
          <span style={{ color: macos.tertiary, margin: '0 4px' }}>/</span>
          <span style={{ color: macos.blue }}>C {fmt(pc.call)}</span>
        </span>
      </div>
      <div style={{ height: '4px', borderRadius: '2px', overflow: 'hidden', display: 'flex', marginTop: '4px', background: 'rgba(255,255,255,0.12)' }}>
        <div style={{ width: `${putShare}%`, background: macos.orange }} />
        <div style={{ flex: 1, background: macos.blue }} />
      </div>
    </div>
  );
};

const TopActive = ({ top, sc }) => {
  if (!top || !top.length) return null;
  return (
    <div style={{ marginTop: '6px' }}>
      <div style={secTitle}>Top Active</div>
      {top.map((t) => (
        <div key={t.strike} style={{ display: 'flex', alignItems: 'baseline', gap: '8px', fontSize: '12px', marginTop: '3px' }}>
          <span style={{ fontWeight: '600', color: sc(t.strike), minWidth: '38px' }}>{t.strike}</span>
          <span style={{ color: macos.secondary }}>{fmt(t.total)}</span>
          <span style={{ color: macos.tertiary, marginLeft: 'auto' }}>
            <span style={{ color: macos.orange }}>P {fmt(t.put)}</span> · <span style={{ color: macos.blue }}>C {fmt(t.call)}</span>
          </span>
        </div>
      ))}
    </div>
  );
};

const SdBlock = ({ sd }) => {
  if (!sd) {
    return (
      <div style={{ marginTop: '10px' }}>
        <div style={secTitle}>SD Range</div>
        <div style={{ fontSize: '12px', color: macos.tertiary, marginTop: '2px' }}>N/A</div>
      </div>
    );
  }
  const rows = [[1, sd.b1, sd.s1], [2, sd.b2, sd.s2], [3, sd.b3, sd.s3]];
  return (
    <div style={{ marginTop: '10px' }}>
      <div style={secTitle}>SD Range</div>
      <div style={{ fontSize: '11px', color: macos.tertiary, marginTop: '1px', whiteSpace: 'nowrap' }}>
        open {fmt(sd.open)} · vol {sd.vol_used} · dte {sd.dte}
      </div>
      {rows.map(([n, b, s]) => (
        <div key={n} style={{ display: 'flex', alignItems: 'baseline', gap: '8px', fontSize: '12px', marginTop: '3px', fontWeight: '600' }}>
          <span style={{ color: macos.tertiary }}>{n}σ</span>
          <span style={{ color: macos.secondary }}>±{(n * sd.sd1).toFixed(1)}</span>
          <span style={{ marginLeft: 'auto' }}>
            <span style={{ color: macos.green }}>{b.toFixed(1)}</span>
            <span style={{ color: macos.tertiary }}> / </span>
            <span style={{ color: macos.red }}>{s.toFixed(1)}</span>
          </span>
        </div>
      ))}
    </div>
  );
};

// smile: median-3 กัน outlier + weighted MA แล้ววาดเป็น Catmull-Rom (ค่าดิบในกล่อง hover ไม่ถูกแตะ)
const smooth = (vs) => {
  if (vs.length < 5) return vs;
  const v = vs.map((r) => r[1]);
  const med = v.map((x, i) => (i > 0 && i < v.length - 1 ? [v[i - 1], x, v[i + 1]].sort((a, b) => a - b)[1] : x));
  const w = [1, 2, 3, 2, 1];
  return vs.map((r, i) => {
    let s = 0, ws = 0;
    for (let k = -2; k <= 2; k++) {
      const j = i + k;
      if (j >= 0 && j < med.length) { s += med[j] * w[k + 2]; ws += w[k + 2]; }
    }
    return [r[0], s / ws];
  });
};
const splinePath = (p) => {
  if (p.length < 2) return '';
  let d = `M${p[0][0].toFixed(1)},${p[0][1].toFixed(1)}`;
  for (let i = 0; i < p.length - 1; i++) {
    const p0 = p[Math.max(i - 1, 0)], p1 = p[i], p2 = p[i + 1], p3 = p[Math.min(i + 2, p.length - 1)];
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += `C${c1[0].toFixed(1)},${c1[1].toFixed(1)} ${c2[0].toFixed(1)},${c2[1].toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }
  return d;
};
const interp = (rows, k) => {
  if (!rows.length || k < rows[0][0] || k > rows[rows.length - 1][0]) return null;
  for (let i = 0; i < rows.length; i++) {
    if (rows[i][0] === k) return rows[i][1];
    if (i > 0 && k < rows[i][0]) {
      const [k0, v0] = rows[i - 1], [k1, v1] = rows[i];
      return v0 + ((v1 - v0) * (k - k0)) / (k1 - k0);
    }
  }
  return null;
};

// ปุ่มสลับโหมด: กันคลิกไม่ให้ทะลุไปถึงกรอบหลัก (คลิกกรอบหลัก = copy)
const ModePill = ({ label, on, onPick }) => (
  <span
    onClick={(e) => { e.stopPropagation(); onPick(); }}
    onDoubleClick={(e) => e.stopPropagation()}
    style={{
      fontSize: '11px', fontWeight: '700', padding: '3px 10px', borderRadius: '999px',
      color: on ? '#fff' : macos.secondary,
      background: on ? 'rgba(100,210,255,0.35)' : 'rgba(255,255,255,0.12)',
    }}>
    {label}
  </span>
);

const Chart = ({ data, liveF, mode, sdMode, dMode, hover, dispatch }) => {
  const ch = data.chart;
  if (!ch) return null;
  const W = MAIN_W, H = CHART_H, L = 38, R = 38, T = 8, B = 22;
  const F = data.F;
  const fNow = liveF != null ? liveF : F;
  const sig = F && data.iv && data.dte > 0 ? (F * data.iv) / 100 * Math.sqrt(data.dte / 365) : null;
  const rows = (ch[mode] || []).filter((r) => r[1] + r[2] > 0);
  const strikes = [...new Set([...ch.id, ...ch.oi].map((r) => r[0]))].sort((a, b) => a - b);
  if (!strikes.length) return null;
  const sdOpen = data.sd && data.sd.open && data.sd.sd1 ? data.sd : null;
  const useOpen = sdMode === 'open' && sdOpen;
  const bandC = useOpen ? sdOpen.open : F;
  const bandS = useOpen ? sdOpen.sd1 : sig;
  let lo = strikes[0], hi = strikes[strikes.length - 1];
  if (sig && F) {
    let a = F - 3.5 * sig, b = F + 3.5 * sig;
    if (useOpen) { a = Math.min(a, bandC - 3.3 * bandS); b = Math.max(b, bandC + 3.3 * bandS); }
    lo = Math.max(lo, a); hi = Math.min(hi, b);
  }
  lo -= 5; hi += 5;
  const x = (v) => L + ((v - lo) / (hi - lo)) * (W - L - R);
  const vrows = rows.filter((r) => r[0] >= lo && r[0] <= hi);
  const ymax = Math.max(1, ...vrows.map((r) => Math.max(r[1], r[2]))) * 1.1;
  const y = (v) => T + (1 - v / ymax) * (H - T - B);
  const ks = strikes.filter((k) => k >= lo && k <= hi);
  const stepX = ks.length > 1 ? Math.min(...ks.slice(1).map((k, i) => k - ks[i])) : 5;
  const bw = Math.max(1.2, (x(lo + stepX) - x(lo)) * 0.36);

  const vs = smooth((ch.vs || []).filter((r) => r[0] >= lo && r[0] <= hi));
  let yr = null, vlo = 0, vhi = 0;
  if (vs.length > 2) {
    vlo = Math.min(...vs.map((r) => r[1])); vhi = Math.max(...vs.map((r) => r[1]));
    const pad = (vhi - vlo) * 0.15 + 0.5; vlo -= pad; vhi += pad;
    yr = (v) => T + (1 - (v - vlo) / (vhi - vlo)) * (H - T - B);
  }

  const onMove = (e) => {
    const bb = e.currentTarget.ownerSVGElement.getBoundingClientRect();
    const v = lo + (((e.clientX - bb.left) * W) / bb.width - L) / (W - L - R) * (hi - lo);
    let k = ks[0];
    for (const s of ks) if (Math.abs(s - v) < Math.abs(k - v)) k = s;
    if (k !== hover) dispatch({ type: 'HOVER', k });
  };
  const idm = new Map(ch.id.map((r) => [r[0], r])), oim = new Map(ch.oi.map((r) => [r[0], r]));

  // เส้น delta: fetcher คิดไว้ที่ F ตอนดึงข้อมูล -> เลื่อนทั้งชุดตาม F สด ให้ยังเป็น delta เดิม
  const dAll = (data.delta || []).map((d) => ({ ...d, k: d.k + (fNow && F ? fNow - F : 0) }));
  const dLines = dMode === 'off' ? [] : dAll.filter((d) => d.k > lo && d.k < hi);
  const dCurve = dAll.map((d) => [d.k, d.side === 'P' ? 1 - d.d : d.d]);
  const deltaAt = (k) => {
    if (dCurve.length < 2) return null;
    const cd = interp(dCurve, k);
    return cd == null ? null : (k >= (fNow || F) ? cd : 1 - cd);
  };

  const xStep = (hi - lo) / 50 > 12 ? 100 : 50;
  const xt = [];
  for (let s = Math.ceil(lo / xStep) * xStep; s <= hi; s += xStep) xt.push(s);
  const bands = bandS && bandC ? [3, 2, 1] : [];
  const bandFill = { 1: 'rgba(255,255,255,0.10)', 2: 'rgba(255,255,255,0.065)', 3: 'rgba(255,255,255,0.035)' };

  let tip = null;
  if (hover != null && hover >= lo && hover <= hi) {
    const X = x(hover), idr = idm.get(hover), oir = oim.get(hover);
    const vk = interp(ch.vs || [], hover), vks = interp(vs, hover);
    const dist = useOpen ? (hover - bandC) / bandS : sig && fNow ? (hover - fNow) / sig : null;
    const line = (name, r) => `${name}  P ${r ? fmt(r[1]) : 0}  C ${r ? fmt(r[2]) : 0}  Σ ${r ? fmt(r[1] + r[2]) : 0}`;
    const lines = mode === 'id'
      ? [[line('Intraday', idr), true], [line('OI', oir), false]]
      : [[line('OI', oir), true], [line('Intraday', idr), false]];
    const hd = deltaAt(hover);
    const bxW = 214, bxH = (vk != null ? 74 : 58) + (hd != null ? 15 : 0);
    const bx = X + 12 + bxW > W - R ? X - 12 - bxW : X + 12;
    tip = (
      <g pointerEvents="none">
        <rect x={X - Math.max(3, bw * 1.3)} y={T} width={Math.max(6, bw * 2.6)} height={H - T - B} fill="rgba(255,255,255,0.10)" />
        <line x1={X} x2={X} y1={T} y2={H - B} stroke="rgba(255,255,255,0.75)" strokeWidth="1" strokeDasharray="3 3" />
        {yr && vks != null && <circle cx={X} cy={yr(vks)} r="3.5" fill="#ff6b6b" stroke="#fff" strokeWidth="1.2" />}
        <rect x={bx} y={T + 18} width={bxW} height={bxH} rx="6" fill="rgba(20,22,28,0.92)" stroke="rgba(255,255,255,0.25)" />
        <text x={bx + 10} y={T + 36} fontSize="13" fontWeight="700" fill="#fff">
          {fmt(hover)}
          {dist != null && <tspan fontSize="10.5" fontWeight="400" fill={macos.tertiary}>{`  ${dist >= 0 ? '+' : ''}${dist.toFixed(2)}σ จาก ${useOpen ? 'open' : 'F'}`}</tspan>}
        </text>
        {lines.map(([t, bold], i) => (
          <text key={i} x={bx + 10} y={T + 53 + i * 15} fontSize="11" fontWeight={bold ? '700' : '400'}
            fill={bold ? '#fff' : macos.secondary}>{t}</text>
        ))}
        {vk != null && (
          <text x={bx + 10} y={T + 83} fontSize="11" fill="#ff8a8a">
            {`${data.iv_settle != null ? 'Vol Settle' : 'IV'} ${vk.toFixed(2)}%`}
          </text>
        )}
        {hd != null && (
          <text x={bx + 10} y={T + (vk != null ? 98 : 83)} fontSize="11" fill={macos.secondary}>
            {`Δ ${hd.toFixed(2)}${hover >= (fNow || F) ? 'C' : 'P'}`}
          </text>
        )}
        <rect x={X - 22} y={H - B + 3} width="44" height="15" rx="3" fill="#fff" />
        <text x={X} y={H - B + 14} fontSize="10.5" fontWeight="700" fill="#111" textAnchor="middle">{fmt(hover)}</text>
      </g>
    );
  }

  return (
    <div style={{ marginTop: '10px', borderTop: `0.5px solid ${macos.divider}`, paddingTop: '8px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
        <span style={{ ...secTitle, color: macos.label, marginRight: '4px' }}>Put / Call by Strike</span>
        <ModePill label="Intraday" on={mode === 'id'} onPick={() => { savePref('chartMode', 'id'); dispatch({ type: 'CHART_MODE', mode: 'id' }); }} />
        <ModePill label="OI" on={mode === 'oi'} onPick={() => { savePref('chartMode', 'oi'); dispatch({ type: 'CHART_MODE', mode: 'oi' }); }} />
        <span style={{ ...secTitle, marginLeft: '10px' }}>SD</span>
        <ModePill label="Open 0.6" on={!!useOpen} onPick={() => { savePref('sdMode', 'open'); dispatch({ type: 'SD_MODE', mode: 'open' }); }} />
        <ModePill label="CME" on={!useOpen} onPick={() => { savePref('sdMode', 'cme'); dispatch({ type: 'SD_MODE', mode: 'cme' }); }} />
        <ModePill label="Δ" on={dMode !== 'off'} onPick={() => {
          const m = dMode === 'off' ? 'all' : 'off';
          savePref('dMode', m); dispatch({ type: 'DELTA_MODE', mode: m });
        }} />
        <span style={{ marginLeft: 'auto', fontSize: '11px', color: macos.tertiary }}>
          <span style={{ color: macos.orange }}>■</span> Put&nbsp;&nbsp;
          <span style={{ color: macos.blue }}>■</span> Call&nbsp;&nbsp;
          <span style={{ color: '#ff8a8a' }}>- -</span> {data.iv_settle != null ? 'Vol Settle' : 'IV'}
        </span>
      </div>
      <svg width={W} height={H} style={{ display: 'block' }}>
        {bands.map((n) => {
          const a = Math.max(x(bandC - n * bandS), L), b = Math.min(x(bandC + n * bandS), W - R);
          return <rect key={n} x={a} y={T} width={Math.max(0, b - a)} height={H - T - B} fill={bandFill[n]} />;
        })}
        {[0.5, 1].map((f) => (
          <g key={f}>
            <line x1={L} x2={W - R} y1={y((ymax / 1.1) * f)} y2={y((ymax / 1.1) * f)} stroke="rgba(255,255,255,0.10)" />
            <text x={L - 5} y={y((ymax / 1.1) * f) + 3} fontSize="9.5" fill={macos.tertiary} textAnchor="end">
              {fmt(Math.round((ymax / 1.1) * f))}
            </text>
          </g>
        ))}
        <line x1={L} x2={W - R} y1={y(0)} y2={y(0)} stroke="rgba(255,255,255,0.25)" />
        {liveF != null && F && F > lo && F < hi && (
          <line x1={x(F)} x2={x(F)} y1={T} y2={H - B} stroke="rgba(255,255,255,0.25)" strokeWidth="0.8" strokeDasharray="2 4" />
        )}
        {fNow && fNow > lo && fNow < hi && (
          <line x1={x(fNow)} x2={x(fNow)} y1={T + 16} y2={H - B} stroke="rgba(255,255,255,0.45)" strokeWidth="0.8" />
        )}
        {vrows.map(([s, p, c]) => (
          <g key={s}>
            {p > 0 && <rect x={x(s) - bw - 0.4} y={y(p)} width={bw} height={y(0) - y(p)} fill={macos.orange} />}
            {c > 0 && <rect x={x(s) + 0.4} y={y(c)} width={bw} height={y(0) - y(c)} fill={macos.blue} />}
          </g>
        ))}
        {dLines.map((d) => (
          <g key={d.side + d.d}>
            <line x1={x(d.k)} x2={x(d.k)} y1={T} y2={H - B} stroke="rgba(255,255,255,0.30)"
              strokeWidth="0.8" strokeDasharray="4 4" />
            <text x={x(d.k) - 3} y={T + 20} fontSize="9" fill={macos.tertiary}
              transform={`rotate(-90 ${x(d.k) - 3} ${T + 20})`} textAnchor="end">
              {`${Math.round(d.d * 100)}Δ${d.side}`}
            </text>
          </g>
        ))}
        {yr && (
          <g>
            <path d={splinePath(vs.map((r) => [x(r[0]), yr(r[1])]))} fill="none" stroke="#ff6b6b"
              strokeWidth="1.6" strokeDasharray="6 4" />
            {[vlo, (vlo + vhi) / 2, vhi].map((v, i) => (
              <text key={i} x={W - R + 5} y={yr(v) + 3} fontSize="9.5" fill={macos.tertiary}>{v.toFixed(1)}</text>
            ))}
          </g>
        )}
        {fNow && fNow > lo && fNow < hi && (
          <g>
            <rect x={x(fNow) - 46} y={T} width="92" height="16" rx="3" fill="rgba(255,255,255,0.85)" />
            <text x={x(fNow)} y={T + 12} fontSize="10.5" fontWeight="700" fill="#111" textAnchor="middle">
              {`Future ${fmt(fNow)}`}
            </text>
          </g>
        )}
        {xt.map((s) => (
          <text key={s} x={x(s)} y={H - 6} fontSize="10" fill={macos.tertiary} textAnchor="middle">{fmt(s)}</text>
        ))}
        {bandS && bandC && (
          <text x={L + 4} y={T + 12} fontSize="10" fill={macos.tertiary}>
            {useOpen
              ? `SD open ${fmt(bandC)} · DTE 0.6 · 1σ ±${bandS.toFixed(1)}`
              : `SD F ${fmt(bandC)} · DTE ${data.dte.toFixed(2)} · 1σ ±${bandS.toFixed(1)}`}
          </text>
        )}
        {tip}
        <rect x={L} y={T} width={W - L - R} height={H - T - B} fill="transparent"
          onMouseMove={onMove} onMouseLeave={() => dispatch({ type: 'HOVER', k: null })}
          style={{ cursor: 'crosshair' }} />
      </svg>
    </div>
  );
};

// ============================================================================
// ส่วน gold-update (มุมขวาบนของกรอบหลัก)
// ============================================================================
const sessionState = () => {
  const now = new Date();
  const h = now.getHours() + now.getMinutes() / 60;
  const day = now.getDay();
  const weekend = day === 0 || (day === 6 && h >= 5);
  const on = (s, e) => !weekend && (s < e ? h >= s && h < e : h >= s || h < e);
  const ldn = on(14, 23);
  const ny = on(19, 5);
  const golden = ldn && ny;
  return [
    { icon: '🌏', label: 'ASIA', on: on(7, 15), golden: false },
    { icon: '🌍', label: 'LDN', on: ldn, golden },
    { icon: '🌎', label: 'NY', on: ny, golden },
  ];
};

const SessionLight = ({ s }) => {
  const color = s.on ? (s.golden ? macos.yellow : macos.green) : macos.orange;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '4px',
      padding: '2px 7px', borderRadius: '999px',
      background: s.on ? 'rgba(255, 255, 255, 0.22)' : 'rgba(255, 255, 255, 0.1)',
    }}>
      <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: color, boxShadow: `0 0 5px ${color}` }} />
      <span style={{ fontSize: '9px', fontWeight: '700', letterSpacing: '0.5px', color: s.on ? macos.label : macos.secondary }}>
        {s.icon} {s.label}
      </span>
    </span>
  );
};

const Asset = ({ asset, fallbackName, accent, showOpen }) => {
  if (!asset) {
    return (
      <div style={{ marginTop: '8px' }}>
        <div style={{ ...secTitle, marginBottom: '2px' }}>{fallbackName}</div>
        <span style={{ fontSize: '24px', fontWeight: '600', color: macos.tertiary }}>N/A</span>
      </div>
    );
  }
  const change = num(asset.change);
  const up = change >= 0;
  return (
    <div style={{ marginTop: '8px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '6px', ...secTitle, marginBottom: '2px', whiteSpace: 'nowrap' }}>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {asset.name}
          {asset.sym && <span style={{ color: macos.tertiary }}> · {asset.sym}</span>}
        </span>
        {showOpen && asset.open != null && (
          <span style={{ color: macos.tertiary, textTransform: 'none', flexShrink: 0 }}>O {fmt2(asset.open)}</span>
        )}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{ fontSize: '24px', fontWeight: '600', letterSpacing: '-0.4px', color: accent || macos.label }}>
          {fmt2(asset.price)}
        </span>
        <span style={{ fontSize: '12px', fontWeight: '600', color: up ? macos.green : macos.red }}>
          {up ? '+' : ''}{fmt2(change)}
          <span style={{ opacity: 0.75, marginLeft: '4px', fontSize: '10px' }}>{up ? '+' : ''}{fmt2(asset.percent)}%</span>
        </span>
      </div>
    </div>
  );
};

const GoldBlock = ({ live }) => {
  // คลิก = เปิด vol2vol.com เหมือนการ์ดเดิม (ไม่ให้ทะลุไป copy ของกรอบหลัก)
  const open = (e) => {
    if (e.altKey) return;
    e.preventDefault();
    e.stopPropagation();
    run("open -a 'Google Chrome' 'https://www.vol2vol.com'");
  };
  if (!live) {
    return (
      <div style={{ width: `${GOLD_W}px`, flexShrink: 0, ...vline, paddingLeft: '16px', color: macos.tertiary, fontSize: '12px' }}>
        ราคาสดยังไม่มา
      </div>
    );
  }
  const stale = live.ts && Date.now() / 1000 - live.ts > 180;
  const hasDiff = live.diff != null;
  const marketTime = (live.future && live.future.time) || (live.spot && live.spot.time) || '--';
  const spreadColor = !hasDiff ? macos.tertiary : num(live.diff) >= 0 ? macos.label : macos.blue;
  const fo = live.future && live.future.change_open;
  return (
    <div onClick={open} onDoubleClick={(e) => e.stopPropagation()}
      title="Click = open vol2vol.com"
      style={{ width: `${GOLD_W}px`, flexShrink: 0, ...vline, paddingLeft: '16px', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '4px' }}>
        <div style={{ display: 'flex', gap: '4px' }}>
          {sessionState().map((s) => <SessionLight s={s} key={s.label} />)}
        </div>
        {stale && <span style={{ fontSize: '10px', fontWeight: '700', color: macos.orange }}>●</span>}
      </div>
      <Asset asset={live.future} fallbackName="Gold Futures" showOpen />
      <Asset asset={live.spot || live.cfd} fallbackName="XAU/USD Spot" accent={macos.blue} />
      <div style={{ borderTop: `0.5px solid ${macos.divider}`, marginTop: '10px', paddingTop: '7px',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '11px', color: macos.secondary, fontWeight: '600', letterSpacing: '0.4px' }}>SPREAD DIFF</span>
        <span style={{ fontSize: '20px', fontWeight: '700', letterSpacing: '-0.3px', color: spreadColor }}>
          {hasDiff ? `${num(live.diff) > 0 ? '+' : ''}${fmt2(live.diff)}` : 'N/A'}
        </span>
      </div>
      {fo != null && (
        <div style={{ marginTop: '3px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '11px', color: macos.secondary, fontWeight: '600', letterSpacing: '0.4px' }}>FUT FROM OPEN</span>
          <span style={{ fontSize: '12px', fontWeight: '600', color: num(fo) >= 0 ? macos.green : macos.red }}>
            {num(fo) >= 0 ? '+' : ''}{fmt2(fo)}
            <span style={{ opacity: 0.75, marginLeft: '4px', fontSize: '10px' }}>
              {num(fo) >= 0 ? '+' : ''}{fmt2(live.future.percent_open)}%
            </span>
          </span>
        </div>
      )}
      <div style={{ fontSize: '10px', color: macos.tertiary, marginTop: 'auto', paddingTop: '6px', textAlign: 'right' }}>
        Market {marketTime} · Sync {live.system_time}
      </div>
    </div>
  );
};

// ============================================================================
// ส่วน cme-ticker (คอลัมน์ซ้าย)
// ============================================================================
let holdTimer = null;   // เก็บนอก render — render ถูกเรียกใหม่ทุกรอบ
const clearHold = () => { if (holdTimer) { clearInterval(holdTimer); holdTimer = null; } };

const hhmm = (ts) => {
  const d = new Date(ts * 1000);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
};
// OI (ถือข้ามคืน) + Intra (volume วันนี้ก่อน flow ก้อนนี้) / OI = 0 = เปิดสถานะใหม่ -> เขียว
const oiCell = (oi, intra) => {
  const inTxt = intra != null ? String(intra) : '?';
  if (oi == null) return { txt: `–+${inTxt}`, color: macos.tertiary };
  return { txt: `${oi}+${inTxt}`, color: oi === 0 ? macos.green : macos.tertiary };
};
// สี strike ตามราคาสด (pastel) — ราคาวิ่งข้าม strike แถวที่ค้างอยู่สลับสีเอง
const STRIKE_UP = '#83e0a3';
const STRIKE_DOWN = '#ff6b78';
const STRIKE_NEAR = 2.6;
const tickColor = (k, Fnow) => {
  if (Fnow == null) return macos.label;
  const d = k - Fnow;
  if (Math.abs(d) <= STRIKE_NEAR) return macos.label;
  return d > 0 ? STRIKE_UP : STRIKE_DOWN;
};
const plus = (side, n) => (n > 0 ? `${side}+${n}` : '');

const IvChart = ({ hist, windowMin }) => {
  const W = TICK_W, H = 54;
  if (!hist || hist.length < 2) {
    return (
      <div style={{ height: `${H}px`, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: macos.tertiary, fontSize: '11px' }}>
        collecting… ({hist ? hist.length : 0}/2)
      </div>
    );
  }
  // พล็อตตามเวลาจริง ไม่ใช่ตาม index — ช่วงที่เครื่องหลับจะไม่ถูกบีบให้ดูต่อเนื่อง
  const PAD_L = 19, PAD_R = 4;
  const now = hist[hist.length - 1].ts;
  const t0 = now - windowMin * 60;
  const ivs = hist.map((p) => p.iv);
  const lo = Math.min(...ivs), hi = Math.max(...ivs);
  const pad = (hi - lo) * 0.15 || 0.5;
  const yMin = lo - pad, yMax = hi + pad;
  const x = (ts) => PAD_L + ((ts - t0) / (now - t0 || 1)) * (W - PAD_L - PAD_R);
  const y = (v) => H - ((v - yMin) / (yMax - yMin || 1)) * H;
  const pts = hist.map((p) => `${x(p.ts).toFixed(1)},${y(p.iv).toFixed(1)}`);
  const last = hist[hist.length - 1];
  const stroke = last.iv >= hist[0].iv ? macos.green : macos.red;
  return (
    <svg width={W} height={H} style={{ display: 'block', marginTop: '6px' }}>
      <polyline points={pts.join(' ')} fill="none" stroke={stroke} strokeWidth="1.5"
                strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(last.ts)} cy={y(last.iv)} r="2.5" fill={stroke} />
      <text x="0" y="9" fill={macos.tertiary} fontSize="8">{hi.toFixed(1)}</text>
      <text x="0" y={H - 2} fill={macos.tertiary} fontSize="8">{lo.toFixed(1)}</text>
    </svg>
  );
};

const rowStyle = {
  display: 'flex', fontSize: '11px', fontFamily: macos.mono,
  fontVariantNumeric: 'tabular-nums', padding: '2px 0', height: '17px', boxSizing: 'border-box',
};
const Row = ({ cells }) => (
  <div style={{ ...rowStyle, color: macos.label }}>
    {cells.map((c, i) => (
      <span key={i} style={{ width: c.w, textAlign: c.a || 'left', color: c.c || 'inherit',
                             overflow: 'hidden', whiteSpace: 'nowrap' }}>{c.v}</span>
    ))}
  </div>
);
const BlankRow = () => <div style={rowStyle}>&nbsp;</div>;
const fixedRows = (items, n, fn) =>
  Array.from({ length: n }, (_, i) => (i < items.length ? fn(items[i], i) : <BlankRow key={`b${i}`} />));

const TickerColumn = ({ tick, live, hold, resetting, dispatch }) => {
  const box = { width: `${TICK_W}px`, flexShrink: 0, cursor: 'default' };
  if (!tick || !tick.meta) {
    return <div style={{ ...box, color: macos.tertiary, fontSize: '12px' }}>CME TICKER · รอรอบ 5 นาทีแรก…</div>;
  }
  const { meta, iv_hist, ticker, active } = tick;
  let Fnow = meta.F;
  const p = live && live.future && live.future.price;
  if (p && live.ts && Date.now() / 1000 - live.ts < 900) Fnow = p;
  const stale = meta.ts && Date.now() / 1000 - meta.ts > 660;   // > 2 คาบ = daemon มีปัญหา
  const chgColor = meta.iv_chg == null ? macos.tertiary : meta.iv_chg >= 0 ? macos.green : macos.red;

  // Reset = ลบ state แล้วรอรอบ 5 นาทีถัดไปตั้ง baseline ใหม่ (ไม่ดึง upstream เอง)
  const doReset = () => {
    dispatch({ type: 'RESET_START' });
    run(`rm -f "${TICKER_STATE}"`)
      .then(() => load(dispatch))
      .then(() => dispatch({ type: 'RESET_DONE' }))
      .catch(() => dispatch({ type: 'RESET_DONE' }));
  };
  const startHold = (e) => {
    if (e.altKey || resetting) return;   // ⌥ สงวนไว้ให้ลากย้ายการ์ด
    e.preventDefault();
    e.stopPropagation();
    clearHold();
    const t0 = Date.now();
    holdTimer = setInterval(() => {
      const pct = (Date.now() - t0) / HOLD_MS;
      if (pct >= 1) { clearHold(); doReset(); } else dispatch({ type: 'HOLD_TICK', pct });
    }, 90);
  };
  const cancelHold = () => {
    if (!holdTimer) return;
    clearHold();
    dispatch({ type: 'HOLD_END' });
  };

  return (
    <div style={box} onClick={(e) => e.stopPropagation()} onDoubleClick={(e) => e.stopPropagation()}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{ fontSize: '11px', fontWeight: '700', letterSpacing: '0.6px' }}>CME TICKER · {meta.series}</span>
        <div onMouseDown={startHold} onMouseUp={cancelHold} onMouseLeave={cancelHold}
          title="Hold 5s to clear all history (ticker / most active / IV chart)"
          style={{ position: 'relative', overflow: 'hidden', userSelect: 'none', borderRadius: '999px',
                   background: 'rgba(255,255,255,0.10)', padding: '2px 8px', lineHeight: '1',
                   cursor: resetting ? 'default' : 'pointer' }}>
          <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${(hold || 0) * 100}%`,
                        background: 'rgba(255,69,58,0.75)', transition: 'width 90ms linear', pointerEvents: 'none' }} />
          <span style={{ position: 'relative', fontSize: '9px', fontWeight: '700', letterSpacing: '0.3px',
                         color: resetting ? macos.yellow : hold > 0 ? macos.label : macos.tertiary }}>Reset</span>
        </div>
        <span style={{ marginLeft: 'auto', fontSize: '10px', color: stale ? macos.orange : macos.tertiary,
                       fontWeight: stale ? '700' : '400' }}>
          {stale ? '● ' : ''}{meta.system_time}
        </span>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: '10px' }}>
        <span style={secTitle}>Implied Vol · {(meta.iv_window_min / 60).toFixed(0)}h</span>
        <span style={{ fontSize: '9px', color: macos.tertiary }}>
          {meta.F_src !== 'live' && <span style={{ color: macos.orange, fontWeight: '700' }}>⚠ stale F · </span>}
          {meta.dte != null && `dte ${meta.dte.toFixed(3)}`}
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '2px' }}>
        <span style={{ fontSize: '26px', fontWeight: '600' }}>{meta.iv != null ? meta.iv.toFixed(2) : '--'}</span>
        <span style={{ fontSize: '13px', fontWeight: '600', color: chgColor }}>
          {meta.iv_chg == null ? '--' : `${meta.iv_chg >= 0 ? '+' : '–'}${Math.abs(meta.iv_chg).toFixed(2)}`}
        </span>
      </div>
      <IvChart hist={iv_hist} windowMin={meta.iv_window_min} />

      <div style={{ height: '1px', background: macos.divider, margin: '10px 0 8px' }} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={secTitle}>
          Ticker · ≥{meta.threshold}
          {Fnow != null && (
            <span style={{ color: macos.tertiary, fontWeight: '400' }}>
              {' · '}<span style={{ color: STRIKE_UP }}>▲</span>{Fnow.toFixed(1)}<span style={{ color: STRIKE_DOWN }}>▼</span>
            </span>
          )}
        </span>
        <span style={{ fontSize: '9px', color: macos.tertiary }}>put call Δ oi+in</span>
      </div>
      <div style={{ marginTop: '4px' }}>
        {fixedRows(ticker || [], TICKER_ROWS, (t, i) => {
          const oi = oiCell(t.oi, t.intra);
          return (
            <Row key={i} cells={[
              { v: hhmm(t.ts), w: '40px', c: macos.tertiary },
              { v: t.strike, w: '44px', c: tickColor(t.strike, Fnow) },
              { v: plus('P', t.dp), w: '36px', a: 'right', c: macos.orange },
              { v: plus('C', t.dc), w: '36px', a: 'right', c: macos.blue },
              { v: t.d != null ? `Δ${t.d.toFixed(2)}` : '–', w: '44px', a: 'right', c: macos.secondary },
              { v: oi.txt, w: '58px', a: 'right', c: oi.color },
            ]} />
          );
        })}
      </div>

      <div style={{ height: '1px', background: macos.divider, margin: '10px 0 8px' }} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={secTitle}>Most Active · {meta.active_window_min}m</span>
        <span style={{ fontSize: '9px', color: macos.tertiary }}>age strike sum rate</span>
      </div>
      <div style={{ marginTop: '4px' }}>
        {fixedRows(active || [], ACTIVE_ROWS, (a, i) => (
          <Row key={i} cells={[
            { v: `${a.age}m`, w: '44px', c: macos.tertiary },
            { v: a.strike, w: '58px', c: tickColor(a.strike, Fnow) },
            { v: a.sum, w: '58px', a: 'right', c: macos.green },
            { v: `${a.rate.toFixed(1)}/m`, w: '98px', a: 'right', c: macos.blue },
          ]} />
        ))}
      </div>
    </div>
  );
};

// ============================================================================
// ประกอบ
// ============================================================================
export const render = (state, dispatch) => {
  const { cme: data, live, tick, src, refreshing, chartMode, sdMode, dMode, hover, hold, resetting } = state || {};

  // ราคาสดใช้กับกรอบหลักได้เมื่อสัญญาตรงกับ underlying ของ series (GCV6 = GCV26) และไม่เก่าเกิน 3 นาที
  let liveF = null;
  const und = data && data.und_sym ? data.und_sym.slice(0, 3) + data.und_sym.slice(-1) : null;
  if (live && live.future && live.future.price && live.future.sym === und && Date.now() / 1000 - live.ts < 180) {
    liveF = live.future.price;
  }

  const container = {
    position: 'fixed', bottom: savedPos().bottom || '9px', left: savedPos().left || '14px',
    width: `${CARD_W}px`, display: 'flex', alignItems: 'stretch',
    padding: `14px ${PAD}px`, borderRadius: macos.radius,
    color: macos.label, fontFamily: macos.font,
    background: macos.material, border: macos.border, boxShadow: macos.shadow,
    fontVariantNumeric: 'tabular-nums', boxSizing: 'border-box',
  };

  // กรอบหลัก: คลิก = copy clip ให้ TradingView / ดับเบิลคลิก = เปิดหน้ากราฟ (⌥ = ลากย้าย)
  const handleCopy = (e) => {
    if (e.altKey) return;
    e.preventDefault();
    run(`curl -sf -m 2 ${API}/api/clip | pbcopy || cat /tmp/cme_putcall_clip.txt | pbcopy`);
  };
  const handleOpenChart = (e) => {
    if (e.altKey) return;
    e.preventDefault();
    run(`curl -sf -m 2 -o /dev/null ${API}/api/health && open ${API}/api/chart`
      + ' || (test -f /tmp/cme_chart.html && open /tmp/cme_chart.html)');
  };
  // ↻ = รัน fetcher เดี๋ยวนั้น (API อ่านอย่างเดียวตามกฎ สั่งดึง upstream ผ่าน API ไม่ได้)
  const handleRefresh = (e) => {
    if (e.altKey) return;
    e.preventDefault();
    e.stopPropagation();
    if (refreshing) return;
    dispatch({ type: 'REFRESH_START' });
    run('/usr/bin/python3 /Users/sorachai/src/claude_code/apphub/goldhub/service/cme_fetcher.py')
      .then(() => run('cat /tmp/cme_putcall_clip.txt | pbcopy'))
      .then(() => load(dispatch))
      .then(() => dispatch({ type: 'REFRESH_DONE' }))
      .catch(() => dispatch({ type: 'REFRESH_DONE' }));
  };
  const refreshPill = (
    <span onClick={handleRefresh} onDoubleClick={(e) => e.stopPropagation()} title="Refresh CME data now + copy"
      style={{ fontSize: '12px', fontWeight: '700', lineHeight: '1', color: refreshing ? macos.yellow : macos.secondary,
               background: 'rgba(255,255,255,0.15)', borderRadius: '999px', padding: '4px 10px', cursor: 'pointer' }}>
      {refreshing ? 'refreshing…' : '↻ refresh'}
    </span>
  );

  // snapshot ทุก 5 นาทีแล้ว (เฟส 3) -- เกิน 15 นาที = daemon/แหล่งข้อมูลมีปัญหา
  const stale = data && data.ts && Date.now() / 1000 - data.ts > 900;
  const fNow = liveF != null ? liveF : data && data.F;
  const strikeColor = (s) => (fNow == null ? macos.label : s >= fNow ? macos.green : macos.red);

  const main = !data ? (
    <div style={{ width: `${MAIN_W}px`, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      <span style={{ fontSize: '11px', fontWeight: '700', letterSpacing: '0.6px' }}>CME GOLD</span>
      <div style={{ textAlign: 'center', color: macos.tertiary, fontSize: '13px' }}>no data yet — press refresh to fetch</div>
      <div style={{ borderTop: `0.5px solid ${macos.divider}`, paddingTop: '8px' }}>{refreshPill}</div>
    </div>
  ) : (
    <div style={{ width: `${MAIN_W}px`, display: 'flex', flexDirection: 'column', cursor: 'pointer' }}
      onClick={handleCopy} onDoubleClick={handleOpenChart}
      title="Click = copy P/C data for TradingView · Double-click = open Intraday/OI chart · ⌥-drag = move">
      <div style={{ display: 'flex', gap: '18px' }}>
        {/* ซ้าย: หัว + ราคา + สัดส่วน P/C + SD */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: '11px', fontWeight: '700', letterSpacing: '0.6px', whiteSpace: 'nowrap' }}>
            CME GOLD {data.series || ''}
            <span style={{ color: macos.tertiary, fontWeight: '600', marginLeft: '8px' }}>
              DTE {data.dte != null ? data.dte.toFixed(2) : '--'}
            </span>
            {stale && <span style={{ color: macos.orange, marginLeft: '8px' }}>● STALE</span>}
            {data.qs && data.qs.paused_until && (
              <span style={{ color: macos.orange, marginLeft: '8px' }}
                title={`ตัวเบรก: หยุดยิง QuikStrike ชั่วคราว (${data.qs.reason || ''})`}>
                ⏸ QS {new Date(data.qs.paused_until * 1000).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: '6px' }}>
            <span style={{ fontSize: '20px', fontWeight: '600', letterSpacing: '-0.3px', whiteSpace: 'nowrap' }}>
              F {fNow == null ? '--' : Number(fNow).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
              <span style={{ fontSize: '9px', marginLeft: '4px', verticalAlign: 'middle', color: liveF != null ? macos.green : macos.tertiary }}>●</span>
            </span>
            <span style={{ fontSize: '12px', fontWeight: '600', whiteSpace: 'nowrap', color: macos.secondary }}>
              IV {data.iv_event != null ? data.iv_event.toFixed(2) : '--'}
            </span>
          </div>
          <PcRow title="Intraday" pc={data.intraday} />
          <PcRow title="Open Interest" pc={data.oi} />
          <SdBlock sd={data.sd} />
        </div>
        <div style={{ flex: 1, minWidth: 0, ...vline, paddingLeft: '16px' }}>
          <div style={{ ...secTitle, color: macos.label }}>Intraday</div>
          <TopActive top={data.intraday && data.intraday.top} sc={strikeColor} />
        </div>
        <div style={{ flex: 1, minWidth: 0, ...vline, paddingLeft: '16px' }}>
          <div style={{ ...secTitle, color: macos.label }}>Open Interest</div>
          <TopActive top={data.oi && data.oi.top} sc={strikeColor} />
        </div>
        <GoldBlock live={live} />
      </div>

      <Chart data={data} liveF={liveF} mode={chartMode || 'id'} sdMode={sdMode || 'open'}
        dMode={dMode || 'off'} hover={hover} dispatch={dispatch} />

      <div style={{ borderTop: `0.5px solid ${macos.divider}`, marginTop: 'auto', paddingTop: '8px',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {refreshPill}
          <span style={{ fontSize: '10px', color: macos.tertiary }}>click → copy for TV · double-click → chart</span>
        </span>
        <span style={{ fontSize: '10px', color: macos.tertiary }}>
          Sync {data.system_time || '--'}{src === 'file' ? ' · file' : ''}
        </span>
      </div>
    </div>
  );

  return (
    <div style={container} onMouseDown={altDrag}>
      <TickerColumn tick={tick} live={live} hold={hold} resetting={resetting} dispatch={dispatch} />
      <div style={{ ...vline, margin: `0 ${COL_GAP}px 0 ${COL_GAP}px` }} />
      {main}
    </div>
  );
};
