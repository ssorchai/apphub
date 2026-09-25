// GENERATED จาก widgets/radar-weather.jsx โดย web/build.js -- ห้ามแก้ไฟล์นี้ แก้ที่ .jsx
window.APPHUB_WIDGETS = window.APPHUB_WIDGETS || {};
window.APPHUB_WIDGETS["radar-weather"] = function (require, exports, React) {
"use strict";

Object.defineProperty(exports, "__esModule", {
  value: true
});
exports.render = exports.updateState = exports.initialState = exports.refreshFrequency = exports.command = void 0;

var _uebersicht = require("uebersicht");

function _extends() { _extends = Object.assign || function (target) { for (var i = 1; i < arguments.length; i++) { var source = arguments[i]; for (var key in source) { if (Object.prototype.hasOwnProperty.call(source, key)) { target[key] = source[key]; } } } return target; }; return _extends.apply(this, arguments); }

// ข้อมูลมาจาก API ของ weatherhub (8788) พร้อมพิกัดของเครื่องนี้ -- API ล่ม/ยังไม่ start
// ค่อยถอยไปอ่าน /tmp แบบเดิม (footer ขึ้น "· file") เหมือนการ์ด gold
//
// ไฟล์เดียวกันนี้เป็นหน้าเว็บ /dashboard ของ weatherhub ด้วย (common/web/build.js, 25 ก.ย.)
// โหมด WEB วาดเป็นหน้าเว็บเต็มรูป (WebPage -- ไม่ใช่การ์ดขยาย) ใช้ข้อมูล/พิกัด/จุดชุดเดียวกัน
// การ์ดบน desktop: คลิก = เปิดหน้าเว็บ / ⌥-drag = ย้ายการ์ด
// หน้าเว็บ: เล่นเฟรมย้อนหลังเป็นภาพเคลื่อนไหว (/api/frames) / ดับเบิลคลิกภาพ = เรดาร์ loop ของ กทม.
const WEB = typeof window !== 'undefined' && !!window.APPHUB_WEB;
const API = WEB ? '' : 'http://127.0.0.1:8788'; // เว็บ = origin เดียวกับ API

const DASHBOARD_URL = 'http://127.0.0.1:8788/dashboard';
const BMA_URL = 'https://weather.tmd.go.th/bma_ncLoop.php';
const S = WEB ? 1.5 : 1; // ขนาดจุดบนภาพใหญ่ของหน้าเว็บ

const API_TIMEOUT = 2000;
const FRAME_COUNT = 12; // 1 ชม. ย้อนหลัง เท่า loop GIF ของ กทม.

const FILE_CMD = 'cat /tmp/weather_meta.json'; // พิกัดเครื่อง: Übersicht ต่อ navigator.geolocation เข้ากับ CoreLocation ของแอปเอง
// (Resources/geolocation.js) ครั้งแรก macOS จะถามสิทธิ์ Location ของ Übersicht
// ตัว shim ไม่เคยเรียก onError -> ต้องมี timeout เอง / ไม่ได้พิกัด = ไม่ส่ง lat/lon
// ⚠️ native ของ Übersicht ส่งกลับเป็น { position: { coords }, address } ไม่ใช่ Position
// มาตรฐาน (strings ในตัวแอป) -- อ่าน p.coords ตรงๆ = undefined แล้วหมดเวลาทุกรอบ
// (API ใช้จุด default) และไม่วาดจุด "ฉัน" / เก็บพิกัดไว้ในหน่วยความจำเท่านั้น

const LOC_TIMEOUT = 8000; // เว็บ: Mac ไม่มี GPS หาตำแหน่งจาก Wi-Fi fix แรกของ Chrome ใช้เกิน 8 วิได้ (ผู้ใช้เจอ "หมดเวลา"
// ทั้งที่อนุญาตแล้ว 25 ก.ย.) -> ใช้ watchPosition ค้างไว้ ได้ fix เมื่อไหร่ใช้เลย + รอนานขึ้น

const LOC_TIMEOUT_WEB = 30000;
const LOC_MAX_AGE = 10 * 60 * 1000; // ขอพิกัดใหม่ทุก 10 นาที

const NOWCAST_MAX_AGE = 3600; // ผล nowcast เก่ากว่านี้ไม่โชว์ (เช็คเฉพาะ 16:xx)

let loc = null; // { lat, lon, at }

let locPending = null;
let locErr = null; // code ของ GeolocationPositionError ล่าสุด / 'timeout' / 'none'
// ---- เว็บ: watchPosition ตัวเดียวตลอดอายุหน้า ----

let watchId = null;
let waiters = [];
let onFix = null; // load() ตั้งไว้: ได้ fix ใหม่ตอนไม่มีใครรอ (มาช้า/หลัง error) ก็ยิง API ซ้ำทันที

const flush = v => {
  const w = waiters;
  waiters = [];
  w.forEach(f => f(v));
};

const locateWeb = geo => {
  if (watchId == null) {
    watchId = geo.watchPosition(p => {
      const c = p && p.coords;
      if (!c || !isFinite(c.latitude) || !isFinite(c.longitude)) return;
      const prev = loc;
      loc = {
        lat: c.latitude,
        lon: c.longitude,
        at: Date.now()
      };
      locErr = null;
      const waiting = waiters.length > 0;
      flush(loc);
      if (!waiting && onFix && (!prev || prev.lat !== loc.lat || prev.lon !== loc.lon)) onFix(loc);
    }, e => {
      locErr = e && e.code || 'error'; // ไม่อนุญาต = watch จบแล้ว ปล่อยให้รอบถัดไปเริ่มใหม่ (เผื่อผู้ใช้เพิ่งกด Allow)

      if (locErr === 1) {
        geo.clearWatch(watchId);
        watchId = null;
      }

      flush(null);
    }, {
      timeout: LOC_TIMEOUT_WEB,
      maximumAge: LOC_MAX_AGE
    });
  }

  if (loc) return Promise.resolve(loc); // watch อัปเดต loc เองอยู่แล้ว

  return Promise.race([new Promise(res => waiters.push(res)), new Promise(res => setTimeout(() => {
    if (!loc) locErr = locErr || 'timeout';
    res(null);
  }, LOC_TIMEOUT_WEB))]).then(() => loc);
};

const locate = () => {
  const geo = typeof navigator !== 'undefined' && navigator.geolocation;
  if (WEB && geo) return locateWeb(geo);
  if (loc && Date.now() - loc.at < LOC_MAX_AGE) return Promise.resolve(loc);
  if (locPending) return locPending;

  if (!geo) {
    locErr = 'none';
    return Promise.resolve(loc);
  }

  locPending = Promise.race([new Promise(res => geo.getCurrentPosition(p => {
    const c = p && p.position && p.position.coords || p && p.coords;

    if (c && isFinite(c.latitude) && isFinite(c.longitude)) {
      locErr = null;
      res({
        lat: c.latitude,
        lon: c.longitude,
        at: Date.now()
      });
    } else res(null);
  }, // เบราว์เซอร์จริงเรียกอันนี้ (shim ของ Übersicht ไม่เรียก): 1 = ไม่อนุญาต, 2 = หาไม่ได้, 3 = หมดเวลา
  e => {
    locErr = e && e.code || 'error';
    res(null);
  }, {
    timeout: LOC_TIMEOUT,
    maximumAge: LOC_MAX_AGE
  })), new Promise(res => setTimeout(() => {
    if (!loc) locErr = locErr || 'timeout';
    res(null);
  }, LOC_TIMEOUT))]).then(got => {
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

  const fetchState = l => fetchJson(API + '/api/state' + (l ? `?lat=${l.lat}&lon=${l.lon}` : '')).then(s => {
    if (!s.radar) throw new Error('no radar yet');
    dispatch({
      type: 'DATA',
      meta: s.radar,
      state: s,
      src: 'api',
      located: !!l,
      locErr
    });
  }); // ไม่รอพิกัดก่อนโหลด: ขอสิทธิ์ Location ครั้งแรก (ป้ายของเบราว์เซอร์/macOS ค้างรอคนกด)
  // เคยทำให้ทั้งการ์ดว่างเปล่าจนหมด LOC_TIMEOUT -- ยิงด้วยพิกัดที่มีอยู่ก่อน ได้พิกัดใหม่ค่อยยิงซ้ำ


  const known = loc;
  if (WEB) onFix = l => fetchState(l).catch(() => {});
  const first = fetchState(known).catch(viaFile); // เฟรมย้อนหลังสำหรับภาพเคลื่อนไหว (เฉพาะหน้าเว็บ) -- พังก็แค่เล่นไม่ได้ ภาพล่าสุดยังขึ้น

  if (WEB) {
    fetchJson(API + '/api/frames?n=' + FRAME_COUNT).then(f => dispatch({
      type: 'FRAMES',
      frames: f.frames || [],
      frameMinutes: f.frame_minutes
    })).catch(() => {});
  }

  locate().then(l => {
    // เว็บ: loc เปลี่ยนทุกครั้งที่ watch ได้ fix ใหม่ -- ยิงซ้ำเฉพาะตอนพิกัดขยับจริง (หรือเพิ่งได้ครั้งแรก)
    const moved = l && (!known || l.lat !== known.lat || l.lon !== known.lon);
    if (moved) fetchState(l).catch(() => {});else if (!l) dispatch({
      type: 'LOC_ERR',
      locErr
    });
  });
  return first;
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
  frames: [],
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
      located: !!event.located,
      locErr: event.located ? null : event.locErr || prev.locErr
    };
  }

  if (event.type === 'LOC_ERR') return { ...prev,
    locErr: event.locErr
  };
  if (event.type === 'FRAMES') return { ...prev,
    frames: event.frames,
    frameMinutes: event.frameMinutes
  };
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
  lat: 13.7733,
  lon: 100.5426,
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
  lat: 13.8062486,
  lon: 100.5352885,
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
  lat: 13.8873269,
  lon: 100.6026284,
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
  lat: 13.873365,
  lon: 100.6494155,
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
}; // เหตุผลที่ยังไม่มีจุด "เครื่องนี้" -- บอกให้รู้ว่าต้องไปแก้ที่ไหน


const locReason = err => {
  if (!WEB) return 'ยังไม่ได้พิกัด -- เช็คสิทธิ์ Location ของ Übersicht';
  if (err === 1) return 'เบราว์เซอร์ไม่อนุญาตให้หน้านี้ใช้ตำแหน่ง -- กดไอคอนข้าง URL → Location → Allow แล้ว reload';
  if (err === 2) return 'เบราว์เซอร์หาตำแหน่งไม่ได้ -- เปิด System Settings → Privacy & Security → Location Services ให้เบราว์เซอร์นี้';
  if (err === 3 || err === 'timeout') return 'ยังหาตำแหน่งไม่ได้ (รอต่อเรื่อยๆ) -- ถ้านานเกิน 1-2 นาที เช็ค System Settings → Privacy & Security → Location Services ว่าเปิดให้เบราว์เซอร์นี้แล้ว และ Wi-Fi เปิดอยู่';
  if (err === 'none') return 'เบราว์เซอร์นี้ไม่มี geolocation';
  return 'กำลังขอตำแหน่ง…';
};

const render = (props, dispatch) => WEB ? /*#__PURE__*/React.createElement(WebPage, _extends({}, props, {
  dispatch: dispatch
})) : /*#__PURE__*/React.createElement(Card, _extends({}, props, {
  dispatch: dispatch
})); // ======================= การ์ดบน desktop =======================


exports.render = render;

const Card = ({
  meta,
  state,
  src,
  located,
  locErr,
  show,
  dispatch
}) => {
  if (!meta) return null; // ภาพเก่ากว่า 20 นาที = เตือนว่าค้าง

  const stale = meta.ts && Date.now() / 1000 - meta.ts > 1200; // โหมด API: ภาพมาจาก /api/radar (ใส่ ts กัน cache) / โหมดไฟล์: base64 ในไฟล์เหมือนเดิม

  const imgSrc = src === 'api' ? `${API}/api/radar?t=${meta.ts}` : `data:${meta.mime || 'image/png'};base64,${meta.img_base64}`;
  const point = state && state.point;
  const me = point && !point.default && point.img_pct; // ปุ่มจุด "ฉัน" เปิดอยู่แต่วาดไม่ได้ -> บอกเหตุผลใน tooltip

  const meNote = !located ? locReason(locErr) : !me ? 'อยู่นอกวงเรดาร์' : null;
  const rain = rainLine(state && state.nowcast);
  const container = {
    // 344px = ความกว้าง medium widget ของ macOS (วัดจากหน้าจอจริง)
    position: 'fixed',
    top: savedPos().top || '390px',
    left: savedPos().left || '35px',
    width: '344px',
    padding: '16px',
    borderRadius: macos.radius,
    color: macos.label,
    fontFamily: macos.font,
    background: macos.material,
    border: macos.border,
    boxShadow: macos.shadow,
    cursor: 'pointer',
    boxSizing: 'border-box',
    userSelect: 'none'
  }; // คลิกเดียว = เปิดหน้าเว็บ (ใหญ่กว่า มีภาพเคลื่อนไหว) -- ⌥ ค้างไว้คือการลากย้ายการ์ด

  const handleClick = e => {
    if (e.altKey) return;
    e.preventDefault();
    (0, _uebersicht.run)(`open '${DASHBOARD_URL}'`);
  };

  return /*#__PURE__*/React.createElement("div", {
    style: container,
    onClick: handleClick,
    onMouseDown: altDrag,
    title: "\u0E04\u0E25\u0E34\u0E01 \u2192 \u0E40\u0E1B\u0E34\u0E14\u0E2B\u0E19\u0E49\u0E32\u0E40\u0E27\u0E47\u0E1A \xB7 \u2325-drag \u0E22\u0E49\u0E32\u0E22\u0E01\u0E32\u0E23\u0E4C\u0E14"
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
      gap: '8px'
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
      fontSize: '11px',
      color: stale ? macos.orange : macos.tertiary,
      fontWeight: stale ? '700' : '400'
    }
  }, stale ? '● ' : '', meta.last_update, src === 'file' ? ' · file' : '')), /*#__PURE__*/React.createElement("div", {
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
      fontSize: '12px',
      fontWeight: '600',
      color: macos.orange
    }
  }, "\uD83C\uDF27 ", rain));
}; // ======================= หน้าเว็บ =======================
// หน้าเว็บจริง ไม่ใช่การ์ดขยาย: แถบหัว / ภาพเรดาร์ใหญ่ + ตัวเล่นเฟรม / แผงข้าง (สถานที่ + ฝน)
// จอแคบ (มือถือ) แผงข้างตกลงไปอยู่ใต้ภาพเอง (flex-wrap)


