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
// จุด custom บนหน้าเว็บ: พิมพ์ lat,lon (หรือวางลิงก์ Google Maps แบบเต็ม) -- **ไม่เก็บที่ไหนเลย**
// (ผู้ใช้ขอ 25 ก.ย.: กรอกใหม่ทุกรอบ) อยู่ในหน่วยความจำของหน้านี้ reload = หาย

let customLL = null;
let refreshForecast = null; // load() ตั้งไว้ ให้ปุ่ม "แสดง" ยิงผลทายของจุดใหม่ได้ทันที

const flush = v => {
  const w = waiters;
  waiters = [];
  w.forEach(f => f(v));
}; // สถานะไว้โชว์บนหน้าเว็บ ให้รู้ว่าติดตรงไหน (ผู้ใช้เจอ "ไม่ขึ้น" ทั้งที่ Chrome อนุญาตแล้ว 25 ก.ย.)


const geoDiag = {
  startedAt: null,
  fixAt: null,
  accuracy: null,
  posAge: null,
  errCode: null,
  errAt: null,
  restarts: 0
};
const WATCH_RESTART_MS = 60000; // ยังไม่ได้ fix นานเท่านี้ -> เริ่ม watch ใหม่
// ⚠️ ต้อง enableHighAccuracy: true -- Chrome บน Mac เครื่องนี้ โหมดปกติ (network provider) ไม่ตอบเลย
// หมดเวลาทุกครั้งทั้งที่สิทธิ์ granted ส่วนโหมดแม่นยำสูงวิ่งผ่าน CoreLocation ตอบทันที ±235 ม.
// (ทดสอบใน Chrome ของผู้ใช้ 25 ก.ย. -- Google Maps ใช้โหมดนี้เลยได้ปกติ)

const GEO_OPTS = {
  enableHighAccuracy: true,
  maximumAge: LOC_MAX_AGE
};

const onPos = p => {
  const c = p && p.coords;
  if (!c || !isFinite(c.latitude) || !isFinite(c.longitude)) return;
  const prev = loc;
  loc = {
    lat: c.latitude,
    lon: c.longitude,
    at: Date.now()
  };
  locErr = null;
  geoDiag.fixAt = Date.now();
  geoDiag.accuracy = isFinite(c.accuracy) ? Math.round(c.accuracy) : null;
  geoDiag.posAge = isFinite(p.timestamp) ? Math.round((Date.now() - p.timestamp) / 1000) : null;
  const waiting = waiters.length > 0;
  flush(loc);
  if (!waiting && onFix && (!prev || prev.lat !== loc.lat || prev.lon !== loc.lon)) onFix(loc);
};

const startWatch = geo => {
  // ไม่ส่ง timeout ให้ watch: Chrome บางครั้งยิง TIMEOUT แล้วไม่ส่งพิกัดต่อ (watch ตายเงียบ)
  // -- จับเวลาเองใน locateWeb แทน และถ้านานเกิน WATCH_RESTART_MS ค่อยเริ่มใหม่
  geoDiag.startedAt = Date.now();
  watchId = geo.watchPosition(onPos, e => {
    locErr = e && e.code || 'error';
    geoDiag.errCode = locErr;
    geoDiag.errAt = Date.now(); // ไม่อนุญาต = watch จบแล้ว ปล่อยให้รอบถัดไปเริ่มใหม่ (เผื่อผู้ใช้เพิ่งกด Allow)

    if (locErr === 1) {
      geo.clearWatch(watchId);
      watchId = null;
    }

    flush(null);
  }, GEO_OPTS); // ขอพิกัดที่เบราว์เซอร์จำไว้แล้ว (ถ้ามี) มาใช้ก่อน ระหว่างรอ fix ใหม่

  try {
    geo.getCurrentPosition(onPos, () => {}, { ...GEO_OPTS,
      maximumAge: Infinity,
      timeout: 5000
    });
  } catch (e) {
    /* ไม่มีก็รอ watch */
  }
};

