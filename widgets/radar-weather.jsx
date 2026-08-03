import { run } from 'uebersicht';

export const command = "cat /tmp/weather_meta.json";
export const refreshFrequency = 60000;

// ---- macOS system palette (shared theme กับ gold-update.jsx) ----
// ไม่ใช้ backdrop-filter เพราะใน Übersicht มันกระพริบตอน re-render ทุกรอบ refresh
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
  orange: '#ffb340',
  blue: '#64d2ff',
  green: '#30d158',
};

// ตำแหน่ง Office/บ้าน เป็น % ของภาพเรดาร์ 965x800
// (เรดาร์หนองจอก 13.8348127,100.8463349 = px(483,400), สเกล 0.3008 กม./px)
const MARKERS = [
  { id: 'office', left: '38.7%', top: '52.8%', color: '#64d2ff' },  // 13.7733, 100.5426
  { id: 'home', left: '41.0%', top: '47.6%', color: '#ffb340' },    // 13.8873, 100.6026
];

const Marker = ({ m }) => (
  <div style={{
    position: 'absolute', left: m.left, top: m.top,
    transform: 'translate(-50%, -50%)', pointerEvents: 'none',
    width: '8px', height: '8px', borderRadius: '50%',
    background: m.color, border: '1.5px solid rgba(255,255,255,0.9)',
    boxShadow: `0 0 6px ${m.color}`,
  }} />
);


// ⌥-drag ย้ายการ์ด: กด Option ค้างแล้วลาก — ตำแหน่งเก็บ localStorage ข้าม reboot
const POS_KEY = 'radar-weather.pos';
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

export const render = ({ output, error }) => {
  if (error) return null;
  if (!output) return null;

  try {
    const data = JSON.parse(output);
    // ภาพเก่ากว่า 20 นาที = เตือนว่าค้าง
    const stale = data.ts && Date.now() / 1000 - data.ts > 1200;

    const container = {
      // 344px = ความกว้าง medium widget ของ macOS (วัดจากหน้าจอจริง)
      position: 'fixed', top: savedPos().top || '390px', left: savedPos().left || '35px', width: '344px',
      padding: '16px', borderRadius: macos.radius,
      color: macos.label, fontFamily: macos.font,
      background: macos.material,
      border: macos.border, boxShadow: macos.shadow,
      cursor: 'pointer',
      boxSizing: 'border-box',
    };

    const handleClick = (e) => {
      if (e.altKey) return;
      e.preventDefault();
      run("open -a 'Google Chrome' 'https://weather.tmd.go.th/bma_ncLoop.php'");
    };

    return (
      <div style={container} onClick={handleClick} onMouseDown={altDrag}>
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
          {MARKERS.map((m) => <Marker m={m} key={m.id} />)}
        </div>
      </div>
    );
  } catch (e) {
    return null;
  }
};
