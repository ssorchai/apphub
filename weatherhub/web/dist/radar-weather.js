// GENERATED จาก widgets/radar-weather.jsx โดย web/build.js -- ห้ามแก้ไฟล์นี้ แก้ที่ .jsx
window.APPHUB_WIDGETS = window.APPHUB_WIDGETS || {};
window.APPHUB_WIDGETS["radar-weather"] = function (require, exports, React) {
"use strict";

Object.defineProperty(exports, "__esModule", {
  value: true
});
exports.render = exports.updateState = exports.initialState = exports.refreshFrequency = exports.command = void 0;

var _uebersicht = require("uebersicht");

// ข้อมูลมาจาก API ของ weatherhub (8788) พร้อมพิกัดของเครื่องนี้ -- API ล่ม/ยังไม่ start
// ค่อยถอยไปอ่าน /tmp แบบเดิม (footer ขึ้น "· file") เหมือนการ์ด gold
//
// ไฟล์เดียวกันนี้เป็นหน้าเว็บ /dashboard ของ weatherhub ด้วย (common/web/build.js, 25 ก.ย.)
// การ์ดบน desktop: คลิก = เปิดหน้าเว็บ (ใหญ่กว่า มีปุ่ม toggle ครบ) / ⌥-drag = ย้ายการ์ด
// หน้าเว็บ: ดับเบิลคลิก = เปิดเรดาร์ loop ของ กทม. (เดิมเป็นคลิกเดียวบนการ์ด)
const WEB = typeof window !== 'undefined' && !!window.APPHUB_WEB;
const API = WEB ? '' : 'http://127.0.0.1:8788'; // เว็บ = origin เดียวกับ API

const DASHBOARD_URL = 'http://127.0.0.1:8788/dashboard';
const BMA_URL = 'https://weather.tmd.go.th/bma_ncLoop.php';
const S = WEB ? 1.6 : 1; // ขนาดปุ่ม/จุดบนหน้าเว็บ

const API_TIMEOUT = 2000;
const FILE_CMD = 'cat /tmp/weather_meta.json'; // พิกัดเครื่อง: Übersicht ต่อ navigator.geolocation เข้ากับ CoreLocation ของแอปเอง
// (Resources/geolocation.js) ครั้งแรก macOS จะถามสิทธิ์ Location ของ Übersicht
// ตัว shim ไม่เคยเรียก onError -> ต้องมี timeout เอง / ไม่ได้พิกัด = ไม่ส่ง lat/lon
// ⚠️ native ของ Übersicht ส่งกลับเป็น { position: { coords }, address } ไม่ใช่ Position
// มาตรฐาน (strings ในตัวแอป) -- อ่าน p.coords ตรงๆ = undefined แล้วหมดเวลาทุกรอบ
// (API ใช้จุด default) และไม่วาดจุด "ฉัน" / เก็บพิกัดไว้ในหน่วยความจำเท่านั้น

const LOC_TIMEOUT = 8000;
const LOC_MAX_AGE = 10 * 60 * 1000; // ขอพิกัดใหม่ทุก 10 นาที

const NOWCAST_MAX_AGE = 3600; // ผล nowcast เก่ากว่านี้ไม่โชว์ (เช็คเฉพาะ 16:xx)

let loc = null; // { lat, lon, at }

let locPending = null;

const locate = () => {
  if (loc && Date.now() - loc.at < LOC_MAX_AGE) return Promise.resolve(loc);
  if (locPending) return locPending;
  const geo = typeof navigator !== 'undefined' && navigator.geolocation;
  if (!geo) return Promise.resolve(loc);
  locPending = Promise.race([new Promise(res => geo.getCurrentPosition(p => {
    const c = p && p.position && p.position.coords || p && p.coords;
    res(c && isFinite(c.latitude) && isFinite(c.longitude) ? {
      lat: c.latitude,
      lon: c.longitude,
      at: Date.now()
    } : null);
  }, () => res(null))), new Promise(res => setTimeout(() => res(null), LOC_TIMEOUT))]).then(got => {
    if (got) loc = got;
    locPending = null;
    return loc;
  });
  return locPending;
};

const fetchJson = url => Promise.race([fetch(url).then(r => {
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}), new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), API_TIMEOUT))]);

