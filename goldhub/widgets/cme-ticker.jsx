import { run } from 'uebersicht';

// อ่าน 2 ไฟล์: cme_ticker.json (ข้อมูล flow เขียนทุก 5 นาที) + gold_data.json (ราคา future สด
// ทุก ~5 วิ) — คั่นด้วย ---SPLIT--- แล้ว parse แยกฝั่ง refresh ทุก 10 วิ ให้สีของ strike
// (เหนือ/ต่ำกว่าราคาปัจจุบัน) ขยับตามราคาสด ไม่ต้องรอรอบเขียน 5 นาที
export const command =
  "printf '%s\\n---SPLIT---\\n%s' \"$(cat /tmp/cme_ticker.json 2>/dev/null)\" \"$(cat /tmp/gold_data.json 2>/dev/null)\"";
export const refreshFrequency = 15000;  // ราคาข้าม strike (ห่าง 5) ไม่บ่อย 15 วิทันสายตา + เบา

const TICKER_ROWS = 12;   // ตรึงจำนวนแถว (เติมแถวเปล่า) การ์ดจะได้ไม่ยืดหดตาม event
const ACTIVE_ROWS = 5;
const HOLD_MS = 5000;     // กดค้างเท่านี้ = reset
const CARD_W = 290;       // แคบลงได้หลังถอดคอลัมน์ %oi ออก (เท่า gold-update)
const CONTENT_W = CARD_W - 32;   // หัก padding 16 สองข้าง

export const initialState = { output: null, hold: 0, resetting: false };
export const updateState = (event, prev) => {
  switch (event.type) {
    case 'UB/COMMAND_RAN': return { ...prev, output: event.output };
    case 'HOLD_TICK': return { ...prev, hold: event.pct };
    case 'HOLD_END': return { ...prev, hold: 0 };
    case 'RESET_START': return { ...prev, hold: 0, resetting: true };
    case 'RESET_DONE': return { ...prev, resetting: false, output: event.output || prev.output };
    default: return prev;
  }
};

// เก็บนอก render — render ถูกเรียกใหม่ทุกรอบ ถ้าเก็บใน closure timer จะหลุด
let holdTimer = null;
const clearHold = () => { if (holdTimer) { clearInterval(holdTimer); holdTimer = null; } };

// ---- macOS dark palette (shared theme กับ widget อื่น — copy ไว้ แก้สีต้องแก้ทุกไฟล์) ----
// ห้ามใช้ backdrop-filter (กระพริบใน Übersicht ทุกรอบ re-render)
const macos = {
  material: 'rgba(28, 28, 30, 0.72)',
  border: '0.5px solid rgba(255, 255, 255, 0.12)',
  radius: '22px',
  shadow: '0 10px 24px rgba(0, 0, 0, 0.44)',
  font: '-apple-system, "SF Pro Display", "SF Pro Text", "Helvetica Neue", sans-serif',
  mono: '"SF Mono", ui-monospace, Menlo, monospace',
  label: '#ffffff',
  secondary: 'rgba(255, 255, 255, 0.55)',
  tertiary: 'rgba(255, 255, 255, 0.35)',
  divider: 'rgba(255, 255, 255, 0.14)',
  green: '#30d158',
  red: '#ff453a',
  blue: '#64d2ff',
  yellow: '#ffd60a',
  orange: '#ff9f0a',
};

const POS_KEY = 'cme-ticker.pos';
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
  const left0 = rect.left, top0 = rect.top;
  const move = (ev) => {
    const pos = { left: `${left0 + ev.clientX - sx}px`, top: `${top0 + (ev.clientY - sy)}px` };
    el.style.left = pos.left;
    el.style.top = pos.top;
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
  fontSize: '10px', color: macos.secondary, fontWeight: '700',
  letterSpacing: '0.6px', textTransform: 'uppercase',
};
const hhmm = (ts) => {
  const d = new Date(ts * 1000);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
};
// คอลัมน์ context: OI (ถือข้ามคืน) + Intra (volume วันนี้ก่อน flow ก้อนนี้) เช่น 51+100
// OI = 0 = ไม่มีใครถือข้ามคืน แล้ววันนี้มีคนเปิด → เน้นสีเขียว (การเปิดสถานะใหม่)
const oiCell = (oi, intra) => {
  const inTxt = intra != null ? String(intra) : '?';
  if (oi == null) return { txt: `–+${inTxt}`, color: macos.tertiary };
  return { txt: `${oi}+${inTxt}`, color: oi === 0 ? macos.green : macos.tertiary };
};

