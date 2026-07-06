import { run } from 'uebersicht';

export const command = "cat /tmp/gold_data.json";
export const refreshFrequency = 1500;

// ---- macOS system palette (shared theme กับ radar-weather.jsx) ----
// ไม่ใช้ backdrop-filter เพราะใน Übersicht มันกระพริบตอน re-render ทุกรอบ refresh
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

const num = (v) => (typeof v === 'number' ? v : parseFloat(String(v).replace(/[,%+]/g, '')) || 0);
const fmt = (v, d = 2) => num(v).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });

// session เทรดทองทั่วโลก (เวลาไทย) — ช่วง overlap ไฟจะติดพร้อมกันหลายดวง
// LDN+NY ติดพร้อมกัน = GOLDEN TIME ไฟเป็นสีทอง
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
  // เปิด = เขียว (ทอง = ช่วง LDN+NY overlap), ปิด = ส้ม
  const color = s.on ? (s.golden ? macos.yellow : macos.green) : macos.orange;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '4px',
      padding: '2px 8px', borderRadius: '999px',
      background: s.on ? 'rgba(255, 255, 255, 0.22)' : 'rgba(255, 255, 255, 0.1)',
    }}>
      <span style={{
        width: '5px', height: '5px', borderRadius: '50%',
        background: color,
        boxShadow: `0 0 5px ${color}`,
      }} />
      <span style={{
        fontSize: '9px', fontWeight: '700', letterSpacing: '0.5px',
        color: s.on ? macos.label : macos.secondary,
      }}>
        {s.icon} {s.label}
      </span>
    </span>
  );
};

export const render = ({ output }) => {
  if (!output) return null;
  let data;
  try { data = JSON.parse(output); } catch (e) { return null; }

  const stale = data.ts && Date.now() / 1000 - data.ts > 180;

  const container = {
    position: 'fixed', bottom: '25px', left: '35px', width: '290px',
    padding: '14px 16px', borderRadius: macos.radius,
    color: macos.label, fontFamily: macos.font,
    background: macos.material,
    border: macos.border, boxShadow: macos.shadow,
    fontVariantNumeric: 'tabular-nums',
    cursor: 'pointer',
    boxSizing: 'border-box',
  };

  // asset = null คือรอบนั้นดึงราคาไม่ได้ — แสดง N/A ไม่ใช้ค่าเก่า
  const renderAsset = (asset, fallbackName, { accent, showOpen, showOpenChange } = {}) => {
    if (!asset) {
      return (
        <div style={{ marginTop: '8px' }}>
          <div style={{ fontSize: '10px', color: macos.secondary, fontWeight: '600', letterSpacing: '0.4px', textTransform: 'uppercase', marginBottom: '2px' }}>
            {fallbackName}
          </div>
          <span style={{ fontSize: '23px', fontWeight: '600', color: macos.tertiary }}>N/A</span>
        </div>
      );
    }
    const change = num(asset.change);
    const up = change >= 0;
    // +/- เทียบ open (เฉพาะ future — ส่ง showOpenChange มาและ fetcher มี change_open)
    const hasOpenChange = showOpenChange && asset.change_open != null;
    const changeOpen = num(asset.change_open);
    const upOpen = changeOpen >= 0;
    return (
      <div style={{ marginTop: '8px' }}>
        <div style={{ fontSize: '10px', color: macos.secondary, fontWeight: '600', letterSpacing: '0.4px', textTransform: 'uppercase', marginBottom: '2px' }}>
          {asset.name}
          {showOpen && asset.open != null && (
            <span style={{ color: macos.tertiary, marginLeft: '6px', textTransform: 'none' }}>O {fmt(asset.open)}</span>
          )}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <span style={{ fontSize: '23px', fontWeight: '600', letterSpacing: '-0.4px', color: accent || macos.label }}>
            {fmt(asset.price)}
          </span>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', lineHeight: '1.1' }}>
            <span style={{ fontSize: '12px', fontWeight: '600', color: up ? macos.green : macos.red }}>
              {up ? '+' : ''}{fmt(change)}
              <span style={{ opacity: 0.75, marginLeft: '5px', fontSize: '10px' }}>
                {up ? '+' : ''}{fmt(asset.percent)}%
              </span>
            </span>
            {hasOpenChange && (
              <span style={{ fontSize: '10px', fontWeight: '600', color: upOpen ? macos.green : macos.red }}>
                <span style={{ color: macos.tertiary, marginRight: '4px', fontWeight: '700' }}>O</span>
                {upOpen ? '+' : ''}{fmt(changeOpen)}
                <span style={{ opacity: 0.75, marginLeft: '5px', fontSize: '9px' }}>
                  {upOpen ? '+' : ''}{fmt(asset.percent_open)}%
                </span>
              </span>
            )}
          </div>
        </div>
      </div>
    );
  };

  const handleClick = (e) => {
    e.preventDefault();
    run("open -a 'Google Chrome' 'https://www.vol2vol.com'");
  };

  const hasDiff = data.diff != null;
  const marketTime = (data.future && data.future.time) || (data.spot && data.spot.time) || '--';

  // Δ = spread จริงเบี่ยงจากทฤษฎี — เกิน ±2 เตือนแดง (basis เบี้ยว รอ converge กลับ)
  const DELTA_WARN = 2;
  const delta = hasDiff && data.theory ? num(data.diff) - num(data.theory.diff) : null;
  const deltaAlert = delta != null && Math.abs(delta) > DELTA_WARN;
  const spreadColor = !hasDiff ? macos.tertiary
    : deltaAlert ? macos.red
    : num(data.diff) >= 0 ? macos.label : macos.blue;

  return (
    <div style={container} onClick={handleClick}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: '5px' }}>
          {sessionState().map((s) => <SessionLight s={s} key={s.label} />)}
        </div>
        {stale && (
          <span style={{ fontSize: '10px', fontWeight: '700', color: macos.orange, letterSpacing: '0.5px' }}>
            ●
          </span>
        )}
      </div>

      {renderAsset(data.future, 'Gold Futures', { showOpen: true, showOpenChange: true })}
      {renderAsset(data.spot || data.cfd, 'XAU/USD Spot', { accent: macos.blue })}

      <div style={{
        borderTop: `0.5px solid ${macos.divider}`,
        marginTop: '12px', paddingTop: '9px',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <span style={{ fontSize: '11px', color: macos.secondary, fontWeight: '600', letterSpacing: '0.4px' }}>
          SPREAD DIFF
        </span>
        <span style={{ fontSize: '15px', fontWeight: '600', color: spreadColor }}>
          {hasDiff ? `${num(data.diff) > 0 ? '+' : ''}${fmt(data.diff)}` : 'N/A'}
        </span>
      </div>

      {data.theory && (
        <div style={{ marginTop: '4px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '11px', color: macos.secondary, fontWeight: '600', letterSpacing: '0.4px' }}>
            THEORY DIFF · {data.theory.days}D
          </span>
          <span style={{ fontSize: '20px', fontWeight: '700', letterSpacing: '-0.3px', color: macos.label }}>
            {delta != null && (
              <span style={{ fontSize: '11px', fontWeight: '600', color: deltaAlert ? macos.red : macos.tertiary, marginRight: '8px' }}>
                Δ {delta > 0 ? '+' : ''}{fmt(delta)}
              </span>
            )}
            +{fmt(data.theory.diff, 1)}
          </span>
        </div>
      )}

      <div style={{ fontSize: '10px', color: macos.tertiary, marginTop: '8px', textAlign: 'right' }}>
        Market {marketTime} · Sync {data.system_time}
      </div>
    </div>
  );
};
