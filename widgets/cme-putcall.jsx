import { run } from 'uebersicht';

// อ่าน JSON ที่ cme_fetcher.py (cron รายชั่วโมง) เขียนไว้
export const command = "cat /tmp/cme_putcall.json";
export const refreshFrequency = 60000;

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

// แถวสรุป Put/Call หนึ่งชุด (Intraday หรือ OI) พร้อมแถบสัดส่วน
const PcRow = ({ title, pc }) => {
  if (!pc) return null;
  const total = pc.put + pc.call;
  const putShare = total > 0 ? (pc.put / total) * 100 : 50;
  return (
    <div style={{ marginTop: '10px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{ fontSize: '10px', color: macos.secondary, fontWeight: '600', letterSpacing: '0.4px', textTransform: 'uppercase' }}>
          {title}
        </span>
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
      {(pc.top || []).map((t) => (
        <div key={t.strike} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginTop: '3px' }}>
          <span style={{ color: macos.label, fontWeight: '600' }}>{t.strike}</span>
          <span style={{ color: macos.secondary }}>
            {fmt(t.total)}
            <span style={{ color: macos.tertiary, marginLeft: '6px' }}>P:{fmt(t.put)} C:{fmt(t.call)}</span>
          </span>
        </div>
      ))}
    </div>
  );
};

export const render = ({ output }) => {
  if (!output) return null;
  let data;
  try { data = JSON.parse(output); } catch (e) { return null; }

  // fetcher รันรายชั่วโมง — เกิน 2 ชม. = ข้อมูลค้าง (cron ตาย/วันหยุด)
  const stale = data.ts && Date.now() / 1000 - data.ts > 7200;

  const container = {
    position: 'fixed', bottom: '25px', left: '345px', width: '265px',
    padding: '14px 16px', borderRadius: macos.radius,
    color: macos.label, fontFamily: macos.font,
    background: macos.material,
    border: macos.border, boxShadow: macos.shadow,
    fontVariantNumeric: 'tabular-nums',
    cursor: 'pointer',
    boxSizing: 'border-box',
  };

  // คลิก = copy string สำหรับ paste ลง oi_block.pine บน TradingView
  const handleClick = (e) => {
    e.preventDefault();
    run('cat /tmp/cme_putcall_clip.txt | pbcopy');
  };

  const ivChg = data.iv_chg;
  // Vol Chg พอง >2-3 จุด = ตลาด reprice vol — กรอบ SD จาก settle แคบเกินจริง
  const ivAlert = ivChg != null && Math.abs(ivChg) > 2;

  return (
    <div style={container} onClick={handleClick} title="Click = copy P/C data for TradingView">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '11px', fontWeight: '700', letterSpacing: '0.6px', color: macos.label }}>
          CME GOLD {data.series || ''}
        </span>
        <span style={{ fontSize: '10px', color: stale ? macos.orange : macos.tertiary, fontWeight: '600' }}>
          {stale ? '● STALE' : `DTE ${data.dte != null ? data.dte.toFixed(2) : '--'}`}
        </span>
      </div>

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

      <div style={{
        borderTop: `0.5px solid ${macos.divider}`,
        marginTop: '12px', paddingTop: '8px',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <span style={{ fontSize: '10px', color: macos.tertiary }}>
          click → copy for TV
        </span>
        <span style={{ fontSize: '10px', color: macos.tertiary }}>
          Sync {data.system_time || '--'}
        </span>
      </div>
    </div>
  );
};
