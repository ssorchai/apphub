import { run } from 'uebersicht';

export const command = "cat /tmp/weather_meta.json";
export const refreshFrequency = 60000;

// ---- macOS system palette (shared theme กับ gold-update.jsx) ----
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
  orange: '#ffb340',
  blue: '#64d2ff',
  green: '#30d158',
};

// ตำแหน่ง Office/บ้าน เป็น % ของภาพเรดาร์ 965x800
// (calibrate จากศูนย์กลางวงแหวนเรดาร์หนองจอก px(483,400), สเกล 0.3008 กม./px)
const MARKERS = [
  { label: 'OFC', left: '38.4%', top: '53.8%', color: '#64d2ff' },   // 13.7733, 100.5426
  { label: 'HOME', left: '40.6%', top: '48.5%', color: '#ffb340' },  // 13.8873, 100.6026
];

const Marker = ({ m }) => (
  <div style={{ position: 'absolute', left: m.left, top: m.top, transform: 'translate(-50%, -50%)', pointerEvents: 'none' }}>
    <div style={{
      width: '8px', height: '8px', borderRadius: '50%', margin: '0 auto',
      background: m.color, border: '1.5px solid rgba(255,255,255,0.9)',
      boxShadow: `0 0 6px ${m.color}`,
    }} />
    <div style={{
      fontSize: '8px', fontWeight: '700', color: m.color, textAlign: 'center',
      marginTop: '1px', letterSpacing: '0.3px',
      textShadow: '0 0 3px rgba(0,0,0,0.9), 0 0 3px rgba(0,0,0,0.9)',
    }}>
      {m.label}
    </div>
  </div>
);

export const render = ({ output, error }) => {
  if (error) return null;
  if (!output) return null;

  try {
    const data = JSON.parse(output);
    // ภาพเก่ากว่า 20 นาที = เตือนว่าค้าง
    const stale = data.ts && Date.now() / 1000 - data.ts > 1200;

    const container = {
      // 344px = ความกว้าง medium widget ของ macOS (วัดจากหน้าจอจริง)
      position: 'fixed', top: '390px', left: '35px', width: '344px',
      padding: '16px', borderRadius: macos.radius,
      color: macos.label, fontFamily: macos.font,
      background: macos.material,
      border: macos.border, boxShadow: macos.shadow,
      cursor: 'pointer',
      boxSizing: 'border-box',
    };

    const handleClick = (e) => {
      e.preventDefault();
      run("open -a 'Google Chrome' 'https://weather.tmd.go.th/bma_ncLoop.php'");
    };

    return (
      <div style={container} onClick={handleClick}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
          <span style={{ fontSize: '11px', color: macos.secondary, fontWeight: '600', letterSpacing: '0.5px', textTransform: 'uppercase' }}>
            {data.source}
          </span>
          <span style={{ fontSize: '11px', color: stale ? macos.orange : macos.tertiary, fontWeight: stale ? '700' : '400' }}>
            {stale ? '● ' : ''}{data.last_update}
          </span>
        </div>

        <div style={{ position: 'relative', width: '100%', borderRadius: '14px', overflow: 'hidden', background: 'rgba(255, 255, 255, 0.1)', minHeight: '200px', display: 'flex', alignItems: 'center' }}>
          <img
            src={`data:${data.mime || 'image/png'};base64,${data.img_base64}`}
            style={{ width: '100%', display: 'block' }}
          />
          {MARKERS.map((m) => <Marker m={m} key={m.label} />)}
        </div>
      </div>
    );
  } catch (e) {
    return null;
  }
};