const load = dispatch => {
  // เว็บไม่มีไฟล์ให้ถอยไปอ่าน: ยิงไม่ได้ก็คงภาพเดิมไว้แล้วขึ้น "· offline"
  const viaFile = WEB ? () => dispatch({
    type: 'OFFLINE'
  }) : () => (0, _uebersicht.run)(FILE_CMD).then(out => {
    try {
      dispatch({
        type: 'DATA',
        meta: JSON.parse(out),
        state: null,
        src: 'file'
      });
    } catch (e) {}
  });
  return locate().then(l => fetchJson(API + '/api/state' + (l ? `?lat=${l.lat}&lon=${l.lon}` : '')).then(s => {
    if (!s.radar) throw new Error('no radar yet');
    dispatch({
      type: 'DATA',
      meta: s.radar,
      state: s,
      src: 'api',
      located: !!l
    });
  })).catch(viaFile);
};

const command = load;
exports.command = command;
const refreshFrequency = 60000; // ---- palette: dark (เดิม) / light (เฉพาะหน้าเว็บ 25 ก.ย. 26 -- ชุดเดียวกับการ์ด gold) ----
// ไม่ใช้ backdrop-filter เพราะใน Übersicht มันกระพริบตอน re-render ทุกรอบ refresh
// ⚠️ ต้องอยู่เหนือ initialState (อ่าน readTheme ตอนโมดูลรัน -- บทเรียนจาก gold-dashboard.jsx)
// `ink` = สีฐานของแผ่นโปร่ง (พื้นปุ่ม/เส้นคั่น) -- ธีมสว่างต้องเป็นหมึกดำ ไม่งั้นขาวบนขาวหาย

exports.refreshFrequency = refreshFrequency;
const DARK = {
  // ฉากหลังโทนเข้มโปร่ง: ตัวหนังสือขาวต้องอ่านออกทั้งบน wallpaper สว่างและมืด
  // (พื้นขาวโปร่งเดิมจมหายเมื่อ wallpaper เป็นโทนส้ม/สว่าง) — ปรับความทึบที่ค่านี้ค่าเดียว
  material: 'rgba(24, 26, 33, 0.55)',
  border: '0.5px solid rgba(255, 255, 255, 0.16)',
  shadow: '0 10px 28px rgba(0, 0, 0, 0.32)',
  label: '#ffffff',
  secondary: 'rgba(255, 255, 255, 0.78)',
  tertiary: 'rgba(255, 255, 255, 0.58)',
  ink: '255, 255, 255',
  badgeBg: 'rgba(24, 26, 33, 0.9)',
  pillOn: 'rgba(100, 210, 255, 0.35)',
  orange: '#ffb340',
  blue: '#64d2ff',
  green: '#30d158'
};
const LIGHT = {
  // ขาวนวล (ครีม) ไม่ใช่ขาวจ้า -- เหมือนธีมสว่างของหน้าเว็บ gold
  material: 'rgba(252, 249, 243, 0.94)',
  border: '0.5px solid rgba(0, 0, 0, 0.08)',
  shadow: '0 10px 28px rgba(0, 0, 0, 0.14)',
  label: '#14161c',
  secondary: 'rgba(0, 0, 0, 0.72)',
  tertiary: 'rgba(0, 0, 0, 0.50)',
  ink: '0, 0, 0',
  badgeBg: 'rgba(252, 249, 243, 0.95)',
  pillOn: 'rgba(10, 126, 164, 0.20)',
  orange: '#d9820b',
  blue: '#4a80e8',
  green: '#1b8a3a'
}; // component ทุกตัวอ่าน macos.* ตอน render -- สลับธีมด้วยการเขียนทับ object นี้แล้ว render ใหม่

const macos = {
  radius: '22px',
  font: '-apple-system, "SF Pro Display", "SF Pro Text", "Helvetica Neue", sans-serif',
  ...DARK
};

const wash = a => `rgba(${macos.ink}, ${a})`; // แผ่นโปร่งตามธีม


const THEME_KEY = 'radar-weather.theme';

const readTheme = () => {
  try {
    return localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark';
  } catch (e) {
    return 'dark';
  }
};

