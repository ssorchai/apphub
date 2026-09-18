import { run } from 'uebersicht';

// อ่าน JSON ที่ cme_fetcher.py (cron รายชั่วโมง) เขียนไว้ + ราคา futures สดจาก gold_fetcher.py
// (เขียนทุก ~5 วินาที) ต่อท้ายหลังตัวคั่น -- รอบ 5 วินาทีเพื่อให้เส้น Future ในกราฟขยับตามราคา
const LIVE_SEP = '@@LIVE@@';
const CMD = `cat /tmp/cme_putcall.json; echo; echo '${LIVE_SEP}'; cat /tmp/gold_data.json 2>/dev/null`;
export const command = CMD;
export const refreshFrequency = 5000;

// state แบบ redux ของ Übersicht: รองรับปุ่ม refresh (รัน fetcher ทันที + copy อัตโนมัติ)
// chartMode = กราฟโชว์ Intraday หรือ OI / hover = สไตรค์ที่เมาส์ชี้อยู่
// ค่าที่ผู้ใช้เลือกในกราฟ (Intraday/OI, SD แบบไหน) จำไว้ใน localStorage ไม่งั้นรีเซ็ตทุกครั้งที่
// Übersicht โหลด widget ใหม่ (แก้ไฟล์ / restart)
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
// sdMode: 'open' = anchor ราคาเปิด + DTE 0.6 (ตรงกับกล่อง SD Range) / 'cme' = รอบ F + DTE ที่เหลือจริง
// dMode: เส้น delta แบบ CME -- 'off' (ค่าเริ่มต้น) / '25' = 25Δ สองเส้น / 'all' = 5-45Δ สิบเส้น
export const initialState = {
  output: null, refreshing: false, hover: null,
  chartMode: pref('chartMode', 'id'), sdMode: pref('sdMode', 'open'), dMode: pref('dMode', 'off'),
  // wMode: แท่งเป็นจำนวนสัญญาดิบ หรือถ่วงด้วย delta / gMode: แถบ gamma x OI ใต้กราฟ
  wMode: pref('wMode', false), gMode: pref('gMode', false),
};
export const updateState = (event, prev) => {
  switch (event.type) {
    case 'UB/COMMAND_RAN': return { ...prev, output: event.output };
    case 'REFRESH_START': return { ...prev, refreshing: true };
    case 'REFRESH_DONE': return { ...prev, refreshing: false, output: event.output || prev.output };
    case 'CHART_MODE': return { ...prev, chartMode: event.mode };
    case 'SD_MODE': return { ...prev, sdMode: event.mode };
    case 'DELTA_MODE': return { ...prev, dMode: event.mode };
    case 'WT_MODE': return { ...prev, wMode: event.on };
    case 'GAMMA_MODE': return { ...prev, gMode: event.on };
    case 'HOVER': return { ...prev, hover: event.k };
    default: return prev;
  }
};

// ---- macOS system palette (shared theme กับ gold-update.jsx) ----
const macos = {
  // ฉากหลังโทนเข้มโปร่ง: ตัวหนังสือขาวต้องอ่านออกทั้งบน wallpaper สว่างและมืด
  // (พื้นขาวโปร่งเดิมจมหายเมื่อ wallpaper เป็นโทนส้ม/สว่าง) — ปรับความทึบที่ค่านี้ค่าเดียว
  material: 'rgba(24, 26, 33, 0.55)',
  border: '0.5px solid rgba(255, 255, 255, 0.16)',
  radius: '22px',
  shadow: '0 10px 28px rgba(0, 0, 0, 0.32)',
  font: '-apple-system, "SF Pro Display", "SF Pro Text", "Helvetica Neue", sans-serif',
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

const fmt = (v) => (v == null ? '--' : Number(v).toLocaleString());

// ⌥-drag ย้ายการ์ด: กด Option ค้างแล้วลาก — ตำแหน่งเก็บ localStorage ข้าม reboot
// (Übersicht ไม่มี drag ในตัว ตำแหน่งในโค้ดเป็นแค่ค่าเริ่มต้น)
const POS_KEY = 'cme-putcall.pos';
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
    // เขียนทุกจังหวะ กัน re-render กลางลากแล้วการ์ดดีดกลับ
    localStorage.setItem(POS_KEY, JSON.stringify(pos));
  };
  const up = () => {
    window.removeEventListener('mousemove', move);
    window.removeEventListener('mouseup', up);
  };
  window.addEventListener('mousemove', move);
  window.addEventListener('mouseup', up);
};
const secTitle = {
  fontSize: '10px', color: macos.secondary, fontWeight: '600',
  letterSpacing: '0.4px', textTransform: 'uppercase',
};