const hhmm = ts => {
  const d = new Date(ts * 1000);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
};

const kmBetween = (a, b) => {
  // haversine พอสำหรับระยะในเมือง
  const R = 6371,
        rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad,
        dLon = (b.lon - a.lon) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
};

const PLAY_MS = 500; // ต่อเฟรม

const HOLD_LAST = 4; // ค้างเฟรมล่าสุดไว้กี่จังหวะก่อนวนใหม่

const Panel = ({
  title,
  children
}) => /*#__PURE__*/React.createElement("div", {
  style: {
    background: macos.material,
    border: macos.border,
    boxShadow: macos.shadow,
    borderRadius: '16px',
    padding: '16px 18px',
    marginBottom: '16px'
  }
}, /*#__PURE__*/React.createElement("div", {
  style: {
    fontSize: '11px',
    fontWeight: '700',
    letterSpacing: '0.6px',
    textTransform: 'uppercase',
    color: macos.tertiary,
    marginBottom: '10px'
  }
}, title), children);

const Switch = ({
  on,
  color,
  onClick
}) => /*#__PURE__*/React.createElement("span", {
  onClick: onClick,
  style: {
    width: '34px',
    height: '20px',
    borderRadius: '10px',
    flex: '0 0 auto',
    cursor: 'pointer',
    position: 'relative',
    background: on ? color : wash(0.18),
    transition: 'background .15s'
  }
}, /*#__PURE__*/React.createElement("span", {
  style: {
    position: 'absolute',
    top: '2px',
    left: on ? '16px' : '2px',
    width: '16px',
    height: '16px',
    borderRadius: '50%',
    background: '#fff',
    boxShadow: '0 1px 2px rgba(0,0,0,0.3)',
    transition: 'left .15s'
  }
}));