const applyTheme = name => {
  Object.assign(macos, name === 'light' ? LIGHT : DARK);

  if (WEB) {
    try {
      localStorage.setItem(THEME_KEY, name);
    } catch (e) {
      /* ไม่จำก็ไม่เป็นไร */
    }
  } // พื้นหลังของหน้าเว็บอยู่ใน dashboard.html -- บอกผ่าน data-theme ให้ CSS เปลี่ยนตาม


  if (WEB && document.body) document.body.dataset.theme = name;
  return name;
}; // การ์ดบน desktop ลอยอยู่บน wallpaper -- คงธีมมืดเสมอ ปุ่มสลับมีเฉพาะหน้าเว็บ


applyTheme(WEB ? readTheme() : 'dark'); // ปุ่มเปิด/ปิดจุด (Office/Home 1-2 + ตำแหน่งเครื่องนี้) -- จำไว้ใน localStorage ข้าม reboot

const SHOW_KEY = 'radar-weather.markers';
const SHOW_DEFAULT = {
  office: true,
  home: true,
  office2: true,
  home2: true,
  me: true
};

const savedShow = () => {
  try {
    return { ...SHOW_DEFAULT,
      ...JSON.parse(localStorage.getItem(SHOW_KEY))
    };
  } catch (e) {
    return SHOW_DEFAULT;
  }
};

const initialState = {
  meta: null,
  state: null,
  src: null,
  located: false,
  show: savedShow(),
  theme: WEB ? readTheme() : 'dark'
};
exports.initialState = initialState;

const updateState = (event, prev) => {
  // command เป็นฟังก์ชัน Übersicht จะยิง UB/COMMAND_RAN เองแบบไม่มี output -- ไม่ใช้ event นั้นเลย
  if (event.type === 'DATA') {
    return { ...prev,
      meta: event.meta,
      state: event.state,
      src: event.src,
      located: !!event.located
    };
  }

  if (event.type === 'OFFLINE') return { ...prev,
    src: 'offline'
  };
  if (event.type === 'THEME') return { ...prev,
    theme: applyTheme(event.name)
  };

  if (event.type === 'TOGGLE') {
    const show = { ...prev.show,
      [event.id]: !prev.show[event.id]
    };

    try {
      localStorage.setItem(SHOW_KEY, JSON.stringify(show));
    } catch (e) {}

    return { ...prev,
      show
    };
  }

  return prev;
}; // ตำแหน่ง Office/บ้าน เป็น % ของภาพเรดาร์ 965x800
// (เรดาร์หนองจอก 13.8348127,100.8463349 = px(483,400), สเกล 0.3008 กม./px)
// (คำนวณด้วยสูตรเดียวกับ geometry() ใน weatherhub/service/api.py)


exports.updateState = updateState;
const MARKERS = [{
  id: 'office',
  icon: 'office',
  n: 1,
  label: 'Office 1',
  left: '38.74%',
  top: '52.84%',
  color: '#64d2ff',
  ink: '#1a86b8'
}, // 13.7733, 100.5426
{
  id: 'office2',
  icon: 'office',
  n: 2,
  label: 'Office 2',
  left: '38.47%',
  top: '51.32%',
  color: '#bf8cff',
  ink: '#7c4dd1'
}, // 13.8062486, 100.5352885
{
  id: 'home',
  icon: 'home',
  n: 1,
  label: 'Home 1',
  left: '40.98%',
  top: '47.58%',
  color: '#ffb340',
  ink: '#c2710a'
}, // 13.8873269, 100.6026284
{
  id: 'home2',
  icon: 'home',
  n: 2,
  label: 'Home 2',
  left: '42.72%',
  top: '48.22%',
  color: '#ff6b6b',
  ink: '#d03a3a'
} // 13.873365, 100.6494155
];
const ME = {
  id: 'me',
  icon: 'me',
  label: 'ตำแหน่งเครื่องนี้',
  color: '#30d158',
  ink: '#1b8a3a'
}; // สีของปุ่ม: ธีมสว่างใช้โทนเข้ม (`ink`) สีอ่อนเดิมจางบนพื้นครีม / จุดบนภาพเรดาร์ใช้ `color` เสมอ

const btnColor = m => macos.ink === LIGHT.ink && m.ink || m.color; // ไอคอนของปุ่ม toggle (SVG วาดเอง ไม่พึ่งฟอนต์/ไฟล์ภายนอก)