const locateWeb = geo => {
  if (watchId == null) startWatch(geo);else if (!loc && Date.now() - geoDiag.startedAt > WATCH_RESTART_MS) {
    geo.clearWatch(watchId);
    geoDiag.restarts += 1;
    startWatch(geo);
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
  // nowcast รายจุด (เฉพาะหน้าเว็บ): 4 สถานที่ + ตำแหน่งเครื่องนี้ + จุด custom -- ผลเก็บตาม id


  const fetchForecast = () => {
    if (!WEB) return;
    const items = MARKERS.map(m => [m.id, m.lat, m.lon]).concat(loc ? [['me', loc.lat, loc.lon]] : []).concat(customLL ? [['custom', customLL.lat, customLL.lon]] : []);
    const pts = items.map(([, la, lo]) => `${la},${lo}`); // ส่งตามที่กรอกทุกหลัก ไม่ปัด (ผู้ใช้ขอ 25 ก.ย.)

    fetchJson(API + '/api/forecast?pts=' + encodeURIComponent(pts.join(';'))).then(f => {
      const byId = {};
      items.forEach(([id], i) => {
        byId[id] = f.points[i];
      });
      dispatch({
        type: 'FORECAST',
        basis: f.basis,
        byId
      });
    }).catch(() => {}); // ความแม่นย้อนหลัง (API cache ตาม mtime ของ history -- ถามทุกนาทีได้)

    fetchJson(API + '/api/verify?days=7').then(v => dispatch({
      type: 'VERIFY',
      verify: v
    })).catch(() => {});
  };

  refreshForecast = fetchForecast;
  const known = loc;
  if (WEB) onFix = l => {
    fetchState(l).catch(() => {});
    fetchForecast();
  };
  fetchForecast();
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
    const moved = l && (!known || l.lat !== known.lat || l.lon !== known.lon); // ต้องยิงทั้งสองตัว: เคยยิงแค่ /api/state -> จุดเขียวขึ้น แต่แถว "ตำแหน่งเครื่องนี้" ค้าง "รอพิกัด…"

    if (moved) {
      fetchState(l).catch(() => {});
      fetchForecast();
    } else if (!l) dispatch({
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
  me: true,
  custom: true
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
  if (event.type === 'FORECAST') return { ...prev,
    basis: event.basis,
    fcById: event.byId
  };
  if (event.type === 'VERIFY') return { ...prev,
    verify: event.verify
  };
  if (event.type === 'CUSTOM') return { ...prev,
    custom: event.ll,
    fcById: { ...(prev.fcById || {}),
      custom: null
    }
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
  label: 'FORTH',
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
  label: 'SCG',
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
  label: "Loon's Home",
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
  label: "Pum's Home",
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
  label: 'My Location',
  color: '#30d158',
  ink: '#1b8a3a'
};
const CUSTOM = {
  id: 'custom',
  icon: 'pin',
  label: 'จุดที่กรอก',
  color: '#ff5fd2',
  ink: '#c2189b'
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
  pin: c => /*#__PURE__*/React.createElement("svg", {
    width: 13 * S,
    height: 13 * S,
    viewBox: "0 0 16 16",
    fill: "none",
    stroke: c,
    strokeWidth: "1.5",
    strokeLinejoin: "round"
  }, /*#__PURE__*/React.createElement("path", {
    d: "M8 14.5s4.75-4.2 4.75-8A4.75 4.75 0 0 0 3.25 6.5c0 3.8 4.75 8 4.75 8z"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: "8",
    cy: "6.5",
    r: "1.6",
    fill: c,
    stroke: "none"
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

const geoDiagText = () => {
  const ago = t => t ? `${Math.round((Date.now() - t) / 1000)} วิที่แล้ว` : '-';

  const parts = [`ขอพิกัดมา ${geoDiag.startedAt ? Math.round((Date.now() - geoDiag.startedAt) / 1000) : 0} วิ`];
  parts.push(geoDiag.fixAt ? `fix ล่าสุด ${ago(geoDiag.fixAt)}${geoDiag.accuracy != null ? ` ±${geoDiag.accuracy} ม.` : ''}${geoDiag.posAge != null ? ` (พิกัดอายุ ${Math.round(geoDiag.posAge / 60)} นาที)` : ''}` : 'ยังไม่เคยได้ fix');
  if (geoDiag.errCode) parts.push(`error ${geoDiag.errCode} (${ago(geoDiag.errAt)})`);
  if (geoDiag.restarts) parts.push(`เริ่มใหม่ ${geoDiag.restarts} ครั้ง`);
  return parts.join(' · ');
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
  }, /*#__PURE__*/React.createElement(ToggleButton, {
    m: ME,
    on: show.me,
    dispatch: dispatch,
    note: show.me ? meNote : null
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      width: '1px',
      height: '14px',
      background: wash(0.18),
      margin: '0 2px'
    }
  }), MARKERS.map(m => /*#__PURE__*/React.createElement(ToggleButton, {
    m: m,
    on: show[m.id],
    dispatch: dispatch,
    key: m.id
  }))), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: '11px',
      color: stale ? macos.orange : macos.tertiary,
      fontWeight: stale ? '700' : '400'
    }
  }, stale ? '● ' : '', meta.observed_at ? hhmm(meta.observed_at) : meta.last_update, src === 'file' ? ' · file' : '')), /*#__PURE__*/React.createElement("div", {
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
}, playing ? '❚❚' : '▶'); // ---- nowcast รายจุด ----


const LEVEL_COLOR = ['transparent', '#30d158', '#ff9f0a']; // ไม่มี / ฝน / ฝนหนัก

const fcText = fc => {
  if (!fc) return {
    main: 'นอกวงเรดาร์',
    sub: null
  };
  if (fc.reason === 'stale') return {
    main: 'no live data',
    sub: `ภาพเรดาร์ล่าสุดเก่า ${fc.age_min} นาที -- ไม่คาดการณ์`
  };
  const nowTxt = fc.level_now === 2 ? 'ฝนหนักตกอยู่' : fc.level_now === 1 ? 'ฝนตกอยู่' : 'ไม่มีฝน';
  if (!fc.predictable) return {
    main: nowTxt,
    sub: 'ยังคาดเริ่ม/หยุดไม่ได้ (รอเฟรมย้อนหลังพอหาทิศทางฝน)'
  }; // แนวโน้มของกลุ่มฝนเหนือจุดนี้ (สัดส่วนฝนในรัศมี 10 กม. เปลี่ยนต่อ 10 นาที)

  const tr = fc.trend && fc.trend.per_10min;
  const trendTxt = tr == null ? '' : tr <= -0.03 ? ' · ฝนกำลังเบาลง' : tr >= 0.03 ? ' · ฝนกำลังแรงขึ้น' : '';

  if (fc.raining_now) {
    return {
      main: nowTxt,
      sub: (fc.stop_at ? `หยุด ~${hhmm(fc.stop_at)} (อีก ${fc.stop_min} นาที)` : 'ยังไม่หยุดใน 1 ชม.') + trendTxt
    };
  }

  if (fc.start_at) {
    const stopTxt = fc.stop_at ? ` · หยุด ~${hhmm(fc.stop_at)}` : '';
    const heavyTxt = fc.heavy_at ? ` · หนัก ~${hhmm(fc.heavy_at)}` : '';
    return {
      main: `เริ่ม ~${hhmm(fc.start_at)}`,
      sub: `อีก ${fc.start_min} นาที${heavyTxt}${stopTxt}`
    };
  }

  return {
    main: 'ไม่มีฝนใน 1 ชม.',
    sub: null
  };
}; // แถบ 13 ช่อง ช่องละ 5 นาที เริ่มที่ t0 (เวลาที่ API คิด ≈ ตอนนี้) + เวลากำกับทุก 15 นาที


const Timeline = ({
  steps,
  t0
}) => /*#__PURE__*/React.createElement("div", {
  style: {
    marginTop: '6px'
  }
}, /*#__PURE__*/React.createElement("div", {
  style: {
    display: 'flex',
    gap: '2px'
  }
}, steps.map((lv, i) => /*#__PURE__*/React.createElement("span", {
  key: i,
  title: `${hhmm(t0 + i * 300)} · ${['ไม่มีฝน', 'ฝน', 'ฝนหนัก'][lv]}`,
  style: {
    flex: '1 1 0',
    height: '6px',
    borderRadius: '2px',
    background: lv ? LEVEL_COLOR[lv] : wash(0.1)
  }
}))), /*#__PURE__*/React.createElement("div", {
  style: {
    position: 'relative',
    height: '13px',
    marginTop: '2px',
    fontSize: '10px',
    color: macos.tertiary
  }
}, [0, 3, 6, 9, 12].map(i => /*#__PURE__*/React.createElement("span", {
  key: i,
  style: {
    position: 'absolute',
    top: 0,
    left: `${(i + 0.5) / steps.length * 100}%`,
    transform: i === 0 ? 'translateX(-25%)' : i === 12 ? 'translateX(-75%)' : 'translateX(-50%)',
    whiteSpace: 'nowrap'
  }
}, hhmm(t0 + i * 300))))); // แถวเดียวรวมทุกอย่างของสถานที่นั้น: ชื่อ + ระยะ / สถานะฝน / สวิตช์จุดบนแผนที่ / timeline
// สวิตช์เปิด-ปิดแค่ "จุดบนภาพเรดาร์" -- ผลทายยังแสดงเสมอ


const ForecastRow = ({
  m,
  fc,
  on,
  dispatch,
  dist,
  note,
  pending
}) => {
  const t = pending ? {
    main: 'รอผล…',
    sub: null
  } : note ? {
    main: '—',
    sub: null
  } : fcText(fc);
  const wet = fc && fc.raining_now;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '10px 0',
      borderTop: `0.5px solid ${wash(0.1)}`
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: '10px'
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
      background: wash(0.08),
      opacity: on ? 1 : 0.45
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
  }, m.label), dist && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '11px',
      color: macos.tertiary,
      marginTop: '1px'
    }
  }, dist)), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: '14px',
      fontWeight: '700',
      textAlign: 'right',
      color: wet || fc && fc.start_at ? macos.orange : macos.secondary
    }
  }, t.main), /*#__PURE__*/React.createElement("span", {
    title: `${on ? 'ซ่อน' : 'แสดง'}จุดนี้บนแผนที่`,
    style: {
      display: 'flex'
    }
  }, /*#__PURE__*/React.createElement(Switch, {
    on: on,
    color: btnColor(m),
    onClick: () => dispatch({
      type: 'TOGGLE',
      id: m.id
    })
  }))), (t.sub || note) && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '12px',
      color: note ? macos.orange : macos.tertiary,
      marginTop: '4px',
      textAlign: note ? 'left' : 'right'
    }
  }, note || t.sub), fc && fc.predictable && !note && /*#__PURE__*/React.createElement(Timeline, {
    steps: fc.timeline,
    t0: fc.t0
  }));
}; // ---- จุด custom: อ่านพิกัดจากข้อความที่พิมพ์/วาง (ในเบราว์เซอร์ล้วน ไม่ยิงไปไหน) ----
// รับ "13.75, 100.50" / "13.75 100.50" / องศา-ลิปดา-ฟิลิปดาแบบที่ Google Maps โชว์
// (13°36'43.3"N 100°32'54.0"E, ลิปดาทศนิยมก็ได้) / ลิงก์ Google Maps แบบเต็ม (!3d..!4d.. = หมุด, @lat,lon = กลางจอ,
// ?q= / query= / ll=) -- ลิงก์สั้น maps.app.goo.gl ต้องให้ server ไปถาม Google ซึ่งผู้ใช้เลือกไม่ทำ


