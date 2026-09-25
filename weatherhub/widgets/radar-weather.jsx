import { run } from 'uebersicht';

// ข้อมูลมาจาก API ของ weatherhub (8788) พร้อมพิกัดของเครื่องนี้ -- API ล่ม/ยังไม่ start
// ค่อยถอยไปอ่าน /tmp แบบเดิม (footer ขึ้น "· file") เหมือนการ์ด gold
const API = 'http://127.0.0.1:8788';
const API_TIMEOUT = 2000;
const FILE_CMD = 'cat /tmp/weather_meta.json';

// พิกัดเครื่อง: Übersicht ต่อ navigator.geolocation เข้ากับ CoreLocation ของแอปเอง
// (Resources/geolocation.js) ครั้งแรก macOS จะถามสิทธิ์ Location ของ Übersicht
// ตัว shim ไม่เคยเรียก onError -> ต้องมี timeout เอง / ไม่ได้พิกัด = ไม่ส่ง lat/lon
// (API ใช้จุด default) และไม่วาดจุด "ฉัน" / เก็บพิกัดไว้ในหน่วยความจำเท่านั้น
const LOC_TIMEOUT = 8000;
const LOC_MAX_AGE = 10 * 60 * 1000;     // ขอพิกัดใหม่ทุก 10 นาที
const NOWCAST_MAX_AGE = 3600;           // ผล nowcast เก่ากว่านี้ไม่โชว์ (เช็คเฉพาะ 16:xx)
let loc = null;                         // { lat, lon, at }
let locPending = null;

const locate = () => {
  if (loc && Date.now() - loc.at < LOC_MAX_AGE) return Promise.resolve(loc);
  if (locPending) return locPending;
  const geo = typeof navigator !== 'undefined' && navigator.geolocation;
  if (!geo) return Promise.resolve(loc);
  locPending = Promise.race([
    new Promise((res) => geo.getCurrentPosition(
      (p) => res({ lat: p.coords.latitude, lon: p.coords.longitude, at: Date.now() }),
      () => res(null))),
    new Promise((res) => setTimeout(() => res(null), LOC_TIMEOUT)),
  ]).then((got) => { if (got) loc = got; locPending = null; return loc; });
  return locPending;
};

const fetchJson = (url) => Promise.race([
  fetch(url).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }),
  new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), API_TIMEOUT)),
]);

const load = (dispatch) => {
  const viaFile = () => run(FILE_CMD).then((out) => {
    try { dispatch({ type: 'DATA', meta: JSON.parse(out), state: null, src: 'file' }); } catch (e) {}
  });
  return locate()
    .then((l) => fetchJson(API + '/api/state' + (l ? `?lat=${l.lat}&lon=${l.lon}` : '')))
    .then((s) => {
      if (!s.radar) throw new Error('no radar yet');
      dispatch({ type: 'DATA', meta: s.radar, state: s, src: 'api' });
    })
    .catch(viaFile);
};

export const command = load;
export const refreshFrequency = 60000;

export const initialState = { meta: null, state: null, src: null };
export const updateState = (event, prev) => {
  // command เป็นฟังก์ชัน Übersicht จะยิง UB/COMMAND_RAN เองแบบไม่มี output -- ไม่ใช้ event นั้นเลย
  if (event.type === 'DATA') return { ...prev, meta: event.meta, state: event.state, src: event.src };
  return prev;
};

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

// จุด "เครื่องนี้อยู่ตรงนี้" จาก point.img_pct ของ API (พิกัดปัดกริด ~5 กม. แล้ว)
const MeMarker = ({ pct }) => (
  <div style={{
    position: 'absolute', left: `${pct.left}%`, top: `${pct.top}%`,
    transform: 'translate(-50%, -50%)', pointerEvents: 'none',
    width: '12px', height: '12px', borderRadius: '50%',
    background: '#ffffff', border: `3px solid ${macos.green}`,
    boxShadow: '0 0 0 2px rgba(0,0,0,0.35), 0 0 8px rgba(48,209,88,0.9)',
    boxSizing: 'border-box',
  }} />
);

// บรรทัดฝนของจุดนี้ -- เฉพาะตอนมีผล nowcast สดและฝนหนักจะถึงภายใน lookahead
const rainLine = (n) => {
  if (!n || n.eta_min == null || n.age == null || n.age > NOWCAST_MAX_AGE) return null;
  const when = n.eta_min === 0
    ? `ฝนหนักอยู่ในรัศมี ${n.radius_km} กม. แล้ว`
    : `ฝนหนักจะถึงในอีก ~${n.eta_min} นาที`;
  return n.from_dir ? `${when} · มาจากทิศ${n.from_dir}` : when;
};


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

export const render = ({ meta, state, src }) => {
  if (!meta) return null;

  // ภาพเก่ากว่า 20 นาที = เตือนว่าค้าง
  const stale = meta.ts && Date.now() / 1000 - meta.ts > 1200;
  // โหมด API: ภาพมาจาก /api/radar (ใส่ ts กัน cache) / โหมดไฟล์: base64 ในไฟล์เหมือนเดิม
  const imgSrc = src === 'api'
    ? `${API}/api/radar?t=${meta.ts}`
    : `data:${meta.mime || 'image/png'};base64,${meta.img_base64}`;
  const point = state && state.point;
  const me = point && !point.default && point.img_pct;
  const rain = rainLine(state && state.nowcast);

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
          {meta.source}
        </span>
        <span style={{ fontSize: '11px', color: stale ? macos.orange : macos.tertiary, fontWeight: stale ? '700' : '400' }}>
          {stale ? '● ' : ''}{meta.last_update}{src === 'file' ? ' · file' : ''}
        </span>
      </div>

      <div style={{ position: 'relative', width: '100%', borderRadius: '14px', overflow: 'hidden', background: 'rgba(255, 255, 255, 0.1)', minHeight: '200px', display: 'flex', alignItems: 'center' }}>
        <img src={imgSrc} style={{ width: '100%', display: 'block' }} />
        {MARKERS.map((m) => <Marker m={m} key={m.id} />)}
        {me && <MeMarker pct={me} />}
      </div>

      {rain && (
        <div style={{ marginTop: '10px', fontSize: '12px', fontWeight: '600', color: macos.orange }}>
          🌧 {rain}
        </div>
      )}
    </div>
  );
};
