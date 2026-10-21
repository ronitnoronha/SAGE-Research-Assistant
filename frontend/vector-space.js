// vector-space.js - AMBIENT THREE.JS BACKGROUND: DOCUMENT CHUNKS AS CLUSTERS IN EMBEDDING SPACE
// While a query runs, a query point appears and links to its nearest chunks (top-k retrieval).
(function () {
    const canvas = document.getElementById("vector-space");
    const noop = { setThinking() {} };
    if (!canvas || !window.THREE) { window.SageSpace = noop; return; }

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

    let renderer;
    try {
        renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    } catch (e) {
        window.SageSpace = noop; return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
    camera.position.set(0, 0, 9);

    // Round sprite for points
    const dot = document.createElement("canvas");
    dot.width = dot.height = 64;
    const g = dot.getContext("2d");
    g.beginPath(); g.arc(32, 32, 28, 0, Math.PI * 2); g.fillStyle = "#fff"; g.fill();
    const sprite = new THREE.CanvasTexture(dot);

    // Clusters of "chunks"
    const CLUSTERS = 7, PER = 70;
    const positions = [], colors = [];
    const gauss = () => (Math.random() + Math.random() + Math.random() - 1.5) * 0.9;
    for (let c = 0; c < CLUSTERS; c++) {
        const phi = Math.acos(1 - 2 * (c + 0.5) / CLUSTERS), th = Math.PI * (1 + Math.sqrt(5)) * c;
        const cx = Math.sin(phi) * Math.cos(th) * 2.6, cy = Math.cos(phi) * 2.6, cz = Math.sin(phi) * Math.sin(th) * 2.6;
        for (let i = 0; i < PER; i++) positions.push(cx + gauss(), cy + gauss(), cz + gauss());
    }
    const count = positions.length / 3;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geo.setAttribute("color", new THREE.Float32BufferAttribute(new Float32Array(count * 3), 3));
    const pointsMat = new THREE.PointsMaterial({
        size: 0.075, map: sprite, alphaTest: 0.2, transparent: true, opacity: 0.85, vertexColors: true, depthWrite: false
    });
    const points = new THREE.Points(geo, pointsMat);

    // Query point + retrieval links
    const K = 6;
    const query = new THREE.Mesh(new THREE.SphereGeometry(0.09, 16, 16), new THREE.MeshBasicMaterial());
    const linkGeo = new THREE.BufferGeometry();
    linkGeo.setAttribute("position", new THREE.Float32BufferAttribute(new Float32Array(K * 6), 3));
    const linkMat = new THREE.LineBasicMaterial({ transparent: true, opacity: 0 });
    const links = new THREE.LineSegments(linkGeo, linkMat);
    query.visible = false;

    const group = new THREE.Group();
    group.add(points, links, query);
    scene.add(group);

    let nearest = [];
    function applyTheme() {
        const muted = new THREE.Color(css("--muted") || "#68716b");
        const accent = new THREE.Color(css("--accent") || "#3d6a50");
        const col = geo.attributes.color;
        for (let i = 0; i < count; i++) {
            const c = nearest.includes(i) ? accent : muted;
            col.setXYZ(i, c.r, c.g, c.b);
        }
        col.needsUpdate = true;
        query.material.color.copy(accent);
        linkMat.color.copy(accent);
    }
    applyTheme();
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);

    function resize() {
        const w = canvas.clientWidth, h = canvas.clientHeight;
        if (!w || !h) return;
        renderer.setSize(w, h, false);
        camera.aspect = w / h;
        camera.position.z = w < 600 ? 12 : 9;
        // On wide screens keep the cloud to the right of the welcome text
        group.position.x = w > 900 ? 2.6 : 0;
        camera.updateProjectionMatrix();
    }
    new ResizeObserver(resize).observe(canvas);
    resize();

    // Retrieval animation state
    let thinking = false, linkProgress = 0, speed = 1;
    function pickQuery() {
        const q = new THREE.Vector3((Math.random() - .5) * 3, (Math.random() - .5) * 3, (Math.random() - .5) * 3);
        query.position.copy(q);
        const pos = geo.attributes.position;
        const d = [];
        for (let i = 0; i < count; i++) {
            const dx = pos.getX(i) - q.x, dy = pos.getY(i) - q.y, dz = pos.getZ(i) - q.z;
            d.push([dx * dx + dy * dy + dz * dz, i]);
        }
        d.sort((a, b) => a[0] - b[0]);
        nearest = d.slice(0, K).map(x => x[1]);
        applyTheme();
    }
    function updateLinks() {
        const pos = geo.attributes.position, arr = linkGeo.attributes.position.array, q = query.position;
        nearest.forEach((idx, k) => {
            const t = Math.min(1, Math.max(0, linkProgress * 1.6 - k * 0.12));
            arr[k * 6] = q.x; arr[k * 6 + 1] = q.y; arr[k * 6 + 2] = q.z;
            arr[k * 6 + 3] = q.x + (pos.getX(idx) - q.x) * t;
            arr[k * 6 + 4] = q.y + (pos.getY(idx) - q.y) * t;
            arr[k * 6 + 5] = q.z + (pos.getZ(idx) - q.z) * t;
        });
        linkGeo.attributes.position.needsUpdate = true;
    }

    window.SageSpace = {
        setThinking(on) {
            thinking = on;
            if (on) { pickQuery(); linkProgress = 0; query.visible = true; }
        }
    };

    let last = performance.now();
    function frame(now) {
        requestAnimationFrame(frame);
        if (document.hidden) { last = now; return; }
        const dt = Math.min((now - last) / 1000, 0.05);
        last = now;

        speed += ((thinking ? 3.5 : 1) - speed) * 0.04;
        if (!reduceMotion) {
            group.rotation.y += dt * 0.05 * speed;
            group.rotation.x = Math.sin(now * 0.00012) * 0.15;
        }

        if (thinking) {
            linkProgress = Math.min(1, linkProgress + dt * 0.9);
            linkMat.opacity += (0.8 - linkMat.opacity) * 0.08;
        } else {
            linkMat.opacity *= 0.93;
            if (linkMat.opacity < 0.02 && query.visible) {
                query.visible = false; nearest = []; applyTheme();
            }
        }
        if (query.visible) {
            updateLinks();
            const s = 1 + Math.sin(now * 0.006) * 0.25;
            query.scale.setScalar(s);
        }
        renderer.render(scene, camera);
    }
    requestAnimationFrame(frame);
})();