// แถบสัดส่วน Put/Call หนึ่งชุด (คอลัมน์ซ้าย)
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

// TOP ACTIVE แบบเรียบ: บรรทัดเดียวต่ออันดับ — strike · รวม · (P/C)
// sc = ฟังก์ชันสี strike (เขียวถ้าสูงกว่า F ปัจจุบัน / แดงถ้าต่ำกว่า)
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

// ของที่เติมเข้ามาตั้งแต่ refresh รอบก่อน (แบบวงเล็บ +28 ของบอท telegram)
// ป้าย P/C คงสีฝั่ง (ส้ม/ฟ้า) แต่ตัวเลขให้สีตามทิศ: บวกเขียว / ลบแดง — เห็นค่าลบชัดทันที
const ChangeRow = ({ rows, since, sc }) => {
  const dnum = (v) => (
    <span style={{ color: v > 0 ? macos.green : macos.red, fontWeight: '700' }}>
      {v > 0 ? '+' : '−'}{fmt(Math.abs(v))}
    </span>
  );
  return (
    <div style={{ marginTop: '10px' }}>
      <div style={secTitle}>Δ Changes{since ? ` · since ${since}` : ''}</div>
      {(!rows || !rows.length) && (
        <div style={{ fontSize: '12px', color: macos.tertiary, marginTop: '2px' }}>no fills</div>
      )}
      {(rows || []).map((r) => (
        <div key={r.strike} style={{ display: 'flex', alignItems: 'baseline', gap: '8px', fontSize: '12px', marginTop: '3px' }}>
          <span style={{ fontWeight: '600', color: sc(r.strike), minWidth: '38px' }}>{r.strike}</span>
          <span style={{ marginLeft: 'auto' }}>
            {r.dp !== 0 && <span style={{ color: macos.orange, fontWeight: '600' }}>P {dnum(r.dp)}</span>}
            {r.dp !== 0 && r.dc !== 0 && <span style={{ color: macos.tertiary }}> · </span>}
            {r.dc !== 0 && <span style={{ color: macos.blue, fontWeight: '600' }}>C {dnum(r.dc)}</span>}
          </span>
        </div>
      ))}
    </div>
  );
};

// กรอบ SD: mean = ราคาเปิด Yahoo, DTE 0.6, vol = event vol ของ 0DTE (คำนวณโดย fetcher)
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

// ---- กราฟ Put/Call รายสไตรค์แบบ CME Vol2Vol (ย่อจาก /tmp/cme_chart.html) ----
const CHART_W = 708;   // ความกว้างการ์ด 740 - padding ซ้ายขวา
const CHART_H = 400;

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

// ปุ่มสลับโหมด: ต้องกันคลิกไม่ให้ทะลุไปถึงการ์ด (คลิกการ์ด = copy)
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

