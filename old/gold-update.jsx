import { run } from 'uebersicht';
export const command = "cat /tmp/gold_data.json";
export const refreshFrequency = 3000; 

export const render = ({output}) => {
  if (!output) return null;
  const data = JSON.parse(output);

  const container = {
    position: 'fixed', bottom: '25px', left: '35px',width: '300px',

    color: '#fff', fontFamily: 'SF Pro Display, Helvetica Neue',
    background: 'rgba(10,10,10,0.75)', padding: '20px',
    borderRadius: '20px', backdropFilter: 'blur(25px)',
     border: '1px solid rgba(255,255,255,0.12)',
    boxShadow: '0 10px 30px rgba(0,0,0,0.5)'
  };

  const badgeStyle = {
    background: data.zone.includes('GOLDEN') ? '#f1c242' : '#6cd17b',
    color: '#000', padding: '3px 10px', borderRadius: '6px',
    fontSize: '10px', fontWeight: '900', marginBottom: '15px', display: 'inline-block',
    letterSpacing: '0.5px'
  };

  const renderAsset = (asset, isCfd = false) => {
    const isPositive = !asset.change.includes('-');
    const color = isPositive ? '#32d74b' : '#f26159';
    const sign = isPositive && !asset.change.includes('+') ? '+' : '';

    return (
      <div style={{marginBottom: '18px'}}>
        <div style={{fontSize: '11px', opacity: 0.6, textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '4px'}}>
            {asset.name} O: {asset.open.toFixed(2)}
        </div>
        
        <div style={{display:'flex', justifyContent:'space-between', alignItems:'flex-end'}}>
          <div>
            <span style={{fontSize: '24px', fontWeight: '700', opacity: 0.8, color: isCfd ? '#007ad1' : '#fff'}}>
                {asset.price.toLocaleString(undefined, {minimumFractionDigits: 2})}
            </span>
          </div>
          <div style={{textAlign: 'right'}}>
            <div style={{fontSize: '18px', fontWeight: '700', opacity: 0.8, color: color}}>
              {sign}{asset.change} {asset.percent}
            </div>
            {/*<div style={{fontSize: '10px', opacity: 0.4}}>Open: {asset.open.toFixed(2)}</div>*/}
          </div>
        </div>
      </div>
    );
  };

  const handleClick = (e) => {
      e.preventDefault();
      // เรียกใช้คำสั่ง OS ผ่าน API ของตัวแอปโดยตรง
      run("open -a 'Google Chrome' 'https://www.vol2vol.com'");
    };

  return (
    <div style={container} onClick={handleClick}>
      <div style={badgeStyle}>{data.zone}</div>
      
      {renderAsset(data.future)}
      {renderAsset(data.cfd, true)}

      <div style={{
        borderTop: '1px solid rgba(255,255,255,0.1)', 
        paddingTop: '12px', 
        display:'flex', 
        justifyContent:'space-between', 
        alignItems:'center'
      }}>
        <span style={{fontSize: '12px', opacity: 0.6, fontWeight: '600'}}>SPREAD DIFF</span>
        <span style={{
            fontSize: '20px', 
            fontWeight: '900', 
            opacity: 0.8,
            color: data.diff >= 0 ? '#fff' : '#007ad1',
            textShadow: `0 0 10px ${data.diff >= 0 ? 'rgba(255,59,48,0.3)' : 'rgba(0,122,255,0.3)'}`
        }}>
          {data.diff > 0 ? '+' : ''}{data.diff.toFixed(2)}
        </span>
      </div>
      
      <div style={{fontSize: '14px', opacity: 0.4, marginTop: '10px', textAlign: 'right', fontStyle: 'italic'}}>
        Last Update: {data.future.time} | Sync: {data.system_time}
      </div>
    </div>
  );
};