const parseLatLon = text => {
  const t = decodeURIComponent((text || '').trim());
  if (!t) return {
    error: null
  };
  if (/goo\.gl\//i.test(t)) return {
    error: 'ลิงก์สั้นอ่านพิกัดไม่ได้ -- เปิดลิงก์แล้วคัดลอก URL เต็ม หรือพิมพ์ lat, lon'
  };

  const pick = (a, b) => {
    const la = parseFloat(a),
          lo = parseFloat(b);
    if (!isFinite(la) || !isFinite(lo) || Math.abs(la) > 90 || Math.abs(lo) > 180) return null;
    return {
      lat: la,
      lon: lo
    };
  };

  const pats = [/!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)/, /[?&](?:q|query|ll|center|destination)=(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)/, /@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/, /^\(?\s*(-?\d+(?:\.\d+)?)\s*[,\s]\s*(-?\d+(?:\.\d+)?)\s*\)?$/];

  for (const re of pats) {
    const m = t.match(re);

    if (m) {
      const ll = pick(m[1], m[2]);
      if (ll) return {
        ll
      };
    }
  } // DMS: ต้องมี ° ถึงจะนับ -- ซีกโลก N/S/E/W อยู่หน้าหรือหลังเลขก็ได้ ถ้ามีจะจับคู่ lat/lon ตามตัวอักษร


  const DMS = /([NSEW])?\s*(-?\d+(?:\.\d+)?)\s*°\s*(?:(\d+(?:\.\d+)?)\s*['′’]\s*)?(?:(\d+(?:\.\d+)?)\s*(?:"|″|”|'')\s*)?([NSEW])?/gi;
  const parts = [];
  let m;

  while ((m = DMS.exec(t)) && parts.length < 3) {
    const deg = parseFloat(m[2]),
          min = m[3] ? parseFloat(m[3]) : 0,
          sec = m[4] ? parseFloat(m[4]) : 0;
    if (min >= 60 || sec >= 60) return {
      error: 'ลิปดา/ฟิลิปดาต้องน้อยกว่า 60'
    };
    const hemi = (m[5] || m[1] || '').toUpperCase();
    let v = Math.abs(deg) + min / 60 + sec / 3600;
    if (deg < 0 || hemi === 'S' || hemi === 'W') v = -v;
    parts.push({
      v,
      hemi
    });
  }

  if (parts.length === 2) {
    let [a, b] = parts;
    if ('EW'.includes(a.hemi) && a.hemi && 'NS'.includes(b.hemi) && b.hemi) [a, b] = [b, a]; // เขียนลองจิจูดก่อน

    const ll = pick(a.v, b.v);
    if (ll) return {
      ll
    };
  }

  return {
    error: 'อ่านพิกัดไม่ออก -- พิมพ์แบบ 13.7563, 100.5018'
  };
};

const CustomInput = ({
  custom,
  dispatch
}) => {
  const [text, setText] = React.useState('');
  const [error, setError] = React.useState(null);

  const submit = e => {
    e.preventDefault();
    const r = parseLatLon(text);

    if (!r.ll) {
      setError(r.error);
      return;
    }

    setError(null);
    customLL = r.ll;
    dispatch({
      type: 'CUSTOM',
      ll: r.ll
    });
    if (refreshForecast) refreshForecast();
  };

  const clear = () => {
    customLL = null;
    setText('');
    setError(null);
    dispatch({
      type: 'CUSTOM',
      ll: null
    });
  };

  const field = {
    flex: '1 1 auto',
    minWidth: 0,
    fontSize: '13px',
    padding: '7px 10px',
    borderRadius: '8px',
    border: `1px solid ${wash(0.2)}`,
    background: wash(0.06),
    color: macos.label,
    outline: 'none',
    fontFamily: macos.font
  };
  const btn = {
    fontSize: '13px',
    fontWeight: '600',
    padding: '7px 12px',
    borderRadius: '8px',
    border: 'none',
    cursor: 'pointer',
    background: macos.pillOn,
    color: macos.label,
    flex: '0 0 auto'
  };
  return /*#__PURE__*/React.createElement("form", {
    onSubmit: submit,
    style: {
      padding: '10px 0 2px',
      borderTop: `0.5px solid ${wash(0.1)}`
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: '6px'
    }
  }, /*#__PURE__*/React.createElement("input", {
    value: text,
    onChange: e => setText(e.target.value),
    style: field,
    placeholder: '13.7563, 100.5018 หรือ 13°45\'22.7"N 100°30\'06.5"E'
  }), /*#__PURE__*/React.createElement("button", {
    type: "submit",
    style: btn
  }, "\u0E41\u0E2A\u0E14\u0E07"), custom && /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: clear,
    style: { ...btn,
      background: wash(0.12)
    },
    title: "\u0E25\u0E1A\u0E08\u0E38\u0E14\u0E19\u0E35\u0E49"
  }, "\u2715")), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '11px',
      color: error ? macos.orange : macos.tertiary,
      marginTop: '4px'
    }
  }, error || 'ทศนิยม / องศา-ลิปดา-ฟิลิปดา / ลิงก์ Google Maps แบบเต็ม · ไม่บันทึก reload แล้วหาย'));
}; // ---- ความแม่นย้อนหลัง (verify.py) ----