// สี strike ตามราคา future **ปัจจุบัน** (ไม่ใช่ตอน log): เหนือราคา = เขียว / ต่ำกว่า = แดง
// / ใกล้ราคา (ในระยะ ±1 strike step ~5) = ขาว — เทียบกับ Fnow ที่อ่านสดทุก refresh
// ใช้ เขียว/แดง (ไม่ใช่ ฟ้า/ส้ม) เพราะ ฟ้า/เหลือง ตีความชนกับ PUT/CALL
// ราคาวิ่งข้าม strike เมื่อไหร่ แถวที่ค้างอยู่จะสลับสีเอง
// โทน pastel เฉพาะ strike (blend เข้าหาขาว ~40%) ไม่ใช้ system green/red ที่แสบตา
// — แยกจาก macos.green/red ที่ยังใช้กับ +n และ IV change (ต้องสดเหมือนเดิม)
const STRIKE_UP = '#83e0a3';    // เขียว mint นวล = เหนือราคา
const STRIKE_DOWN = '#ff6b78';  // แดง rose เย็น = ต่ำกว่าราคา (#ff8f8f เดิมออก salmon/ส้ม)
const STRIKE_NEAR = 2.6;  // ครึ่งหนึ่งของ strike step 5 → นับว่า "ที่ราคา"
const strikeColor = (k, Fnow) => {
  if (Fnow == null) return macos.label;
  const d = k - Fnow;
  if (Math.abs(d) <= STRIKE_NEAR) return macos.label;
  return d > 0 ? STRIKE_UP : STRIKE_DOWN;
};

// ---- กราฟ IV: พล็อตตามเวลาจริง ไม่ใช่ตาม index ----
// ถ้าพล็อตตาม index ช่วงที่เครื่อง sleep/cron ไม่ทำงานจะถูกบีบให้ดูเหมือนต่อเนื่อง = กราฟโกหก
const IvChart = ({ hist, windowMin }) => {
  const W = CONTENT_W, H = 54;
  if (!hist || hist.length < 2) {
    return (
      <div style={{ height: `${H}px`, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: macos.tertiary, fontSize: '11px' }}>
        collecting… ({hist ? hist.length : 0}/2)
      </div>
    );
  }
  const PAD_L = 19, PAD_R = 4;  // gutter ซ้ายพอดีตัวเลข hi/lo (~15px) ไม่ให้เส้นทับ / ขวากันจุดล้น
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
  const rising = hist.length > 1 && last.iv >= hist[0].iv;
  const stroke = rising ? macos.green : macos.red;
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
  fontVariantNumeric: 'tabular-nums', padding: '2px 0', height: '17px',
  boxSizing: 'border-box',
};
const Row = ({ cells }) => (
  <div style={{ ...rowStyle, color: macos.label }}>
    {cells.map((c, i) => (
      <span key={i} style={{ width: c.w, textAlign: c.a || 'left', color: c.c || 'inherit',
                             overflow: 'hidden', whiteSpace: 'nowrap' }}>{c.v}</span>
    ))}
  </div>
);
// แถวเปล่าที่สูงเท่าแถวจริง — ตรึงความสูงการ์ดไว้ ไม่ให้ยืดหดตามจำนวน event
const BlankRow = () => <div style={rowStyle}>&nbsp;</div>;
const fixedRows = (items, n, fn) =>
  Array.from({ length: n }, (_, i) => (i < items.length ? fn(items[i], i) : <BlankRow key={`b${i}`} />));