const ICONS = {
  office: c => /*#__PURE__*/React.createElement("svg", {
    width: 13 * S,
    height: 13 * S,
    viewBox: "0 0 16 16",
    fill: "none",
    stroke: c,
    strokeWidth: "1.5",
    strokeLinejoin: "round"
  }, /*#__PURE__*/React.createElement("rect", {
    x: "3",
    y: "1.75",
    width: "10",
    height: "12.5",
    rx: "1"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M6 5h1M9 5h1M6 8h1M9 8h1M7 14.25v-3h2v3",
    strokeLinecap: "round"
  })),
  home: c => /*#__PURE__*/React.createElement("svg", {
    width: 13 * S,
    height: 13 * S,
    viewBox: "0 0 16 16",
    fill: "none",
    stroke: c,
    strokeWidth: "1.5",
    strokeLinejoin: "round"
  }, /*#__PURE__*/React.createElement("path", {
    d: "M2 7.5 8 2.5l6 5",
    strokeLinecap: "round"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M3.75 6.25v7.5h8.5v-7.5M6.75 13.75v-3.5h2.5v3.5"
  })),
  me: c => /*#__PURE__*/React.createElement("svg", {
    width: 13 * S,
    height: 13 * S,
    viewBox: "0 0 16 16",
    fill: "none",
    stroke: c,
    strokeWidth: "1.5",
    strokeLinecap: "round"
  }, /*#__PURE__*/React.createElement("circle", {
    cx: "8",
    cy: "8",
    r: "4.25"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: "8",
    cy: "8",
    r: "1.25",
    fill: c,
    stroke: "none"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M8 1v2M8 13v2M1 8h2M13 8h2"
  }))
}; // กดแล้วต้องไม่ไปเปิดหน้าเว็บ/เว็บ กทม. (คลิก/ดับเบิลคลิกการ์ด) และไม่เริ่ม ⌥-drag

const stop = e => e.stopPropagation();

const ToggleButton = ({
  m,
  on,
  dispatch,
  note
}) => /*#__PURE__*/React.createElement("div", {
  title: `${on ? 'ซ่อน' : 'แสดง'}จุด ${m.label}${note ? ` (${note})` : ''}`,
  onMouseDown: stop,
  onDoubleClick: stop,
  onClick: e => {
    e.stopPropagation();
    e.preventDefault();
    dispatch({
      type: 'TOGGLE',
      id: m.id
    });
  },
  style: {
    position: 'relative',
    width: `${22 * S}px`,
    height: `${22 * S}px`,
    borderRadius: '50%',
    boxSizing: 'border-box',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    background: on ? wash(0.16) : 'transparent',
    // ปุ่มเปิดอยู่แต่ยังวาดจุดไม่ได้ (เช่นยังไม่ได้พิกัด) = ขอบเส้นประ
    border: `1px ${note ? 'dashed' : 'solid'} ${on ? btnColor(m) : wash(0.22)}`,
    opacity: on ? 1 : 0.55
  }
}, ICONS[m.icon](on ? btnColor(m) : wash(0.7)), m.n && /*#__PURE__*/React.createElement("span", {
  style: {
    position: 'absolute',
    right: '-3px',
    bottom: '-3px',
    minWidth: `${10 * S}px`,
    height: `${10 * S}px`,
    borderRadius: `${5 * S}px`,
    background: macos.badgeBg,
    color: on ? btnColor(m) : wash(0.7),
    fontSize: `${8 * S}px`,
    fontWeight: '700',
    lineHeight: `${10 * S}px`,
    textAlign: 'center'
  }
}, m.n));

const Marker = ({
  m
}) => /*#__PURE__*/React.createElement("div", {
  style: {
    position: 'absolute',
    left: m.left,
    top: m.top,
    transform: 'translate(-50%, -50%)',
    pointerEvents: 'none',
    width: `${8 * S}px`,
    height: `${8 * S}px`,
    borderRadius: '50%',
    background: m.color,
    border: '1.5px solid rgba(255,255,255,0.9)',
    boxShadow: `0 0 6px ${m.color}`
  }
}); // จุด "เครื่องนี้อยู่ตรงนี้" จาก point.img_pct ของ API (พิกัดปัดกริด ~5 กม. แล้ว)