const PlaceRow = ({
  m,
  on,
  sub,
  note,
  dispatch
}) => /*#__PURE__*/React.createElement("div", {
  style: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    padding: '8px 0',
    borderTop: `0.5px solid ${wash(0.1)}`
  }
}, /*#__PURE__*/React.createElement("span", {
  style: {
    width: '28px',
    height: '28px',
    borderRadius: '8px',
    flex: '0 0 auto',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: wash(0.08)
  }
}, ICONS[m.icon](btnColor(m))), /*#__PURE__*/React.createElement("span", {
  style: {
    flex: '1 1 auto',
    minWidth: 0
  }
}, /*#__PURE__*/React.createElement("div", {
  style: {
    fontSize: '14px',
    fontWeight: '600'
  }
}, m.label), (sub || note) && /*#__PURE__*/React.createElement("div", {
  style: {
    fontSize: '12px',
    color: note ? macos.orange : macos.tertiary,
    marginTop: '2px'
  }
}, note || sub)), /*#__PURE__*/React.createElement(Switch, {
  on: on,
  color: btnColor(m),
  onClick: () => dispatch({
    type: 'TOGGLE',
    id: m.id
  })
}));

const PlayButton = ({
  playing,
  onClick
}) => /*#__PURE__*/React.createElement("button", {
  onClick: onClick,
  title: playing ? 'หยุด' : 'เล่น',
  style: {
    width: '36px',
    height: '36px',
    borderRadius: '50%',
    border: 'none',
    cursor: 'pointer',
    flex: '0 0 auto',
    background: macos.pillOn,
    color: macos.label,
    fontSize: '14px',
    lineHeight: '36px',
    padding: 0
  }
}, playing ? '❚❚' : '▶');

