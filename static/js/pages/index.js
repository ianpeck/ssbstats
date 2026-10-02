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

    // ---- Layout: spread tiles evenly over a sphere (Fibonacci / golden-angle spiral) ----
    const N = tiles.length;
    const GOLDEN = Math.PI * (3 - Math.sqrt(5));
    const points = tiles.map((tile, i) => {
        const y = 1 - (2 * (i + 0.5)) / N;          // 1 (top) .. -1 (bottom)
        const lat = Math.asin(y);
        const lon = (i * GOLDEN) % (2 * Math.PI);
        return {
            lat, lon,
            // outward normal in CSS space (y points down)
            nx: Math.cos(lat) * Math.sin(lon),
            ny: -Math.sin(lat),
            nz: Math.cos(lat) * Math.cos(lon),
        };
    });
    let radius = 300;

    function layout() {
        const size = stage.clientWidth;
        if (!size) return;
        radius = size * 0.4;
        const tile = radius * Math.sqrt((4 * Math.PI) / N) * 1.1;
        stage.style.setProperty('--tile', `${tile}px`);
        tiles.forEach((el, i) => {
            const p = points[i];
            el.style.transform = `rotateY(${p.lon}rad) rotateX(${p.lat}rad) translateZ(${radius}px)`;
        });
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
        for (let i = 0; i < N; i++) {
            const p = points[i];
            const z1 = -p.nx * sy + p.nz * cy;
            const facing = p.ny * sp + z1 * cp;     // 1 = facing the viewer, -1 = far side
            const el = tiles[i];
            el.style.setProperty('--facing', facing.toFixed(3));
            el.classList.toggle('is-back', facing < 0.08);
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

    function flyTo(i, { spin = 0, ease = 0.11 } = {}) {
        const p = points[i];
        const wantYaw = -p.lon / DEG;
        target = {
            yaw: yaw + shortest(wantYaw - yaw) + spin,
            pitch: clampPitch(-p.lat / DEG),
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
        const tile = e.target.closest('.globe-tile');
        if (!tile) {                      // clicking empty space clears the selection
            if (e.target.closest('.globe-stage')) select(-1);
            return;
        }
        const i = tiles.indexOf(tile);
        if (i !== selected) {            // first click selects, second opens the profile
            e.preventDefault();
            select(i);
        }
    }, true);

    tiles.forEach((tile, i) => {
        tile.draggable = false;
        // Keyboard focus selects; mouse clicks are handled above (focus also fires on click).
        tile.addEventListener('focus', () => {
            if (i !== selected && tile.matches(':focus-visible')) select(i);
        });
    });

    function select(i, options) {
        if (selected >= 0) tiles[selected].classList.remove('is-selected');
        selected = i;
        if (i < 0) { showCard(null); wake(); return; }
        tiles[i].classList.add('is-selected');
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
