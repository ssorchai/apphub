// แปลง widgets/gold-dashboard.jsx -> web/dist/gold-dashboard.js ให้หน้าเว็บโหลดด้วย <script> ได้ตรงๆ
// ไม่มี Babel ในเบราว์เซอร์ และไม่พึ่ง CDN
//
// ใช้ node + @babel ที่มากับ Übersicht.app (ไม่ต้องติดตั้งอะไรเพิ่ม):
//   UB_NODE_MODULES=".../Übersicht.app/Contents/Resources/node_modules" \
//     ".../Übersicht.app/Contents/Resources/node-arm64" build.js <in.jsx> <out.js>
// api.py ของแต่ละบริการ (common/hub/webwidget.py) เรียกให้เองเมื่อ .jsx ใหม่กว่า dist -- dist ถูก commit ไว้ด้วย
// เครื่องที่ไม่มี Übersicht (cloud) ก็ยังเสิร์ฟได้
const fs = require('fs');
const path = require('path');

const NM = process.env.UB_NODE_MODULES;
if (!NM) { console.error('ต้องตั้ง UB_NODE_MODULES'); process.exit(2); }
const babel = require(path.join(NM, '@babel/core'));
const [inFile, outFile] = process.argv.slice(2);
const name = path.basename(inFile, '.jsx');

const { code } = babel.transformSync(fs.readFileSync(inFile, 'utf8'), {
  babelrc: false, configFile: false, filename: path.basename(inFile),
  presets: [path.join(NM, '@babel/preset-react')],               // JSX -> React.createElement
  plugins: [path.join(NM, '@babel/plugin-transform-modules-commonjs')],  // import/export -> require/exports
});

// ห่อเป็นฟังก์ชันลงทะเบียนไว้ที่ window -- หน้า host ส่ง require('uebersicht') ปลอม + exports เข้าไปเอง
// (ต้องเรียกหลังตั้ง window.APPHUB_WEB เพราะ widget อ่านค่านั้นตอนโมดูลรัน)
const out = `// GENERATED จาก widgets/${path.basename(inFile)} โดย web/build.js -- ห้ามแก้ไฟล์นี้ แก้ที่ .jsx
window.APPHUB_WIDGETS = window.APPHUB_WIDGETS || {};
window.APPHUB_WIDGETS[${JSON.stringify(name)}] = function (require, exports, React) {
${code}
};
`;
const tmp = outFile + '.tmp';
fs.writeFileSync(tmp, out);
fs.renameSync(tmp, outFile);
console.log(`built ${outFile} (${out.length} bytes)`);
