"""HTML dashboard for the read-only rover status service.

Copied from robot-deep_robotics-lite3/scripts/rtk_imu/rover_dashboard.py so
the standalone tools and this service serve the same UI. Keep the JSON
contract of build_status() stable when editing either copy.
"""

DASHBOARD_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Rover Status</title>
<style>
:root{--bg:#0a0e13;--panel:#121a22;--line:#1f2b36;--fg:#e8eef5;--dim:#8fa0b3;--accent:#4cc2ff;--ok:#3fb950;--warn:#d29922;--bad:#f85149}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1200px 600px at 50% -200px,#12202c 0%,var(--bg) 55%);color:var(--fg);font:15px/1.45 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans CJK SC",sans-serif;-webkit-font-smoothing:antialiased}
header{display:flex;align-items:baseline;justify-content:space-between;gap:12px;padding:16px 20px 6px;max-width:1100px;margin:0 auto}
.title{font-size:18px;font-weight:600;letter-spacing:.3px}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#3a4a5c;margin-left:8px;vertical-align:middle;transition:background .3s}
.dot.on{background:var(--ok);box-shadow:0 0 8px var(--ok)}
.dot.bad{background:var(--bad)}
.sub{color:var(--dim);font-size:13px;font-variant-numeric:tabular-nums;text-align:right}
main{max-width:1100px;margin:0 auto;padding:10px 20px 28px;display:grid;grid-template-columns:repeat(12,1fr);gap:14px}
.card{background:linear-gradient(180deg,rgba(255,255,255,.03),rgba(255,255,255,0)),var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;min-width:0}
.c5{grid-column:span 5}.c3{grid-column:span 3}.c4{grid-column:span 4}.c7{grid-column:span 7}.c12{grid-column:span 12}
.card-head{display:flex;justify-content:space-between;align-items:baseline;gap:8px;color:var(--dim);font-size:13px;margin-bottom:10px}
.dim{color:var(--dim)}.center{text-align:center}
.big{font-size:44px;font-weight:650;line-height:1.15;font-variant-numeric:tabular-nums;letter-spacing:-.5px}
.big .unit{font-size:16px;font-weight:500;color:var(--dim);margin-left:4px;letter-spacing:0}
.kv{display:flex;justify-content:space-between;gap:12px;padding:6px 0;font-size:14px}
.kv span{color:var(--dim)}.kv b{font-weight:500;font-variant-numeric:tabular-nums;text-align:right}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:18px;word-break:break-all;font-variant-numeric:tabular-nums}
.local{display:flex;gap:32px;margin:12px 0 8px}
.local b{display:block;font-size:22px;font-weight:550;font-variant-numeric:tabular-nums}
.badge{display:inline-block;padding:7px 14px;border-radius:999px;font-weight:600;font-size:15px;border:1px solid var(--line);background:rgba(255,255,255,.04)}
.badge.ok{color:var(--ok);border-color:rgba(63,185,80,.45);background:rgba(63,185,80,.12)}
.badge.warn{color:var(--warn);border-color:rgba(210,153,34,.45);background:rgba(210,153,34,.12)}
.badge.bad{color:var(--bad);border-color:rgba(248,81,73,.45);background:rgba(248,81,73,.12)}
.ntrip-up{color:var(--ok)}.ntrip-down{color:var(--bad)}.ntrip-auth-error{color:var(--warn)}
.imu-ok{color:var(--ok)}.imu-bad{color:var(--bad)}
.compass-wrap{display:flex;justify-content:center}
.compass-wrap svg{width:100%;max-width:290px;height:auto}
.cardinal{fill:var(--dim);font-size:13px;font-weight:600}
.track-wrap{position:relative;height:340px;border-radius:10px;background:#0c131a;border:1px solid var(--line);overflow:hidden}
#track{width:100%;height:100%;display:block}
@media (max-width:820px){
  main{grid-template-columns:1fr;padding:10px 12px 24px}
  .c5,.c3,.c4,.c7,.c12{grid-column:1 / -1}
  .compass-wrap svg{max-width:240px}
  .big{font-size:38px}
  .track-wrap{height:280px}
}
</style>
</head>
<body>
<header>
  <div class="title">Rover Status<span id="conn" class="dot"></span></div>
  <div class="sub"><span id="uptime">--</span><br><span id="wall">--</span></div>
</header>
<main>
  <section class="card c5">
    <div class="card-head"><span>航向</span><span>IMU 磁参考</span></div>
    <div class="compass-wrap">
      <svg viewBox="0 0 220 220" role="img" aria-label="compass">
        <circle cx="110" cy="110" r="100" fill="none" stroke="#28384a" stroke-width="1.5"/>
        <g id="ticks"></g>
        <text x="110" y="30" class="cardinal" text-anchor="middle">N</text>
        <text x="192" y="115" class="cardinal" text-anchor="middle">E</text>
        <text x="110" y="200" class="cardinal" text-anchor="middle">S</text>
        <text x="28" y="115" class="cardinal" text-anchor="middle">W</text>
        <g id="needle" opacity="0.15">
          <polygon points="110,34 101,110 110,124 119,110" fill="#4cc2ff"/>
          <polygon points="110,186 103,110 110,98 117,110" fill="#3a4a5c"/>
        </g>
        <g id="courseMark" visibility="hidden">
          <line x1="110" y1="6" x2="110" y2="22" stroke="#3fb950" stroke-width="4" stroke-linecap="round"/>
        </g>
        <circle cx="110" cy="110" r="5" fill="#0a0e13" stroke="#4cc2ff" stroke-width="2"/>
      </svg>
    </div>
    <div class="big center"><span id="heading">--</span><span class="unit">°</span></div>
    <div class="dim center">相对正北，顺时针；绿色刻度为 GNSS 航向角</div>
  </section>

  <section class="card c3">
    <div class="card-head"><span>速度</span><span>GNSS</span></div>
    <div class="big"><span id="speed">--</span><span class="unit">m/s</span></div>
    <div class="dim"><span id="speedKmh">--</span> km/h</div>
    <div class="kv"><span>航向角</span><b id="course">--</b></div>
    <div class="kv"><span>航向来源</span><b>IMU</b></div>
  </section>

  <section class="card c4">
    <div class="card-head"><span>定位质量</span><span id="qualityCode">--</span></div>
    <div><span id="fixBadge" class="badge">--</span></div>
    <div class="kv"><span>卫星数</span><b id="sats">--</b></div>
    <div class="kv"><span>HDOP</span><b id="hdop">--</b></div>
    <div class="kv"><span>差分龄期</span><b id="diffAge">--</b></div>
  </section>

  <section class="card c7">
    <div class="card-head"><span>位置</span><span>WGS84</span></div>
    <div class="mono"><span id="lat">--</span>, <span id="lon">--</span></div>
    <div class="dim" id="alt">高程 --</div>
    <div class="local">
      <div><span class="dim">东</span><b id="east">--</b></div>
      <div><span class="dim">北</span><b id="north">--</b></div>
    </div>
    <div class="dim" id="datum">原点：等待首次定位</div>
  </section>

  <section class="card c5">
    <div class="card-head"><span>链路</span><span>NTRIP / IMU</span></div>
    <div class="kv"><span>NTRIP</span><b id="ntrip">--</b></div>
    <div class="kv"><span>RTCM 累计</span><b id="rtcm">--</b></div>
    <div class="kv"><span>GGA 上行次数</span><b id="gga">--</b></div>
    <div class="kv"><span>IMU</span><b id="imu">--</b></div>
    <div class="kv"><span>磁场模量</span><b id="mag">--</b></div>
  </section>

  <section class="card c12">
    <div class="card-head"><span>轨迹</span><span>本地东/北坐标（米），以首个定位为原点</span></div>
    <div class="track-wrap"><canvas id="track"></canvas></div>
  </section>
</main>
<script>
(function(){
  var $=function(id){return document.getElementById(id);};
  var INITIAL=__INITIAL_STATUS__;
  var trail=[],lastGood=0,cv=$('track'),ctx=cv.getContext('2d'),W=0,H=0,last=null;
  var ticks=$('ticks');
  for(var a=0;a<360;a+=10){
    var major=a%30===0,r1=major?84:91,r2=97,rad=(a-90)*Math.PI/180;
    var line=document.createElementNS('http://www.w3.org/2000/svg','line');
    line.setAttribute('x1',110+r1*Math.cos(rad));line.setAttribute('y1',110+r1*Math.sin(rad));
    line.setAttribute('x2',110+r2*Math.cos(rad));line.setAttribute('y2',110+r2*Math.sin(rad));
    line.setAttribute('stroke',major?'#4a6075':'#2b3a49');line.setAttribute('stroke-width',major?2:1);
    ticks.appendChild(line);
  }
  function setText(id,text){$(id).textContent=text;}
  function fmt(v,d,sign){
    if(v===null||v===undefined||isNaN(v))return '--';
    var s=Number(v).toFixed(d);
    return (sign&&v>0?'+':'')+s;
  }
  function apply(d){
    last=d;
    setText('uptime','运行 '+Math.round(d.uptime_s)+' s');
    setText('wall',new Date(d.t_wall*1000).toLocaleTimeString());
    var h=d.heading_deg,needle=$('needle');
    if(h===null||h===undefined){setText('heading','--');needle.setAttribute('opacity','0.15');}
    else{setText('heading',h.toFixed(0));needle.setAttribute('transform','rotate('+h+' 110 110)');needle.setAttribute('opacity','1');}
    var cm=$('courseMark'),course=d.motion.course_deg;
    if(course===null||course===undefined){cm.setAttribute('visibility','hidden');}
    else{cm.setAttribute('visibility','visible');cm.setAttribute('transform','rotate('+course+' 110 110)');}
    var sp=d.motion.speed_mps;
    setText('speed',fmt(sp,2));
    setText('speedKmh',sp===null||sp===undefined?'--':(sp*3.6).toFixed(2));
    setText('course',course===null||course===undefined?'--':course.toFixed(0)+'°');
    var p=d.position,q=p.fix_quality,badge=$('fixBadge');
    badge.textContent=q===null||q===undefined?'--':(p.fix_name||'q='+q);
    badge.className='badge '+(q===4?'ok':(q===5||q===2||q===1?'warn':'bad'));
    setText('qualityCode',q===null||q===undefined?'--':'q='+q);
    setText('sats',p.sats===null||p.sats===undefined?'--':p.sats);
    setText('hdop',fmt(p.hdop,1));
    setText('diffAge',p.diff_age_s===null||p.diff_age_s===undefined?'--':fmt(p.diff_age_s,1)+' s');
    setText('lat',p.lat===null||p.lat===undefined?'--':p.lat.toFixed(7));
    setText('lon',p.lon===null||p.lon===undefined?'--':p.lon.toFixed(7));
    setText('alt',p.alt_m===null||p.alt_m===undefined?'高程 --':'高程 '+p.alt_m.toFixed(1)+' m');
    setText('east',p.east_m===null||p.east_m===undefined?'--':fmt(p.east_m,1,true)+' m');
    setText('north',p.north_m===null||p.north_m===undefined?'--':fmt(p.north_m,1,true)+' m');
    var dm=d.datum;
    setText('datum',dm.lat0===null||dm.lat0===undefined?'原点：等待首次定位':'原点：'+dm.lat0.toFixed(7)+', '+dm.lon0.toFixed(7));
    var n=d.ntrip,el=$('ntrip');
    el.textContent=n.state;el.className='ntrip-'+n.state;
    var rb=n.rtcm_bytes||0;
    setText('rtcm',rb>=1048576?(rb/1048576).toFixed(2)+' MiB':(rb>=1024?(rb/1024).toFixed(1)+' KiB':rb+' B'));
    setText('gga',n.gga_uploaded);
    var imu=$('imu');
    imu.textContent=d.imu.status+(d.imu.age_s===null||d.imu.age_s===undefined?'':' · '+d.imu.age_s.toFixed(1)+' s');
    imu.className=d.imu.status.indexOf('open')===0?'imu-ok':'imu-bad';
    setText('mag',d.imu.mag_norm?d.imu.mag_norm.toFixed(0):'--');
    if(p.east_m!==null&&p.east_m!==undefined&&p.north_m!==null&&p.north_m!==undefined){
      var prev=trail[trail.length-1];
      if(!prev||Math.hypot(p.east_m-prev[0],p.north_m-prev[1])>=0.02){trail.push([p.east_m,p.north_m]);}
      if(trail.length>6000)trail.shift();
      drawTrack(h);
    }
  }
  function niceStep(x){
    var p=Math.pow(10,Math.floor(Math.log10(x))),m=x/p;
    return (m<=1?1:m<=2?2:m<=5?5:10)*p;
  }
  function resizeCanvas(){
    var r=cv.getBoundingClientRect(),dpr=window.devicePixelRatio||1;
    cv.width=Math.max(1,Math.round(r.width*dpr));cv.height=Math.max(1,Math.round(r.height*dpr));
    ctx.setTransform(dpr,0,0,dpr,0,0);W=r.width;H=r.height;drawTrack(last?last.heading_deg:null);
  }
  function drawTrack(heading){
    if(!W||!H)return;
    ctx.clearRect(0,0,W,H);
    ctx.fillStyle='#8fa0b3';ctx.font='12px ui-sans-serif,system-ui,sans-serif';
    if(!trail.length){ctx.textAlign='center';ctx.fillText('等待定位...',W/2,H/2);ctx.textAlign='left';return;}
    var minE=0,maxE=0,minN=0,maxN=0;
    for(var i=0;i<trail.length;i++){var pt=trail[i];
      if(pt[0]<minE)minE=pt[0];if(pt[0]>maxE)maxE=pt[0];
      if(pt[1]<minN)minN=pt[1];if(pt[1]>maxN)maxN=pt[1];
    }
    var span=Math.max(maxE-minE,maxN-minN,5),pad=34;
    var cx=(minE+maxE)/2,cy=(minN+maxN)/2;
    var s=Math.min((W-2*pad)/span,(H-2*pad)/span);
    var X=function(e){return W/2+(e-cx)*s;},Y=function(n){return H/2-(n-cy)*s;};
    var step=niceStep(span/5);
    ctx.strokeStyle='#1a2733';ctx.lineWidth=1;
    ctx.fillStyle='#5d6f82';
    for(var gx=Math.ceil((cx-W/2/s)/step)*step;gx<=cx+W/2/s;gx+=step){
      ctx.beginPath();ctx.moveTo(X(gx),0);ctx.lineTo(X(gx),H);ctx.stroke();
    }
    for(var gy=Math.ceil((cy-H/2/s)/step)*step;gy<=cy+H/2/s;gy+=step){
      ctx.beginPath();ctx.moveTo(0,Y(gy));ctx.lineTo(W,Y(gy));ctx.stroke();
    }
    ctx.strokeStyle='#2c4152';ctx.lineWidth=1.5;
    ctx.beginPath();ctx.moveTo(X(0),0);ctx.lineTo(X(0),H);ctx.stroke();
    ctx.beginPath();ctx.moveTo(0,Y(0));ctx.lineTo(W,Y(0));ctx.stroke();
    ctx.fillStyle='#4cc2ff';
    ctx.beginPath();ctx.arc(X(0),Y(0),3,0,Math.PI*2);ctx.fill();
    ctx.strokeStyle='#4cc2ff';ctx.lineWidth=2;ctx.lineJoin='round';
    ctx.beginPath();
    for(var j=0;j<trail.length;j++){
      var e=trail[j][0],nn=trail[j][1];
      if(j===0)ctx.moveTo(X(e),Y(nn));else ctx.lineTo(X(e),Y(nn));
    }
    ctx.stroke();
    var le=trail[trail.length-1][0],ln=trail[trail.length-1][1];
    ctx.fillStyle='#e8eef5';
    ctx.beginPath();ctx.arc(X(le),Y(ln),4,0,Math.PI*2);ctx.fill();
    if(heading!==null&&heading!==undefined){
      ctx.save();ctx.translate(X(le),Y(ln));ctx.rotate(heading*Math.PI/180);
      ctx.beginPath();ctx.moveTo(0,-14);ctx.lineTo(6,6);ctx.lineTo(-6,6);ctx.closePath();
      ctx.fillStyle='#4cc2ff';ctx.fill();ctx.restore();
    }
    ctx.fillStyle='#8fa0b3';ctx.textAlign='right';ctx.fillText('N ↑',W-12,20);
    ctx.textAlign='left';ctx.fillText(step+' m 网格',12,H-12);
  }
  async function tick(){
    try{
      var res=await fetch('/status',{cache:'no-store'});
      if(!res.ok)throw new Error(res.status);
      var d=await res.json();
      apply(d);
      $('conn').classList.add('on');$('conn').classList.remove('bad');lastGood=Date.now();
    }catch(e){
      $('conn').classList.remove('on');$('conn').classList.add('bad');
      $('wall').textContent='连接中断';
    }
    setTimeout(tick,1000);
  }
  if(INITIAL){apply(INITIAL);$('conn').classList.add('on');}
  new ResizeObserver(resizeCanvas).observe(cv);
  resizeCanvas();
  tick();
})();
</script>
</body>
</html>
"""
