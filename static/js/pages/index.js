// Roster page: a spinnable globe of fighter hexes (default) or the classic grid.
(() => {
    const section = document.getElementById('rosterSection');
    const search = document.getElementById('rosterSearch');
    const gridCards = [...document.querySelectorAll('.fighter-card')];
    const stage = document.getElementById('globeStage');
    const globe = document.getElementById('globe');
    const tiles = [...globe.querySelectorAll('.globe-tile')];
    const hint = document.getElementById('globeHint');
    const card = document.getElementById('globeCard');
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const DEG = Math.PI / 180;

    // ---- View toggle -------------------------------------------------------
    const viewButtons = [...document.querySelectorAll('.roster-view-toggle button')];
    function setView(view) {
        section.dataset.view = view;
        viewButtons.forEach(b => b.classList.toggle('active', b.dataset.view === view));
        try { localStorage.setItem('rosterView', view); } catch (e) { /* private mode */ }
        if (view === 'globe') { loadTileImages(); layout(); wake(); }
        applyFilters();
    }
    viewButtons.forEach(b => b.addEventListener('click', () => setView(b.dataset.view)));

    // Browser lazy-loading doesn't work inside 3D transforms, so load the globe's
    // portraits ourselves, and only once the globe is actually shown.
    let tileImagesLoaded = false;
    function loadTileImages() {
        if (tileImagesLoaded) return;
        tileImagesLoaded = true;
        tiles.forEach(tile => {
            const img = tile.querySelector('img[data-src]');
            if (img) img.src = img.dataset.src;
        });
    }

    // ---- Geometry: a Goldberg polyhedron (the "soccer ball" tiling) ---------------
    // A sphere can only be tiled seamlessly with hexagons if exactly 12 pentagons are
    // mixed in. Subdividing an icosahedron and taking its dual gives that tiling:
    // frequency 3 -> 92 faces (80 hexagons + 12 pentagons).
    const N = tiles.length;
    const v3 = {
        add: (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]],
        scale: (a, k) => [a[0] * k, a[1] * k, a[2] * k],
        dot: (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2],
        cross: (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]],
        norm: a => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; },
    };

    // Tangent basis for a face: u points "right" and v points "down" on screen when the
    // face is at the front, so pictures stay upright. Uses CSS axes (y down, z toward viewer).
    function faceBasis(n) {
        let u = v3.cross([0, 1, 0], n);
        if (Math.hypot(u[0], u[1], u[2]) < 1e-6) u = [1, 0, 0];
        u = v3.norm(u);
        return [u, v3.cross(n, u)];
    }

    function buildGoldberg(freq) {
        const t = (1 + Math.sqrt(5)) / 2;
        const ico = [[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t],
            [0, -1, -t], [0, 1, -t], [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]].map(v3.norm);
        const icoFaces = [[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11], [1, 5, 9], [5, 11, 4],
            [11, 10, 2], [10, 7, 6], [7, 1, 8], [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9],
            [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1]];
        const verts = [];
        const index = new Map();
        const addVert = p => {
            const v = v3.norm(p);
            const key = v.map(x => Math.round(x * 1e5)).join(',');
            if (!index.has(key)) { index.set(key, verts.length); verts.push(v); }
            return index.get(key);
        };
        const tris = [];
        icoFaces.forEach(([a, b, c]) => {
            const A = ico[a], B = ico[b], C = ico[c];
            const grid = [];
            for (let i = 0; i <= freq; i++) {
                grid[i] = [];
                for (let j = 0; j <= freq - i; j++) {
                    const k = freq - i - j;
                    grid[i][j] = addVert(v3.add(v3.add(v3.scale(A, k), v3.scale(B, i)), v3.scale(C, j)));
                }
            }
            for (let i = 0; i < freq; i++) {
                for (let j = 0; j < freq - i; j++) {
                    tris.push([grid[i][j], grid[i + 1][j], grid[i][j + 1]]);
                    if (j < freq - i - 1) tris.push([grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]]);
                }
            }
        });
        // Dual: one face per subdivision vertex; its corners are the centers of the
        // triangles around that vertex, sorted by angle.
        const around = verts.map(() => []);
        const centers = tris.map((tri, ti) => {
            tri.forEach(v => around[v].push(ti));
            return v3.norm(v3.add(v3.add(verts[tri[0]], verts[tri[1]]), verts[tri[2]]));
        });
        return verts.map((n, vi) => {
            const [u, v] = faceBasis(n);
            const corners = around[vi].map(ti => centers[ti])
                .sort((p, q) => Math.atan2(v3.dot(p, v), v3.dot(p, u)) - Math.atan2(v3.dot(q, v), v3.dot(q, u)));
            return { n, u, v, corners, sides: corners.length };
        });
    }

    // Smallest tiling with room for every fighter (frequency 3 fits up to 80).
    let freq = 3;
    while (10 * freq * freq - 10 < N) freq++;
    const faces = buildGoldberg(freq);
    const pentagons = faces.filter(f => f.sides === 5);
    let freeHexes = faces.filter(f => f.sides === 6);
    const takeNearest = dir => {
        let best = 0, bestDot = -Infinity;
        freeHexes.forEach((f, i) => { const d = v3.dot(f.n, dir); if (d > bestDot) { bestDot = d; best = i; } });
        return freeHexes.splice(best, 1)[0];
    };

    // ---- Assign pieces: brand "continents", belts on pentagons, a few special tiles ----
    const BRANDS = ['Melee', 'Brawl', 'Ultimate'];
    const seeds = {};
    BRANDS.forEach((brand, i) => {
        const lon = (i * 2 * Math.PI) / 3;
        seeds[brand] = [Math.sin(lon), 0, Math.cos(lon)];
    });
    const pieces = [];   // {el, face, kind}
    const faceOf = [];   // fighter index -> face

    // Special tiles first (only as many as there's room for): brand labels at the heart of
    // each continent, the Smash Ball at the north pole, "?" (random) tiles at the south pole.
    let spare = freeHexes.length - N;
    const specials = [];
    BRANDS.forEach(brand => { if (spare-- > 0) specials.push({ kind: 'brand', brand, face: takeNearest(seeds[brand]) }); });
    if (spare-- > 0) specials.push({ kind: 'smash', face: takeNearest([0, -1, 0]) });
    while (spare-- > 0) specials.push({ kind: 'random', face: takeNearest([0, 1, 0]) });

    // Fighters: each brand claims the free faces nearest its seed (best power rank closest
    // to the center), which grows three contiguous continents.
    const byBrand = {};
    tiles.forEach((tile, i) => {
        const brand = BRANDS.includes(tile.dataset.brand) ? tile.dataset.brand : BRANDS[i % 3];
        (byBrand[brand] = byBrand[brand] || []).push(i);
    });
    Object.values(byBrand).forEach(list => list.sort((a, b) =>
        (Number(tiles[a].dataset.rank) || 999) - (Number(tiles[b].dataset.rank) || 999)));
    const capacity = Object.fromEntries(BRANDS.map(b => [b, (byBrand[b] || []).length]));
    const claimed = Object.fromEntries(BRANDS.map(b => [b, []]));
    freeHexes
        .flatMap(face => BRANDS.map(brand => ({ face, brand, d: v3.dot(face.n, seeds[brand]) })))
        .sort((a, b) => b.d - a.d)
        .forEach(({ face, brand }) => {
            if (face.claimed || claimed[brand].length >= capacity[brand]) return;
            face.claimed = true;
            claimed[brand].push(face);
        });
    BRANDS.forEach(brand => {
        claimed[brand].sort((a, b) => v3.dot(b.n, seeds[brand]) - v3.dot(a.n, seeds[brand]));
        (byBrand[brand] || []).forEach((tileIndex, k) => { faceOf[tileIndex] = claimed[brand][k]; });
    });
    tiles.forEach((tile, i) => {
        tile.classList.add('globe-piece');
        pieces.push({ el: tile, face: faceOf[i], kind: 'fighter' });
    });

    // Belts: each brand's major title sits on the pentagon nearest its continent.
    let belts = [];
    try { belts = JSON.parse(document.getElementById('globeBelts').textContent); } catch (e) { belts = []; }
    const freePentagons = pentagons.slice();
    const placeBelt = (belt, face) => { freePentagons.splice(freePentagons.indexOf(face), 1); belt.face = face; };
    BRANDS.forEach(brand => {
        const belt = belts.find(b => b.title === brand);
        if (!belt) return;
        const face = freePentagons.reduce((a, b) => (v3.dot(b.n, seeds[brand]) > v3.dot(a.n, seeds[brand]) ? b : a));
        placeBelt(belt, face);
    });
    belts.forEach(belt => { if (!belt.face && freePentagons.length) placeBelt(belt, freePentagons[0]); });

    const makePiece = (tag, className, inner) => {
        const el = document.createElement(tag);
        el.className = `globe-piece ${className}`;
        if (tag === 'button') el.type = 'button';
        el.innerHTML = `<span class="globe-tile-hex"></span><span class="globe-tile-face">${inner}</span>`;
        globe.appendChild(el);
        return el;
    };
    belts.filter(b => b.face).forEach(belt => {
        const src = championshipToBeltAsset(belt.title, 'md');
        const holders = belt.champions.length ? belt.champions.join(' & ') : 'Vacant';
        const el = makePiece('button', 'globe-belt',
            src ? `<img src="${src}" alt="" draggable="false">` : `<span class="globe-special-label">${escapeHTML(belt.display)}</span>`);
        el.title = `${belt.display} Championship: ${holders}`;
        el.setAttribute('aria-label', el.title);
        el.dataset.champion = belt.champions[0] || '';
        pieces.push({ el, face: belt.face, kind: 'belt' });
    });
    specials.forEach(sp => {
        let el;
        if (sp.kind === 'brand') {
            el = makePiece('button', `globe-special globe-special-brand brand-${sp.brand.toLowerCase()}`,
                `<span class="globe-special-label">${sp.brand}</span>`);
            el.title = `Show ${sp.brand} fighters`;
            el.dataset.brand = sp.brand;
        } else if (sp.kind === 'smash') {
            el = makePiece('button', 'globe-special globe-special-smash',
                `<img src="/static/assets/other/firesmashball.png" alt="" draggable="false">`);
            el.title = 'Smash!';
        } else {
            el = makePiece('button', 'globe-special globe-special-random', '<span class="globe-special-label">?</span>');
            el.title = 'Random fighter';
        }
        el.setAttribute('aria-label', el.title);
        pieces.push({ el, face: sp.face, kind: sp.kind });
    });

    // ---- Placing faces in 3D ------------------------------------------------------
    // Each piece is a flat div positioned with matrix3d on its face plane, clipped to the
    // face's exact polygon. Corners are projected onto the face plane along rays from the
    // center, so neighbouring pieces meet edge to edge.
    let radius = 300;
    const SEAM = 0.965;   // outer edge, leaves a thin seam between pieces
    const INNER = 0.88;   // inner picture area, leaves a colored rim
    const polygon = (pts, k, minX, minY) =>
        `polygon(${pts.map(([x, y]) => `${(x * k - minX).toFixed(2)}px ${(y * k - minY).toFixed(2)}px`).join(',')})`;

    function placePiece(piece, { lift = 0, grow = 1 } = {}) {
        const { el, face } = piece;
        const { n, u, v } = face;
        const R = radius;
        const pts = face.corners.map(c => {
            const t = R / v3.dot(n, c);
            return [t * v3.dot(c, u) * grow, t * v3.dot(c, v) * grow];
        });
        const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
        const minX = Math.min(...xs), minY = Math.min(...ys);
        const w = Math.max(...xs) - minX, h = Math.max(...ys) - minY;
        const d = R + lift;
        el.style.width = `${w}px`;
        el.style.height = `${h}px`;
        el.style.marginLeft = `${minX}px`;
        el.style.marginTop = `${minY}px`;
        el.style.transformOrigin = `${-minX}px ${-minY}px`;
        el.style.transform = `matrix3d(${u[0]},${u[1]},${u[2]},0,${v[0]},${v[1]},${v[2]},0,${n[0]},${n[1]},${n[2]},0,${n[0] * d},${n[1] * d},${n[2] * d},1)`;
        el.style.setProperty('--outer', polygon(pts, SEAM, minX, minY));
        el.style.setProperty('--inner', polygon(pts, INNER, minX, minY));
        el.style.setProperty('--piece', `${w}px`);
    }

    function layout() {
        const size = stage.clientWidth;
        if (!size) return;
        radius = size * 0.4;
        pieces.forEach(piece => placePiece(piece, piece.el.classList.contains('is-selected') ? { lift: radius * 0.06, grow: 1.12 } : {}));
        render();
    }

    // ---- Rotation state + animation loop ----------------------------------
    let yaw = 25, pitch = -10;          // degrees
    let vYaw = 0, vPitch = 0;           // momentum, degrees per frame
    let target = null;                  // {yaw, pitch, ease}
    let dragging = false;
    let lastInteraction = 0;
    let running = false;
    let visible = true;
    let selected = -1;

    const clampPitch = p => Math.max(-85, Math.min(85, p));
    const shortest = d => ((d + 540) % 360) - 180;

    function render() {
        globe.style.transform = `rotateX(${pitch}deg) rotateY(${yaw}deg)`;
        const cy = Math.cos(yaw * DEG), sy = Math.sin(yaw * DEG);
        const cp = Math.cos(pitch * DEG), sp = Math.sin(pitch * DEG);
        for (const piece of pieces) {
            const [nx, ny, nz] = piece.face.n;
            const z1 = -nx * sy + nz * cy;
            const facing = ny * sp + z1 * cp;       // 1 = facing the viewer, -1 = far side
            piece.el.style.setProperty('--facing', facing.toFixed(3));
            piece.el.classList.toggle('is-back', facing < 0.08);
        }
    }

    function frame() {
        running = false;
        if (!visible || section.dataset.view !== 'globe') return;
        let moving = false;
        if (target) {
            const dYaw = shortest(target.yaw - yaw);
            const dPitch = target.pitch - pitch;
            yaw += dYaw * target.ease;
            pitch += dPitch * target.ease;
            if (Math.abs(dYaw) < 0.05 && Math.abs(dPitch) < 0.05) {
                yaw = target.yaw; pitch = target.pitch; target = null;
            }
            moving = true;
        } else if (!dragging) {
            if (Math.abs(vYaw) > 0.01 || Math.abs(vPitch) > 0.01) {
                yaw += vYaw; pitch += vPitch;
                vYaw *= 0.95; vPitch *= 0.95;
                moving = true;
            }
            if (!reduceMotion && selected < 0) {
                // keep ticking so the idle spin resumes a moment after the last interaction
                if (performance.now() - lastInteraction > 2500) yaw += 0.07;
                moving = true;
            }
        }
        pitch = clampPitch(pitch);
        render();
        if (moving || dragging) wake();
    }

    function wake() {
        if (!running) { running = true; requestAnimationFrame(frame); }
    }

    function flyToNormal(n, { spin = 0, ease = 0.11 } = {}) {
        const lat = Math.asin(-n[1]);
        const lon = Math.atan2(n[0], n[2]);
        target = {
            yaw: yaw + shortest(-lon / DEG - yaw) + spin,
            pitch: clampPitch(-lat / DEG),
            ease: reduceMotion ? 1 : ease,
        };
        vYaw = vPitch = 0;
        if (document.hidden) {           // no animation frames in background tabs: just snap
            yaw = target.yaw; pitch = target.pitch; target = null;
            render();
            return;
        }
        wake();
    }

    const flyTo = (i, options) => flyToNormal(faceOf[i].n, options);

    // ---- Dragging (with momentum). Pointer capture starts only once a drag begins,
    // so a plain click still reaches the tile underneath.
    let down = null;
    stage.addEventListener('pointerdown', e => {
        if (e.button !== 0) return;
        down = { x: e.clientX, y: e.clientY, lastX: e.clientX, lastY: e.clientY, id: e.pointerId, moved: 0 };
        target = null;
        vYaw = vPitch = 0;
        lastInteraction = performance.now();
    });
    window.addEventListener('pointermove', e => {
        if (!down || e.pointerId !== down.id) return;
        const dx = e.clientX - down.lastX;
        const dy = e.clientY - down.lastY;
        down.lastX = e.clientX; down.lastY = e.clientY;
        down.moved += Math.abs(dx) + Math.abs(dy);
        if (!dragging && down.moved > 6) {
            dragging = true;
            stage.classList.add('is-dragging');
            try { stage.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
            hint.classList.add('is-hidden');
        }
        if (dragging) {
            const k = 1 / (radius * DEG);           // px -> degrees at the globe's surface
            yaw += dx * k;
            pitch = clampPitch(pitch - dy * k);
            vYaw = dx * k * 0.9;
            vPitch = -dy * k * 0.9;
            lastInteraction = performance.now();
            wake();
        }
    });
    const endDrag = e => {
        if (!down || (e && e.pointerId !== down.id)) return;
        if (dragging) {
            stage.classList.remove('is-dragging');
            try { stage.releasePointerCapture(down.id); } catch (err) { /* ignore */ }
            // let momentum carry on; swallow the click that follows a drag
            stage.dataset.justDragged = '1';
            setTimeout(() => delete stage.dataset.justDragged, 0);
        }
        dragging = false;
        down = null;
        lastInteraction = performance.now();
        wake();
    };
    window.addEventListener('pointerup', endDrag);
    window.addEventListener('pointercancel', endDrag);

    // ---- Selecting ----------------------------------------------------------
    stage.addEventListener('click', e => {
        if (stage.dataset.justDragged) { e.preventDefault(); e.stopPropagation(); return; }
        const pieceEl = e.target.closest('.globe-piece');
        if (!pieceEl) {                   // clicking empty space clears the selection
            if (e.target.closest('.globe-stage')) select(-1);
            return;
        }
        const i = tiles.indexOf(pieceEl);
        if (i < 0) { e.preventDefault(); onSpecialClick(pieceEl); return; }
        if (i !== selected) {            // first click selects, second opens the profile
            e.preventDefault();
            select(i);
        }
    }, true);

    function onSpecialClick(el) {
        lastInteraction = performance.now();
        if (el.classList.contains('globe-belt')) {
            const i = tiles.findIndex(t => t.dataset.name === el.dataset.champion);
            if (i >= 0) select(i);
            else flyToNormal(pieces.find(p => p.el === el).face.n);
        } else if (el.classList.contains('globe-special-brand')) {
            document.querySelector(`.brand-filter[data-filter="${el.dataset.brand}"]`)?.click();
        } else if (el.classList.contains('globe-special-random')) {
            document.getElementById('rosterRandom').click();
        } else if (el.classList.contains('globe-special-smash')) {
            select(-1);
            flyToNormal(pieces.find(p => p.el === el).face.n, { spin: reduceMotion ? 0 : 360, ease: 0.05 });
        }
    }

    tiles.forEach((tile, i) => {
        tile.draggable = false;
        // Keyboard focus selects; mouse clicks are handled above (focus also fires on click).
        tile.addEventListener('focus', () => {
            if (i !== selected && tile.matches(':focus-visible')) select(i);
        });
    });

    function select(i, options) {
        if (selected >= 0) {
            tiles[selected].classList.remove('is-selected');
            placePiece(pieces[selected]);
        }
        selected = i;
        if (i < 0) { showCard(null); wake(); return; }
        tiles[i].classList.add('is-selected');
        placePiece(pieces[i], { lift: radius * 0.06, grow: 1.12 });
        lastInteraction = performance.now();
        hint.classList.add('is-hidden');
        flyTo(i, options);
        showCard(tiles[i]);
    }

    // ---- Info card -----------------------------------------------------------
    const cardEmpty = card.querySelector('.globe-card-empty');
    const cardBody = card.querySelector('.globe-card-body');
    function showCard(tile) {
        if (!tile) { cardEmpty.hidden = false; cardBody.hidden = true; card.className = 'globe-card'; return; }
        const d = tile.dataset;
        cardEmpty.hidden = true;
        cardBody.hidden = false;
        card.className = `globe-card${d.brand ? ` brand-${d.brand.toLowerCase()}` : ''}`;
        document.getElementById('globeCardImg').src = d.img;
        document.getElementById('globeCardName').textContent = d.name;
        const brandEl = document.getElementById('globeCardBrand');
        brandEl.textContent = d.brand || '';
        brandEl.hidden = !d.brand;
        const psEl = document.getElementById('globeCardPs');
        const ps = d.ps === '' ? null : Number(d.ps);
        psEl.textContent = ps == null ? '--' : ps.toFixed(1);
        psEl.className = `globe-card-stat ${getPowerScoreClass(ps)}`;
        document.getElementById('globeCardRank').textContent = d.rank ? `#${d.rank} of ${N}` : '--';
        const titles = d.titles ? d.titles.split('|') : [];
        document.getElementById('globeCardTitles').innerHTML = titles.map(t => {
            const belt = championshipToBeltAsset(t, 'sm');
            return `<span class="globe-card-title">${belt ? `<img src="${belt}" alt="">` : ''}${escapeHTML(t)} Champion</span>`;
        }).join('');
        document.getElementById('globeCardLink').href = tile.getAttribute('href');
    }

    // ---- Search, brand filters, random ------------------------------------
    let brandFilter = '';
    const filterButtons = [...document.querySelectorAll('.brand-filter')];
    filterButtons.forEach(b => b.addEventListener('click', () => {
        brandFilter = brandFilter === b.dataset.filter ? '' : b.dataset.filter;
        filterButtons.forEach(x => x.classList.toggle('active', x.dataset.filter === brandFilter));
        applyFilters();
    }));

    function matchesFilter(name, brand, isChampion) {
        if (!brandFilter) return true;
        if (brandFilter === 'champions') return isChampion;
        return brand === brandFilter;
    }

    function applyFilters({ fly = false } = {}) {
        const q = search.value.trim().toLowerCase();
        const active = !!q || !!brandFilter;
        let best = -1, bestScore = Infinity;
        tiles.forEach((tile, i) => {
            const name = tile.dataset.name.toLowerCase();
            const ok = (!q || name.includes(q)) && matchesFilter(name, tile.dataset.brand, tile.classList.contains('is-champion'));
            tile.classList.toggle('is-dim', active && !ok);
            tile.classList.toggle('is-match', active && ok);
            if (ok && q) {
                const score = name.startsWith(q) ? name.length : 100 + name.indexOf(q);
                if (score < bestScore) { bestScore = score; best = i; }
            }
        });
        pieces.forEach(piece => {
            if (piece.kind === 'fighter') return;
            const lit = !active ||
                (piece.kind === 'belt' && brandFilter === 'champions' && !q) ||
                (piece.kind === 'brand' && piece.el.dataset.brand === brandFilter && !q);
            piece.el.classList.toggle('is-dim', !lit);
        });
                gridCards.forEach(cardEl => {
            const ok = (!q || cardEl.dataset.name.includes(q)) &&
                matchesFilter(cardEl.dataset.name, cardEl.dataset.brand, cardEl.classList.contains('is-champion'));
            cardEl.style.display = ok ? '' : 'none';
        });
        if (fly && best >= 0 && section.dataset.view === 'globe') select(best);
        wake();
    }

    search.addEventListener('input', () => applyFilters({ fly: true }));
    search.addEventListener('keydown', e => {
        if (e.key === 'Enter' && selected >= 0 && section.dataset.view === 'globe') {
            window.location.href = tiles[selected].getAttribute('href');
        } else if (e.key === 'Escape') {
            search.value = '';
            applyFilters();
        }
    });

    document.getElementById('rosterRandom').addEventListener('click', () => {
        const pool = tiles.map((t, i) => i).filter(i => i !== selected && !tiles[i].classList.contains('is-dim'));
        if (!pool.length) return;
        const pick = pool[Math.floor(Math.random() * pool.length)];
        if (section.dataset.view === 'grid') {
            window.location.href = tiles[pick].getAttribute('href');
            return;
        }
        select(pick, { spin: reduceMotion ? 0 : 720, ease: 0.045 });
    });

    // ---- Pause when off-screen or in a background tab ------------------------
    if ('IntersectionObserver' in window) {
        new IntersectionObserver(entries => {
            visible = entries[0].isIntersecting;
            if (visible) wake();
        }).observe(stage);
    }
    document.addEventListener('visibilitychange', () => { if (!document.hidden) wake(); });
    window.addEventListener('resize', () => { if (section.dataset.view === 'globe') layout(); });

    // ---- League pulse ---------------------------------------------------------
    // Champions: show their belt, and clicking one flies the globe to that fighter.
    document.querySelectorAll('.home-champ').forEach(btn => {
        const belt = btn.querySelector('.home-champ-belt');
        const src = championshipToBeltAsset(btn.dataset.title, 'sm');
        if (src) belt.src = src; else belt.remove();
        btn.addEventListener('click', () => {
            const i = tiles.findIndex(t => t.dataset.name === btn.dataset.fighter);
            if (i < 0) return;
            if (section.dataset.view !== 'globe') setView('globe');
            search.value = '';
            applyFilters();
            stage.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'center' });
            select(i);
        });
    });
    document.querySelectorAll('.home-top-score').forEach(el => {
        el.classList.add(getPowerScoreClass(Number(el.dataset.ps)));
    });
    const latest = document.getElementById('homeLatest');
    if (latest) {
        fetch('/api/fights?page=1')
            .then(r => r.json())
            .then(fights => {
                latest.innerHTML = '';
                if (!Array.isArray(fights) || !fights.length) {
                    latest.innerHTML = '<div class="fight-empty">No fights yet.</div>';
                    return;
                }
                fights.slice(0, 5).forEach(fight => appendFight(latest, fight));
            })
            .catch(() => { latest.innerHTML = '<div class="fight-empty">Couldn\'t load results.</div>'; });
    }

    // ---- Start ------------------------------------------------------------------
    gridCards.forEach((cardEl, i) => {
        cardEl.style.animationDelay = `${(i % 12) * 0.03}s`;
        cardEl.classList.add('fade-in');
    });
    setView(section.dataset.view === 'grid' ? 'grid' : 'globe');
})();