const MeMarker = ({
  pct
}) => /*#__PURE__*/React.createElement("div", {
  style: {
    position: 'absolute',
    left: `${pct.left}%`,
    top: `${pct.top}%`,
    transform: 'translate(-50%, -50%)',
    pointerEvents: 'none',
    width: `${12 * S}px`,
    height: `${12 * S}px`,
    borderRadius: '50%',
    background: '#ffffff',
    border: `3px solid ${macos.green}`,
    boxShadow: '0 0 0 2px rgba(0,0,0,0.35), 0 0 8px rgba(48,209,88,0.9)',
    boxSizing: 'border-box'
  }
}); // ปุ่มเลือกธีม (เฉพาะหน้าเว็บ) -- แบบเดียวกับ ModePill ของการ์ด gold


const ThemePill = ({
  label,
  on,
  onPick
}) => /*#__PURE__*/React.createElement("span", {
  onClick: e => {
    e.stopPropagation();
    onPick();
  },
  onDoubleClick: stop,
  style: {
    fontSize: '12px',
    fontWeight: '700',
    padding: '3px 10px',
    borderRadius: '999px',
    cursor: 'pointer',
    color: on ? macos.label : macos.secondary,
    background: on ? macos.pillOn : wash(0.12)
  }
}, label); // บรรทัดฝนของจุดนี้ -- เฉพาะตอนมีผล nowcast สดและฝนหนักจะถึงภายใน lookahead


const rainLine = n => {
  if (!n || n.eta_min == null || n.age == null || n.age > NOWCAST_MAX_AGE) return null;
  const when = n.eta_min === 0 ? `ฝนหนักอยู่ในรัศมี ${n.radius_km} กม. แล้ว` : `ฝนหนักจะถึงในอีก ~${n.eta_min} นาที`;
  return n.from_dir ? `${when} · มาจากทิศ${n.from_dir}` : when;
}; // ⌥-drag ย้ายการ์ด: กด Option ค้างแล้วลาก — ตำแหน่งเก็บ localStorage ข้าม reboot


const POS_KEY = 'radar-weather.pos';

const savedPos = () => {
  try {
    return JSON.parse(localStorage.getItem(POS_KEY)) || {};
  } catch (e) {
    return {};
  }
};

