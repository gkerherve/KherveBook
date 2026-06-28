"""JavaScript / HTML cell examples (Examples menu, "JavaScript" category).

Each example pairs a markdown heading describing the demo with a single
JavaScript cell holding an HTML+JS snippet. The snippet is rendered in
the cell's Chromium web view (see ``jscell.py``): because every snippet
carries HTML tags (``<canvas>``, ``<div>``, ``<script>``, ...) it loads
as a full page. Self-contained canvas demos need no network; the library
demos pull a chart library from a public CDN, so they need internet
access at run time (each says so in its heading).

Brand colours: blue ``#3776ab`` / orange ``#e07b39``.

This module is self-contained — it defines its own ``_md``/``_js``
helpers and exports ``JS_EXAMPLES`` rather than importing anything from
``examples.py``.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""


def _md(t):
    return {"type": "markdown", "source": t}


def _js(s):
    return {"type": "js", "source": s}


# -- 1. Self-contained canvas animation -------------------------------------

_CANVAS_BALLS = r"""<canvas id="c" width="440" height="320"
        style="border:1px solid #ccc;border-radius:6px"></canvas>
<script>
const cv = document.getElementById("c");
const ctx = cv.getContext("2d");
const W = cv.width, H = cv.height;
const COLORS = ["#3776ab", "#e07b39", "#2e7d4f", "#c0392b", "#8e44ad"];
const balls = [];
for (let i = 0; i < 18; i++) {
    balls.push({
        x: Math.random() * W, y: Math.random() * H,
        vx: (Math.random() - 0.5) * 4, vy: (Math.random() - 0.5) * 4,
        r: 8 + Math.random() * 14,
        c: COLORS[i % COLORS.length]
    });
}
function frame() {
    ctx.fillStyle = "rgba(255,255,255,0.35)";
    ctx.fillRect(0, 0, W, H);
    for (const b of balls) {
        b.x += b.vx; b.y += b.vy;
        if (b.x < b.r || b.x > W - b.r) b.vx *= -1;
        if (b.y < b.r || b.y > H - b.r) b.vy *= -1;
        ctx.beginPath();
        ctx.arc(b.x, b.y, b.r, 0, Math.PI * 2);
        ctx.fillStyle = b.c;
        ctx.fill();
    }
    requestAnimationFrame(frame);
}
frame();
</script>"""


def _canvas_balls():
    return [
        _md("# Bouncing Balls (canvas)\nA self-contained HTML5 `<canvas>` "
            "animation driven by `requestAnimationFrame` — 18 coloured "
            "balls bounce off the walls with a fading trail. No network "
            "needed; everything runs in the cell's web view."),
        _js(_CANVAS_BALLS),
    ]


# -- 2. Chart.js bar chart (CDN) --------------------------------------------

_CHARTJS = r"""<canvas id="bar" width="480" height="300"></canvas>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
window.addEventListener("load", function () {
    const ctx = document.getElementById("bar").getContext("2d");
    new Chart(ctx, {
        type: "bar",
        data: {
            labels: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            datasets: [{
                label: "Visitors",
                data: [120, 190, 170, 220, 260, 90, 60],
                backgroundColor: "#3776ab",
                hoverBackgroundColor: "#e07b39",
                borderRadius: 4
            }]
        },
        options: {
            responsive: false,
            plugins: { legend: { display: true } },
            scales: { y: { beginAtZero: true } }
        }
    });
});
</script>"""


def _chartjs_bar():
    return [
        _md("# Chart.js Bar Chart\nA bar chart drawn with **Chart.js** "
            "loaded from a CDN. Hover a bar to highlight it in orange. "
            "*Needs internet* — the library is fetched from "
            "`cdn.jsdelivr.net` at run time."),
        _js(_CHARTJS),
    ]


# -- 3. D3 bar chart (CDN) --------------------------------------------------

_D3 = r"""<div id="chart"></div>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
window.addEventListener("load", function () {
    const data = [
        { name: "A", value: 30 }, { name: "B", value: 80 },
        { name: "C", value: 45 }, { name: "D", value: 60 },
        { name: "E", value: 20 }, { name: "F", value: 90 },
        { name: "G", value: 55 }
    ];
    const W = 480, H = 300, m = { top: 20, right: 20, bottom: 30, left: 40 };
    const svg = d3.select("#chart").append("svg")
        .attr("width", W).attr("height", H);
    const x = d3.scaleBand()
        .domain(data.map(d => d.name))
        .range([m.left, W - m.right]).padding(0.2);
    const y = d3.scaleLinear()
        .domain([0, d3.max(data, d => d.value)]).nice()
        .range([H - m.bottom, m.top]);
    svg.append("g").attr("transform", `translate(0,${H - m.bottom})`)
        .call(d3.axisBottom(x));
    svg.append("g").attr("transform", `translate(${m.left},0)`)
        .call(d3.axisLeft(y));
    svg.selectAll("rect").data(data).join("rect")
        .attr("x", d => x(d.name)).attr("y", d => y(d.value))
        .attr("width", x.bandwidth())
        .attr("height", d => H - m.bottom - y(d.value))
        .attr("fill", "#3776ab")
        .on("mouseover", function () { d3.select(this).attr("fill", "#e07b39"); })
        .on("mouseout", function () { d3.select(this).attr("fill", "#3776ab"); });
});
</script>"""


def _d3_bar():
    return [
        _md("# D3 Bar Chart\nA bar chart built with **D3 v7** — scales, "
            "axes and SVG rectangles, with an orange hover. *Needs "
            "internet*: D3 is loaded from `d3js.org`."),
        _js(_D3),
    ]


# -- 4. Plotly 3D surface (CDN) ---------------------------------------------

_PLOTLY = r"""<div id="surf" style="width:520px;height:380px"></div>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<script>
window.addEventListener("load", function () {
    const n = 40, z = [];
    for (let i = 0; i < n; i++) {
        const row = [];
        for (let j = 0; j < n; j++) {
            const x = (i - n / 2) / 5, y = (j - n / 2) / 5;
            row.push(Math.sin(Math.sqrt(x * x + y * y)));
        }
        z.push(row);
    }
    Plotly.newPlot("surf", [{
        z: z, type: "surface", colorscale: "Viridis", showscale: true
    }], {
        title: "z = sin(√(x² + y²))",
        margin: { l: 0, r: 0, t: 40, b: 0 },
        scene: { aspectratio: { x: 1, y: 1, z: 0.6 } }
    }, { responsive: false });
});
</script>"""


def _plotly_surface():
    return [
        _md("# Plotly 3D Surface\nAn interactive **Plotly** surface of a "
            "radial sine — drag to rotate, scroll to zoom, hover to read "
            "values. *Needs internet*: Plotly is loaded from "
            "`cdn.plot.ly`."),
        _js(_PLOTLY),
    ]


# -- 5. Interactive slider -> canvas sine wave ------------------------------

_SLIDER = r"""<div style="font-family:system-ui,Arial,sans-serif">
  <label>Frequency:
    <input id="freq" type="range" min="1" max="20" value="5" step="1">
  </label>
  <span id="val">5</span> Hz
