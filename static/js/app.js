/* ============================================
   SSB STATS - Client-Side Logic
   ============================================ */

// ---------- Utility Functions ----------

function fighterToFilename(name) {
    const overrides = {
        'banjo & kazooie': 'banjoandkazooie',
        'banjo and kazooie': 'banjoandkazooie',
    };
    const lower = name.toLowerCase();
    if (overrides[lower]) return overrides[lower];
    return lower.replace(/ /g, '').replace(/\./g, '').replace(/&/g, 'and');
}

function stageToFilename(name) {
    return name.toLowerCase().replace(/ /g, '').replace(/,/g, '').replace(/'/g, '').replace(/\(/g, '').replace(/\)/g, '').replace(/-/g, '');
}

function debounce(fn, delay) {
    let timer;
    return function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

// ---------- Animated Counter ----------

function animateCounter(elementId, start, end, duration) {
    const el = document.getElementById(elementId);
    if (!el) return;
    if (end === 0) { el.textContent = '0'; return; }

    const range = end - start;
    const startTime = performance.now();

    function step(now) {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        // Ease out cubic
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = Math.round(start + range * eased);
        el.textContent = current;
        if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
}

// ---------- Autocomplete ----------

function setupAutocomplete(input, category) {
    const wrapper = input.closest('.autocomplete-wrapper');
    if (!wrapper) return;

    let dropdown = wrapper.querySelector('.autocomplete-dropdown');
    if (!dropdown) {
        dropdown = document.createElement('div');
        dropdown.className = 'autocomplete-dropdown';
        wrapper.appendChild(dropdown);
    }

    let allItems = [];
    let highlightedIndex = -1;

    // Fetch initial list
    fetch(`/api/autocomplete/${category}`)
        .then(res => res.json())
        .then(data => { allItems = data; })
        .catch(() => {});

    const showDropdown = debounce(function() {
        const val = input.value.toLowerCase().trim();
        if (!val) {
            dropdown.classList.remove('show');
            return;
        }

        const matches = allItems.filter(item =>
            item.toLowerCase().includes(val)
        ).slice(0, 15);

        if (matches.length === 0) {
            dropdown.classList.remove('show');
            return;
        }

        dropdown.innerHTML = '';
        highlightedIndex = -1;

        matches.forEach((item, i) => {
            const div = document.createElement('div');
            div.className = 'autocomplete-item';
            div.textContent = item;
            div.addEventListener('mousedown', function(e) {
                e.preventDefault();
                input.value = item;
                dropdown.classList.remove('show');
                input.dispatchEvent(new Event('change'));
            });
            dropdown.appendChild(div);
        });

        dropdown.classList.add('show');
    }, 150);

    input.addEventListener('input', showDropdown);
    input.addEventListener('focus', showDropdown);

    input.addEventListener('blur', function() {
        setTimeout(() => dropdown.classList.remove('show'), 200);
    });

    // Keyboard navigation
    input.addEventListener('keydown', function(e) {
        const items = dropdown.querySelectorAll('.autocomplete-item');
        if (!items.length) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            highlightedIndex = Math.min(highlightedIndex + 1, items.length - 1);
            updateHighlight(items);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            highlightedIndex = Math.max(highlightedIndex - 1, 0);
            updateHighlight(items);
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (highlightedIndex >= 0 && highlightedIndex < items.length) {
                input.value = items[highlightedIndex].textContent;
                dropdown.classList.remove('show');
                input.dispatchEvent(new Event('change'));
            }
        } else if (e.key === 'Escape') {
            dropdown.classList.remove('show');
        }
    });

    function updateHighlight(items) {
        items.forEach((item, i) => {
            item.classList.toggle('highlighted', i === highlightedIndex);
        });
        if (highlightedIndex >= 0) {
            items[highlightedIndex].scrollIntoView({ block: 'nearest' });
        }
    }
}

// ---------- Fight Log Rendering (shared: fight log page + fighter profile page) ----------

function isWinner(f) {
    const w = f.win;
    if (w == null) return false;
    const s = String(w).toUpperCase();
    return s === 'W' || s === 'Y' || w === 1 || w === true;
}

function chipHTML(f) {
    const fn  = fighterToFilename(f.name);
    const win = isWinner(f);
    const stocks = (f.match_result != null && f.match_result !== '') ? f.match_result : null;
    const resultText = (win ? 'W' : 'L') + (stocks != null ? ` ${stocks}` : '');
    return `<span class="fight-fighter-chip ${win ? 'chip-win' : 'chip-loss'}">
        <img src="/static/assets/fighters/${fn}.png" alt="${f.name}"
             class="fight-portrait" onerror="this.style.display='none'">
        <a href="/fighter/${encodeURIComponent(f.name)}" class="fight-fighter-name"
           onclick="event.stopPropagation()">${f.name}</a>
        <span class="fight-chip-result ${win ? 'win' : 'loss'}">${resultText}</span>
    </span>`;
}

function renderFight(fight) {
    const { season, month, week, ppv, location, fight_type,
            championship, brand, fighters } = fight;

    const winners   = fighters.filter(isWinner);
    const losers    = fighters.filter(f => !isWinner(f));
    const isBig     = fighters.length > 6;
    // Tag Team and Handicap use & within each side; everything else uses vs between all fighters
    const ftLower   = fight_type ? fight_type.toLowerCase() : '';
    const isTeamMatch = ftLower === 'tag team' || ftLower === 'handicap';
    const is1v1       = !isTeamMatch && fighters.length === 2;
    // #1 Contender is a match attribute — true if any fighter has it set
    const isContender = fighters.some(f => f.contender &&
        String(f.contender).toUpperCase() !== 'N' && f.contender !== 0);
    const MAX = 4;

    function sideHTML(group, cssClass, useAmp) {
        const shown  = group.slice(0, MAX);
        const hidden = group.length - shown.length;
        const sep    = useAmp ? '<span class="fight-amp">&amp;</span>' : '';
        let html = `<div class="fight-side ${cssClass}">`;
        html += shown.map(f => chipHTML(f)).join(sep);
        if (hidden > 0) html += `<span class="fight-overflow-chip">+${hidden} more</span>`;
        html += '</div>';
        return html;
    }

    let participantsHTML;
    if (isBig) {
        const winChip = winners.length ? chipHTML(winners[0]) : '';
        participantsHTML = `
            <div class="fight-side fight-side-win">${winChip}</div>
            <div class="fight-vs-divider">&middot;</div>
            <span class="fight-overflow-chip">${fighters.length}-person ${fight_type || 'match'}</span>`;
    } else if (isTeamMatch) {
        // Tag Team / Handicap: group each side with & between teammates
        participantsHTML =
            sideHTML(winners, 'fight-side-win', true) +
            (winners.length && losers.length ? '<span class="fight-vs-divider">vs</span>' : '') +
            sideHTML(losers, 'fight-side-loss', true);
    } else if (is1v1) {
        // Standard 1v1
        participantsHTML =
            sideHTML(winners, 'fight-side-win', false) +
            (winners.length && losers.length ? '<span class="fight-vs-divider">vs</span>' : '') +
            sideHTML(losers, 'fight-side-loss', false);
    } else {
        // Multi-person free-for-all: show every fighter with vs between each
        // (winners first so W badges appear on the left)
        const all    = [...winners, ...losers];
        const shown  = all.slice(0, MAX);
        const hidden = all.length - shown.length;
        participantsHTML =
            '<div class="fight-side fight-side-ffa">' +
            shown.map(f => chipHTML(f)).join('<span class="fight-vs-divider">vs</span>') +
            (hidden > 0 ? `<span class="fight-overflow-chip">+${hidden} more</span>` : '') +
            '</div>';
    }

    const metaHTML = `
        <div class="fight-meta-col">
            ${season != null ? `<span class="fight-badge fight-badge-season">S${season}${month != null ? ` M${month}` : ''}${week != null ? ` W${week}` : ''}</span>` : ''}
            ${fight_type   ? `<span class="fight-badge fight-badge-type">${fight_type}</span>` : ''}
            ${isContender  ? `<span class="fight-badge fight-badge-contender">#1 Contender</span>` : ''}
            ${championship ? `<span class="fight-badge fight-badge-champ">&#127942; ${championship}</span>` : ''}
            ${ppv          ? `<span class="fight-badge fight-badge-ppv">${ppv}</span>` : ''}
            ${location     ? `<span class="fight-location-text">${location}</span>` : ''}
        </div>`;

    function detailFighterHTML(f) {
        const fn  = fighterToFilename(f.name);
        const win = isWinner(f);
        const extras = [
            f.match_result != null && f.match_result !== '' ? String(f.match_result) : '',
            f.defending ? 'Defending'  : '',
            f.seed      ? `Seed #${f.seed}` : '',
            // #1 Contender is match-level; shown in meta badges above, not per-fighter
        ].filter(Boolean).join(' \u00b7 ');
        return `<div class="fight-detail-fighter ${win ? 'is-winner' : 'is-loser'}">
            <img src="/static/assets/fighters/${fn}.png" alt="${f.name}"
                 class="fight-detail-portrait" onerror="this.style.display='none'">
            <div class="fight-detail-fighter-info">
                <a href="/fighter/${encodeURIComponent(f.name)}"
                   class="fight-detail-fighter-name"
                   onclick="event.stopPropagation()">${f.name}</a>
            </div>
            <span class="fight-detail-result-badge ${win ? 'win' : 'loss'}">${win ? 'WIN' : 'LOSS'}</span>
            ${extras ? `<span class="fight-detail-stocks">${extras}</span>` : ''}
        </div>`;
    }

    const stageImg = location ? `
        <div class="fight-detail-stage">
            <div class="fight-stage-img-wrap">
                <img src="/static/assets/stages/${stageToFilename(location)}.png"
                     alt="${location}" class="fight-stage-img"
                     onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
                <div class="fight-stage-placeholder">
                    <span>Stage Photo<br>Not Available</span>
                </div>
            </div>
            <span class="fight-stage-label">${location}</span>
        </div>` : '';

    const infoRows = [
        season  != null ? `<div>Season <span>${season}</span></div>` : '',
        month   != null ? `<div>Month <span>${month}</span></div>` : '',
        week    != null ? `<div>Week <span>${week}</span></div>` : '',
        ppv     ? `<div>PPV <span>${ppv}</span></div>` : '',
        location? `<div>Location <span>${location}</span></div>` : '',
        fight_type   ? `<div>Fight Type <span>${fight_type}</span></div>` : '',
        championship ? `<div>Championship <span>${championship}</span></div>` : '',
        brand        ? `<div>Brand <span>${brand}</span></div>` : '',
    ].filter(Boolean).join('');

    const row = document.createElement('div');
    row.className = 'fight-row';
    row.innerHTML = `
        <div class="fight-row-main">
            ${metaHTML}
            <div class="fight-participants-col">${participantsHTML}</div>
            <span class="fight-chevron">&#9660;</span>
        </div>
        <div class="fight-detail">
            <div class="fight-detail-grid">
                <div class="fight-detail-left">
                    <div class="fight-detail-info">${infoRows}</div>
                    ${stageImg}
                </div>
                <div class="fight-detail-participants">
                    ${fighters.map(detailFighterHTML).join('')}
                </div>
            </div>
        </div>`;

    row.querySelector('.fight-row-main').addEventListener('click', () => {
        row.classList.toggle('is-open');
    });

    return row;
}