const MODEL_LABEL = {
  trend: 'ตัวที่ใช้อยู่',
  advect: 'ตามทิศอย่างเดียว',
  persist: 'เหมือนตอนนี้ (ฐาน)'
};
const BUCKET_LABEL = {
  '0-10': '≤10 นาที',
  '15-30': '15–30',
  '35-60': '35–60'
};

const VerifyPanel = ({
  verify
}) => {
  const models = verify && verify.models || {};
  const order = ['trend', 'advect', 'persist'].filter(k => models[k]);
  const buckets = Object.keys(BUCKET_LABEL);
  const cell = {
    padding: '4px 6px',
    textAlign: 'right',
    fontSize: '12px',
    whiteSpace: 'nowrap'
  };
  return /*#__PURE__*/React.createElement(Panel, {
    title: `ความแม่นย้อนหลัง ${verify ? verify.days : 7} วัน`
  }, !order.length ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '13px',
      color: macos.secondary
    }
  }, "\u0E22\u0E31\u0E07\u0E44\u0E21\u0E48\u0E21\u0E35\u0E1C\u0E25\u0E17\u0E35\u0E48\u0E04\u0E23\u0E1A\u0E40\u0E27\u0E25\u0E32\u0E43\u0E2B\u0E49\u0E40\u0E17\u0E35\u0E22\u0E1A") : /*#__PURE__*/React.createElement("table", {
    style: {
      width: '100%',
      borderCollapse: 'collapse'
    }
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", {
    style: {
      color: macos.tertiary
    }
  }, /*#__PURE__*/React.createElement("th", {
    style: { ...cell,
      textAlign: 'left',
      fontWeight: '600'
    }
  }, "\u0E17\u0E32\u0E22\u0E25\u0E48\u0E27\u0E07\u0E2B\u0E19\u0E49\u0E32"), buckets.map(b => /*#__PURE__*/React.createElement("th", {
    key: b,
    style: { ...cell,
      fontWeight: '600'
    }
  }, BUCKET_LABEL[b])))), /*#__PURE__*/React.createElement("tbody", null, order.map(k => /*#__PURE__*/React.createElement("tr", {
    key: k,
    style: {
      borderTop: `0.5px solid ${wash(0.1)}`
    }
  }, /*#__PURE__*/React.createElement("td", {
    style: { ...cell,
      textAlign: 'left',
      fontWeight: k === 'trend' ? '700' : '400'
    }
  }, MODEL_LABEL[k]), buckets.map(b => {
    const x = models[k].buckets[b];
    return /*#__PURE__*/React.createElement("td", {
      key: b,
      style: cell,
      title: x && x.n ? `n=${x.n} · ทายฝนแล้วตกจริง ${x.counts.hit} · ทายฝนแต่ไม่ตก ${x.counts.false_alarm} · ตกแต่ไม่ได้ทาย ${x.counts.miss}` : ''
    }, x && x.n ? `${Math.round(x.accuracy * 100)}%` : '–', /*#__PURE__*/React.createElement("span", {
      style: {
        color: macos.tertiary,
        fontSize: '10px'
      }
    }, x && x.n ? ` ·${x.n}` : ''));
  }))))), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '11px',
      color: macos.tertiary,
      marginTop: '8px',
      lineHeight: 1.5
    }
  }, "\u0E16\u0E39\u0E01 = \u0E17\u0E32\u0E22 \"\u0E1D\u0E19/\u0E44\u0E21\u0E48\u0E1D\u0E19\" \u0E15\u0E23\u0E07\u0E01\u0E31\u0E1A\u0E20\u0E32\u0E1E\u0E08\u0E23\u0E34\u0E07\u0E43\u0E19\u0E23\u0E31\u0E28\u0E21\u0E35 2 \u0E01\u0E21. \u0E02\u0E2D\u0E07 4 \u0E2A\u0E16\u0E32\u0E19\u0E17\u0E35\u0E48 \xB7 \u0E15\u0E31\u0E27\u0E40\u0E25\u0E02\u0E40\u0E25\u0E47\u0E01 = \u0E08\u0E33\u0E19\u0E27\u0E19\u0E04\u0E23\u0E31\u0E49\u0E07\u0E17\u0E35\u0E48\u0E40\u0E17\u0E35\u0E22\u0E1A \xB7 \u0E40\u0E2D\u0E32\u0E40\u0E21\u0E32\u0E2A\u0E4C\u0E0A\u0E35\u0E49\u0E14\u0E39\u0E23\u0E32\u0E22\u0E25\u0E30\u0E40\u0E2D\u0E35\u0E22\u0E14"));
};

