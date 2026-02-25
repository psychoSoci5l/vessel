  // ── Sigil Canvas Engine (Fase 44) ──
  // Motore condiviso: header micro-sigil, dashboard widget, login screen

  const SigilEngine = (() => {
    const COL = {
      hood: '#2a0e42', hoodEdge: '#4a1d70',
      eye: '#00ff41', glow: '#00ff41',
      sigil: '#ff0040', bg: '#050208'
    };

    function hexToRgb(hex) {
      if (typeof hex === 'string' && hex.startsWith('rgb')) {
        const m = hex.match(/(\d+)/g);
        return { r: +m[0], g: +m[1], b: +m[2] };
      }
      hex = hex.replace('#', '');
      if (hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
      return { r: parseInt(hex.slice(0,2),16), g: parseInt(hex.slice(2,4),16), b: parseInt(hex.slice(4,6),16) };
    }

    function lerpColor(c1, c2, t) {
      const a = hexToRgb(c1), b = hexToRgb(c2);
      return `rgb(${a.r+(b.r-a.r)*t|0},${a.g+(b.g-a.g)*t|0},${a.b+(b.b-a.b)*t|0})`;
    }

    function rgbaStr(hex, alpha) {
      const c = hexToRgb(hex);
      return `rgba(${c.r},${c.g},${c.b},${alpha})`;
    }

    // ── Hood (landscape) ──
    function drawHood(ctx, W, H) {
      const cx = W/2, r = W*0.297, hcy = H*0.635, peakY = H*0.071;
      const shoulder = W*0.328, baseY = H*1.03;

      // Ambient glow (molto sottile)
      const ambGrad = ctx.createRadialGradient(cx, hcy, r*0.6, cx, hcy, r*1.6);
      ambGrad.addColorStop(0, rgbaStr(COL.hoodEdge, 0.03));
      ambGrad.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = ambGrad;
      ctx.fillRect(0, 0, W, H);

      function hoodPath() {
        ctx.beginPath();
        ctx.moveTo(cx-shoulder, baseY);
        ctx.bezierCurveTo(cx-shoulder, hcy+r*0.15, cx-r*0.85, hcy-r*0.2, cx-r*0.5, peakY+H*0.103);
        ctx.quadraticCurveTo(cx, peakY-H*0.024, cx+r*0.5, peakY+H*0.103);
        ctx.bezierCurveTo(cx+r*0.85, hcy-r*0.2, cx+shoulder, hcy+r*0.15, cx+shoulder, baseY);
        ctx.closePath();
      }

      // Hood body gradient (scuro come ESP32 — svanisce nel nero ai bordi)
      hoodPath();
      const darkHood = lerpColor(COL.hood, '#000', 0.55);
      const midHood = lerpColor(COL.hood, '#000', 0.25);
      const hg = ctx.createLinearGradient(cx-shoulder, 0, cx+shoulder, 0);
      hg.addColorStop(0, rgbaStr(darkHood, 0.15));
      hg.addColorStop(0.15, darkHood);
      hg.addColorStop(0.3, midHood);
      hg.addColorStop(0.42, COL.hood);
      hg.addColorStop(0.5, lerpColor(COL.hood, '#fff', 0.04));
      hg.addColorStop(0.58, COL.hood);
      hg.addColorStop(0.7, midHood);
      hg.addColorStop(0.85, darkHood);
      hg.addColorStop(1, rgbaStr(darkHood, 0.15));
      ctx.fillStyle = hg; ctx.fill();

      // Vertical shading
      hoodPath();
      const vg = ctx.createLinearGradient(0, peakY, 0, baseY);
      vg.addColorStop(0, 'rgba(255,255,255,0.03)');
      vg.addColorStop(0.2, 'rgba(0,0,0,0)');
      vg.addColorStop(0.55, 'rgba(0,0,0,0.25)');
      vg.addColorStop(1, 'rgba(0,0,0,0.65)');
      ctx.fillStyle = vg; ctx.fill();

      // Center dark
      hoodPath();
      const cd = ctx.createRadialGradient(cx, hcy+H*0.03, r*0.05, cx, hcy+H*0.03, r*0.95);
      cd.addColorStop(0, 'rgba(0,0,0,0.85)');
      cd.addColorStop(0.4, 'rgba(0,0,0,0.6)');
      cd.addColorStop(0.7, 'rgba(0,0,0,0.2)');
      cd.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = cd; ctx.fill();

      // Face cavity (3 strati come ESP32 drawFaceShadow — ellissi più scure)
      const fow = r*0.72, ovalCY = hcy+H*0.07;
      // Outer soft
      const sh0 = ctx.createRadialGradient(cx, ovalCY, fow*0.1, cx, ovalCY, fow*1.2);
      sh0.addColorStop(0, 'rgba(0,0,0,0.95)');
      sh0.addColorStop(0.35, 'rgba(0,0,0,0.75)');
      sh0.addColorStop(0.65, 'rgba(0,0,0,0.4)');
      sh0.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = sh0;
      ctx.beginPath(); ctx.ellipse(cx, ovalCY, fow*1.15, fow*1.05, 0, 0, Math.PI*2); ctx.fill();
      // Deep core (quasi nero — come ESP32 shadow2)
      const sh1 = ctx.createRadialGradient(cx, ovalCY+fow*0.12, fow*0.05, cx, ovalCY+fow*0.12, fow*0.7);
      sh1.addColorStop(0, 'rgba(0,0,0,0.9)');
      sh1.addColorStop(0.6, 'rgba(0,0,0,0.5)');
      sh1.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = sh1;
      ctx.beginPath(); ctx.ellipse(cx, ovalCY+fow*0.12, fow*0.7, fow*0.65, 0, 0, Math.PI*2); ctx.fill();

      // Edge highlight (sottile come ESP32 edgeHighlight)
      ctx.strokeStyle = rgbaStr(COL.hoodEdge, 0.12);
      ctx.lineWidth = 0.8; ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(cx-shoulder+5, baseY-10);
      ctx.bezierCurveTo(cx-shoulder+3, hcy+r*0.15, cx-r*0.85, hcy-r*0.2, cx-r*0.5, peakY+H*0.103);
      ctx.quadraticCurveTo(cx, peakY-H*0.024, cx+r*0.5, peakY+H*0.103);
      ctx.bezierCurveTo(cx+r*0.85, hcy-r*0.2, cx+shoulder-3, hcy+r*0.15, cx+shoulder-5, baseY-10);
      ctx.stroke();
    }

    // ── Eye (mandorla angolare — stile ESP32) ──
    function drawGlowingEye(ctx, ex, ey, size, col, glowCol, glowR, intensity) {
      intensity = intensity ?? 1.0;
      const gc = hexToRgb(glowCol);
      // Glow più contenuto (come drawEyeGlow su ESP32: cerchi concentrici)
      const g1 = ctx.createRadialGradient(ex, ey, 0, ex, ey, glowR*0.7*intensity);
      g1.addColorStop(0, `rgba(${gc.r},${gc.g},${gc.b},${0.18*intensity})`);
      g1.addColorStop(0.5, `rgba(${gc.r},${gc.g},${gc.b},${0.08*intensity})`);
      g1.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = g1;
      ctx.beginPath(); ctx.arc(ex, ey, glowR*0.7*intensity, 0, Math.PI*2); ctx.fill();

      // Mandorla angolare (due triangoli come ESP32 drawMandorlaEye)
      const hw = size, hh = size*0.52;
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(ex-hw, ey);
      ctx.lineTo(ex, ey-hh);
      ctx.lineTo(ex+hw, ey);
      ctx.lineTo(ex, ey+hh);
      ctx.closePath();
      ctx.clip();

      // Fill piatto (come ESP32 — niente gradient luminosi)
      ctx.fillStyle = col;
      ctx.fillRect(ex-hw, ey-hh, hw*2, hh*2);

      // Scan-lines orizzontali dentro l'occhio (effetto TFT pixel grid)
      ctx.fillStyle = 'rgba(0,0,0,0.35)';
      for (let y = ey-hh; y < ey+hh; y += 3) {
        ctx.fillRect(ex-hw, y, hw*2, 1);
      }

      // Palpebra superiore (lid cut come drawMandorlaEyeRelaxed, ~15%)
      const lidCut = hh * 0.15;
      ctx.fillStyle = COL.bg;
      ctx.fillRect(ex-hw-1, ey-hh-1, hw*2+2, lidCut+1);

      ctx.restore();

      // Pupilla (più piccola, stile minimale)
      ctx.fillStyle = '#000';
      ctx.beginPath(); ctx.arc(ex, ey+1, size*0.13, 0, Math.PI*2); ctx.fill();
    }

    function drawHappyEye(ctx, ex, ey, size, col, glowCol, glowR) {
      const gc = hexToRgb(glowCol);
      const g1 = ctx.createRadialGradient(ex, ey, 0, ex, ey, glowR*0.7);
      g1.addColorStop(0, `rgba(${gc.r},${gc.g},${gc.b},0.25)`);
      g1.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = g1;
      ctx.beginPath(); ctx.arc(ex, ey, glowR*0.7, 0, Math.PI*2); ctx.fill();
      ctx.strokeStyle = col; ctx.lineWidth = 3.5; ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.arc(ex, ey+size*0.3, size*0.8, Math.PI*1.15, Math.PI*1.85);
      ctx.stroke();
    }

    // ── Sigil symbol (scala ridotta per coerenza con ESP32) ──
    function drawSigil(ctx, sx, sy, col, sigScale, rotation) {
      sigScale = sigScale || 1;
      rotation = rotation || 0;
      const s = 8 * sigScale;
      const gc = hexToRgb(col);
      // Glow minimo (come ESP32: fillCircle con colore appena visibile)
      const g = ctx.createRadialGradient(sx, sy, 0, sx, sy, s*2);
      g.addColorStop(0, `rgba(${gc.r},${gc.g},${gc.b},0.12)`);
      g.addColorStop(0.6, `rgba(${gc.r},${gc.g},${gc.b},0.05)`);
      g.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(sx, sy, s*2, 0, Math.PI*2); ctx.fill();
      ctx.save();
      ctx.translate(sx, sy);
      ctx.rotate(rotation);
      ctx.strokeStyle = col; ctx.lineCap = 'round';
      // Croce (come ESP32: drawWideLine vertical + horizontal)
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(0,-s); ctx.lineTo(0,s); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(-s,0); ctx.lineTo(s,0); ctx.stroke();
      // Diagonali (più sottili)
      ctx.lineWidth = 1;
      const d = s*0.65;
      ctx.beginPath(); ctx.moveTo(-d,-d); ctx.lineTo(d,d); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(-d,d); ctx.lineTo(d,-d); ctx.stroke();
      // Cerchietto al centro
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(0, 0, s*0.35, 0, Math.PI*2); ctx.stroke();
      // Punte esterne (pixel singoli come ESP32 drawPixel)
      ctx.fillStyle = col;
      [[0,-s*1.2],[0,s*1.2],[-s*1.2,0],[s*1.2,0]].forEach(([dx,dy]) => {
        ctx.beginPath(); ctx.arc(dx, dy, 1.2, 0, Math.PI*2); ctx.fill();
      });
      ctx.restore();
    }

    function drawMouth(ctx, mx, my, w, col, curve) {
      ctx.strokeStyle = col; ctx.lineWidth = 2; ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(mx-w, my);
      ctx.quadraticCurveTo(mx, my+curve, mx+w, my);
      ctx.stroke();
    }

    // ── State renderer (parametrizzato per layout) ──
    function renderStates(ctx, cx, eyeY, eyeDist, eyeSize, sigilY, mouthY, glowR, now, state) {
      const lx = cx - eyeDist, rx = cx + eyeDist;
      const es = eyeSize, gr = glowR;

      if (state === 'IDLE') {
        const breath = 0.7 + 0.3*Math.sin(now/4000*Math.PI*2);
        const ec = lerpColor('#003310', COL.eye, breath);
        const dx = 2*Math.sin(now/5000), dy = 1.5*Math.cos(now/7000);
        drawGlowingEye(ctx, lx+dx, eyeY+dy, es, ec, COL.glow, gr*0.7, breath);
        drawGlowingEye(ctx, rx+dx, eyeY+dy, es, ec, COL.glow, gr*0.7, breath);
        const sb = 0.08+0.04*Math.sin(now/3000);
        drawSigil(ctx, cx, sigilY, rgbaStr(COL.sigil, sb), 0.5);
        drawMouth(ctx, cx, mouthY, 12, rgbaStr(COL.eye, 0.2), 0);

      } else if (state === 'THINKING') {
        drawGlowingEye(ctx, lx, eyeY-2, es, COL.eye, COL.glow, gr*0.8, 1);
        drawGlowingEye(ctx, rx, eyeY-2, es, COL.eye, COL.glow, gr*0.8, 1);
        const thinkRot = (now/8000)*Math.PI*2;
        const thinkPulse = 0.6+0.2*Math.sin(now/600);
        drawSigil(ctx, cx, sigilY, lerpColor('#000', COL.sigil, thinkPulse), 0.8, thinkRot);
        drawMouth(ctx, cx, mouthY, 10, rgbaStr(COL.eye, 0.3), 0);
        const dots = ['','.','..','...'][Math.floor(now/400)%4];
        ctx.fillStyle = rgbaStr(COL.eye, 0.3);
        ctx.font = '14px "JetBrains Mono", monospace'; ctx.textAlign = 'center';
        ctx.fillText(dots, cx, mouthY+22);

      } else if (state === 'WORKING') {
        const sq = es*0.5;
        drawGlowingEye(ctx, lx, eyeY, sq, COL.eye, COL.glow, gr*0.4, 0.6);
        drawGlowingEye(ctx, rx, eyeY, sq, COL.eye, COL.glow, gr*0.4, 0.6);
        // Sopracciglia concentrate (come ESP32)
        ctx.strokeStyle = rgbaStr(COL.eye, 0.4); ctx.lineWidth = 1.5; ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(lx-es, eyeY-es*0.55-4); ctx.lineTo(lx+es*0.4, eyeY-es*0.55-2); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(rx-es*0.4, eyeY-es*0.55-2); ctx.lineTo(rx+es, eyeY-es*0.55-4); ctx.stroke();
        const workRot = (now/3000)*Math.PI*2;
        drawSigil(ctx, cx, sigilY, rgbaStr(COL.eye, 0.3), 0.7, workRot);
        drawMouth(ctx, cx, mouthY, 8, rgbaStr(COL.eye, 0.25), 0);
        const dots2 = ['','.','..','...'][Math.floor(now/600)%4];
        ctx.fillStyle = rgbaStr(COL.eye, 0.25);
        ctx.font = '12px "JetBrains Mono", monospace'; ctx.textAlign = 'center';
        ctx.fillText(dots2, cx, mouthY+20);

      } else if (state === 'PROUD') {
        drawHappyEye(ctx, lx, eyeY, es, COL.eye, COL.glow, gr);
        drawHappyEye(ctx, rx, eyeY, es, COL.eye, COL.glow, gr);
        const proudScale = 1.1+0.1*Math.sin(now/500);
        drawSigil(ctx, cx, sigilY, COL.sigil, proudScale);
        const ringT = (now%2000)/2000;
        const ringR = 12+ringT*25, ringA = 0.4*(1-ringT);
        if (ringA>0.01) {
          ctx.strokeStyle = rgbaStr(COL.sigil, ringA); ctx.lineWidth = 1.5;
          ctx.beginPath(); ctx.arc(cx, sigilY, ringR, 0, Math.PI*2); ctx.stroke();
        }
        drawMouth(ctx, cx, mouthY, 18, COL.eye, 8);

      } else if (state === 'SLEEPING') {
        ctx.strokeStyle = rgbaStr(COL.eye, 0.3); ctx.lineWidth = 2.5; ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(lx-es, eyeY); ctx.lineTo(lx+es, eyeY); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(rx-es, eyeY); ctx.lineTo(rx+es, eyeY); ctx.stroke();
        const yO = 6*Math.sin(now/800);
        ctx.fillStyle = rgbaStr(COL.eye, 0.3);
        ctx.font = '12px "JetBrains Mono", monospace'; ctx.textAlign = 'center';
        ctx.fillText('z', cx+30, eyeY-25+yO);
        ctx.font = '20px "JetBrains Mono", monospace';
        ctx.fillText('Z', cx+45, eyeY-42+yO);
        ctx.font = '12px "JetBrains Mono", monospace';
        ctx.fillText('z', cx+58, eyeY-58+yO);

      } else if (state === 'HAPPY') {
        drawHappyEye(ctx, lx, eyeY, es*1.1, COL.eye, COL.glow, gr);
        drawHappyEye(ctx, rx, eyeY, es*1.1, COL.eye, COL.glow, gr);
        const sc = (Math.floor(now/300)%2===0) ? COL.sigil : lerpColor(COL.sigil,'#000',0.3);
        const bounceY = sigilY+4*Math.sin(now/400);
        drawSigil(ctx, cx, bounceY, sc, 1.1);
        drawMouth(ctx, cx, mouthY, 22, COL.eye, 10);
        const sp = 0.5+0.5*Math.sin(now/600);
        ctx.fillStyle = lerpColor('#000', COL.eye, sp);
        ctx.font = '16px "JetBrains Mono", monospace'; ctx.textAlign = 'center';
        ctx.fillText('*', cx-45, eyeY-25); ctx.fillText('*', cx+45, eyeY-25);

      } else if (state === 'CURIOUS') {
        const scanX = 5*Math.sin(now/1500);
        drawGlowingEye(ctx, lx+scanX, eyeY, es*1.05, COL.eye, COL.glow, gr*0.9, 1);
        drawGlowingEye(ctx, rx+scanX, eyeY, es*1.05, COL.eye, COL.glow, gr*0.9, 1);
        // Sopracciglia sottili (come ESP32 — linee semplici)
        ctx.strokeStyle = rgbaStr(COL.eye, 0.6); ctx.lineWidth = 1.5; ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(lx-es, eyeY-es*0.6-2); ctx.lineTo(lx+es*0.6, eyeY-es*0.6-6); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(rx-es*0.6, eyeY-es*0.6-6); ctx.lineTo(rx+es, eyeY-es*0.6-2); ctx.stroke();
        const curiousTilt = 0.2*Math.sin(now/1200);
        const curiousScale = 0.6+0.15*(0.5+0.5*Math.sin(now/1000*Math.PI*2));
        drawSigil(ctx, cx, sigilY, rgbaStr(COL.sigil, 0.5), curiousScale, curiousTilt);
        drawMouth(ctx, cx, mouthY, 10, rgbaStr(COL.eye, 0.3), 0);

      } else if (state === 'ALERT') {
        const alertCol = '#ffaa00';
        const flash = Math.floor(now/500)%2===0;
        drawGlowingEye(ctx, lx, eyeY, es, alertCol, alertCol, gr, 1);
        drawGlowingEye(ctx, rx, eyeY, es, alertCol, alertCol, gr, 1);
        const shakeX = 3*Math.sin(now/80);
        drawSigil(ctx, cx+shakeX, sigilY, flash ? COL.sigil : lerpColor(COL.sigil,'#000',0.4), 1.2);
        ctx.strokeStyle = alertCol; ctx.lineWidth = 2.5; ctx.lineCap = 'round';
        ctx.beginPath();
        for (let i=0;i<5;i++) {
          const mx=cx-18+i*9, my=mouthY+((i%2===0)?0:5);
          if(i===0) ctx.moveTo(mx,my); else ctx.lineTo(mx,my);
        }
        ctx.stroke();
        if (flash) {
          ctx.fillStyle = COL.sigil;
          ctx.font = 'bold 24px "JetBrains Mono", monospace'; ctx.textAlign = 'center';
          ctx.fillText('!', cx+eyeDist+22, eyeY-5);
        }

      } else if (state === 'ERROR') {
        const errCol = '#ff0040';
        const gc2 = hexToRgb(errCol);
        [-1,1].forEach(side => {
          const ex = side===-1 ? lx : rx;
          const g = ctx.createRadialGradient(ex, eyeY, 0, ex, eyeY, gr*0.6);
          g.addColorStop(0, `rgba(${gc2.r},${gc2.g},${gc2.b},0.25)`);
          g.addColorStop(1, 'rgba(0,0,0,0)');
          ctx.fillStyle = g;
          ctx.beginPath(); ctx.arc(ex, eyeY, gr*0.6, 0, Math.PI*2); ctx.fill();
          ctx.strokeStyle = errCol; ctx.lineWidth = 3.5; ctx.lineCap = 'round';
          const xs = es*0.65;
          ctx.beginPath(); ctx.moveTo(ex-xs, eyeY-xs); ctx.lineTo(ex+xs, eyeY+xs); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(ex-xs, eyeY+xs); ctx.lineTo(ex+xs, eyeY-xs); ctx.stroke();
        });
        if (Math.random()>0.4) drawSigil(ctx, cx, sigilY, rgbaStr(errCol, 0.4), 0.7+Math.random()*0.3);
        drawMouth(ctx, cx, mouthY+3, 14, errCol, -5);
        ctx.fillStyle = rgbaStr(errCol, 0.5);
        ctx.font = '11px "JetBrains Mono", monospace'; ctx.textAlign = 'center';
        ctx.fillText('reconnecting', cx, mouthY+32);

      } else if (state === 'BORED') {
        const phase = Math.floor((now/5000)%6);
        const t = (now%5000)/5000;

        if (phase === 0) {
          const angle = t*Math.PI*2, rollR = 10;
          const ldx = Math.cos(angle)*rollR, ldy = Math.sin(angle)*rollR;
          drawGlowingEye(ctx, lx+ldx, eyeY+ldy, es*0.9, COL.eye, COL.glow, gr*0.7, 0.7);
          drawGlowingEye(ctx, rx+ldx, eyeY+ldy, es*0.9, COL.eye, COL.glow, gr*0.7, 0.7);
          drawSigil(ctx, cx, sigilY, rgbaStr(COL.sigil, 0.15), 0.6);
          drawMouth(ctx, cx, mouthY, 12, rgbaStr(COL.eye, 0.3), -2);
        } else if (phase === 1) {
          let lookX, lookY;
          if (t<0.25) { lookX=-18*(t/0.25); lookY=0; }
          else if (t<0.5) { lookX=-18+36*((t-0.25)/0.25); lookY=0; }
          else if (t<0.75) { lookX=18-18*((t-0.5)/0.25); lookY=-10*((t-0.5)/0.25); }
          else { lookX=0; lookY=-10+10*((t-0.75)/0.25); }
          drawGlowingEye(ctx, lx+lookX, eyeY+lookY, es, COL.eye, COL.glow, gr*0.8, 0.8);
          drawGlowingEye(ctx, rx+lookX, eyeY+lookY, es, COL.eye, COL.glow, gr*0.8, 0.8);
          drawSigil(ctx, cx, sigilY, rgbaStr(COL.sigil, lookY<-5 ? 0.4 : 0.12), 0.7);
          drawMouth(ctx, cx, mouthY, 14, rgbaStr(COL.eye, 0.2), 0);
        } else if (phase === 2) {
          const yawnOpen = t<0.3 ? t/0.3 : t<0.7 ? 1 : 1-(t-0.7)/0.3;
          const lidClose = Math.max(0, yawnOpen-0.3);
          const eyeH = es*(1-lidClose*0.7);
          drawGlowingEye(ctx, lx, eyeY, eyeH, COL.eye, COL.glow, gr*0.5, 0.5+0.3*(1-yawnOpen));
          drawGlowingEye(ctx, rx, eyeY, eyeH, COL.eye, COL.glow, gr*0.5, 0.5+0.3*(1-yawnOpen));
          drawMouth(ctx, cx, mouthY, 6+yawnOpen*12, rgbaStr(COL.eye, 0.3+yawnOpen*0.2), yawnOpen*10);
          drawSigil(ctx, cx, sigilY, rgbaStr(COL.sigil, 0.08+0.04*(1-yawnOpen)), 0.5);
        } else if (phase === 3) {
          const bounceT = Math.abs(Math.sin(t*Math.PI*3));
          const juggleY = sigilY+20-bounceT*40;
          const juggleRot = t*Math.PI*4;
          drawSigil(ctx, cx, juggleY, COL.sigil, 0.8+bounceT*0.4, juggleRot);
          const trackY = (juggleY-eyeY)*0.15;
          drawGlowingEye(ctx, lx, eyeY+trackY, es, COL.eye, COL.glow, gr*0.8, 0.85);
          drawGlowingEye(ctx, rx, eyeY+trackY, es, COL.eye, COL.glow, gr*0.8, 0.85);
          drawMouth(ctx, cx, mouthY, 14, rgbaStr(COL.eye, 0.3), 3);
        } else if (phase === 4) {
          const droopCycle = t<0.7 ? t/0.7 : 0;
          const snap = t>=0.7 ? Math.min(1,(t-0.7)/0.1) : 0;
          const eyeDroop = droopCycle*0.8*(1-snap);
          const eyeScale = es*(1-eyeDroop*0.6);
          const eyeInt = 0.9-eyeDroop*0.5+snap*0.5;
          drawGlowingEye(ctx, lx, eyeY+eyeDroop*6, eyeScale, COL.eye, COL.glow, gr*0.6, eyeInt);
          drawGlowingEye(ctx, rx, eyeY+eyeDroop*6, eyeScale, COL.eye, COL.glow, gr*0.6, eyeInt);
          if (eyeDroop<0.5||snap>0||Math.random()>0.5)
            drawSigil(ctx, cx, sigilY, rgbaStr(COL.sigil, 0.12*(1-eyeDroop)+snap*0.2), 0.5+snap*0.3);
          drawMouth(ctx, cx, mouthY, 12, rgbaStr(COL.eye, 0.2), -2*eyeDroop);
          if (snap>0.5) {
            ctx.fillStyle = rgbaStr(COL.eye, 0.4*(1-(t-0.8)/0.2));
            ctx.font = 'bold 16px "JetBrains Mono", monospace'; ctx.textAlign = 'center';
            ctx.fillText('!', cx+eyeDist+8, eyeY-14);
          }
        } else if (phase === 5) {
          drawGlowingEye(ctx, lx, eyeY-4, es*0.9, COL.eye, COL.glow, gr*0.7, 0.75);
          drawGlowingEye(ctx, rx, eyeY-4, es*0.9, COL.eye, COL.glow, gr*0.7, 0.75);
          drawSigil(ctx, cx, sigilY, rgbaStr(COL.sigil, 0.3), 0.8, (now/2000)*Math.PI*2);
          ctx.strokeStyle = rgbaStr(COL.eye, 0.35); ctx.lineWidth = 2;
          ctx.beginPath(); ctx.arc(cx, mouthY, 4, 0, Math.PI*2); ctx.stroke();
          const notes = ['\u266A','\u266B'];
          for (let i=0;i<2;i++) {
            const nt = (t+i*0.4)%1;
            const nx = cx+20+i*12+6*Math.sin(nt*Math.PI*2);
            const ny = mouthY-nt*45;
            const na = nt<0.8 ? 0.5 : 0.5*(1-(nt-0.8)/0.2);
            ctx.fillStyle = rgbaStr(COL.eye, na);
            ctx.font = `${12+i*3}px "JetBrains Mono", monospace`;
            ctx.textAlign = 'center';
            ctx.fillText(notes[i], nx, ny);
          }
        }
      }
    }

    // ── Scanlines ──
    function drawScanlines(ctx, W, H) {
      ctx.fillStyle = 'rgba(0,0,0,0.04)';
      for (let y = 0; y < H; y += 2) ctx.fillRect(0, y, W, 1);
    }

    // ── Full frame render ──
    function renderFrame(canvas, state, startTime) {
      const ctx = canvas.getContext('2d');
      const dpr = window.devicePixelRatio || 1;
      const dispW = canvas.clientWidth, dispH = canvas.clientHeight;
      if (canvas.width !== dispW*dpr || canvas.height !== dispH*dpr) {
        canvas.width = dispW*dpr;
        canvas.height = dispH*dpr;
      }
      const W = dispW, H = dispH;
      const now = Date.now() - startTime;

      ctx.save();
      ctx.scale(dpr, dpr);
      ctx.fillStyle = COL.bg;
      ctx.fillRect(0, 0, W, H);
      drawHood(ctx, W, H);
      drawScanlines(ctx, W, H);
      // Landscape coords scaled to canvas size (reference: 320x170)
      const sx = W/320, sy = H/170;
      const s = Math.min(sx, sy);
      const cx = W/2;
      renderStates(ctx, cx, 82*sy, 44*s, 18*s, 38*sy, 115*sy, 28*s, now, state);
      ctx.restore();
    }

    // ── Mini render (header — solo occhi) ──
    function renderMini(canvas, state, startTime) {
      const ctx = canvas.getContext('2d');
      const dpr = window.devicePixelRatio || 1;
      const dispW = canvas.clientWidth, dispH = canvas.clientHeight;
      if (canvas.width !== dispW*dpr || canvas.height !== dispH*dpr) {
        canvas.width = dispW*dpr;
        canvas.height = dispH*dpr;
      }
      const now = Date.now() - startTime;
      ctx.save();
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, dispW, dispH);
      // Just draw eyes centered in the mini canvas
      const cx = dispW/2, ey = dispH/2;
      const es = dispH*0.35, gr = dispH*0.6, ed = dispW*0.22;

      if (state === 'SLEEPING') {
        ctx.strokeStyle = rgbaStr(COL.eye, 0.3); ctx.lineWidth = 2; ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(cx-ed-es, ey); ctx.lineTo(cx-ed+es, ey); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(cx+ed-es, ey); ctx.lineTo(cx+ed+es, ey); ctx.stroke();
      } else if (state === 'HAPPY' || state === 'PROUD') {
        drawHappyEye(ctx, cx-ed, ey, es, COL.eye, COL.glow, gr);
        drawHappyEye(ctx, cx+ed, ey, es, COL.eye, COL.glow, gr);
      } else if (state === 'ERROR') {
        const errCol = '#ff0040';
        ctx.strokeStyle = errCol; ctx.lineWidth = 3; ctx.lineCap = 'round';
        const xs = es*0.6;
        [cx-ed, cx+ed].forEach(ex => {
          ctx.beginPath(); ctx.moveTo(ex-xs, ey-xs); ctx.lineTo(ex+xs, ey+xs); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(ex-xs, ey+xs); ctx.lineTo(ex+xs, ey-xs); ctx.stroke();
        });
      } else if (state === 'ALERT') {
        const alertCol = '#ffaa00';
        drawGlowingEye(ctx, cx-ed, ey, es, alertCol, alertCol, gr, 1);
        drawGlowingEye(ctx, cx+ed, ey, es, alertCol, alertCol, gr, 1);
      } else if (state === 'THINKING' || state === 'WORKING') {
        const pulse = 0.6+0.4*Math.sin(now/800);
        drawGlowingEye(ctx, cx-ed, ey-2, es, COL.eye, COL.glow, gr, pulse);
        drawGlowingEye(ctx, cx+ed, ey-2, es, COL.eye, COL.glow, gr, pulse);
      } else {
        // IDLE, CURIOUS, BORED — breathing eyes
        const breath = 0.7+0.3*Math.sin(now/4000*Math.PI*2);
        const ec = lerpColor('#004415', COL.eye, breath);
        const dx = 2*Math.sin(now/5000), dy = 1*Math.cos(now/7000);
        drawGlowingEye(ctx, cx-ed+dx, ey+dy, es, ec, COL.glow, gr, breath);
        drawGlowingEye(ctx, cx+ed+dx, ey+dy, es, ec, COL.glow, gr, breath);
      }
      ctx.restore();
    }

    return { renderFrame, renderMini, COL };
  })();

  // ── Sigil Widget State ──
  let _sigilState = 'IDLE';
  let _sigilStartTime = Date.now();
  let _sigilOnline = false;
  let _sigilStateTime = Date.now();
  let _sigilAnimFrame = null;

  function setSigilState(state) {
    if (state !== _sigilState) {
      _sigilState = state;
      _sigilStartTime = Date.now();
      _sigilStateTime = Date.now();
    }
    _sigilOnline = true;
    // Update mood timer display
    const moodEl = document.getElementById('sigil-mood-info');
    if (moodEl) moodEl.textContent = state;
  }

  // Update sigil indicator (DOM + canvas state)
  function updateSigilIndicator(state) {
    const ind = document.getElementById('sigil-indicator');
    if (ind) {
      ind.setAttribute('data-state', state);
      ind.title = 'Sigil: ' + state;
      const label = document.getElementById('sigil-label');
      if (label) label.textContent = state;
    }
    setSigilState(state);
  }

  // ── Animation loop (shared for all canvases) ──
  function _sigilAnimLoop() {
    // Dashboard widget canvas
    const wc = document.getElementById('sigil-widget-canvas');
    if (wc && wc.offsetParent !== null) {
      SigilEngine.renderFrame(wc, _sigilState, _sigilStartTime);
    }
    // Header mini canvas
    const mc = document.getElementById('sigil-header-canvas');
    if (mc && mc.offsetParent !== null) {
      SigilEngine.renderMini(mc, _sigilState, _sigilStartTime);
    }
    // Mood timer update
    const timerEl = document.getElementById('sigil-mood-timer');
    if (timerEl) {
      const elapsed = Math.floor((Date.now() - _sigilStateTime) / 1000);
      if (elapsed < 60) timerEl.textContent = elapsed + 's';
      else if (elapsed < 3600) timerEl.textContent = Math.floor(elapsed/60) + 'm ' + (elapsed%60) + 's';
      else timerEl.textContent = Math.floor(elapsed/3600) + 'h ' + Math.floor((elapsed%3600)/60) + 'm';
    }
    _sigilAnimFrame = requestAnimationFrame(_sigilAnimLoop);
  }

  // Start anim loop on init
  _sigilAnimLoop();

  // ── Sigil commands ──
  function sigilCommand(state) {
    fetch('/api/tamagotchi/state', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state })
    }).then(r => r.json()).then(d => {
      if (d.ok !== false) showToast('Sigil: ' + state);
    }).catch(() => showToast('Errore invio comando'));
  }

  function sigilSendText() {
    const input = document.getElementById('sigil-text-input');
    if (!input || !input.value.trim()) return;
    fetch('/api/tamagotchi/text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: input.value.trim() })
    }).then(r => r.json()).then(d => {
      if (d.ok !== false) showToast('Messaggio inviato');
      input.value = '';
    }).catch(() => showToast('Errore invio messaggio'));
  }

  function sigilOTA() {
    if (!confirm('Avviare aggiornamento OTA firmware?')) return;
    fetch('/api/tamagotchi/ota', { method: 'POST' })
      .then(r => r.json())
      .then(d => showToast(d.status || 'OTA avviato'))
      .catch(() => showToast('Errore OTA'));
  }

  // ── Header click → scroll to widget ──
  function scrollToSigilWidget() {
    switchView('dashboard');
    setTimeout(() => {
      const el = document.getElementById('sigil-widget-wrap');
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 100);
  }