</div>
<canvas id="wave" width="440" height="220"
        style="border:1px solid #ccc;border-radius:6px;margin-top:6px"></canvas>
<script>
const cv = document.getElementById("wave");
const ctx = cv.getContext("2d");
const W = cv.width, H = cv.height;
const slider = document.getElementById("freq");
const label = document.getElementById("val");
function draw() {
    const f = +slider.value;
    label.textContent = f;
    ctx.clearRect(0, 0, W, H);
    ctx.strokeStyle = "#eee";
    ctx.beginPath(); ctx.moveTo(0, H / 2); ctx.lineTo(W, H / 2); ctx.stroke();
    ctx.strokeStyle = "#3776ab";
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let x = 0; x <= W; x++) {
        const y = H / 2 - (H / 2 - 12) * Math.sin(2 * Math.PI * f * x / W);
        if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
}
slider.addEventListener("input", draw);
draw();
</script>"""


def _slider_wave():
    return [
        _md("# Interactive Sine Slider\nA `<input type=range>` slider "
            "wired to a `<canvas>`: drag it to change the frequency of "
            "the sine wave, redrawn live. Self-contained — no network "
            "needed."),
        _js(_SLIDER),
    ]


# -- 6. three.js spinning cube (CDN) ----------------------------------------

_THREE = r"""<div id="box" style="width:440px;height:320px"></div>
<script src="https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js"></script>
<script>
window.addEventListener("load", function () {
    const mount = document.getElementById("box");
    const W = 440, H = 320;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf4f7fb);
    const camera = new THREE.PerspectiveCamera(60, W / H, 0.1, 100);
    camera.position.z = 4;
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(W, H);
    mount.appendChild(renderer.domElement);
    const cube = new THREE.Mesh(
        new THREE.BoxGeometry(1.6, 1.6, 1.6),
        new THREE.MeshStandardMaterial({ color: 0x3776ab })
    );
    scene.add(cube);
    const light = new THREE.DirectionalLight(0xffffff, 1.4);
    light.position.set(3, 4, 5);
    scene.add(light, new THREE.AmbientLight(0xe07b39, 0.5));
    function animate() {
        requestAnimationFrame(animate);
        cube.rotation.x += 0.012;
        cube.rotation.y += 0.016;
        renderer.render(scene, camera);
    }
    animate();
});
</script>"""


def _three_cube():
    return [
        _md("# three.js Spinning Cube\nA lit, rotating 3D cube rendered "
            "with **three.js** and WebGL. *Needs internet*: three.js is "
            "loaded from `cdn.jsdelivr.net`."),
        _js(_THREE),
    ]


# -- Registry ---------------------------------------------------------------

JS_EXAMPLES = [
    # (name, category, builder)
    ("Bouncing Balls (canvas)", "JavaScript", _canvas_balls),
    ("Chart.js Bar Chart",      "JavaScript", _chartjs_bar),
    ("D3 Bar Chart",            "JavaScript", _d3_bar),
    ("Plotly 3D Surface",       "JavaScript", _plotly_surface),
    ("Sine Slider (canvas)",    "JavaScript", _slider_wave),
    ("three.js Spinning Cube",  "JavaScript", _three_cube),
]
