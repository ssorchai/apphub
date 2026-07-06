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
const TopActive = ({ title, top }) => {
  if (!top || !top.length) return null;
  return (
    <div style={{ marginTop: '8px' }}>
      <div style={secTitle}>Top Active · {title}</div>
      {top.map((t) => (
        <div key={t.strike} style={{ display: 'flex', alignItems: 'baseline', gap: '8px', fontSize: '12px', marginTop: '3px' }}>
          <span style={{ fontWeight: '600', color: macos.label, minWidth: '38px' }}>{t.strike}</span>
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
const ChangeRow = ({ title, rows, since }) => {
  if (!rows || !rows.length) return null;
  const dfmt = (v) => (v > 0 ? `+${fmt(v)}` : fmt(v));
  return (
    <div style={{ marginTop: '8px' }}>
      <div style={secTitle}>Δ {title}{since ? ` · ตั้งแต่ ${since}` : ''}</div>
      {rows.map((r) => (
        <div key={r.strike} style={{ display: 'flex', alignItems: 'baseline', gap: '8px', fontSize: '12px', marginTop: '3px' }}>
          <span style={{ fontWeight: '600', color: macos.label, minWidth: '38px' }}>{r.strike}</span>
          <span style={{ marginLeft: 'auto' }}>
            {r.dp !== 0 && <span style={{ color: macos.orange, fontWeight: '600' }}>P {dfmt(r.dp)}</span>}
            {r.dp !== 0 && r.dc !== 0 && <span style={{ color: macos.tertiary }}> · </span>}
            {r.dc !== 0 && <span style={{ color: macos.blue, fontWeight: '600' }}>C {dfmt(r.dc)}</span>}
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
      <div style={secTitle}>
        SD · open {fmt(sd.open)} · vol {sd.vol_used} · dte {sd.dte}
      </div>
      {rows.map(([n, b, s]) => (
        <div key={n} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginTop: '3px', fontWeight: '600' }}>
          <span style={{ color: macos.tertiary, fontWeight: '600' }}>{n}σ</span>
          <span style={{ color: macos.green }}>{b.toFixed(1)}</span>
          <span style={{ color: macos.tertiary }}>·</span>
          <span style={{ color: macos.red }}>{s.toFixed(1)}</span>
        </div>
      ))}
    </div>
  );
};

export const render = (state, dispatch) => {
  const { output, refreshing } = state || {};
  if (!output) return null;
  let data;
  try { data = JSON.parse(output); } catch (e) { return null; }

  // fetcher รันรายชั่วโมง — เกิน 2 ชม. = ข้อมูลค้าง (cron ตาย/วันหยุด)
  const stale = data.ts && Date.now() / 1000 - data.ts > 7200;

  const container = {
    position: 'fixed', bottom: '25px', left: '345px', width: '540px',
    padding: '14px 16px', borderRadius: macos.radius,
    color: macos.label, fontFamily: macos.font,
    background: macos.material,
    border: macos.border, boxShadow: macos.shadow,
    fontVariantNumeric: 'tabular-nums',
    cursor: 'pointer',
    boxSizing: 'border-box',
  };

  // คลิกการ์ด = copy string สำหรับ paste ลง oi_block.pine
  const handleCopy = (e) => {
    e.preventDefault();
    run('cat /tmp/cme_putcall_clip.txt | pbcopy');
  };

  // ปุ่ม ↻ = รัน fetcher เดี๋ยวนั้น เสร็จแล้ว copy ให้อัตโนมัติ (กันกดซ้ำระหว่างรัน)
  const handleRefresh = (e) => {
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

  const ivChg = data.iv_chg;
  // Vol Chg พอง >2-3 จุด = ตลาด reprice vol — กรอบ SD จาก settle แคบเกินจริง
  const ivAlert = ivChg != null && Math.abs(ivChg) > 2;

  return (
    <div style={container} onClick={handleCopy} title="Click = copy P/C data for TradingView">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '11px', fontWeight: '700', letterSpacing: '0.6px', color: macos.label }}>
          CME GOLD {data.series || ''}
          {stale && <span style={{ color: macos.orange, marginLeft: '8px' }}>● STALE</span>}
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '10px', color: macos.tertiary, fontWeight: '600' }}>
            DTE {data.dte != null ? data.dte.toFixed(2) : '--'}
          </span>
          <span
            onClick={handleRefresh}
            title="Refresh CME data now + copy"
            style={{
              fontSize: '13px', fontWeight: '700', lineHeight: '1',
              color: refreshing ? macos.yellow : macos.secondary,
              background: 'rgba(255,255,255,0.15)', borderRadius: '999px',
              padding: '4px 9px',
            }}>
            {refreshing ? 'refreshing…' : '↻'}
          </span>
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

        {/* คอลัมน์ขวา: Top Active + ของที่เติมเข้ามาตั้งแต่ refresh ก่อน */}
        <div style={{ flex: 1, minWidth: 0, borderLeft: `0.5px solid ${macos.divider}`, paddingLeft: '16px' }}>
          <TopActive title="Intraday" top={data.intraday && data.intraday.top} />
          <TopActive title="OI" top={data.oi && data.oi.top} />
          <ChangeRow title="Intraday" rows={data.changes && data.changes.intraday} since={data.changes && data.changes.since} />
          <ChangeRow title="OI" rows={data.changes && data.changes.oi} since={data.changes && data.changes.since} />
        </div>
      </div>

      <div style={{
        borderTop: `0.5px solid ${macos.divider}`,
        marginTop: '12px', paddingTop: '8px',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <span style={{ fontSize: '10px', color: macos.tertiary }}>
          click card → copy for TV · ↻ → refresh + copy
        </span>
        <span style={{ fontSize: '10px', color: macos.tertiary }}>
          Sync {data.system_time || '--'}
        </span>
      </div>
    </div>
  );
};
