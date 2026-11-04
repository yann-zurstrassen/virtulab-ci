/* The virtual board, drawn as hardware: the chip in the middle, one connector per bus, and each
 * sensor as a breakout module wired to its connector. Shared by the setup page and the board view.
 * VirtuBoard.draw(svg, { board, modules, emptyText }) returns handles the pages animate. */
(function () {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";

  // How each catalog sensor looks: the breakout colour, the part name printed on it, what it does.
  const STYLE = {
    mpu6050:    { color: "#6b3fa0", chip: "MPU-6050",  kind: "6-axis motion sensor" },
    adxl345:    { color: "#7a3f8f", chip: "ADXL345",   kind: "accelerometer" },
    sht31:      { color: "#1f5fa8", chip: "SHT31",     kind: "temperature & humidity" },
    tmp108:     { color: "#1d6f8a", chip: "TMP108",    kind: "temperature sensor" },
    bmp180:     { color: "#2b5d9c", chip: "BMP180",    kind: "pressure & temperature" },
    ina219:     { color: "#8a5a1d", chip: "INA219",    kind: "current & power monitor" },
    max31855:   { color: "#9a3b3b", chip: "MAX31855",  kind: "thermocouple converter" },
    w25q128:    { color: "#3d4f63", chip: "W25Q128",   kind: "16 MiB SPI flash" },
    at_modem:   { color: "#2f6b4f", chip: "AT modem",  kind: "cellular modem" },
    modbus_rtu: { color: "#5a4a8a", chip: "Modbus RTU", kind: "temperature transmitter" },
    nmea_gps:   { color: "#2d6a6a", chip: "GPS",       kind: "NMEA receiver" },
  };
  function style(model) {
    const key = String(model || "").toLowerCase().replace(/[^a-z0-9_]/g, "");
    return STYLE[key] || { color: "#3a4560", chip: String(model || "device").toUpperCase(), kind: "custom device" };
  }
  // The part number on the chip package, from the board's description.
  function partNumber(board) {
    const words = String(board.description || board.title || board.id || "").split(/\s+/);
    return words.find(w => /\d/.test(w) && w.length >= 5) || board.id || "MCU";
  }

  function draw(svg, opts) {
    const board = opts.board || {}, modules = opts.modules || [];
    svg.replaceChildren();
    const el = (tag, attrs, parent, text) => {
      const e = document.createElementNS(NS, tag);
      for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
      if (text !== undefined) e.textContent = text;
      (parent || svg).appendChild(e);
      return e;
    };
    const defs = el("defs", {});
    defs.innerHTML = `
      <linearGradient id="vb-pcb" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0f4a39"/><stop offset="1" stop-color="#0a3328"/></linearGradient>
      <linearGradient id="vb-chip" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2a2d33"/><stop offset="1" stop-color="#16181c"/></linearGradient>
      <linearGradient id="vb-gold" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f4d58a"/><stop offset="1" stop-color="#b98b2e"/></linearGradient>
      <linearGradient id="vb-silver" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e6e9ee"/><stop offset="1" stop-color="#8d939c"/></linearGradient>
      <filter id="vb-glow" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="5" result="b"/>
        <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
      <filter id="vb-shadow" x="-10%" y="-10%" width="130%" height="130%"><feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="#000" flood-opacity=".55"/></filter>
      <pattern id="vb-dots" width="14" height="14" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".9" fill="#ffffff" opacity=".05"/></pattern>`;

    // the main board
    const B = { x: 30, y: 40, w: 560, h: 560 };
    const pcb = el("g", { filter: "url(#vb-shadow)" });
    el("rect", { x: B.x, y: B.y, width: B.w, height: B.h, rx: 22, fill: "url(#vb-pcb)", stroke: "#1d6b54", "stroke-width": 2 }, pcb);
    el("rect", { x: B.x, y: B.y, width: B.w, height: B.h, rx: 22, fill: "url(#vb-dots)" });
    const deco = el("g", { stroke: "#1f7a5e", "stroke-width": 2, fill: "none", opacity: .45 });
    [[90,120,170,120,170,220],[90,160,140,160,140,250,230,250],[520,110,450,110,450,230],[520,150,480,150,480,260,400,260],
     [100,520,180,520,180,420,240,420],[500,520,430,520,430,400],[300,500,300,400],[340,560,340,410],[120,320,230,320],[120,360,230,360]]
      .forEach(p => el("polyline", { points: p.join(" ") }, deco));
    for (const [cx, cy] of [[B.x+24,B.y+24],[B.x+B.w-24,B.y+24],[B.x+24,B.y+B.h-24],[B.x+B.w-24,B.y+B.h-24]]) {
      el("circle", { cx, cy, r: 11, fill: "url(#vb-gold)" }); el("circle", { cx, cy, r: 6, fill: "#0b0d12" });
    }
    for (const x of [B.x + 22, B.x + B.w - 34]) for (let i = 0; i < 22; i++) for (let c = 0; c < 2; c++) {
      el("rect", { x: x + c * 12 - 6, y: B.y + 70 + i * 19, width: 10, height: 10, rx: 1.5, fill: "#111", stroke: "#2b2b2b" });
      el("rect", { x: x + c * 12 - 3.5, y: B.y + 72.5 + i * 19, width: 5, height: 5, fill: "url(#vb-gold)" });
    }
    el("rect", { x: 255, y: 22, width: 70, height: 42, rx: 5, fill: "url(#vb-silver)", stroke: "#666" });
    el("rect", { x: 268, y: 30, width: 44, height: 12, rx: 2, fill: "#3a3f47" });
    el("rect", { x: 195, y: 205, width: 46, height: 18, rx: 9, fill: "url(#vb-silver)", stroke: "#777" });
    for (const [x, y] of [[372,200],[386,200],[400,200],[200,400],[214,400],[372,414],[386,414],[180,280],[180,294]])
      el("rect", { x, y, width: 9, height: 6, rx: 1, fill: "#c9a46a", stroke: "#7a5f30", "stroke-width": .6 });
    el("text", { x: B.x + 70, y: B.y + 48, fill: "#e8f5ee", opacity: .85, "font-size": 15, "font-weight": 700, "letter-spacing": 2 }, null, "VIRTUAL BOARD");
    el("text", { x: B.x + 70, y: B.y + 64, fill: "#e8f5ee", opacity: .55, "font-size": 11, "letter-spacing": 1 }, null,
       String(board.description || board.title || "").toUpperCase());

    // the microcontroller
    const M = { x: 228, y: 228, s: 150 };
    for (let side = 0; side < 4; side++) for (let i = 0; i < 18; i++) {
      const o = 12 + i * 7.1;
      const r = side === 0 ? { x: M.x + o, y: M.y - 9, width: 3, height: 9 } : side === 1 ? { x: M.x + M.s, y: M.y + o, width: 9, height: 3 }
              : side === 2 ? { x: M.x + o, y: M.y + M.s, width: 3, height: 9 } : { x: M.x - 9, y: M.y + o, width: 9, height: 3 };
      el("rect", Object.assign(r, { fill: "url(#vb-silver)" }));
    }
    el("rect", { x: M.x, y: M.y, width: M.s, height: M.s, rx: 6, fill: "url(#vb-chip)", stroke: "#3b3f47", "stroke-width": 1.5 });
    el("circle", { cx: M.x + 16, cy: M.y + 16, r: 5, fill: "#0d0e10", stroke: "#444" });
    el("text", { x: M.x + M.s / 2, y: M.y + 70, "text-anchor": "middle", fill: "#d9dde4", "font-size": 15, "font-weight": 700, "letter-spacing": 1 }, null, partNumber(board));
    el("text", { x: M.x + M.s / 2, y: M.y + 90, "text-anchor": "middle", fill: "#8d939e", "font-size": 11 }, null, board.cpu || "");
    el("text", { x: M.x + M.s / 2, y: M.y + 108, "text-anchor": "middle", fill: "#5aa9ff", "font-size": 10, opacity: .8 }, null,
       opts.chipNote || "running your firmware");
    const mcuGlow = el("rect", { x: M.x - 4, y: M.y - 4, width: M.s + 8, height: M.s + 8, rx: 9, fill: "none", stroke: "#5aa9ff", "stroke-width": 2, opacity: 0 });

    // status LEDs
    const leds = {};
    [["act", "BUS", "#4fd18b", 450], ["alarm", "ALARM", "#ff4545", 490], ["warn", "FAULT", "#ffc94d", 530]].forEach(([k, label, c, x]) => {
      el("rect", { x: x - 9, y: 470, width: 18, height: 10, rx: 2, fill: "#d8d8d8", opacity: .9 });
      const lens = el("rect", { x: x - 7, y: 471.5, width: 14, height: 7, rx: 2, fill: c, opacity: .18 });
      const halo = el("circle", { cx: x, cy: 475, r: 15, fill: c, opacity: 0, filter: "url(#vb-glow)" });
      el("text", { x, y: 498, "text-anchor": "middle", fill: "#e8f5ee", opacity: .7, "font-size": 9, "letter-spacing": 1 }, null, label);
      leds[k] = { lens, halo, on: false };
    });

    // one connector per bus, with its modules stacked beside the board
    const buses = [...new Set(modules.map(m => m.bus))];
    const paths = {}, cards = {};
    const moduleH = Math.min(170, (560 - 20 * (modules.length - 1)) / Math.max(1, modules.length));
    let slot = 0;
    buses.forEach((b, bi) => {
      const on = modules.filter(m => m.bus === b);
      const hy = 290 + bi * 70, hx = B.x + B.w - 70;
      el("path", { d: `M${M.x + M.s + 9} ${M.y + 60 + bi * 30} H${M.x + M.s + 50} L${hx - 30} ${hy - 6} H${hx}`, stroke: "#c08a2e", "stroke-width": 3, fill: "none", opacity: .85 });
      el("path", { d: `M${M.x + M.s + 9} ${M.y + 70 + bi * 30} H${M.x + M.s + 40} L${hx - 30} ${hy + 6} H${hx}`, stroke: "#c08a2e", "stroke-width": 3, fill: "none", opacity: .85 });
      el("rect", { x: hx, y: hy - 16, width: 26, height: 32, rx: 3, fill: "#111", stroke: "#333" });
      for (let i = 0; i < 4; i++) el("rect", { x: hx + 9, y: hy - 13 + i * 7.5, width: 8, height: 5, fill: "url(#vb-gold)" });
      el("text", { x: hx - 4, y: hy - 22, "text-anchor": "end", fill: "#e8f5ee", opacity: .8, "font-size": 11, "font-weight": 700, "letter-spacing": 1 }, null, String(b).toUpperCase());
      const pins = /^i2c/.test(b) ? "SCL · SDA · 3V3 · GND" : /^spi/.test(b) ? "SCK · MISO · MOSI · CS" : /uart|usart/.test(b) ? "TX · RX · 3V3 · GND" : "";
      el("text", { x: hx - 4, y: hy + 30, "text-anchor": "end", fill: "#e8f5ee", opacity: .5, "font-size": 9 }, null, pins);
      on.forEach(mod => {
        const y = 40 + slot * (moduleH + 20), x = 690, w = 280, h = moduleH;
        const st = style(mod.model);
        const group = el("g", { class: "vb-module" });
        const wire = (dy, c, w2) => el("path", { d: `M${hx + 26} ${hy - 9 + dy} C ${hx + 80} ${hy - 9 + dy}, ${x - 60} ${y + 34 + dy}, ${x} ${y + 34 + dy}`,
                                                 stroke: c, "stroke-width": w2, fill: "none", "stroke-linecap": "round", opacity: .9 }, group);
        wire(0, "#ffd24a", 3); const main = wire(7.5, "#4aa3ff", 3); wire(15, "#e04848", 2.5); wire(22.5, "#202020", 2.5);
        paths[mod.name] = { el: main, len: 0 };
        const shadowed = el("g", { filter: "url(#vb-shadow)" }, group);
        const body = el("rect", { x, y, width: w, height: h, rx: 12, fill: st.color, stroke: "#ffffff22", "stroke-width": 1.5 }, shadowed);
        el("rect", { x, y, width: w, height: h, rx: 12, fill: "url(#vb-dots)" }, group);
        for (let i = 0; i < 4; i++) el("circle", { cx: x + 14, cy: y + 34 + i * 7.5, r: 3.2, fill: "url(#vb-gold)" }, group);
        el("rect", { x: x + 34, y: y + 24, width: 44, height: 44, rx: 4, fill: "url(#vb-chip)", stroke: "#444" }, group);
        el("circle", { cx: x + 40, cy: y + 30, r: 2, fill: "#555" }, group);
        el("text", { x: x + 90, y: y + 30, fill: "#fff", "font-size": 15, "font-weight": 700 }, group, st.chip);
        el("text", { x: x + 90, y: y + 46, fill: "#ffffffb0", "font-size": 11 }, group, `${mod.name} · ${st.kind}`);
        el("text", { x: x + 90, y: y + 61, fill: "#ffffff80", "font-size": 10.5, "font-family": "ui-monospace, Menlo, monospace" }, group,
           `${mod.bus}${mod.address != null ? " · 0x" + Number(mod.address).toString(16) : ""}${mod.cs ? " · CS " + mod.cs : ""}`);
        let big = null, bigLabel = null, rows = [];
        if (h >= 120) {
          el("rect", { x: x + 12, y: y + 78, width: w - 24, height: h - 90, rx: 8, fill: "#06080cdd", stroke: "#ffffff1a" }, group);
          big = el("text", { x: x + 24, y: y + 108, fill: "#fff", "font-size": 24, "font-weight": 700, "font-family": "ui-monospace, Menlo, monospace" }, group, opts.idleValue || "—");
          bigLabel = el("text", { x: x + 24, y: y + 124, fill: "#8b94a7", "font-size": 10.5 }, group, opts.idleLabel || "waiting for the first reading");
          rows = [0, 1, 2].map(i => el("text", { x: x + w - 24, y: y + 100 + i * 15, "text-anchor": "end", fill: "#c8cedb", "font-size": 11.5,
                                                 "font-family": "ui-monospace, Menlo, monospace" }, group, ""));
        }
        const halo = el("rect", { x: x - 3, y: y - 3, width: w + 6, height: h + 6, rx: 14, fill: "none", stroke: "#fff", "stroke-width": 2, opacity: 0 }, group);
        cards[mod.name] = { big, bigLabel, rows, halo, body, group };
        slot++;
      });
    });
    if (!modules.length)
      el("text", { x: 780, y: 320, "text-anchor": "middle", fill: "#8b94a7", "font-size": 15 }, null, opts.emptyText || "No sensors on a bus");
    el("path", { d: `M${M.x + 60} ${M.y + M.s + 9} V${B.y + B.h - 60} H${B.x + 60}`, stroke: "#c08a2e", "stroke-width": 3, fill: "none", opacity: .7 });
    el("text", { x: B.x + 62, y: B.y + B.h - 68, fill: "#e8f5ee", opacity: .6, "font-size": 10, "letter-spacing": 1 }, null, "USART2 → CONSOLE");
    const pulseLayer = el("g", {});
    Object.values(paths).forEach(p => p.len = p.el.getTotalLength());
    return { paths, cards, mcuGlow, leds, pulseLayer };
  }

  window.VirtuBoard = { draw, style };
})();
