import { run } from 'uebersicht';
// ดึงข้อมูลจากไฟล์ JSON (ใช้ Path เต็มของคุณ)
export const command = "cat /tmp/weather_meta.json";
     //top: '390px', 
     //left: '35px', // จัดวางตำแหน่งตามต้องการ
     //width: '305px',
export const refreshFrequency = 60000; 

export const render = ({output, error}) => {
  if (error) return <div style={{color: 'red'}}>Error: {String(error)}</div>;
  if (!output) return null;
  
  try {
    const data = JSON.parse(output);

    const container = {
      position: 'fixed',
      top: '390px', 
      left: '35px', // จัดวางตำแหน่งตามต้องการ
      width: '305px',
      padding: '20px',
      borderRadius: '24px',
      color: '#fff',
      fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display"',
      backgroundColor: 'rgba(255, 255, 255, 0.30)',
      backdropFilter: 'blur(25px) saturate(70%)',
      WebkitBackdropFilter: 'blur(25px) saturate(70%)',
      border: '1px solid rgba(255, 255, 255, 0.15)',
      boxShadow: '0 8px 32px 0 rgba(0,0,0,0.4)',
      cursor: 'pointer',
    };

    const handleClick = (e) => {
      e.preventDefault();
      // เรียกใช้คำสั่ง OS ผ่าน API ของตัวแอปโดยตรง
      run("open -a 'Google Chrome' 'https://weather.tmd.go.th/bma_ncLoop.php'");
    };

    return (
      <div style={container} onClick={handleClick}>
        <div style={{fontSize: '11px', opacity: 0.4, fontWeight: '700', marginBottom: '12px', textAlign: 'center', letterSpacing: '0.5px'}}>
          {data.source}
        </div>
        
        <div style={{width: '100%', borderRadius: '14px', overflow: 'hidden', background: '#000', minHeight: '200px', display: 'flex', alignItems: 'center'}}>
          {/* แสดงภาพจาก Base64 */}
          <img 
            src={`data:image/png;base64,${data.img_base64}`} 
            style={{ width: '100%', display: 'block' }}
          />
        </div>

        <div style={{fontSize: '12px', opacity: 0.4, marginTop: '8px', textAlign: 'left'}}>
          Updated: {data.last_update}
        </div>
      </div>
    );
  } catch (e) {
    return null;
  }
};