const WebPage = ({
  meta,
  state,
  src,
  located,
  locErr,
  show,
  theme,
  frames,
  dispatch
}) => {
  const [idx, setIdx] = React.useState(null); // null = ตามเฟรมล่าสุด

  const [playing, setPlaying] = React.useState(true);
  const holdRef = React.useRef(0);
  const list = frames || [];
  const canPlay = list.length > 1; // เล่นวน: เดินทีละเฟรม ถึงเฟรมล่าสุดค้างไว้ HOLD_LAST จังหวะแล้วเริ่มใหม่

  React.useEffect(() => {
    if (!playing || !canPlay) return undefined;
    const t = setInterval(() => {
      setIdx(i => {
        const cur = i == null ? list.length - 1 : Math.min(i, list.length - 1);

        if (cur >= list.length - 1) {
          if (holdRef.current < HOLD_LAST) {
            holdRef.current += 1;
            return cur;
          }

          holdRef.current = 0;
          return 0;
        }

        return cur + 1;
      });
    }, PLAY_MS);
    return () => clearInterval(t);
  }, [playing, canPlay, list.length]); // โหลดเฟรมล่วงหน้า ไม่งั้นรอบแรกภาพกระพริบ

  React.useEffect(() => {
    list.forEach(f => {
      const im = new Image();
      im.src = API + f.image;
    });
  }, [list]);

  if (!meta) {
    return /*#__PURE__*/React.createElement("div", {
      style: {
        padding: '40px',
        color: macos.tertiary,
        fontFamily: macos.font,
        fontSize: '14px'
      }
    }, src === 'offline' ? 'เรียก API ของ weatherhub ไม่ได้ -- daemon รันอยู่ไหม?' : 'กำลังโหลดเรดาร์…');
  }

  const cur = canPlay ? idx == null ? list.length - 1 : Math.min(idx, list.length - 1) : null;
  const frame = cur != null ? list[cur] : null;
  const imgSrc = frame ? API + frame.image : `${API}/api/radar?t=${meta.ts}`;
  const frameTs = frame ? frame.ts : meta.ts;
  const latestTs = list.length ? list[list.length - 1].ts : meta.ts;
  const behind = Math.round((latestTs - frameTs) / 60);
  const stale = meta.ts && Date.now() / 1000 - meta.ts > 1200;
  const point = state && state.point;
  const me = point && !point.default && point.img_pct;
  const meNote = !located ? locReason(locErr) : !me ? 'อยู่นอกวงเรดาร์' : null;
  const myLL = located && point && !point.default ? {
    lat: point.lat,
    lon: point.lon
  } : null;
  const rain = rainLine(state && state.nowcast);
  const nc = state && state.nowcast;
  const page = {
    maxWidth: '1320px',
    margin: '0 auto',
    padding: '24px 20px 40px',
    boxSizing: 'border-box',
    color: macos.label,
    fontFamily: macos.font
  };
  const link = {
    fontSize: '13px',
    fontWeight: '600',
    color: macos.label,
    textDecoration: 'none',
    padding: '6px 12px',
    borderRadius: '999px',
    background: wash(0.12)
  };
  return /*#__PURE__*/React.createElement("div", {
    style: page
  }, /*#__PURE__*/React.createElement("header", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'flex-end',
      flexWrap: 'wrap',
      gap: '12px',
      marginBottom: '18px'
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '26px',
      fontWeight: '700',
      letterSpacing: '-0.3px'
    }
  }, "\u0E40\u0E23\u0E14\u0E32\u0E23\u0E4C\u0E1D\u0E19 \u0E01\u0E23\u0E38\u0E07\u0E40\u0E17\u0E1E\u0E2F"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '13px',
      color: stale || src === 'offline' ? macos.orange : macos.tertiary,
      marginTop: '4px'
    }
  }, meta.source, " \xB7 \u0E2D\u0E31\u0E1B\u0E40\u0E14\u0E15 ", meta.last_update, " \xB7 via ", meta.via || '?', stale ? ' · ภาพค้างเกิน 20 นาที' : '', src === 'offline' ? ' · offline' : '')), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: '8px'
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
  }), /*#__PURE__*/React.createElement("a", {
    href: BMA_URL,
    target: "_blank",
    rel: "noopener",
    style: link
  }, "\u0E40\u0E27\u0E47\u0E1A \u0E01\u0E17\u0E21. \u2197"))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexWrap: 'wrap',
      gap: '20px',
      alignItems: 'flex-start'
    }
  }, /*#__PURE__*/React.createElement("section", {
    style: {
      flex: '1 1 640px',
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    onDoubleClick: () => window.open(BMA_URL, '_blank'),
    title: "\u0E14\u0E31\u0E1A\u0E40\u0E1A\u0E34\u0E25\u0E04\u0E25\u0E34\u0E01 \u2192 \u0E40\u0E23\u0E14\u0E32\u0E23\u0E4C loop \u0E02\u0E2D\u0E07 \u0E01\u0E17\u0E21.",
    style: {
      position: 'relative',
      borderRadius: '16px',
      overflow: 'hidden',
      background: wash(0.08),
      boxShadow: macos.shadow,
      lineHeight: 0
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
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'absolute',
      top: '12px',
      right: '12px',
      lineHeight: 1.2,
      padding: '5px 10px',
      borderRadius: '999px',
      fontSize: '13px',
      fontWeight: '700',
      background: 'rgba(20,22,28,0.72)',
      color: '#fff'
    }
  }, hhmm(frameTs), behind > 0 ? ` · −${behind} นาที` : ' · ล่าสุด')), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
      marginTop: '12px'
    }
  }, /*#__PURE__*/React.createElement(PlayButton, {
    playing: playing && canPlay,
    onClick: () => {
      if (canPlay) setPlaying(!playing);
    }
  }), /*#__PURE__*/React.createElement("input", {
    type: "range",
    min: 0,
    max: Math.max(0, list.length - 1),
    value: cur == null ? 0 : cur,
    disabled: !canPlay,
    onChange: e => {
      setPlaying(false);
      setIdx(Number(e.target.value));
    },
    style: {
      flex: '1 1 auto',
      accentColor: macos.blue
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: '12px',
      color: macos.tertiary,
      whiteSpace: 'nowrap'
    }
  }, canPlay ? `${list.length} เฟรม · ${hhmm(list[0].ts)}–${hhmm(latestTs)}` : 'กำลังสะสมเฟรม (ทุก 5 นาที)'))), /*#__PURE__*/React.createElement("aside", {
    style: {
      flex: '0 1 340px',
      minWidth: '280px'
    }
  }, /*#__PURE__*/React.createElement(Panel, {
    title: "\u0E1D\u0E19\u0E2B\u0E19\u0E31\u0E01 (nowcast)"
  }, rain ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '15px',
      fontWeight: '600',
      color: macos.orange
    }
  }, "\uD83C\uDF27 ", rain) : /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '14px',
      color: nc && nc.age != null && nc.age <= NOWCAST_MAX_AGE ? macos.label : macos.secondary
    }
  }, !nc ? 'ยังไม่มีผลการเช็ค' : nc.age != null && nc.age > NOWCAST_MAX_AGE ? 'ผลล่าสุดเก่าเกิน 1 ชม. -- ไม่ใช้ตัดสิน' : 'ไม่มีฝนหนักเข้าใกล้ตำแหน่งนี้'), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '12px',
      color: macos.tertiary,
      marginTop: '6px'
    }
  }, nc && nc.ts ? `เช็คล่าสุด ${hhmm(nc.ts)} · รัศมี ${nc.radius_km} กม. · มองล่วงหน้า ${nc.lookahead_min} นาที` : 'ยังไม่มีผล -- ระบบเช็คเฉพาะ 16:00–16:45')), /*#__PURE__*/React.createElement(Panel, {
    title: "\u0E2A\u0E16\u0E32\u0E19\u0E17\u0E35\u0E48\u0E1A\u0E19\u0E41\u0E1C\u0E19\u0E17\u0E35\u0E48"
  }, MARKERS.map(m => /*#__PURE__*/React.createElement(PlaceRow, {
    key: m.id,
    m: m,
    on: show[m.id],
    dispatch: dispatch,
    sub: myLL ? `ห่างจากเครื่องนี้ ${kmBetween(myLL, m).toFixed(1)} กม.` : null
  })), /*#__PURE__*/React.createElement(PlaceRow, {
    m: ME,
    on: show.me,
    dispatch: dispatch,
    note: show.me ? meNote : null,
    sub: point && !point.default ? `ห่างสถานีเรดาร์ ${point.distance_km} กม. (ปัดกริด ~5 กม.)` : null
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '12px',
      color: macos.tertiary,
      lineHeight: 1.6,
      padding: '0 4px'
    }
  }, "\u0E20\u0E32\u0E1E\u0E40\u0E04\u0E25\u0E37\u0E48\u0E2D\u0E19\u0E44\u0E2B\u0E27 = \u0E20\u0E32\u0E1E\u0E19\u0E34\u0E48\u0E07\u0E17\u0E35\u0E48\u0E14\u0E36\u0E07\u0E17\u0E38\u0E01 5 \u0E19\u0E32\u0E17\u0E35\u0E22\u0E49\u0E2D\u0E19\u0E2B\u0E25\u0E31\u0E07 1 \u0E0A\u0E21. (\u0E44\u0E21\u0E48\u0E22\u0E34\u0E07\u0E40\u0E27\u0E47\u0E1A \u0E01\u0E17\u0E21. \u0E40\u0E1E\u0E34\u0E48\u0E21) \xB7 \u0E14\u0E31\u0E1A\u0E40\u0E1A\u0E34\u0E25\u0E04\u0E25\u0E34\u0E01\u0E17\u0E35\u0E48\u0E20\u0E32\u0E1E = \u0E40\u0E1B\u0E34\u0E14 loop \u0E02\u0E2D\u0E07 \u0E01\u0E17\u0E21."))));
};
};
