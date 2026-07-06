import { run } from 'uebersicht';

// อ่าน JSON ที่ cme_fetcher.py (cron รายชั่วโมง) เขียนไว้
export const command = "cat /tmp/cme_putcall.json";
export const refreshFrequency = 60000;

// state แบบ redux ของ Übersicht: รองรับปุ่ม refresh (รัน fetcher ทันที + copy อัตโนมัติ)
export const initialState = { output: null, refreshing: false };
export const updateState = (event, prev) => {
  switch (event.type) {
    case 'UB/COMMAND_RAN': return { ...prev, output: event.output };
    case 'REFRESH_START': return { ...prev, refreshing: true };
    case 'REFRESH_DONE': return { ...prev, refreshing: false, output: event.output || prev.output };
    default: return prev;
  }
};

// ---- macOS system palette (shared theme กับ gold-update.jsx) ----
const macos = {
  material: 'rgba(255, 255, 255, 0.25)',
  border: '0.5px solid rgba(255, 255, 255, 0.25)',
  radius: '22px',
  shadow: '0 10px 24px rgba(0, 0, 0, 0.22)',
  font: '-apple-system, "SF Pro Display", "SF Pro Text", "Helvetica Neue", sans-serif',
  label: '#ffffff',
  secondary: 'rgba(255, 255, 255, 0.65)',
  tertiary: 'rgba(255, 255, 255, 0.42)',
  divider: 'rgba(255, 255, 255, 0.3)',
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

// กรอบ SD: mean = ราคาเปิด Yahoo, DTE 0.6, vol = Vol + Vol Chg (คำนวณโดย fetcher)
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

export const render = (state, dispatch) => {
  const { output, refreshing } = state || {};
  let data = null;
  try { data = JSON.parse(output); } catch (e) { data = null; }

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

  // ปุ่ม ↻ = รัน fetcher เดี๋ยวนั้น เสร็จแล้ว copy ให้อัตโนมัติ (กันกดซ้ำระหว่างรัน)
  const handleRefresh = (e) => {
    if (e.altKey) return;
    e.preventDefault();
    e.stopPropagation();
    if (refreshing) return;
    dispatch({ type: 'REFRESH_START' });
    run('/usr/bin/python3 /Users/sorachai/src/my-cronjob/cme_fetcher.py')
      .then(() => run('cat /tmp/cme_putcall_clip.txt | pbcopy'))
      .then(() => run('cat /tmp/cme_putcall.json'))
      .then((out) => dispatch({ type: 'REFRESH_DONE', output: out }))
      .catch(() => dispatch({ type: 'REFRESH_DONE', output: null }));
  };

  const refreshPill = (
    <span
      onClick={handleRefresh}
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

  const ivChg = data.iv_chg;
  // Vol Chg พอง >2-3 จุด = ตลาด reprice vol — กรอบ SD จาก settle แคบเกินจริง
  const ivAlert = ivChg != null && Math.abs(ivChg) > 2;

  // strike สูงกว่า F ที่ดึงได้ = เขียว / ต่ำกว่า = แดง
  const strikeColor = (s) => (data.F == null ? macos.label : s >= data.F ? macos.green : macos.red);

  return (
    <div style={container} onClick={handleCopy} onMouseDown={altDrag} title="Click = copy P/C data for TradingView · ⌥-drag = move">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '11px', fontWeight: '700', letterSpacing: '0.6px', color: macos.label }}>
          CME GOLD {data.series || ''}
          {stale && <span style={{ color: macos.orange, marginLeft: '8px' }}>● STALE</span>}
        </span>
        <span style={{ fontSize: '10px', color: macos.tertiary, fontWeight: '600' }}>
          DTE {data.dte != null ? data.dte.toFixed(2) : '--'}
        </span>
      </div>

      <div style={{ display: 'flex', gap: '18px' }}>
        {/* คอลัมน์ซ้าย: ราคา + สัดส่วน P/C */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: '6px' }}>
            <span style={{ fontSize: '20px', fontWeight: '600', letterSpacing: '-0.3px' }}>
              F {fmt(data.F)}
            </span>
            <span style={{ fontSize: '12px', fontWeight: '600', color: ivAlert ? macos.red : macos.secondary }}>
              IV {data.iv != null ? data.iv.toFixed(2) : '--'}
              {ivChg != null && (
                <span style={{ marginLeft: '4px', color: ivAlert ? macos.red : macos.tertiary }}>
                  {ivChg > 0 ? '+' : ''}{ivChg.toFixed(2)}
                </span>
              )}
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