const Chart = ({ data, liveF, mode, sdMode, dMode, wMode, gMode, hover, dispatch }) => {
  const ch = data.chart;
  if (!ch) return null;
  const W = CHART_W, H = CHART_H, L = 38, R = 38, T = 8, B = 22;
  const F = data.F;
  const fNow = liveF != null ? liveF : F;
  const sig = F && data.iv && data.dte > 0 ? (F * data.iv) / 100 * Math.sqrt(data.dte / 365) : null;
  // greeks ต่อสไตรค์จาก fetcher: [strike, call delta, gamma] -- ใช้ถ่วงน้ำหนักและทำแถบ gamma
  const gk = new Map((ch.gk || []).map((r) => [r[0], { cd: r[1], g: r[2] }]));
  const wRow = (r) => {
    if (!wMode) return r;
    const g = gk.get(r[0]);
    return g ? [r[0], r[1] * (1 - g.cd), r[2] * g.cd] : [r[0], 0, 0];
  };
  const rows = (ch[mode] || []).filter((r) => r[1] + r[2] > 0).map(wRow);
  const strikes = [...new Set([...ch.id, ...ch.oi].map((r) => r[0]))].sort((a, b) => a - b);
  if (!strikes.length) return null;
  // ช่วงแกน x: ±3.5σ รอบ F เหมือนหน้าเว็บ (ไม่เกินช่วงข้อมูลที่มี)
  // แถบ SD: 'open' = จุดกลางราคาเปิด + 1σ จาก DTE 0.6 (ค่าเดียวกับกล่อง SD Range จาก fetcher)
  //         'cme'  = จุดกลาง F ตอนดึงข้อมูล + 1σ จาก DTE ที่เหลือจริง (แบบ Expected Range ของ CME)
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
  // แถบ gamma x OI: จุดที่คนเฮดจ์ต้องเทรด futures หนักสุดถ้าราคาวิ่งมาถึง (ใช้ OI เสมอ)
  const oiRaw = new Map((ch.oi || []).map((r) => [r[0], r]));
  const gRows = gMode
    ? vrows.map((r) => r[0]).map((k) => {
        const g = gk.get(k), o = oiRaw.get(k);
        return [k, g && o ? g.g * (o[1] + o[2]) : 0];
      }).filter((r) => r[1] > 0)
    : [];
  const gMax = Math.max(0, ...gRows.map((r) => r[1]));
  const gH = 46;
  const gY = (v) => (H - B) - (v / gMax) * gH;
  const y = (v) => T + (1 - v / ymax) * (H - T - B);
  const ks = strikes.filter((k) => k >= lo && k <= hi);
  const stepX = ks.length > 1 ? Math.min(...ks.slice(1).map((k, i) => k - ks[i])) : 5;
  const bw = Math.max(1.2, (x(lo + stepX) - x(lo)) * 0.36);

  // smile แกนขวา
  const vs = smooth((ch.vs || []).filter((r) => r[0] >= lo && r[0] <= hi));
  let yr = null, vlo = 0, vhi = 0;
  if (vs.length > 2) {
    vlo = Math.min(...vs.map((r) => r[1])); vhi = Math.max(...vs.map((r) => r[1]));
    const pad = (vhi - vlo) * 0.15 + 0.5; vlo -= pad; vhi += pad;
    yr = (v) => T + (1 - (v - vlo) / (vhi - vlo)) * (H - T - B);
  }

  // hover: ดูดเข้าสไตรค์ใกล้สุด / dispatch เฉพาะตอนสไตรค์เปลี่ยน กัน re-render ถี่เกิน
  const onMove = (e) => {
    const bb = e.currentTarget.ownerSVGElement.getBoundingClientRect();
    const v = lo + (((e.clientX - bb.left) * W) / bb.width - L) / (W - L - R) * (hi - lo);
    let k = ks[0];
    for (const s of ks) if (Math.abs(s - v) < Math.abs(k - v)) k = s;
    if (k !== hover) dispatch({ type: 'HOVER', k });
  };
  const idm = new Map(ch.id.map((r) => [r[0], r])), oim = new Map(ch.oi.map((r) => [r[0], r]));

  // เส้น delta (fetcher คำนวณจาก bid/ask ของ barchart ให้แล้ว) -- 25Δ อย่างเดียวหรือครบชุด
  // เส้นคิดไว้ตอน fetcher ดึงข้อมูล (F ตอนนั้น) -- เลื่อนทั้งชุดตาม F สด ให้ยังเป็น delta เดิม
  const dAll = (data.delta || []).map((d) => ({ ...d, k: d.k + (fNow && F ? fNow - F : 0) }));
  const dLines = dMode === 'off' ? []
    : (dMode === '25' ? dAll.filter((d) => d.d === 0.25) : dAll).filter((d) => d.k > lo && d.k < hi);
  // delta ณ สไตรค์ใดๆ: แปลงฝั่ง put เป็น delta ของ call (put -0.25 = call 0.75) แล้ว interpolate
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
    // ระยะ σ ในกล่อง hover ใช้กรอบเดียวกับแถบที่เลือกอยู่
    const dist = useOpen ? (hover - bandC) / bandS : sig && fNow ? (hover - fNow) / sig : null;
    const line = (name, r) => `${name}  P ${r ? fmt(r[1]) : 0}  C ${r ? fmt(r[2]) : 0}  Σ ${r ? fmt(r[1] + r[2]) : 0}`;
    const lines = mode === 'id'
      ? [[line('Intraday', idr), true], [line('OI', oir), false]]
      : [[line('OI', oir), true], [line('Intraday', idr), false]];
    const hd = deltaAt(hover);
    const hg = gk.get(hover);
    const hrow = mode === 'id' ? idm.get(hover) : oim.get(hover);
    const hdw = hg && hrow ? `${Math.round(hrow[1] * (1 - hg.cd))} / ${Math.round(hrow[2] * hg.cd)}` : null;
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
            {`Δ ${hd.toFixed(2)}${hover >= (fNow || F) ? 'C' : 'P'}${hdw ? `  ·  Δw P/C ${hdw}` : ''}`}
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
        <span style={{ ...secTitle, color: macos.label, marginRight: '4px' }}>
          {wMode ? 'Put / Call × Δ' : 'Put / Call by Strike'}
        </span>
        <ModePill label="Intraday" on={mode === 'id'} onPick={() => { savePref('chartMode', 'id'); dispatch({ type: 'CHART_MODE', mode: 'id' }); }} />
        <ModePill label="OI" on={mode === 'oi'} onPick={() => { savePref('chartMode', 'oi'); dispatch({ type: 'CHART_MODE', mode: 'oi' }); }} />
        <span style={{ ...secTitle, marginLeft: '10px' }}>SD</span>
        <ModePill label="Open 0.6" on={!!useOpen} onPick={() => { savePref('sdMode', 'open'); dispatch({ type: 'SD_MODE', mode: 'open' }); }} />
        <ModePill label="CME" on={!useOpen} onPick={() => { savePref('sdMode', 'cme'); dispatch({ type: 'SD_MODE', mode: 'cme' }); }} />
        <ModePill label="Δw" on={!!wMode}
          onPick={() => { savePref('wMode', !wMode); dispatch({ type: 'WT_MODE', on: !wMode }); }} />
        <ModePill label="γ" on={!!gMode}
          onPick={() => { savePref('gMode', !gMode); dispatch({ type: 'GAMMA_MODE', on: !gMode }); }} />
        <span style={{ ...secTitle, marginLeft: '10px' }}>Δ</span>
        {[['off', 'ปิด'], ['25', '25Δ'], ['all', 'ครบ']].map(([m, lbl]) => (
          <ModePill key={m} label={lbl} on={(dMode || 'off') === m}
            onPick={() => { savePref('dMode', m); dispatch({ type: 'DELTA_MODE', mode: m }); }} />
        ))}
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
        {/* เส้น Future วาดก่อนแท่ง ให้แท่ง P/C ทับเส้น ไม่ใช่เส้นบังแท่ง / ป้ายราคาวาดทีหลังสุด */}
        {liveF != null && F && F > lo && F < hi && (
          <line x1={x(F)} x2={x(F)} y1={T} y2={H - B} stroke="rgba(255,255,255,0.25)" strokeWidth="0.8" strokeDasharray="2 4" />
        )}
        {fNow && fNow > lo && fNow < hi && (
          <line x1={x(fNow)} x2={x(fNow)} y1={T + 16} y2={H - B} stroke="rgba(255,255,255,0.45)" strokeWidth="0.8" />
        )}
        {gRows.length > 1 && gMax > 0 && (
          <g>
            <path d={`M${x(gRows[0][0]).toFixed(1)},${H - B}L` +
              splinePath(gRows.map((r) => [x(r[0]), gY(r[1])])).slice(1) +
              `L${x(gRows[gRows.length - 1][0]).toFixed(1)},${H - B}Z`}
              fill="rgba(191,144,255,0.22)" stroke="#bf90ff" strokeWidth="1" />
            <text x={L + 3} y={H - B - gH - 3} fontSize="9" fill="#bf90ff">γ × OI</text>
          </g>
        )}
        {vrows.map(([s, p, c]) => (
          <g key={s}>
            {p > 0.05 && <rect x={x(s) - bw - 0.4} y={y(p)} width={bw} height={y(0) - y(p)} fill={macos.orange} />}
            {c > 0.05 && <rect x={x(s) + 0.4} y={y(c)} width={bw} height={y(0) - y(c)} fill={macos.blue} />}
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

export const render = (state, dispatch) => {
  const { output, refreshing, chartMode, sdMode, dMode, wMode, gMode, hover } = state || {};
  const [cmeTxt, liveTxt] = (output || '').split(LIVE_SEP);
  let data = null;
  try { data = JSON.parse(cmeTxt); } catch (e) { data = null; }
  // ราคาสดใช้ได้เมื่อสัญญาตรงกับ underlying ของ series (GCV6 = GCV26) และไม่เก่าเกิน 3 นาที
  let liveF = null;
  try {
    const g = JSON.parse(liveTxt);
    const und = data && data.und_sym ? data.und_sym.slice(0, 3) + data.und_sym.slice(-1) : null;
    if (g.future && g.future.price && g.future.sym === und && Date.now() / 1000 - g.ts < 180) liveF = g.future.price;
  } catch (e) { liveF = null; }

  const container = {
    position: 'fixed', bottom: savedPos().bottom || '25px', left: savedPos().left || '35px', width: '740px',
    minHeight: '285px', display: 'flex', flexDirection: 'column',
    padding: '14px 16px', borderRadius: macos.radius,
    color: macos.label, fontFamily: macos.font,
    background: macos.material,
    border: macos.border, boxShadow: macos.shadow,
    fontVariantNumeric: 'tabular-nums',
    cursor: 'pointer',
    boxSizing: 'border-box',
  };

  // คลิกการ์ด = copy string สำหรับ paste ลง oi_block.pine (⌥+คลิก = ลากย้าย ไม่ copy)
  const handleCopy = (e) => {
    if (e.altKey) return;
    e.preventDefault();
    run('cat /tmp/cme_putcall_clip.txt | pbcopy');
  };

  // ดับเบิลคลิก = เปิดกราฟ Intraday/OI แบบ CME (fetcher เขียนไว้ทุกรอบ หน้า reload ตัวเองทุก 5 นาที)
  // สองคลิกแรกของดับเบิลคลิกจะ copy ไปด้วย ซึ่งไม่เสียหายอะไร
  const handleOpenChart = (e) => {
    if (e.altKey) return;
    e.preventDefault();
    run('test -f /tmp/cme_chart.html && open /tmp/cme_chart.html');
  };

  // ปุ่ม ↻ = รัน fetcher เดี๋ยวนั้น เสร็จแล้ว copy ให้อัตโนมัติ (กันกดซ้ำระหว่างรัน)
  const handleRefresh = (e) => {
    if (e.altKey) return;
    e.preventDefault();
    e.stopPropagation();
    if (refreshing) return;
    dispatch({ type: 'REFRESH_START' });
    run('/usr/bin/python3 /Users/sorachai/src/my-cronjob/cme_fetcher.py')
      .then(() => run('cat /tmp/cme_putcall_clip.txt | pbcopy'))
      .then(() => run(CMD))
      .then((out) => dispatch({ type: 'REFRESH_DONE', output: out }))
      .catch(() => dispatch({ type: 'REFRESH_DONE', output: null }));
  };

  const refreshPill = (
    <span
      onClick={handleRefresh}
      onDoubleClick={(e) => e.stopPropagation()}
      title="Refresh CME data now + copy"
      style={{
        fontSize: '12px', fontWeight: '700', lineHeight: '1',
        color: refreshing ? macos.yellow : macos.secondary,
        background: 'rgba(255,255,255,0.15)', borderRadius: '999px',
        padding: '4px 10px',
      }}>
      {refreshing ? 'refreshing…' : '↻ refresh'}
    </span>
  );

  // ยังไม่มีไฟล์ข้อมูล (เช่นเพิ่งเปิดเครื่อง /tmp ถูกล้าง และ cron ยังไม่ถึงนาทีที่ 7)
  // — ขึ้นโครงเปล่าพร้อมปุ่ม refresh ให้กดดึงเองได้เลย
  if (!data) {
    return (
      <div style={{ ...container, justifyContent: 'space-between' }} onMouseDown={altDrag}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '11px', fontWeight: '700', letterSpacing: '0.6px', color: macos.label }}>
            CME GOLD
          </span>
        </div>
        <div style={{ textAlign: 'center', color: macos.tertiary, fontSize: '13px' }}>
          no data yet — press refresh to fetch
        </div>
        <div style={{
          borderTop: `0.5px solid ${macos.divider}`, paddingTop: '8px',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          {refreshPill}
          <span style={{ fontSize: '10px', color: macos.tertiary }}>Sync --</span>
        </div>
      </div>
    );
  }

  // fetcher รันรายชั่วโมง — เกิน 2 ชม. = ข้อมูลค้าง (cron ตาย/วันหยุด)
  const stale = data.ts && Date.now() / 1000 - data.ts > 7200;

  // F ปัจจุบัน = ราคาสดจาก gold_fetcher ถ้าใช้ได้ ไม่งั้นราคาตอน cme_fetcher ดึงข้อมูล
  const fNow = liveF != null ? liveF : data.F;
  // strike สูงกว่า F ปัจจุบัน = เขียว / ต่ำกว่า = แดง
  const strikeColor = (s) => (fNow == null ? macos.label : s >= fNow ? macos.green : macos.red);

  return (
    <div style={container} onClick={handleCopy} onDoubleClick={handleOpenChart} onMouseDown={altDrag}
      title="Click = copy P/C data for TradingView · Double-click = open Intraday/OI chart · ⌥-drag = move">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '11px', fontWeight: '700', letterSpacing: '0.6px', color: macos.label }}>
          CME GOLD {data.series || ''}
          {data.source && data.source !== 'barchart' && (
            <span style={{ color: macos.orange, marginLeft: '8px', fontWeight: '600' }}>via {data.source}</span>
          )}
          {stale && <span style={{ color: macos.orange, marginLeft: '8px' }}>● STALE</span>}
          {data.qs && data.qs.paused_until && (
            <span style={{ color: macos.orange, marginLeft: '8px', fontWeight: '600' }}
              title={`ตัวเบรก: หยุดยิง QuikStrike ชั่วคราว (${data.qs.reason || ''}) ระหว่างนี้ใช้ค่า vol ที่ cache ไว้`}>
              ⏸ QS paused → {new Date(data.qs.paused_until * 1000).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
        </span>
        <span style={{ fontSize: '10px', color: macos.tertiary, fontWeight: '600' }}>
          DTE {data.dte != null ? data.dte.toFixed(2) : '--'}
        </span>
      </div>

      <div style={{ display: 'flex', gap: '18px' }}>
        {/* คอลัมน์ซ้าย: ราคา + สัดส่วน P/C */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: '6px' }}>
            <span style={{ fontSize: '20px', fontWeight: '600', letterSpacing: '-0.3px', whiteSpace: 'nowrap' }}
              title={liveF != null ? 'ราคาสดจาก gold_fetcher (อัปเดตทุก ~5 วินาที)'
                                   : `ราคาตอน cme_fetcher ดึงข้อมูล ${data.system_time || ''}`}>
              F {fNow == null ? '--' : Number(fNow).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
              <span style={{ fontSize: '9px', marginLeft: '4px', verticalAlign: 'middle',
                color: liveF != null ? macos.green : macos.tertiary }}>●</span>
            </span>
            {/* event IV ของ 0DTE (QuikStrike Event Vol) อย่างเดียว -- ไม่มีก็ขึ้น -- */}
            <span style={{ fontSize: '12px', fontWeight: '600', whiteSpace: 'nowrap', color: macos.secondary }}>
              IV {data.iv_event != null ? data.iv_event.toFixed(2) : '--'}
            </span>
          </div>
          <PcRow title="Intraday" pc={data.intraday} />
          <PcRow title="Open Interest" pc={data.oi} />
          <SdBlock sd={data.sd} />
        </div>

        {/* คอลัมน์กลาง: Intraday (Top Active + Δ) */}
        <div style={{ flex: 1, minWidth: 0, borderLeft: `0.5px solid ${macos.divider}`, paddingLeft: '16px' }}>
          <div style={{ ...secTitle, marginTop: '6px', color: macos.label }}>Intraday</div>
          <TopActive top={data.intraday && data.intraday.top} sc={strikeColor} />
          <ChangeRow rows={data.changes && data.changes.intraday} since={data.changes && data.changes.since} sc={strikeColor} />
        </div>

        {/* คอลัมน์ขวา: Open Interest (Top Active + Δ) */}
        <div style={{ flex: 1, minWidth: 0, borderLeft: `0.5px solid ${macos.divider}`, paddingLeft: '16px' }}>
          <div style={{ ...secTitle, marginTop: '6px', color: macos.label }}>Open Interest</div>
          <TopActive top={data.oi && data.oi.top} sc={strikeColor} />
          <ChangeRow rows={data.changes && data.changes.oi} since={data.changes && data.changes.since} sc={strikeColor} />
        </div>
      </div>

      <Chart data={data} liveF={liveF} mode={chartMode || 'id'} sdMode={sdMode || 'open'}
        dMode={dMode || 'off'} wMode={!!wMode} gMode={!!gMode} hover={hover} dispatch={dispatch} />

      <div style={{
        borderTop: `0.5px solid ${macos.divider}`,
        marginTop: 'auto', paddingTop: '8px',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {refreshPill}
          <span style={{ fontSize: '10px', color: macos.tertiary }}>
            click card → copy for TV
          </span>
        </span>
        <span style={{ fontSize: '10px', color: macos.tertiary }}>
          Sync {data.system_time || '--'}
        </span>
      </div>
    </div>
  );
};
