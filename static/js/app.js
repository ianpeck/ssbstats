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