export const render = (state, dispatch) => {
  const { output, hold, resetting } = state || {};
  if (!output) return null;
  // output = ticker JSON + ---SPLIT--- + gold JSON (ดู command)
  const [tickerRaw, goldRaw] = String(output).split('---SPLIT---');
  let data;
  try { data = JSON.parse(tickerRaw); } catch (e) { return null; }
  const { meta, iv_hist, ticker, active } = data;
  if (!meta) return null;

  // ราคา future สดจาก gold_data.json — ใช้ระบายสี strike ให้ขยับตามราคาแบบ real-time
  // สดเกิน 15 นาที/พังก็ตกไปใช้ F ที่ fetcher บันทึกไว้ (เก่ากว่าแต่ดีกว่าไม่มี)
  let Fnow = meta.F;
  try {
    const g = JSON.parse(goldRaw);
    const p = (g.future || {}).price;
    if (p && g.ts && Date.now() / 1000 - g.ts < 900) Fnow = p;
  } catch (e) { /* ใช้ meta.F ต่อ */ }

  const stale = meta.ts && Date.now() / 1000 - meta.ts > 660;  // > 2 คาบ = fetcher มีปัญหา
  const chgColor = meta.iv_chg == null ? macos.tertiary : meta.iv_chg >= 0 ? macos.green : macos.red;

  // reset = ลบ state (baseline + ประวัติ) แล้วรัน fetcher ทันทีเพื่อตั้ง baseline ใหม่
  // ไม่ลบ cache OI — OI นิ่งทั้งวัน ไม่ใช่ "ประวัติ" ที่สะสม
  const doReset = () => {
    dispatch({ type: 'RESET_START' });
    run('rm -f /tmp/cme_ticker_state.json && /usr/bin/python3 /Users/sorachai/src/my-cronjob/cme_ticker.py')
      .then(() => run('cat /tmp/cme_ticker.json'))
      .then((out) => dispatch({ type: 'RESET_DONE', output: out }))
      .catch(() => dispatch({ type: 'RESET_DONE', output: null }));
  };
  const startHold = (e) => {
    if (e.altKey || resetting) return;   // ⌥ สงวนไว้ให้ลากย้ายการ์ด
    e.preventDefault();
    e.stopPropagation();
    clearHold();
    const t0 = Date.now();
    holdTimer = setInterval(() => {
      const pct = (Date.now() - t0) / HOLD_MS;
      if (pct >= 1) { clearHold(); doReset(); }
      else dispatch({ type: 'HOLD_TICK', pct });
    }, 90);
  };
  const cancelHold = () => {
    if (!holdTimer) return;
    clearHold();
    dispatch({ type: 'HOLD_END' });
  };

  const container = {
    position: 'fixed',
    top: savedPos().top || '60px',
    left: savedPos().left || '400px',
    width: `${CARD_W}px`,
    padding: '16px',
    borderRadius: macos.radius,
    color: macos.label,
    fontFamily: macos.font,
    background: macos.material,
    border: macos.border,
    boxShadow: macos.shadow,
    boxSizing: 'border-box',
    cursor: 'default',
  };

  return (
    <div style={container} onMouseDown={altDrag}>
      {/* ---- header: ชื่อ · series · [Reset] · เวลา ---- */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{ fontSize: '12px', fontWeight: '700', letterSpacing: '0.4px' }}>
          CME TICKER · {meta.series}
        </span>
        {/* กดค้าง 5 วิ — ไม่เขียนบอก แถบแดงที่วิ่งคือ feedback ว่ากำลังนับ */}
        <div
          onMouseDown={startHold}
          onMouseUp={cancelHold}
          onMouseLeave={cancelHold}
          title="Hold 5s to clear all history (ticker / most active / IV chart)"
          style={{
            position: 'relative', overflow: 'hidden', userSelect: 'none',
            borderRadius: '999px', background: 'rgba(255,255,255,0.10)',
            padding: '2px 8px', lineHeight: '1',
            cursor: resetting ? 'default' : 'pointer',
          }}>
          <div style={{
            position: 'absolute', left: 0, top: 0, bottom: 0,
            width: `${(hold || 0) * 100}%`,
            background: 'rgba(255,69,58,0.75)',
            transition: 'width 90ms linear', pointerEvents: 'none',
          }} />
          <span style={{
            position: 'relative', fontSize: '9px', fontWeight: '700', letterSpacing: '0.3px',
            color: resetting ? macos.yellow : hold > 0 ? macos.label : macos.tertiary,
          }}>
            Reset
          </span>
        </div>
        <span style={{ marginLeft: 'auto', fontSize: '10px',
                       color: stale ? macos.orange : macos.tertiary,
                       fontWeight: stale ? '700' : '400' }}>
          {stale ? '● ' : ''}{meta.system_time}
        </span>
      </div>

      {/* ---- IV + chart ---- */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
                    marginTop: '10px' }}>
        <span style={secTitle}>Implied Vol · {(meta.iv_window_min / 60).toFixed(0)}h</span>
        <span style={{ fontSize: '9px', color: macos.tertiary }}>
          {/* F ไม่โชว์แล้ว แต่ยังต้องเตือนถ้า delta ถูกคำนวณจาก F เก่าของ QuikStrike */}
          {meta.F_src !== 'live' && <span style={{ color: macos.orange, fontWeight: '700' }}>⚠ stale F · </span>}
          {meta.dte != null && `dte ${meta.dte.toFixed(3)}`}
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '2px' }}>
        <span style={{ fontSize: '28px', fontWeight: '600', fontVariantNumeric: 'tabular-nums' }}>
          {meta.iv != null ? meta.iv.toFixed(2) : '--'}
        </span>
        <span style={{ fontSize: '13px', fontWeight: '600', color: chgColor,
                       fontVariantNumeric: 'tabular-nums' }}>
          {meta.iv_chg == null ? '--' : `${meta.iv_chg >= 0 ? '+' : '–'}${Math.abs(meta.iv_chg).toFixed(2)}`}
        </span>
      </div>
      <IvChart hist={iv_hist} windowMin={meta.iv_window_min} />

      <div style={{ height: '1px', background: macos.divider, margin: '10px 0 8px' }} />

      {/* ---- ticker ---- */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={secTitle}>
          Ticker · ≥{meta.threshold}
          {/* จุดอ้างอิงสีของ strike = ราคา future สด (เขียว=เหนือ / แดง=ต่ำกว่า) */}
          {Fnow != null && (
            <span style={{ color: macos.tertiary, fontWeight: '400' }}>
              {' · '}
              <span style={{ color: STRIKE_UP }}>▲</span>
              {Fnow.toFixed(1)}
              <span style={{ color: STRIKE_DOWN }}>▼</span>
            </span>
          )}
        </span>
        <span style={{ fontSize: '9px', color: macos.tertiary }}>time strike +n Δ oi+in</span>
      </div>
      <div style={{ marginTop: '4px' }}>
        {fixedRows(ticker || [], TICKER_ROWS, (t, i) => {
          const oi = oiCell(t.oi, t.intra);
          return (
            <Row key={i} cells={[
              { v: hhmm(t.ts), w: '40px', c: macos.tertiary },
              { v: t.strike, w: '44px', c: strikeColor(t.strike, Fnow) },
              { v: `+${t.n}`, w: '42px', a: 'right', c: macos.green },
              { v: t.d != null ? `Δ${t.d.toFixed(2)}` : '–', w: '50px', a: 'right', c: macos.secondary },
              { v: oi.txt, w: '82px', a: 'right', c: oi.color },
            ]} />
          );
        })}
      </div>

      <div style={{ height: '1px', background: macos.divider, margin: '10px 0 8px' }} />

      {/* ---- most active (เรียงตาม rate) ---- */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={secTitle}>Most Active · {meta.active_window_min}m</span>
        <span style={{ fontSize: '9px', color: macos.tertiary }}>age strike sum rate</span>
      </div>
      <div style={{ marginTop: '4px' }}>
        {fixedRows(active || [], ACTIVE_ROWS, (a, i) => (
          <Row key={i} cells={[
            { v: `${a.age}m`, w: '44px', c: macos.tertiary },
            { v: a.strike, w: '58px', c: strikeColor(a.strike, Fnow) },
            { v: a.sum, w: '58px', a: 'right', c: macos.green },
            { v: `${a.rate.toFixed(1)}/m`, w: '98px', a: 'right', c: macos.blue },
          ]} />
        ))}
      </div>

    </div>
  );
};
