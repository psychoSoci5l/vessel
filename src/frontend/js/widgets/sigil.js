  // ── Sigil Canvas Engine (Fase 46 — Pixel-Perfect ESP32 Match) ──
  // Offscreen 320×170 buffer + pixelated scaling = TFT-identical rendering

  const SigilEngine = (() => {
    // ── ESP32 exact colors (RGB888 from tft.color565 args) ──
    const C = {
      bg: [5,2,8], green: [0,255,65], dim: [0,85,21],
      red: [255,0,64], yellow: [255,170,0], scan: [3,1,5],
      hood: [61,21,96], hoodLt: [106,45,158], white: [255,255,255]
    };

    // ── ESP32 exact geometry ──
    const G = {
      cx: 160, cy: 85, eyeY: 70, sigilY: 43, mouthY: 115,
      lx: 130, rx: 190, hw: 19, hh: 10, eyelid: 15
    };

    // ── Offscreen buffer ──
    const _off = document.createElement('canvas');
    _off.width = 320; _off.height = 170;

    // ── Color helpers ──
    function rgb(c) { return `rgb(${c[0]},${c[1]},${c[2]})`; }
    function rgba(c, a) { return `rgba(${c[0]},${c[1]},${c[2]},${a})`; }
    function lerp(c1, c2, t) {
      if (t <= 0) return c1; if (t >= 1) return c2;
      return [c1[0]+(c2[0]-c1[0])*t|0, c1[1]+(c2[1]-c1[1])*t|0, c1[2]+(c2[2]-c1[2])*t|0];
    }
    // Hex compat for renderMini
    function hexToRgb(hex) {
      if (typeof hex !== 'string') return {r:0,g:0,b:0};
      if (hex.startsWith('rgb')) { const m=hex.match(/(\d+)/g); return {r:+m[0],g:+m[1],b:+m[2]}; }
      hex=hex.replace('#','');
      if (hex.length===3) hex=hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
      return {r:parseInt(hex.slice(0,2),16),g:parseInt(hex.slice(2,4),16),b:parseInt(hex.slice(4,6),16)};
    }
    function lerpHex(c1,c2,t) {
      const a=hexToRgb(c1),b=hexToRgb(c2);
      return `rgb(${a.r+(b.r-a.r)*t|0},${a.g+(b.g-a.g)*t|0},${a.b+(b.b-a.b)*t|0})`;
    }
    function rgbaHex(hex,alpha) { const c=hexToRgb(hex); return `rgba(${c.r},${c.g},${c.b},${alpha})`; }

    // ── Drawing primitives (ESP32 equivalents) ──

    function fillCircle(ctx, x, y, r, col) {
      ctx.fillStyle = rgb(col); ctx.beginPath(); ctx.arc(x, y, Math.max(0,r), 0, Math.PI*2); ctx.fill();
    }

    function fillEllipse(ctx, cx, cy, rx, ry, col) {
      ctx.fillStyle = rgb(col); ctx.beginPath(); ctx.ellipse(cx, cy, Math.max(0,rx), Math.max(0,ry), 0, 0, Math.PI*2); ctx.fill();
    }

    function fillTriangle(ctx, x0,y0,x1,y1,x2,y2, col) {
      ctx.fillStyle = rgb(col); ctx.beginPath();
      ctx.moveTo(x0,y0); ctx.lineTo(x1,y1); ctx.lineTo(x2,y2);
      ctx.closePath(); ctx.fill();
    }

    function drawLine(ctx, x0,y0,x1,y1, w, col) {
      ctx.strokeStyle = rgb(col); ctx.lineWidth = w; ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(x0,y0); ctx.lineTo(x1,y1); ctx.stroke();
    }

    function drawCircleStroke(ctx, x, y, r, col) {
      ctx.strokeStyle = rgb(col); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(x, y, Math.max(0,r), 0, Math.PI*2); ctx.stroke();
    }

    // ── Scanlines (ESP32: every 2px, COL_SCAN color) ──
    function drawScanlines(ctx) {
      ctx.fillStyle = rgb(C.scan);
      for (let y = 0; y < 170; y += 2) ctx.fillRect(0, y, 320, 1);
    }

    // ── Hood filled (column-by-column, ESP32 drawHoodFilled port) ──
    function drawHoodFilled(ctx, col) {
      const cx = G.cx, cy = G.cy;
      const shoulder = 78, peakH = 60, baseY = 170, neckMinY = cy + 10;

      const c_center = lerp(col, C.white, 0.04);
      const c_inner = col;
      const c_mid = lerp(col, C.bg, 0.25);
      const c_outer = lerp(col, C.bg, 0.55);
      const c_edge = lerp(col, C.bg, 0.82);

      for (let dx = -shoulder; dx <= shoulder; dx++) {
        const x = cx + dx;
        if (x < 0 || x >= 320) continue;
        const t = Math.abs(dx) / shoulder;

        let topY = cy - peakH + (peakH * t * t)|0;
        if (topY < 0) topY = 0;

        let botY;
        if (t < 0.28) { botY = baseY; }
        else {
          const curve = (t - 0.28) / 0.72;
          const rise = 0.5 * (1 - Math.cos(curve * Math.PI));
          botY = baseY - (rise * (baseY - neckMinY))|0;
        }

        const lineH = botY - topY;
        if (lineH <= 0) continue;

        // Horizontal gradient color
        let hCol;
        if (t < 0.12) hCol = lerp(c_center, c_inner, t / 0.12);
        else if (t < 0.3) hCol = lerp(c_inner, c_mid, (t - 0.12) / 0.18);
        else if (t < 0.55) hCol = lerp(c_mid, c_outer, (t - 0.3) / 0.25);
        else if (t < 0.8) hCol = lerp(c_outer, c_edge, (t - 0.55) / 0.25);
        else hCol = lerp(c_edge, C.bg, (t - 0.8) / 0.2);

        // Vertical gradient: 45% top normal, 55% bottom darker
        const topH = lineH * 45 / 100 | 0;
        const botH = lineH - topH;
        const botCol = lerp(hCol, C.bg, 0.35);

        ctx.fillStyle = rgb(hCol);
        ctx.fillRect(x, topY, 1, topH);
        ctx.fillStyle = rgb(botCol);
        ctx.fillRect(x, topY + topH, 1, botH);
      }

      // Edge highlight on upper arc
      const edgeHL = lerp(col, C.white, 0.15);
      for (let dx = -(shoulder-10); dx <= (shoulder-10); dx++) {
        const t = Math.abs(dx) / shoulder;
        const topY = cy - peakH + (peakH * t * t)|0;
        const alpha = 0.4 * (1 - t * 1.3);
        if (alpha > 0 && topY > 0) {
          ctx.fillStyle = rgba(lerp(C.bg, edgeHL, alpha), 1);
          ctx.fillRect(cx + dx, topY - 1, 1, 1);
        }
      }
    }

    // ── Face shadow (3 nested ellipses, ESP32 drawFaceShadow) ──
    function drawFaceShadow(ctx) {
      fillEllipse(ctx, G.cx, G.cy+2, 56, 62, [4,2,6]);
      fillEllipse(ctx, G.cx, G.cy+5, 46, 54, [2,1,3]);
      fillEllipse(ctx, G.cx, G.cy+10, 34, 42, [1,0,2]);
    }

    // ── Eye glow (2 concentric circles, ESP32 drawEyeGlow) ──
    function drawEyeGlow(ctx, ex, ey, col, intensity) {
      if (intensity < 0.05) return;
      fillCircle(ctx, ex, ey, 24, lerp(C.bg, col, Math.min(1, 0.08*intensity)));
      fillCircle(ctx, ex, ey, 16, lerp(C.bg, col, Math.min(1, 0.18*intensity)));
    }

    // ── Mandorla eye (2 triangles, ESP32 drawMandorlaEye) ──
    function drawMandorlaEye(ctx, ex, ey, hw, hh, col) {
      fillTriangle(ctx, ex-hw,ey, ex,ey-hh, ex+hw,ey, col);
      fillTriangle(ctx, ex-hw,ey, ex,ey+hh, ex+hw,ey, col);
    }

    // ── Relaxed mandorla (with upper lid cut) ──
    function drawMandorlaEyeRelaxed(ctx, ex, ey, hw, hh, col, lidPct) {
      drawMandorlaEye(ctx, ex, ey, hw, hh, col);
      if (lidPct > 0) {
        const cutH = hh * lidPct / 100 | 0;
        ctx.fillStyle = rgb(C.bg);
        ctx.fillRect(ex-hw-1, ey-hh-1, hw*2+2, cutH+2);
      }
    }

    // ── Happy eye (parabolic arc, 3px thick, ESP32 drawHappyEye) ──
    function drawHappyEye(ctx, ex, ey, hw, col) {
      ctx.fillStyle = rgb(col);
      for (let dx = -hw; dx <= hw; dx++) {
        const t = dx / hw;
        const dy = (-8 * (1 - t*t))|0;
        ctx.fillRect(ex+dx, ey+dy-1, 1, 3);
      }
    }

    // ── Sigil symbol (ESP32 drawSigil exact port) ──
    function drawSigil(ctx, sx, sy, col, scale, rotation) {
      scale = scale || 1; rotation = rotation || 0;
      // Glow halo (2 concentric circles)
      const glowR = (14 * scale)|0;
      if (glowR > 2) {
        fillCircle(ctx, sx, sy, glowR+4, lerp(C.bg, col, 0.05));
        fillCircle(ctx, sx, sy, glowR, lerp(C.bg, col, 0.12));
      }
      const cosR = Math.cos(rotation), sinR = Math.sin(rotation);
      function pt(dx,dy) {
        return [sx + (scale*(dx*cosR-dy*sinR))|0, sy + (scale*(dx*sinR+dy*cosR))|0];
      }
      // Cross (2px wide)
      const [v0x,v0y]=pt(0,-8),[v1x,v1y]=pt(0,8);
      const [h0x,h0y]=pt(-8,0),[h1x,h1y]=pt(8,0);
      drawLine(ctx,v0x,v0y,v1x,v1y,2,col);
      drawLine(ctx,h0x,h0y,h1x,h1y,2,col);
      // Diagonals (1px)
      const [d0x,d0y]=pt(-5,-5),[d1x,d1y]=pt(5,5);
      const [d2x,d2y]=pt(-5,5),[d3x,d3y]=pt(5,-5);
      drawLine(ctx,d0x,d0y,d1x,d1y,1,col);
      drawLine(ctx,d2x,d2y,d3x,d3y,1,col);
      // Center circle
      drawCircleStroke(ctx, sx, sy, Math.max(1,(3*scale)|0), col);
      // Cardinal points
      ctx.fillStyle = rgb(col);
      [pt(0,-10),pt(0,10),pt(-10,0),pt(10,0)].forEach(([px,py]) => {
        ctx.fillRect(px, py, 1, 1);
      });
    }

    // ── Mouth (parabolic curve for smiles/frowns) ──
    function drawMouth(ctx, mx, my, w, col, curve) {
      ctx.fillStyle = rgb(col);
      for (let dx = -w; dx <= w; dx++) {
        const t = dx / w;
        const dy = (curve * t * t)|0;
        ctx.fillRect(mx+dx, my+dy, 1, 1);
        if (Math.abs(curve) > 3) ctx.fillRect(mx+dx, my+dy+1, 1, 1);
      }
    }

    // ── Straight mouth line ──
    function drawMouthLine(ctx, mx, my, hw, col) {
      drawLine(ctx, mx-hw, my, mx+hw, my, 1, col);
    }

    // ── Text helper (ESP32 font approximation) ──
    function drawText(ctx, text, x, y, col, size) {
      ctx.fillStyle = rgb(col);
      ctx.font = `${size||10}px "JetBrains Mono",monospace`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(text, x, y);
    }

    // ── State renderer (all 11 states, ESP32-accurate) ──
    function renderStates(ctx, now, state) {
      const {cx,cy,eyeY,sigilY,mouthY,lx,rx,hw,hh} = G;

      if (state === 'IDLE') {
        drawHoodFilled(ctx, C.hood);
        drawFaceShadow(ctx);
        const breath = 0.7 + 0.3*Math.sin(now/4000*Math.PI*2);
        const eyeCol = [0, (255*breath)|0, (65*breath)|0];
        drawEyeGlow(ctx, lx, eyeY, C.green, 0.8);
        drawEyeGlow(ctx, rx, eyeY, C.green, 0.8);
        const dx = (2*Math.sin(now/5000))|0, dy = (1*Math.cos(now/7000))|0;
        drawMandorlaEyeRelaxed(ctx, lx, eyeY, hw, hh, eyeCol, G.eyelid);
        drawMandorlaEyeRelaxed(ctx, rx, eyeY, hw, hh, eyeCol, G.eyelid);
        fillCircle(ctx, lx+dx, eyeY+dy, 4, C.bg);
        fillCircle(ctx, rx+dx, eyeY+dy, 4, C.bg);
        const sb = 0.1 + 0.05*Math.sin(now/6000*Math.PI*2);
        drawSigil(ctx, cx, sigilY, lerp(C.bg, C.red, sb), 0.6);
        drawLine(ctx, cx-15, mouthY, cx+15, mouthY, 1, eyeCol);

      } else if (state === 'THINKING') {
        drawHoodFilled(ctx, C.hood);
        drawFaceShadow(ctx);
        drawEyeGlow(ctx, lx, eyeY, C.green, 1);
        drawEyeGlow(ctx, rx, eyeY, C.green, 1);
        drawMandorlaEyeRelaxed(ctx, lx, eyeY, hw, hh, C.green, 0);
        drawMandorlaEyeRelaxed(ctx, rx, eyeY, hw, hh, C.green, 0);
        fillCircle(ctx, lx, eyeY-5, 5, C.bg);
        fillCircle(ctx, rx, eyeY-5, 5, C.bg);
        const pulse = 0.7+0.3*Math.sin(now/1000*Math.PI*2);
        const sigilCol = lerp(C.bg, C.red, pulse);
        const rot = now/8000*Math.PI*2;
        drawSigil(ctx, cx, sigilY, sigilCol, 1, rot);
        drawLine(ctx, cx-12, mouthY, cx+12, mouthY, 1, C.green);
        const dots = ['','.','..','...'][(now/400|0)%4];
        if (dots) drawText(ctx, dots, cx, cy+50, C.dim, 14);

      } else if (state === 'WORKING') {
        drawHoodFilled(ctx, C.hood);
        drawFaceShadow(ctx);
        drawEyeGlow(ctx, lx, eyeY, C.green, 0.5);
        drawEyeGlow(ctx, rx, eyeY, C.green, 0.5);
        drawMandorlaEye(ctx, lx, eyeY, hw, 4, C.dim);
        drawMandorlaEye(ctx, rx, eyeY, hw, 4, C.dim);
        drawLine(ctx, lx-18, eyeY-14, lx+18, eyeY-14, 2, C.dim);
        drawLine(ctx, rx-18, eyeY-14, rx+18, eyeY-14, 2, C.dim);
        const rot = now/3000*Math.PI*2;
        drawSigil(ctx, cx, sigilY, C.dim, 0.9, rot);
        drawLine(ctx, cx-8, mouthY, cx+8, mouthY, 1, C.dim);
        const dots = ['','.','..','...'][(now/600|0)%4];
        if (dots) drawText(ctx, dots, cx, cy+50, C.dim, 14);

      } else if (state === 'PROUD') {
        drawHoodFilled(ctx, C.hoodLt);
        drawFaceShadow(ctx);
        drawEyeGlow(ctx, lx, eyeY, C.green, 1);
        drawEyeGlow(ctx, rx, eyeY, C.green, 1);
        drawHappyEye(ctx, lx, eyeY, (hw*0.7)|0, C.green);
        drawHappyEye(ctx, rx, eyeY, (hw*0.7)|0, C.green);
        const ss = 1.1+0.1*Math.sin(now/500*Math.PI*2);
        drawSigil(ctx, cx, sigilY, C.red, ss);
        const ringT = (now%1500)/1500;
        const ringR = (15*ringT)|0;
        const ringCol = lerp(C.red, C.bg, ringT);
        if (ringR > 0) drawCircleStroke(ctx, cx, sigilY, ringR, ringCol);
        drawMouth(ctx, cx, mouthY, 18, C.green, 7);

      } else if (state === 'SLEEPING') {
        drawHoodFilled(ctx, lerp(C.hood, C.bg, 0.4));
        drawLine(ctx, lx-hw, eyeY, lx+hw, eyeY, 2, C.dim);
        drawLine(ctx, rx-hw, eyeY, rx+hw, eyeY, 2, C.dim);
        drawSigil(ctx, cx, sigilY, [40,0,10], 0.5);
        const yOff = (5*Math.sin(now/800))|0;
        drawText(ctx, 'z', cx+50, cy-45+yOff, C.dim, 14);
        drawText(ctx, 'Z', cx+65, cy-60+yOff, C.dim, 24);
        drawText(ctx, 'z', cx+85, cy-75+yOff, C.dim, 14);

      } else if (state === 'HAPPY') {
        drawHoodFilled(ctx, C.hoodLt);
        drawFaceShadow(ctx);
        drawEyeGlow(ctx, lx, eyeY, C.green, 1);
        drawEyeGlow(ctx, rx, eyeY, C.green, 1);
        drawHappyEye(ctx, lx, eyeY, (hw*0.8)|0, C.green);
        drawHappyEye(ctx, rx, eyeY, (hw*0.8)|0, C.green);
        const flash = (now/300|0)%2 === 0;
        const sigilCol = flash ? C.red : [180,0,45];
        const bounceY = (5*Math.sin(now/300*Math.PI*2))|0;
        drawSigil(ctx, cx, sigilY+bounceY, sigilCol, 1.1);
        drawMouth(ctx, cx, mouthY, 22, C.green, 9);
        const sp = 0.5+0.5*Math.sin(now/600);
        const starCol = [0,(255*sp)|0,(65*sp)|0];
        drawText(ctx, '*', cx-60, cy-30, starCol, 14);
        drawText(ctx, '*', cx+58, cy-30, starCol, 14);
        drawText(ctx, '*', cx-45, cy-48, starCol, 8);
        drawText(ctx, '*', cx+48, cy-48, starCol, 8);

      } else if (state === 'CURIOUS') {
        drawHoodFilled(ctx, C.hoodLt);
        drawFaceShadow(ctx);
        drawEyeGlow(ctx, lx, eyeY, C.green, 1);
        drawEyeGlow(ctx, rx, eyeY, C.green, 1);
        drawMandorlaEyeRelaxed(ctx, lx, eyeY, hw+2, hh+2, C.green, 0);
        drawMandorlaEyeRelaxed(ctx, rx, eyeY, hw+2, hh+2, C.green, 0);
        const scanX = (8*Math.sin(now/1500))|0;
        fillCircle(ctx, lx+scanX, eyeY, 5, C.bg);
        fillCircle(ctx, rx+scanX, eyeY, 5, C.bg);
        drawLine(ctx, lx-20, eyeY-20, lx+15, eyeY-16, 2, C.green);
        drawLine(ctx, rx-15, eyeY-16, rx+20, eyeY-20, 2, C.green);
        const sp = 0.5+0.5*Math.sin(now/1000*Math.PI*2);
        const sigilCol = lerp(C.bg, C.red, sp);
        const tilt = 0.25*Math.sin(now/1200);
        const sc = 0.9+0.2*sp;
        drawSigil(ctx, cx, sigilY, sigilCol, sc, tilt);
        drawCircleStroke(ctx, cx, mouthY, 5, C.green);
        const qY = (3*Math.sin(now/800))|0;
        drawText(ctx, '?', cx+80, cy-30+qY, C.dim, 24);

      } else if (state === 'ALERT') {
        drawHoodFilled(ctx, C.yellow);
        drawFaceShadow(ctx);
        drawEyeGlow(ctx, lx, eyeY, C.yellow, 1);
        drawEyeGlow(ctx, rx, eyeY, C.yellow, 1);
        drawMandorlaEye(ctx, lx, eyeY, hw, hh, C.yellow);
        drawMandorlaEye(ctx, rx, eyeY, hw, hh, C.yellow);
        fillCircle(ctx, lx, eyeY, 5, C.bg);
        fillCircle(ctx, rx, eyeY, 5, C.bg);
        drawLine(ctx, lx-18, eyeY-18, lx+5, eyeY-12, 2, C.yellow);
        drawLine(ctx, rx-5, eyeY-12, rx+18, eyeY-18, 2, C.yellow);
        const shakeX = (3*Math.sin(now/80))|0;
        drawSigil(ctx, cx+shakeX, sigilY, C.red, 1.2);
        // Zigzag mouth
        for (let i = 0; i < 4; i++) {
          const sx0 = cx-20+i*10, sy0 = mouthY+((i%2===0)?0:5);
          const sx1 = sx0+10, sy1 = mouthY+((i%2===0)?5:0);
          drawLine(ctx, sx0, sy0, sx1, sy1, 2, C.yellow);
        }
        if ((now/500|0)%2===0) drawText(ctx, '!', cx+90, cy-15, C.red, 24);

      } else if (state === 'ERROR') {
        drawHoodFilled(ctx, C.red);
        drawFaceShadow(ctx);
        drawEyeGlow(ctx, lx, eyeY, C.red, 0.6);
        drawEyeGlow(ctx, rx, eyeY, C.red, 0.6);
        // X marks
        [lx, rx].forEach(ex => {
          drawLine(ctx, ex-12, eyeY-12, ex+12, eyeY+12, 3, C.red);
          drawLine(ctx, ex-12, eyeY+12, ex+12, eyeY-12, 3, C.red);
        });
        if (Math.random()>0.4) {
          const sc = 0.7+Math.random()*0.3;
          drawSigil(ctx, cx, sigilY, [120,0,30], sc);
        }
        drawLine(ctx, cx-15, mouthY+5, cx, mouthY, 2, C.red);
        drawLine(ctx, cx, mouthY, cx+15, mouthY+5, 2, C.red);
        drawText(ctx, 'reconnecting', cx, cy+55, C.red, 8);

      } else if (state === 'BORED') {
        const elapsed = now;
        const phase = (elapsed/5000|0)%6;
        const t = (elapsed%5000)/5000;

        drawHoodFilled(ctx, C.hood);
        drawFaceShadow(ctx);
        drawEyeGlow(ctx, lx, eyeY, C.green, 0.7);
        drawEyeGlow(ctx, rx, eyeY, C.green, 0.7);

        if (phase === 0) {
          // Eye Roll
          const edx = (Math.cos(t*Math.PI*2)*12)|0;
          const edy = (Math.sin(t*Math.PI*2)*12)|0;
          drawMandorlaEyeRelaxed(ctx, lx, eyeY, hw, hh, C.green, G.eyelid);
          drawMandorlaEyeRelaxed(ctx, rx, eyeY, hw, hh, C.green, G.eyelid);
          fillCircle(ctx, lx+edx, eyeY+edy, 4, C.bg);
          fillCircle(ctx, rx+edx, eyeY+edy, 4, C.bg);
          drawSigil(ctx, cx, sigilY, [38,0,10], 0.6);
          drawMouth(ctx, cx, mouthY, 10, C.dim, -2);
          drawText(ctx, '...', cx, mouthY+18, [0,40,10], 8);

        } else if (phase === 1) {
          // Wander
          let pdx=0, pdy=0;
          if (t<0.25) { pdx=(-25*(t/0.25))|0; }
          else if (t<0.5) { pdx=(-25+50*((t-0.25)/0.25))|0; }
          else if (t<0.75) { pdx=(25*(1-(t-0.5)/0.25))|0; pdy=(-15*((t-0.5)/0.25))|0; }
          else { pdy=(-15*(1-(t-0.75)/0.25))|0; }
          drawMandorlaEyeRelaxed(ctx, lx, eyeY, hw, hh, C.green, G.eyelid);
          drawMandorlaEyeRelaxed(ctx, rx, eyeY, hw, hh, C.green, G.eyelid);
          fillCircle(ctx, lx+pdx, eyeY+pdy, 4, C.bg);
          fillCircle(ctx, rx+pdx, eyeY+pdy, 4, C.bg);
          const sb = (t>0.5&&t<0.75) ? 0.5 : 0.15;
          drawSigil(ctx, cx, sigilY, lerp(C.bg, C.red, sb), 0.7);
          drawLine(ctx, cx-10, mouthY, cx+10, mouthY, 1, C.dim);
          if (t>0.6&&t<0.85) drawText(ctx, '?', cx+70, cy-35, [0,40,10], 14);

        } else if (phase === 2) {
          // Yawn
          let yawnOpen;
          if (t<0.3) yawnOpen=t/0.3;
          else if (t<0.7) yawnOpen=1;
          else yawnOpen=1-(t-0.7)/0.3;
          const eyeH = Math.max(2, (hh*(1-yawnOpen*0.7))|0);
          drawMandorlaEye(ctx, lx, eyeY, hw, eyeH, C.green);
          drawMandorlaEye(ctx, rx, eyeY, hw, eyeH, C.green);
          if (eyeH>3) { fillCircle(ctx,lx,eyeY,3,C.bg); fillCircle(ctx,rx,eyeY,3,C.bg); }
          const mH = Math.max(1,(12*yawnOpen)|0);
          fillEllipse(ctx, cx, mouthY, 8, mH, C.dim);
          const sd = 0.15*(1-yawnOpen*0.8);
          drawSigil(ctx, cx, sigilY, lerp(C.bg, C.red, sd), 0.6);

        } else if (phase === 3) {
          // Juggle
          const bounceY = 30 - Math.abs(Math.sin(t*3*Math.PI))*60;
          const juggleRot = t*4*Math.PI;
          const juggleSY = sigilY + bounceY|0;
          drawSigil(ctx, cx, juggleSY, C.red, 0.9, juggleRot);
          const trackY = (bounceY*0.15)|0;
          drawMandorlaEyeRelaxed(ctx, lx, eyeY, hw, hh, C.green, G.eyelid);
          drawMandorlaEyeRelaxed(ctx, rx, eyeY, hw, hh, C.green, G.eyelid);
          fillCircle(ctx, lx, eyeY+trackY-2, 4, C.bg);
          fillCircle(ctx, rx, eyeY+trackY-2, 4, C.bg);
          drawMouth(ctx, cx, mouthY, 12, C.green, 4);

        } else if (phase === 4) {
          // Doze off
          let droop;
          if (t<0.7) droop=t/0.7;
          else if (t<0.8) droop=1-(t-0.7)/0.1;
          else droop=0;
          const eyeH = Math.max(2, (hh*(1-droop*0.85))|0);
          const eyeCol = lerp(C.green, C.dim, droop*0.6);
          drawMandorlaEye(ctx, lx, eyeY, hw, eyeH, eyeCol);
          drawMandorlaEye(ctx, rx, eyeY, hw, eyeH, eyeCol);
          if (eyeH>3) { fillCircle(ctx,lx,eyeY,3,C.bg); fillCircle(ctx,rx,eyeY,3,C.bg); }
          if (droop<0.5||Math.random()>(droop*0.8))
            drawSigil(ctx, cx, sigilY, lerp(C.bg,C.red,0.2*(1-droop)), 0.6);
          drawLine(ctx, cx-10, mouthY, cx+10, mouthY, 1, C.dim);
          if (t>0.7&&t<0.9) drawText(ctx, '!', cx+60, cy-30, C.green, 24);

        } else {
          // Whistle
          drawMandorlaEyeRelaxed(ctx, lx, eyeY, hw, hh, C.green, G.eyelid);
          drawMandorlaEyeRelaxed(ctx, rx, eyeY, hw, hh, C.green, G.eyelid);
          fillCircle(ctx, lx, eyeY-6, 4, C.bg);
          fillCircle(ctx, rx, eyeY-6, 4, C.bg);
          const vinylRot = now/4000*Math.PI*2;
          drawSigil(ctx, cx, sigilY, lerp(C.bg,C.red,0.35), 0.7, vinylRot);
          drawCircleStroke(ctx, cx, mouthY, 4, C.green);
          const nt1 = (t*2)%1, nt2 = (t*2+0.5)%1;
          const ny1 = mouthY-10-(35*nt1)|0, ny2 = mouthY-10-(35*nt2)|0;
          drawText(ctx, '~', cx+30, ny1, lerp(C.green,C.bg,nt1), 14);
          drawText(ctx, '*', cx+45, ny2, lerp(C.green,C.bg,nt2), 8);
        }
      }
    }

    // ── Dormant frame (just pulsing sigil symbol) ──
    function renderDormantFrame(canvas, startTime) {
      const ctx = _off.getContext('2d');
      ctx.fillStyle = rgb(C.bg);
      ctx.fillRect(0, 0, 320, 170);
      const now = Date.now() - startTime;
      const pulse = 0.3 + 0.2*Math.sin(now/3000*Math.PI*2);
      drawSigil(ctx, 160, 85, lerp(C.bg, C.red, pulse), 1.5);
      drawScanlines(ctx);
      _blit(canvas);
    }

    // ── Blit offscreen → visible canvas ──
    function _blit(canvas) {
      const vctx = canvas.getContext('2d');
      const dpr = window.devicePixelRatio || 1;
      const dw = canvas.clientWidth, dh = canvas.clientHeight;
      if (canvas.width !== dw*dpr || canvas.height !== dh*dpr) {
        canvas.width = dw*dpr; canvas.height = dh*dpr;
      }
      vctx.imageSmoothingEnabled = false;
      vctx.drawImage(_off, 0, 0, dw*dpr, dh*dpr);
    }

    // ── Full frame render (offscreen 320×170 → pixelated blit) ──
    function renderFrame(canvas, state, startTime) {
      const ctx = _off.getContext('2d');
      ctx.fillStyle = rgb(C.bg);
      ctx.fillRect(0, 0, 320, 170);
      const now = Date.now() - startTime;
      renderStates(ctx, now, state);
      drawScanlines(ctx);
      _blit(canvas);
    }

    // ── Mini render (header — smooth, not pixel-art) ──
    function renderMini(canvas, state, startTime) {
      const ctx = canvas.getContext('2d');
      const dpr = window.devicePixelRatio || 1;
      const dispW = canvas.clientWidth, dispH = canvas.clientHeight;
      if (canvas.width !== dispW*dpr || canvas.height !== dispH*dpr) {
        canvas.width = dispW*dpr; canvas.height = dispH*dpr;
      }
      const now = Date.now() - startTime;
      ctx.save(); ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, dispW, dispH);
      const cx = dispW/2, ey = dispH/2;
      const es = dispH*0.35, gr = dispH*0.6, ed = dispW*0.22;
      const COL = { eye:'#00ff41', glow:'#00ff41', bg:'#050208' };

      function miniGlowEye(ex, ey2, es2, col, gcol, gr2, inten) {
        inten = inten ?? 1;
        const gc = hexToRgb(gcol);
        const g1 = ctx.createRadialGradient(ex,ey2,0,ex,ey2,gr2*0.7*inten);
        g1.addColorStop(0, `rgba(${gc.r},${gc.g},${gc.b},${0.18*inten})`);
        g1.addColorStop(0.5, `rgba(${gc.r},${gc.g},${gc.b},${0.08*inten})`);
        g1.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = g1;
        ctx.beginPath(); ctx.arc(ex,ey2,gr2*0.7*inten,0,Math.PI*2); ctx.fill();
        const hw2=es2, hh2=es2*0.52;
        ctx.save(); ctx.beginPath();
        ctx.moveTo(ex-hw2,ey2); ctx.lineTo(ex,ey2-hh2); ctx.lineTo(ex+hw2,ey2); ctx.lineTo(ex,ey2+hh2);
        ctx.closePath(); ctx.clip();
        ctx.fillStyle = col; ctx.fillRect(ex-hw2,ey2-hh2,hw2*2,hh2*2);
        ctx.fillStyle = 'rgba(0,0,0,0.35)';
        for (let y2=ey2-hh2;y2<ey2+hh2;y2+=3) ctx.fillRect(ex-hw2,y2,hw2*2,1);
        ctx.fillStyle = COL.bg;
        ctx.fillRect(ex-hw2-1,ey2-hh2-1,hw2*2+2,(hh2*0.15|0)+1);
        ctx.restore();
        ctx.fillStyle = '#000';
        ctx.beginPath(); ctx.arc(ex,ey2+1,es2*0.13,0,Math.PI*2); ctx.fill();
      }
      function miniHappyEye(ex, ey2, es2, col, gcol, gr2) {
        const gc = hexToRgb(gcol);
        const g1=ctx.createRadialGradient(ex,ey2,0,ex,ey2,gr2*0.7);
        g1.addColorStop(0,`rgba(${gc.r},${gc.g},${gc.b},0.25)`);
        g1.addColorStop(1,'rgba(0,0,0,0)');
        ctx.fillStyle=g1; ctx.beginPath(); ctx.arc(ex,ey2,gr2*0.7,0,Math.PI*2); ctx.fill();
        ctx.strokeStyle=col; ctx.lineWidth=3.5; ctx.lineCap='round';
        ctx.beginPath(); ctx.arc(ex,ey2+es2*0.3,es2*0.8,Math.PI*1.15,Math.PI*1.85); ctx.stroke();
      }

      if (state==='SLEEPING') {
        ctx.strokeStyle=rgbaHex(COL.eye,0.3); ctx.lineWidth=2; ctx.lineCap='round';
        ctx.beginPath(); ctx.moveTo(cx-ed-es,ey); ctx.lineTo(cx-ed+es,ey); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(cx+ed-es,ey); ctx.lineTo(cx+ed+es,ey); ctx.stroke();
      } else if (state==='HAPPY'||state==='PROUD') {
        miniHappyEye(cx-ed,ey,es,COL.eye,COL.glow,gr);
        miniHappyEye(cx+ed,ey,es,COL.eye,COL.glow,gr);
      } else if (state==='ERROR') {
        ctx.strokeStyle='#ff0040'; ctx.lineWidth=3; ctx.lineCap='round';
        const xs=es*0.6;
        [cx-ed,cx+ed].forEach(ex2=>{
          ctx.beginPath(); ctx.moveTo(ex2-xs,ey-xs); ctx.lineTo(ex2+xs,ey+xs); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(ex2-xs,ey+xs); ctx.lineTo(ex2+xs,ey-xs); ctx.stroke();
        });
      } else if (state==='ALERT') {
        miniGlowEye(cx-ed,ey,es,'#ffaa00','#ffaa00',gr,1);
        miniGlowEye(cx+ed,ey,es,'#ffaa00','#ffaa00',gr,1);
      } else if (state==='THINKING'||state==='WORKING') {
        const p=0.6+0.4*Math.sin(now/800);
        miniGlowEye(cx-ed,ey-2,es,COL.eye,COL.glow,gr,p);
        miniGlowEye(cx+ed,ey-2,es,COL.eye,COL.glow,gr,p);
      } else {
        const breath=0.7+0.3*Math.sin(now/4000*Math.PI*2);
        const ec=lerpHex('#004415',COL.eye,breath);
        const dx2=2*Math.sin(now/5000), dy2=1*Math.cos(now/7000);
        miniGlowEye(cx-ed+dx2,ey+dy2,es,ec,COL.glow,gr,breath);
        miniGlowEye(cx+ed+dx2,ey+dy2,es,ec,COL.glow,gr,breath);
      }
      ctx.restore();
    }

    // Legacy compat
    const COL = { hood:'#3d1560',hoodEdge:'#6a2d9e',eye:'#00ff41',glow:'#00ff41',sigil:'#ff0040',bg:'#050208' };

    return { renderFrame, renderMini, renderDormantFrame, COL };
  })();

  // ── Sigil Widget State ──
  let _sigilState = 'IDLE';
  let _sigilStartTime = Date.now();
  let _sigilOnline = false;
  let _sigilStateTime = Date.now();
  let _sigilAnimFrame = null;
  let _sigilDormant = true;

  // Map API state → button text for highlight
  const _sigilBtnMap = {
    'HAPPY': 'HAPPY', 'THINKING': 'THINK', 'SLEEPING': 'SLEEP',
    'ALERT': 'ALERT', 'PROUD': 'PROUD', 'CURIOUS': 'CURIO', 'IDLE': 'IDLE'
  };

  function _updateSigilBtns(state) {
    const target = _sigilBtnMap[state];
    document.querySelectorAll('.btn-sigil-term').forEach(btn => {
      if (target && btn.textContent.trim() === target) {
        btn.classList.add('sigil-active');
      } else {
        btn.classList.remove('sigil-active');
      }
    });
  }

  function setSigilState(state) {
    if (state !== _sigilState) {
      _sigilState = state;
      _sigilStartTime = Date.now();
      _sigilStateTime = Date.now();
    }
    _sigilOnline = true;
    const moodEl = document.getElementById('sigil-mood-info');
    if (moodEl) moodEl.textContent = state;
    _updateSigilBtns(state);
  }

  function updateSigilIndicator(state) {
    const ind = document.getElementById('sigil-indicator');
    if (ind) {
      ind.setAttribute('data-state', state);
      ind.title = 'Sigil: ' + state;
      const label = document.getElementById('sigil-label');
      if (label) label.textContent = state;
    }
    setSigilState(state);
    // Auto-wake: quando arriva stato reale dal WS, esci da dormant
    if (_sigilDormant) wakeSigil();
  }

  // ── Wake sigil (click to activate) ──
  function wakeSigil() {
    if (!_sigilDormant) return;
    _sigilDormant = false;
    const label = document.getElementById('sigil-wake-label');
    if (label) label.style.display = 'none';
    const cmds = document.getElementById('sigil-commands');
    if (cmds) cmds.style.display = 'flex';
    const textRow = document.querySelector('.sigil-text-row');
    if (textRow) textRow.style.display = 'flex';
    const dbgToggle = document.querySelector('.sigil-debug-toggle');
    if (dbgToggle) dbgToggle.style.display = 'flex';
  }

  // ── Toggle debug controls ──
  function toggleSigilDebug() {
    const el = document.getElementById('sigil-debug-actions');
    if (el) el.style.display = el.style.display === 'none' ? 'flex' : 'none';
  }

  // ── Animation loop ──
  function _sigilAnimLoop() {
    const wc = document.getElementById('sigil-widget-canvas');
    if (wc && wc.offsetParent !== null) {
      if (_sigilDormant) {
        SigilEngine.renderDormantFrame(wc, _sigilStartTime);
      } else {
        SigilEngine.renderFrame(wc, _sigilState, _sigilStartTime);
      }
    }
    const mc = document.getElementById('sigil-header-canvas');
    if (mc && mc.offsetParent !== null) {
      SigilEngine.renderMini(mc, _sigilState, _sigilStartTime);
    }
    if (!_sigilDormant) {
      const timerEl = document.getElementById('sigil-mood-timer');
      if (timerEl) {
        const elapsed = Math.floor((Date.now() - _sigilStateTime) / 1000);
        if (elapsed < 60) timerEl.textContent = elapsed + 's';
        else if (elapsed < 3600) timerEl.textContent = Math.floor(elapsed/60) + 'm ' + (elapsed%60) + 's';
        else timerEl.textContent = Math.floor(elapsed/3600) + 'h ' + Math.floor((elapsed%3600)/60) + 'm';
      }
    }
    _sigilAnimFrame = requestAnimationFrame(_sigilAnimLoop);
  }

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

  function scrollToSigilWidget() {
    switchView('dashboard');
    setTimeout(() => {
      const el = document.getElementById('sigil-widget-wrap');
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 100);
  }
