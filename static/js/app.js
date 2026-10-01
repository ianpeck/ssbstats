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

const _STAGE_OVERRIDES = { 'mushroom kingdom ii': 'mushroomkingdom2' };

function stageToFilename(name) {
    const lower = name.toLowerCase();
    if (_STAGE_OVERRIDES[lower]) return _STAGE_OVERRIDES[lower];
    // Strip diacritics (é→e, ō→o, etc.) then remove special chars
    const ascii = name.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    return ascii.toLowerCase().replace(/ /g, '').replace(/,/g, '').replace(/'/g, '').replace(/\(/g, '').replace(/\)/g, '').replace(/-/g, '').replace(/\./g, '');
}

function championshipToBeltFilename(name) {
    if (!name) return null;

    const normalized = String(name)
        .toLowerCase()
        .replace(/unified tag 1/g, 'unified tag')
        .replace(/championship/g, '')
        .replace(/title/g, '')
        .replace(/[^a-z0-9 ]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();

    const overrides = {
        'animal': 'animal',
        'brawl': 'brawl',
        'chaos': 'chaos',
        'hardcore': 'hardcore',
        'human': 'human',
        'melee': 'melee',
        'monster': 'monster',
        'smash bros': 'smashbros',
        'smashbros': 'smashbros',
        'special': 'special',
        'tag': 'tagteam',
        'tag team': 'tagteam',
        'unified tag': 'tagteam',
        'ultimate': 'ultimate',
    };

    for (const [needle, filename] of Object.entries(overrides)) {
        if (normalized.includes(needle)) return filename;
    }

    return null;
}

function championshipHasTransparentBelt(name) {
    const filename = championshipToBeltFilename(name);
    return !!filename;
}

function championshipToBeltAsset(name) {
    const filename = championshipToBeltFilename(name);
    if (!filename || !championshipHasTransparentBelt(name)) return null;
    return `/static/assets/belts/${filename}.png`;
}

function debounce(fn, delay) {
    let timer;
    return function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

function getPowerScoreClass(score, prefix = "ps-tier") {
    if (score == null || Number.isNaN(Number(score))) return "";
    const value = Number(score);
    if (value >= 90) return `${prefix}-5`;
    if (value >= 75) return `${prefix}-4`;
    if (value >= 50) return `${prefix}-3`;
    if (value >= 25) return `${prefix}-2`;
    return `${prefix}-1`;
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

function isNoContest(f) {
    return String(f.win ?? '').toUpperCase() === 'NC';
}

function chipHTML(f) {
    const fn  = fighterToFilename(f.name);
    const win = isWinner(f);
    const nc  = isNoContest(f);
    const stocks = (f.match_result != null && f.match_result !== '') ? f.match_result : null;
    const resultText = nc ? 'NC' : (win ? 'W' : 'L') + (stocks != null ? ` ${stocks}` : '');
    const chipClass = nc ? 'chip-nc' : (win ? 'chip-win' : 'chip-loss');
    const resultClass = nc ? 'nc' : (win ? 'win' : 'loss');
    return `<span class="fight-fighter-chip ${chipClass}">
        <img src="/static/assets/fighters/${fn}.png" alt="${f.name}"
             class="fight-portrait" onerror="this.style.display='none'">
        <a href="/fighter/${encodeURIComponent(f.name)}" class="fight-fighter-name"
           onclick="event.stopPropagation()">${f.name}</a>
        <span class="fight-chip-result ${resultClass}">${resultText}</span>
    </span>`;
}

// Shared fight row, laid out as aligned columns:
//   When | Match | Winner | Defeated | Event | Stage
// Columns adapt to the list's width via CSS container queries, and collapse into a
// stacked card on narrow screens. opts.hideEvent drops the Event column for lists
// that all come from one event (the View Card popup and event pages).
const FIGHT_CHIPS_SHOWN = 4;

function fightChips(group, joiner) {
    const shown = group.slice(0, FIGHT_CHIPS_SHOWN);
    const hidden = group.length - shown.length;
    return shown.map(f => chipHTML(f)).join(joiner) +
        (hidden > 0 ? `<span class="fight-overflow-chip">+${hidden} more</span>` : '');
}

function renderFight(fight, opts = {}) {
    const { fight_id, season, month, week, ppv, location, fight_type,
            championship, brand, fighters } = fight;

    const winners  = fighters.filter(isWinner);
    const losers   = fighters.filter(f => !isWinner(f));
    const noWinner = winners.length === 0;
    const ftLower  = fight_type ? fight_type.toLowerCase() : '';
    const isTeamMatch = !noWinner && (ftLower === 'tag team' || ftLower === 'handicap');
    const teamJoin = '<span class="fight-amp">&amp;</span>';
    const isContender = fighters.some(f => f.contender &&
        String(f.contender).toUpperCase() !== 'N' && f.contender !== 0);

    const when = season != null
        ? `S${season}${month != null ? ` · M${month}` : ''}${week != null ? ` · W${week}` : ''}`
        : '—';
    const matchBadges =
        (championship ? `<span class="fight-badge fight-badge-champ">&#127942; ${championship}</span>` : '') +
        (isContender ? `<span class="fight-badge fight-badge-contender">#1 Contender</span>` : '');
    const winnerHTML = noWinner
        ? '<span class="fight-nc-label">No contest</span>'
        : fightChips(winners, isTeamMatch ? teamJoin : '');
    const defeatedHTML = noWinner
        ? fightChips(fighters, '<span class="fight-vs-divider">vs</span>')
        : (losers.length ? fightChips(losers, isTeamMatch ? teamJoin : '') : '<span class="fight-muted">—</span>');
    const eventText = ppv || (brand ? `${brand} weekly` : 'Weekly');
    const stageHTML = location
        ? `<img src="/static/assets/stages/${stageToFilename(location)}.png" alt="" class="fight-location-thumb"
                onerror="this.style.display='none'"><span class="fight-location-text">${location}</span>`
        : '<span class="fight-muted">—</span>';

    const row = document.createElement('div');
    row.className = 'fight-row' + (opts.hideEvent ? ' no-event' : '');
    row.innerHTML = `
        <div class="fight-row-main">
            <div class="fight-col fight-col-when">${when}</div>
            <div class="fight-col fight-col-match">
                <span class="fight-type-label">${fight_type || 'Match'}</span>${matchBadges}
            </div>
            <div class="fight-col fight-col-winner">${winnerHTML}</div>
            <div class="fight-col fight-col-defeated">
                ${noWinner ? '' : '<span class="fight-col-defeated-label">def.</span>'}${defeatedHTML}
            </div>
            ${opts.hideEvent ? '' : `<div class="fight-col fight-col-event${ppv ? ' is-ppv' : ''}">${eventText}</div>`}
            <div class="fight-col fight-col-stage" title="${location || ''}">${stageHTML}</div>
        </div>`;

    row.querySelector('.fight-row-main').addEventListener('click', () => {
        window.location.href = `/fight/${fight_id}`;
    });

    return row;
}

function fightListHeader(opts = {}) {
    const header = document.createElement('div');
    header.className = 'fight-list-header' + (opts.hideEvent ? ' no-event' : '');
    header.innerHTML = `
        <div class="fight-row-main">
            <div class="fight-col fight-col-when">When</div>
            <div class="fight-col fight-col-match">Match</div>
            <div class="fight-col fight-col-winner">Winner</div>
            <div class="fight-col fight-col-defeated">Defeated</div>
            ${opts.hideEvent ? '' : '<div class="fight-col fight-col-event">Event</div>'}
            <div class="fight-col fight-col-stage">Stage</div>
        </div>`;
    return header;
}

// Append a fight to a .fight-list, adding the column header first if needed.
function appendFight(list, fight, opts = {}) {
    if (!list.querySelector(':scope > .fight-list-header')) {
        list.querySelectorAll(':scope > .fight-empty').forEach(el => el.remove());
        list.prepend(fightListHeader(opts));
    }
    const row = renderFight(fight, opts);
    list.appendChild(row);
    return row;
}

// ---------- Mobile Nav Toggle ----------

document.addEventListener('DOMContentLoaded', function() {
    const toggle = document.getElementById('navToggle');
    const links = document.querySelector('.nav-links');

    if (toggle && links) {
        toggle.addEventListener('click', function() {
            const open = links.classList.toggle('show');
            toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
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