const WebPage = ({
  meta,
  state,
  src,
  located,
  locErr,
  show,
  theme,
  frames,
  basis,
  fcById,
  verify,
  custom,
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
  }, "Bangkok Radar"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '13px',
      color: stale || src === 'offline' ? macos.orange : macos.tertiary,
      marginTop: '4px'
    }
  }, meta.source, " \xB7 \u0E20\u0E32\u0E1E\u0E40\u0E27\u0E25\u0E32 ", meta.observed_at ? hhmm(meta.observed_at) : '?', " (\u0E14\u0E36\u0E07\u0E40\u0E21\u0E37\u0E48\u0E2D ", meta.last_update, ") \xB7 via ", meta.via || '?', stale ? ' · ภาพค้างเกิน 20 นาที' : '', src === 'offline' ? ' · offline' : '')), /*#__PURE__*/React.createElement("div", {
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
  }), custom && show.custom && fcById && fcById.custom && fcById.custom.img_pct && /*#__PURE__*/React.createElement(Marker, {
    m: { ...CUSTOM,
      left: `${fcById.custom.img_pct.left}%`,
      top: `${fcById.custom.img_pct.top}%`
    }
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
    title: "\u0E2A\u0E16\u0E32\u0E19\u0E17\u0E35\u0E48 \xB7 \u0E1D\u0E19 1 \u0E0A\u0E21. \u0E02\u0E49\u0E32\u0E07\u0E2B\u0E19\u0E49\u0E32"
  }, /*#__PURE__*/React.createElement(ForecastRow, {
    m: ME,
    on: show.me,
    dispatch: dispatch,
    pending: !basis,
    note: !(fcById && fcById.me) ? `${meNote || 'รอพิกัด…'} [${geoDiagText()}]` : null,
    fc: fcById && fcById.me && fcById.me.forecast,
    dist: point && !point.default ? `ห่างสถานีเรดาร์ ${point.distance_km} กม.` : null
  }), MARKERS.map(m => /*#__PURE__*/React.createElement(ForecastRow, {
    key: m.id,
    m: m,
    on: show[m.id],
    dispatch: dispatch,
    pending: !basis,
    fc: fcById && fcById[m.id] && fcById[m.id].forecast,
    dist: myLL ? `ห่างจากเครื่องนี้ ${kmBetween(myLL, m).toFixed(1)} กม.` : null
  })), custom && /*#__PURE__*/React.createElement(ForecastRow, {
    m: CUSTOM,
    on: show.custom,
    dispatch: dispatch,
    pending: !(fcById && fcById.custom),
    note: fcById && fcById.custom && !fcById.custom.in_coverage ? 'อยู่นอกวงเรดาร์ (120 กม. จากหนองจอก)' : null,
    fc: fcById && fcById.custom && fcById.custom.forecast,
    dist: `${+custom.lat.toFixed(7)}, ${+custom.lon.toFixed(7)}${myLL ? ` · ห่างจากเครื่องนี้ ${kmBetween(myLL, custom).toFixed(1)} กม.` : ''}`
  }), /*#__PURE__*/React.createElement(CustomInput, {
    custom: custom,
    dispatch: dispatch
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      fontSize: '10px',
      color: macos.tertiary,
      marginTop: '6px'
    }
  }, /*#__PURE__*/React.createElement("span", null, "\u0E41\u0E16\u0E1A\u0E2A\u0E35: \u0E17\u0E38\u0E01 5 \u0E19\u0E32\u0E17\u0E35 \xB7 \u0E2A\u0E27\u0E34\u0E15\u0E0A\u0E4C = \u0E08\u0E38\u0E14\u0E1A\u0E19\u0E41\u0E1C\u0E19\u0E17\u0E35\u0E48"), /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement("span", {
    style: {
      color: LEVEL_COLOR[1]
    }
  }, "\u25A0"), " \u0E1D\u0E19 ", /*#__PURE__*/React.createElement("span", {
    style: {
      color: LEVEL_COLOR[2]
    }
  }, "\u25A0"), " \u0E1D\u0E19\u0E2B\u0E19\u0E31\u0E01")), basis && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '12px',
      color: macos.tertiary,
      marginTop: '10px',
      lineHeight: 1.5
    }
  }, "\u0E2D\u0E34\u0E07\u0E20\u0E32\u0E1E\u0E40\u0E23\u0E14\u0E32\u0E23\u0E4C ~", hhmm(basis.observed_at), !basis.motion ? ' · ยังไม่รู้ทิศทางฝน' : basis.motion.speed_kmh < 3 ? ' · ฝนแทบอยู่กับที่' : ` · ฝนเคลื่อนจากทิศ${basis.motion.from_dir} ~${Math.round(basis.motion.speed_kmh)} กม./ชม.`, /*#__PURE__*/React.createElement("br", null), "\u0E09\u0E32\u0E22\u0E1D\u0E19\u0E15\u0E32\u0E21\u0E17\u0E34\u0E28\u0E40\u0E14\u0E34\u0E21 + \u0E41\u0E19\u0E27\u0E42\u0E19\u0E49\u0E21\u0E40\u0E1A\u0E32\u0E25\u0E07/\u0E41\u0E23\u0E07\u0E02\u0E36\u0E49\u0E19 30 \u0E19\u0E32\u0E17\u0E35\u0E25\u0E48\u0E32\u0E2A\u0E38\u0E14 (\u0E1D\u0E19\u0E17\u0E35\u0E48\u0E01\u0E48\u0E2D\u0E15\u0E31\u0E27\u0E43\u0E2B\u0E21\u0E48\u0E17\u0E32\u0E22\u0E44\u0E21\u0E48\u0E44\u0E14\u0E49) \u0E23\u0E31\u0E28\u0E21\u0E35\u0E08\u0E38\u0E14 ", basis.radius_km, " \u0E01\u0E21."), rain && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '12px',
      color: macos.orange,
      marginTop: '10px'
    }
  }, "\u0E41\u0E08\u0E49\u0E07\u0E40\u0E15\u0E37\u0E2D\u0E19 16:xx: ", rain)), /*#__PURE__*/React.createElement(VerifyPanel, {
    verify: verify
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '12px',
      color: macos.tertiary,
      lineHeight: 1.6,
      padding: '0 4px'
    }
  }, "\u0E20\u0E32\u0E1E\u0E40\u0E04\u0E25\u0E37\u0E48\u0E2D\u0E19\u0E44\u0E2B\u0E27 = \u0E20\u0E32\u0E1E\u0E19\u0E34\u0E48\u0E07\u0E17\u0E35\u0E48\u0E14\u0E36\u0E07\u0E17\u0E38\u0E01 5 \u0E19\u0E32\u0E17\u0E35\u0E22\u0E49\u0E2D\u0E19\u0E2B\u0E25\u0E31\u0E07 1 \u0E0A\u0E21. (\u0E44\u0E21\u0E48\u0E22\u0E34\u0E07\u0E40\u0E27\u0E47\u0E1A \u0E01\u0E17\u0E21. \u0E40\u0E1E\u0E34\u0E48\u0E21) \xB7 \u0E14\u0E31\u0E1A\u0E40\u0E1A\u0E34\u0E25\u0E04\u0E25\u0E34\u0E01\u0E17\u0E35\u0E48\u0E20\u0E32\u0E1E = \u0E40\u0E1B\u0E34\u0E14 loop \u0E02\u0E2D\u0E07 \u0E01\u0E17\u0E21."))));
};
};
