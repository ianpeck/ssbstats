// Site-wide search: press / (or Ctrl/Cmd+K) anywhere, or click Search in the navbar.
// The index (/api/search-index) loads on first open and is searched locally as you type.

(() => {
    const dialog = document.getElementById('siteSearch');
    const openBtn = document.getElementById('searchOpen');
    if (!dialog) return;
    const input = document.getElementById('siteSearchInput');
    const list = document.getElementById('siteSearchResults');

    const TYPE_ORDER = { Fight: 0, Matchup: 0, Fighter: 1, Title: 2, Event: 3, Stage: 4, Season: 5, Page: 6 };
    const MAX_RESULTS = 12;
    let index = null;
    let loading = null;
    let results = [];
    let active = 0;
    let lastFocus = null;

    // Lowercase, strip accents and punctuation: "Pokémon Stadium 2" -> "pokemon stadium 2", "Mr. Game & Watch" -> "mr game watch".
    const norm = s => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();

    function load() {
        if (!loading) {
            loading = fetch('/api/search-index')
                .then(r => r.json())
                .then(items => {
                    index = items.map(item => {
                        const key = norm(item.name);
                        return { ...item, key, words: key.split(' '), subKey: norm(item.sub) };
                    });
                })
                .catch(() => { loading = null; });
        }
        return loading;
    }

    // Lower is better; -1 means no match.
    function score(item, q, qWords) {
        if (item.key === q) return 0;
        if (item.key.startsWith(q)) return 1;
        if (item.words.some(w => w.startsWith(q))) return 2;
        if (qWords.every(qw => item.words.some(w => w.startsWith(qw)))) return 3;
        if (item.key.includes(q)) return 4;
        if (qWords.every(qw => item.key.includes(qw) || item.subKey.includes(qw))) return 6;
        return -1;
    }

    function bestFighter(q) {
        const qWords = q.split(' ');
        let best = null, bestScore = Infinity;
        index.forEach(item => {
            if (item.type !== 'Fighter') return;
            const s = score(item, q, qWords);
            if (s >= 0 && s < bestScore) { best = item; bestScore = s; }
        });
        return best;
    }

    function search(raw) {
        const q = norm(raw);
        if (!q) return index.filter(item => item.type === 'Page');
        const extra = [];

        const fight = q.match(/^(?:fight )?(\d{1,5})$/);
        if (fight) extra.push({ type: 'Fight', name: `Fight #${fight[1]}`, sub: 'Open this fight', url: `/fight/${fight[1]}`, icon: 'swords' });

        const sides = q.split(/ (?:vs|v) /);
        if (sides.length === 2 && sides[0] && sides[1]) {
            const a = bestFighter(sides[0]);
            const b = bestFighter(sides[1]);
            if (a && b && a !== b) {
                extra.push({ type: 'Matchup', name: `${a.name} vs ${b.name}`, sub: 'Head to head',
                             url: `/head2head?f1=${encodeURIComponent(a.name)}&f2=${encodeURIComponent(b.name)}`, img: a.img, img2: b.img });
            }
        }

        const qWords = q.split(' ');
        const matches = index
            .map(item => [score(item, q, qWords), item])
            .filter(([s]) => s >= 0)
            .sort((a, b) => a[0] - b[0]
                || TYPE_ORDER[a[1].type] - TYPE_ORDER[b[1].type]
                || (a[1].rank || 999) - (b[1].rank || 999)
                || a[1].name.localeCompare(b[1].name))
            .map(([, item]) => item);
        return extra.concat(matches).slice(0, MAX_RESULTS);
    }

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text != null) node.textContent = text;
        return node;
    }

    function render() {
        list.innerHTML = '';
        if (!index) {
            list.appendChild(el('li', 'site-search-empty', 'Loading…'));
            return;
        }
        if (!results.length) {
            list.appendChild(el('li', 'site-search-empty', 'No matches. Try a fighter, stage, event, title or fight number.'));
            return;
        }
        if (!input.value.trim()) list.appendChild(el('li', 'site-search-heading', 'Jump to'));
        results.forEach((item, i) => {
            const li = el('li');
            li.setAttribute('role', 'option');
            li.id = `site-search-${i}`;
            const a = el('a', 'site-search-item' + (i === active ? ' is-active' : ''));
            a.href = item.url;
            li.setAttribute('aria-selected', String(i === active));

            const shape = { Stage: ' is-wide', Event: ' is-wide is-logo', Title: ' is-wide is-logo' }[item.type] || '';
            const art = el('span', 'site-search-art' + shape + (item.img2 ? ' is-pair' : ''));
            if (item.img) {
                [item.img, item.img2].filter(Boolean).forEach(src => {
                    const img = el('img');
                    img.src = src;
                    img.alt = '';
                    img.loading = 'lazy';
                    art.appendChild(img);
                });
            } else {
                const icon = el('i');
                icon.setAttribute('data-lucide', item.icon || 'arrow-right');
                art.appendChild(icon);
            }
            const text = el('span', 'site-search-text');
            text.appendChild(el('strong', null, item.name));
            if (item.sub) text.appendChild(el('small', null, item.sub));
            a.append(art, text, el('span', `site-search-type type-${item.type.toLowerCase()}`, item.type));

            a.addEventListener('mousemove', () => { if (active !== i) setActive(i); });
            li.appendChild(a);
            list.appendChild(li);
        });
        input.setAttribute('aria-activedescendant', `site-search-${active}`);
        if (window.lucide) lucide.createIcons();
    }

    function setActive(i) {
        const items = list.querySelectorAll('.site-search-item');
        if (!items.length) return;
        active = (i + items.length) % items.length;
        items.forEach((item, j) => {
            item.classList.toggle('is-active', j === active);
            item.parentElement.setAttribute('aria-selected', String(j === active));
        });
        items[active].scrollIntoView({ block: 'nearest' });
        input.setAttribute('aria-activedescendant', `site-search-${active}`);
    }

    function update() {
        results = index ? search(input.value) : [];
        active = 0;
        render();
    }

    function open() {
        if (!dialog.hidden) return;
        lastFocus = document.activeElement;
        dialog.hidden = false;
        document.body.classList.add('site-search-open');
        input.value = '';
        input.focus();
        update();
        load().then(update);
    }

    function close() {
        dialog.hidden = true;
        document.body.classList.remove('site-search-open');
        if (lastFocus && lastFocus.focus) lastFocus.focus();
    }

    function go(newTab) {
        const item = results[active];
        if (!item) return;
        if (newTab) window.open(item.url, '_blank');
        else window.location.href = item.url;
    }

    if (openBtn) openBtn.addEventListener('click', open);
    // Warm the index when the pointer heads for the button, so results are ready on open.
    if (openBtn) openBtn.addEventListener('pointerenter', load, { once: true });
    input.addEventListener('input', update);
    input.addEventListener('keydown', e => {
        if (e.key === 'ArrowDown') { e.preventDefault(); setActive(active + 1); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(active - 1); }
        else if (e.key === 'Enter') { e.preventDefault(); go(e.metaKey || e.ctrlKey); }
        else if (e.key === 'Escape') { e.preventDefault(); close(); }
    });
    dialog.addEventListener('click', e => { if (e.target === dialog) close(); });

    document.addEventListener('keydown', e => {
        const typing = e.target.closest && e.target.closest('input, textarea, select, [contenteditable="true"]');
        if ((e.key === 'k' || e.key === 'K') && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            if (dialog.hidden) open(); else close();
        } else if (e.key === '/' && !typing && !e.metaKey && !e.ctrlKey && !e.altKey) {
            e.preventDefault();
            open();
        }
    });
})();