const altDrag = e => {
  if (!e.altKey) return;
  e.preventDefault();
  e.stopPropagation();
  const el = e.currentTarget;
  const sx = e.clientX,
        sy = e.clientY;
  const rect = el.getBoundingClientRect();
  const left0 = rect.left,
        top0 = rect.top;

  const move = ev => {
    const pos = {
      left: `${left0 + ev.clientX - sx}px`,
      top: `${top0 + (ev.clientY - sy)}px`
    };
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

const render = ({
  meta,
  state,
  src,
  located,
  show,
  theme
}, dispatch) => {
  if (!meta) return null; // ภาพเก่ากว่า 20 นาที = เตือนว่าค้าง

  const stale = meta.ts && Date.now() / 1000 - meta.ts > 1200; // โหมด API: ภาพมาจาก /api/radar (ใส่ ts กัน cache) / โหมดไฟล์: base64 ในไฟล์เหมือนเดิม

  const imgSrc = src === 'api' ? `${API}/api/radar?t=${meta.ts}` : `data:${meta.mime || 'image/png'};base64,${meta.img_base64}`;
  const point = state && state.point;
  const me = point && !point.default && point.img_pct; // ปุ่มจุด "ฉัน" เปิดอยู่แต่วาดไม่ได้ -> บอกเหตุผลใน tooltip

  const meNote = !located ? WEB ? 'ยังไม่ได้พิกัด -- อนุญาต Location ให้หน้านี้ (ต้องเปิดผ่าน localhost/https)' : 'ยังไม่ได้พิกัด -- เช็คสิทธิ์ Location ของ Übersicht' : !me ? 'อยู่นอกวงเรดาร์' : null;
  const rain = rainLine(state && state.nowcast);
  const container = { ...(WEB // หน้าเว็บ: การ์ดใหญ่กลางจอ (ภาพเรดาร์ 965x800 -> กว้างสุด 980px)
    ? {
      position: 'relative',
      margin: '24px auto',
      width: 'min(980px, calc(100vw - 32px))',
      padding: '20px'
    } // 344px = ความกว้าง medium widget ของ macOS (วัดจากหน้าจอจริง)
    : {
      position: 'fixed',
      top: savedPos().top || '390px',
      left: savedPos().left || '35px',
      width: '344px',
      padding: '16px'
    }),
    borderRadius: macos.radius,
    color: macos.label,
    fontFamily: macos.font,
    background: macos.material,
    border: macos.border,
    boxShadow: macos.shadow,
    cursor: 'pointer',
    boxSizing: 'border-box',
    userSelect: 'none'
  }; // desktop: คลิกเดียว = เปิดหน้าเว็บของการ์ดนี้ / เว็บ: ดับเบิลคลิก = เว็บเรดาร์ กทม.

  const handleClick = e => {
    if (WEB || e.altKey) return;
    e.preventDefault();
    (0, _uebersicht.run)(`open '${DASHBOARD_URL}'`);
  };

  const handleDoubleClick = e => {
    if (!WEB) return;
    e.preventDefault();
    window.open(BMA_URL, '_blank');
  };

  const fs = px => `${px * (WEB ? 1.25 : 1)}px`;

  return /*#__PURE__*/React.createElement("div", {
    style: container,
    onClick: handleClick,
    onDoubleClick: handleDoubleClick,
    onMouseDown: WEB ? undefined : altDrag,
    title: WEB ? 'ดับเบิลคลิก → เรดาร์ loop ของ กทม.' : 'คลิก → เปิดหน้าเว็บ · ⌥-drag ย้ายการ์ด'
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: '10px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: `${8 * S}px`
    },
    title: meta.source
  }, MARKERS.map(m => /*#__PURE__*/React.createElement(ToggleButton, {
    m: m,
    on: show[m.id],
    dispatch: dispatch,
    key: m.id
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      width: '1px',
      height: '14px',
      background: wash(0.18),
      margin: '0 2px'
    }
  }), /*#__PURE__*/React.createElement(ToggleButton, {
    m: ME,
    on: show.me,
    dispatch: dispatch,
    note: show.me ? meNote : null
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: fs(11),
      color: stale || src === 'offline' ? macos.orange : macos.tertiary,
      fontWeight: stale ? '700' : '400'
    }
  }, stale ? '● ' : '', meta.last_update, src === 'file' ? ' · file' : '', src === 'offline' ? ' · offline' : '')), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative',
      width: '100%',
      borderRadius: '14px',
      overflow: 'hidden',
      background: wash(0.1),
      minHeight: '200px',
      display: 'flex',
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: imgSrc,
    style: {
      width: '100%',
      display: 'block'
    }
  }), MARKERS.filter(m => show[m.id]).map(m => /*#__PURE__*/React.createElement(Marker, {
    m: m,
    key: m.id
  })), me && show.me && /*#__PURE__*/React.createElement(MeMarker, {
    pct: me
  })), rain && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: '10px',
      fontSize: fs(12),
      fontWeight: '600',
      color: macos.orange
    }
  }, "\uD83C\uDF27 ", rain), WEB && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: '10px',
      display: 'flex',
      alignItems: 'center',
      gap: '10px'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'flex',
      gap: '6px'
    }
  }, /*#__PURE__*/React.createElement(ThemePill, {
    label: "\u25D0 Dark",
    on: theme !== 'light',
    onPick: () => dispatch({
      type: 'THEME',
      name: 'dark'
    })
  }), /*#__PURE__*/React.createElement(ThemePill, {
    label: "\u25D1 Light",
    on: theme === 'light',
    onPick: () => dispatch({
      type: 'THEME',
      name: 'light'
    })
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: fs(10),
      color: macos.tertiary
    }
  }, meta.source, " \xB7 via ", meta.via || '?', " \xB7 \u0E14\u0E31\u0E1A\u0E40\u0E1A\u0E34\u0E25\u0E04\u0E25\u0E34\u0E01 \u2192 \u0E40\u0E23\u0E14\u0E32\u0E23\u0E4C loop \u0E02\u0E2D\u0E07 \u0E01\u0E17\u0E21.")));
};

exports.render = render;
};