// ---------- Mobile Nav Toggle ----------

document.addEventListener('DOMContentLoaded', function() {
    const toggle = document.getElementById('navToggle');
    const links = document.querySelector('.nav-links');

    if (toggle && links) {
        toggle.addEventListener('click', function() {
            links.classList.toggle('show');
        });
    }
});

// ---------- Star Field Background ----------

(function() {
    const canvas = document.getElementById('particleCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    // Three layers: [count, speed, minRadius, maxRadius, minOpacity, maxOpacity]
    const LAYERS = [
        { count: 180, speed: 0.08, minR: 0.4, maxR: 0.9,  minA: 0.2, maxA: 0.5 }, // far
        { count: 80,  speed: 0.20, minR: 0.9, maxR: 1.6,  minA: 0.4, maxA: 0.7 }, // mid
        { count: 30,  speed: 0.45, minR: 1.5, maxR: 2.8,  minA: 0.6, maxA: 1.0 }, // near
    ];

    let stars = [];
    let width, height;
    let time = 0;

    function rand(a, b) { return a + Math.random() * (b - a); }

    function resize() {
        width  = canvas.width  = window.innerWidth;
        height = canvas.height = window.innerHeight;
    }

    function createStar(layer, x) {
        return {
            x:       x !== undefined ? x : rand(0, width),
            y:       rand(0, height),
            radius:  rand(layer.minR, layer.maxR),
            opacity: rand(layer.minA, layer.maxA),
            speed:   layer.speed,
            // twinkle offset so stars don't all pulse together
            twinkleOffset: rand(0, Math.PI * 2),
            twinkleSpeed:  rand(0.005, 0.02),
            baseOpacity:   rand(layer.minA, layer.maxA),
        };
    }

    function init() {
        resize();
        stars = [];
        LAYERS.forEach(layer => {
            for (let i = 0; i < layer.count; i++) {
                stars.push({ ...createStar(layer), layer });
            }
        });
    }

    function draw() {
        ctx.clearRect(0, 0, width, height);
        time++;

        stars.forEach(s => {
            // Drift left (parallax — near layer faster)
            s.x -= s.speed;
            if (s.x < -2) {
                // Respawn on right edge
                const fresh = createStar(s.layer, width + 2);
                Object.assign(s, fresh, { layer: s.layer });
            }

            // Twinkle: gentle opacity sine wave
            const twinkle = Math.sin(time * s.twinkleSpeed + s.twinkleOffset) * 0.15;
            const alpha = Math.max(0, Math.min(1, s.baseOpacity + twinkle));

            // Occasional blue-tinted stars
            const isBlue = s.radius > 1.8;
            const color = isBlue ? `rgba(160, 180, 255, ${alpha})` : `rgba(255, 255, 255, ${alpha})`;

            // Glow for larger stars
            if (s.radius > 1.5) {
                ctx.beginPath();
                const gradient = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, s.radius * 3);
                gradient.addColorStop(0, isBlue ? `rgba(96, 124, 255, ${alpha * 0.4})` : `rgba(255, 255, 255, ${alpha * 0.3})`);
                gradient.addColorStop(1, 'rgba(0,0,0,0)');
                ctx.fillStyle = gradient;
                ctx.arc(s.x, s.y, s.radius * 3, 0, Math.PI * 2);
                ctx.fill();
            }

            // Star dot
            ctx.beginPath();
            ctx.arc(s.x, s.y, s.radius, 0, Math.PI * 2);
            ctx.fillStyle = color;
            ctx.fill();
        });

        requestAnimationFrame(draw);
    }

    window.addEventListener('resize', () => { resize(); init(); });
    init();
    draw();
})();
