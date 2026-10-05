// Season recap: awards, big-event winners, a 12-month title timeline and the standings.

const $ = id => document.getElementById(id);

// Marquee events, with the holistic_view column that records each winner.
const EVENTS = [
    { col: 'Won_Royal_Rumble',      name: 'Royal Rumble',                 art: ['ppv', 'royalrumble'],                href: '/events/royalrumble' },
    { col: 'Won_Money_In_The_Bank', name: 'Money in the Bank',            art: ['ppv', 'moneyinthebank'],             href: '/events/moneyinthebank', detail: () => 'Won the briefcase' },
    { col: 'Won_Tournament',        name: 'Final Destination Tournament', art: ['ppv', 'finaldestinationtournament'], href: '/events/finaldestinationtournament', detail: v => `${v} bracket` },
    { col: 'Won_Smash_Series',      name: 'Smash Series',                 art: ['ppv', 'smashseries'],                href: '/events/smashseries' },
    { col: 'Won_Scramble',          name: 'Championship Scramble',        art: ['ppv', 'championshipscramble'],       href: '/events/championshipscramble', detail: v => `${v} scramble` },
    { col: 'Won_Smash_Bros',        name: 'Smash Bros. Trophy',           art: ['belts', 'smashbros'],                href: '/championships', detail: () => 'Yearly trophy' },
];
const AWARD_ORDER = ['superstar', 'most improved', 'disappoint', 'tag'];
const TITLE_ORDER = ['Melee', 'Brawl', 'Ultimate', 'Unified Tag'];

let currentSeason = null;
let latestSeason = null;
let standings = [];
let sort = { key: 'power_score', dir: 'desc' };
let showAll = false;

const esc = v => escapeHTML(v == null ? '' : String(v));
const fighterLink = name => `/fighter/${encodeURIComponent(name)}`;
const portrait = (name, size = 'sm', cls = '') => `<img class="${cls}" src="${fighterImg(name, size)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">`;

document.addEventListener('DOMContentLoaded', () => {
    const pills = [...document.querySelectorAll('#seasonPills .season-pill')];
    latestSeason = pills.length ? +pills[pills.length - 1].dataset.season : null;
    pills.forEach(pill => pill.addEventListener('click', () => {
        pills.forEach(p => p.classList.toggle('active', p === pill));
        loadSeason(+pill.dataset.season);
    }));

    const params = new URLSearchParams(window.location.search);
    const start = pills.find(p => p.dataset.season === params.get('season')) || pills[pills.length - 1];
    if (params.get('sort')) sort = { key: params.get('sort'), dir: params.get('dir') === 'asc' ? 'asc' : 'desc' };
    if (start) {
        pills.forEach(p => p.classList.toggle('active', p === start));
        loadSeason(+start.dataset.season, { keepSort: true });
    }

    document.querySelectorAll('#seasonRankingsTable .sortable').forEach(th => th.addEventListener('click', () => {
        const key = th.dataset.sort;
        sort = sort.key === key ? { key, dir: sort.dir === 'desc' ? 'asc' : 'desc' } : { key, dir: key === 'power_rank' ? 'asc' : 'desc' };
        renderStandings();
        updateURL();
    }));
    $('showAllBtn').addEventListener('click', () => { showAll = !showAll; renderStandings(); });
    $('seasonRankingsTbody').addEventListener('click', e => {
        const row = e.target.closest('tr[data-name]');
        if (row && !e.target.closest('a')) window.location.href = fighterLink(row.dataset.name);
    });
    setupSectionNav();
});

function updateURL() {
    const params = new URLSearchParams();
    if (currentSeason !== latestSeason) params.set('season', currentSeason);
    if (sort.key !== 'power_score') params.set('sort', sort.key);
    if (sort.dir !== 'desc') params.set('dir', sort.dir);
    const qs = params.toString();
    history.replaceState(null, '', '/seasons' + (qs ? '?' + qs : ''));
}

function loadSeason(season, { keepSort = false } = {}) {
    if (currentSeason === season) return;
    currentSeason = season;
    if (!keepSort) sort = { key: 'power_score', dir: 'desc' };
    showAll = false;
    updateURL();
    $('seasonHeading').textContent = `Season ${season}`;
    $('fullRankingsLink').href = `/leaderboard?season=${season}`;
    $('loadingOverlay').style.display = 'flex';
    $('seasonContent').hidden = true;

    fetch(`/api/season/${season}`)
        .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(data => {
            if (season !== currentSeason) return;   // a newer season was picked meanwhile
            const facts = (data.facts || [])[0] || {};
            renderFacts(facts, data);
            renderAwards(data.awards || [], facts);
            renderEvents(data.holistic || [], data.cashins || [], data.calendar || []);
            renderTitles(data.champ_history || [], data.calendar || [], facts);
            buildStandings(data);
            renderStandings();
            $('loadingOverlay').style.display = 'none';
            $('seasonContent').hidden = false;
        })
        .catch(() => { $('loadingOverlay').innerHTML = "<p>Couldn't load this season. Refresh to try again.</p>"; });
}

// ── Header facts ───────────────────────────────────────────────
function renderFacts(facts, data) {
    $('seasonKicker').textContent = facts.game ? `Season recap · ${facts.game} era` : 'Season recap';
    const stat = (value, label) => `<div class="season-fact"><span class="season-fact-value">${value}</span><span class="season-fact-label">${label}</span></div>`;
    $('seasonFacts').innerHTML =
        (facts.in_progress ? `<span class="season-live"><span class="season-live-dot"></span>In progress · through Month ${facts.last_month}</span>` : '') +
        `<div class="season-fact-row">
            ${stat((facts.fights || 0).toLocaleString(), 'Fights')}
            ${stat(facts.ppvs || 0, 'PPVs')}
            ${stat(facts.title_changes || 0, 'Title changes')}
            ${stat((data.rankings || []).length, 'Fighters')}
        </div>`;
}

// ── Awards ─────────────────────────────────────────────────────
function renderAwards(rows, facts) {
    const groups = [];
    rows.forEach(r => {
        let g = groups.find(x => x.award === r.Award_Name);
        if (!g) groups.push(g = { award: r.Award_Name, names: [], note: r.note });
        if (!g.names.includes(r.Fighter_Name)) g.names.push(r.Fighter_Name);
    });
    const rank = a => { const i = AWARD_ORDER.findIndex(k => a.toLowerCase().includes(k)); return i < 0 ? AWARD_ORDER.length : i; };
    groups.sort((a, b) => rank(a.award) - rank(b.award));

    $('awardsNote').textContent = groups.length ? '' : (facts.in_progress ? 'Handed out when the season ends' : 'No awards recorded');
    $('awardsList').innerHTML = groups.map((g, i) => {
        const featured = i === 0 && g.award.toLowerCase().includes('superstar');
        return `<article class="season-award${featured ? ' is-featured' : ''}">
            <span class="season-award-faces">${g.names.map(n => `<a href="${fighterLink(n)}">${portrait(n, featured ? 'md' : 'sm')}</a>`).join('')}</span>
            <span class="season-award-name">${esc(g.award)}</span>
            <span class="season-award-winner">${g.names.map(n => `<a href="${fighterLink(n)}">${esc(n)}</a>`).join(' &amp; ')}</span>
            ${awardNote(g.note)}
        </article>`;
    }).join('');
}

// The numbers behind an award: a before/after comparison, or a few stat tiles.
function awardNote(note) {
    if (!note) return '';
    if (note.type === 'change') {
        const side = (s, cls) => `<div class="award-delta-side ${cls}">
            <span class="award-delta-season">S${s.season}</span>
            <span class="award-delta-score ${getPowerScoreClass(s.score)}">${s.score.toFixed(1)}</span>
            ${s.record ? `<span class="award-delta-record">${esc(s.record)}</span>` : ''}
        </div>`;
        const up = note.delta >= 0;
        return `<div class="award-note award-delta" title="Power score and record, season over season">
            ${side(note.before, 'is-before')}
            <div class="award-delta-mid">
                <span class="award-delta-arrow" aria-hidden="true">→</span>
                <span class="award-delta-badge ${up ? 'is-up' : 'is-down'}">${up ? '▲' : '▼'} ${Math.abs(note.delta).toFixed(1)}</span>
            </div>
            ${side(note.after, 'is-after')}
        </div>`;
    }
    const tiles = (note.items || []).map(i => `<div class="award-stat">
            <span class="award-stat-value${i.score != null ? ' ' + getPowerScoreClass(i.score) : ''}">${esc(i.value)}</span>
            <span class="award-stat-label">${esc(i.label)}</span>
        </div>`).join('');
    const belts = (note.titles || []).map(t => {
        const belt = championshipToBeltAsset(t, 'sm');
        return `<span class="lb-belt">${belt ? `<img src="${belt}" alt="" loading="lazy">` : ''}${esc(t)}</span>`;
    }).join('');
    return `<div class="award-note">
        ${tiles ? `<div class="award-stats">${tiles}</div>` : ''}
        ${belts ? `<div class="award-titles">${belts}</div>` : ''}
    </div>`;
}

// ── Big events ─────────────────────────────────────────────────
function renderEvents(holistic, cashins, calendar) {
    const monthOf = name => (calendar.find(c => c.PPV_Name === name) || {}).Month || 13;
    const cards = [];
    EVENTS.forEach(ev => {
        const winners = [];
        holistic.forEach(r => {
            const v = r[ev.col];
            if (v == null || v === '') return;
            const detail = ev.detail ? ev.detail(v) : '';
            if (!winners.some(w => w.name === r.Fighter_Name && w.detail === detail)) winners.push({ name: r.Fighter_Name, detail });
        });
        if (winners.length) cards.push({ ...ev, month: ev.col === 'Won_Smash_Bros' ? 14 : monthOf(ev.name), winners });
    });
    cards.sort((a, b) => a.month - b.month);

    // Pick a column count that never leaves a lone card on the last row.
    const cols = cards.length <= 5 ? cards.length : cards.length % 3 === 0 ? 3 : 4;
    const grid = cards.length ? `<div class="season-event-grid" style="--cols:${cols}">${cards.map(c => `
        <article class="season-event">
            <a class="season-event-art" href="${c.href}">
                <img src="${assetVariant(c.art[0], c.art[1], 'sm')}" alt="" loading="lazy" onerror="this.remove()">
            </a>
            <a class="season-event-name" href="${c.href}">${esc(c.name)}</a>
            <span class="season-event-when">${c.month <= 12 ? `Month ${c.month}` : 'End of season'}</span>
            <div class="season-event-winners"><div class="season-event-winner-list">${c.winners.map(w => `
                <a class="season-event-winner" href="${fighterLink(w.name)}">
                    ${portrait(w.name)}
                    <span><strong>${esc(w.name)}</strong>${w.detail ? `<small>${esc(w.detail)}</small>` : ''}</span>
                </a>`).join('')}
            </div></div>
        </article>`).join('')}</div>` : '';

    $('eventsList').innerHTML = grid + (cashins.length ? cashinCard(cashins) : '')
        || '<p class="season-empty">No marquee events decided yet.</p>';
}

// Each cash-in as a matchup: the champion vs the briefcase holder, and whether the champion held on.
function cashinCard(cashins) {
    const side = (name, role, won) => `
        <a class="season-cashin-side${won ? ' is-winner' : ''}" href="${fighterLink(name)}">
            ${portrait(name)}
            <span><small>${role}</small><strong>${esc(name)}</strong></span>
        </a>`;
    return `<article class="season-cashins">
        <a class="season-event-art" href="/events/moneyinthebank">
            <img src="${assetVariant('ppv', 'moneyinthebank', 'sm')}" alt="" loading="lazy" onerror="this.remove()">
        </a>
        <div class="season-cashins-body">
            <a class="season-event-name" href="/events/moneyinthebank">Money in the Bank cash-ins</a>
            ${cashins.map(c => {
                const held = c.Fight_Winner === 'Champion';
                const champion = held ? c.Fight_Winner_Name : c.Fight_Loser_Name;
                const challenger = held ? c.Fight_Loser_Name : c.Fight_Winner_Name;
                const belt = championshipToBeltAsset(c.Championship_Name, 'sm');
                return `<div class="season-cashin">
                    <div class="season-cashin-head">
                        ${belt ? `<img src="${belt}" alt="" loading="lazy">` : ''}
                        <span>${esc(c.Championship_Name)} title · M${c.Month}${c.PPV_Name ? ' · ' + esc(c.PPV_Name) : ''}</span>
                        <span class="season-cashin-result ${held ? 'is-held' : 'is-new'}">${held ? 'Champion held' : 'New champion'}</span>
                    </div>
                    <div class="season-cashin-match">
                        ${side(champion, 'Champion', held)}
                        <span class="season-cashin-vs">vs</span>
                        ${side(challenger, 'Cashed in', !held)}
                    </div>
                </div>`;
            }).join('')}
        </div>
    </article>`;
}

// ── Title picture: every belt on a 12-month track ─────────────
function renderTitles(rows, calendar, facts) {
    const lastMonth = facts.in_progress ? facts.last_month : 12;
    const byTitle = new Map();
    rows.filter(r => r.Championship_Name !== 'Smash Bros.').forEach(r => {
        if (!byTitle.has(r.Championship_Name)) byTitle.set(r.Championship_Name, []);
        byTitle.get(r.Championship_Name).push(r);
    });
    const order = name => { const i = TITLE_ORDER.indexOf(name); return i < 0 ? TITLE_ORDER.length : i; };
    const titles = [...byTitle.keys()].sort((a, b) => order(a) - order(b) || a.localeCompare(b));

    const changes = facts.title_changes || 0;
    $('titlesNote').textContent = `${changes} title change${changes === 1 ? '' : 's'}` + (facts.in_progress ? ` through Month ${lastMonth}` : '');

    const ppvByMonth = Object.fromEntries(calendar.map(c => [c.Month, c.PPV_Name]));
    const axis = `<div class="season-track-axis">${Array.from({ length: 12 }, (_, i) => {
        const m = i + 1;
        return `<span class="${m > lastMonth ? 'is-future' : ''}" title="${esc(ppvByMonth[m] || '')}">M${m}</span>`;
    }).join('')}</div>`;

    const lines = titles.map(title => {
        // Tag partners share a reign: same won/lost dates.
        const reigns = [];
        byTitle.get(title).forEach(r => {
            const same = reigns.find(g => g.Season_Won === r.Season_Won && g.Month_Won === r.Month_Won && g.Season_Lost === r.Season_Lost && g.Month_Lost === r.Month_Lost);
            if (same) { same.names.push(r.Fighter_Name); same.inaugural = same.inaugural || !!r.inaugural; }
            else reigns.push({ ...r, inaugural: !!r.inaugural, names: [r.Fighter_Name] });
        });

        const segments = [], brief = [];
        reigns.forEach(g => {
            // A reign starts the month after the title is won; the month it's lost still counts.
            // Inaugural champions already held the title going into its first fight, so their
            // reign covers that month too.
            const start = g.Season_Won < currentSeason ? 1 : g.Month_Won + (g.inaugural ? 0 : 1);
            const current = g.Season_Lost == null;
            const end = current ? (currentSeason === latestSeason ? lastMonth : 12) : (g.Season_Lost > currentSeason ? 12 : g.Month_Lost);
            if (start <= end) segments.push({ g, start, end, current: current && currentSeason === latestSeason });
            else if (g.Season_Won === currentSeason) brief.push({ g, month: g.Month_Won });   // won and lost the same month, or won in M12
        });

        const label = g => g.names.join(' & ');
        const seg = ({ g, start, end, current }, i) => {
            const span = end - start + 1;
            const tip = `${label(g)} · M${start}–M${end}${g.inaugural ? ' · inaugural champion' : ''}${current ? ' · current champion' : ''}`;
            return `<a class="season-reign${i % 2 ? ' is-alt' : ''}${current ? ' is-current' : ''}${span < 2 ? ' is-narrow' : ''}" href="${fighterLink(g.names[0])}"
                    style="left:${(start - 1) / 12 * 100}%;width:${span / 12 * 100}%" title="${esc(tip)}">
                <span class="season-reign-faces">${g.names.map(n => portrait(n)).join('')}</span>
                <span class="season-reign-name">${esc(label(g))}</span>
            </a>`;
        };
        const mark = ({ g, month }) => `<a class="season-reign-brief" href="${fighterLink(g.names[0])}" style="left:${(month - 0.5) / 12 * 100}%"
                title="${esc(`${label(g)} · won in M${month}${g.Season_Lost === currentSeason && g.Month_Lost === month ? ', lost it the same month' : month === 12 ? ', reign continues next season' : ''}`)}">${portrait(g.names[0])}</a>`;

        const belt = championshipToBeltAsset(title, 'sm');
        return `<div class="season-title-row">
            <div class="season-title-name">${belt ? `<img src="${belt}" alt="" loading="lazy">` : ''}<span>${esc(title)}</span></div>
            <div class="season-track">
                ${lastMonth < 12 ? `<span class="season-track-future" style="left:${lastMonth / 12 * 100}%"></span>` : ''}
                ${segments.map(seg).join('')}${brief.map(mark).join('')}
            </div>
        </div>`;
    }).join('');

    $('champTimeline').innerHTML = titles.length
        ? `<div class="season-title-row season-title-axis"><div></div>${axis}</div>${lines}`
        : '<p class="season-empty">No title reigns recorded.</p>';
}

// ── Standings ──────────────────────────────────────────────────
function buildStandings(data) {
    const months = {};
    (data.holistic || []).forEach(r => { months[r.Fighter_Name.toLowerCase()] = parseInt(r.Months_With_Title) || 0; });
    const awards = {};
    (data.awards || []).forEach(r => (awards[r.Fighter_Name.toLowerCase()] ||= []).push(r.Award_Name));
    const belts = {};
    (data.current_champions || []).forEach(r => (belts[String(r.Fighter_Name).toLowerCase()] ||= []).push(r.Championship_Name));

    standings = (data.rankings || []).map(r => {
        const name = r.Fighter_Name, key = name.toLowerCase();
        const pct = r['Win Percentage'] || '0.00%';
        return {
            name, pct,
            pctVal: parseFloat(String(pct).replace('%', '')) || 0,
            wins: parseInt(r.Wins) || 0, losses: parseInt(r.Losses) || 0,
            power_score: r.power_score, power_rank: r.power_rank,
            champ_months: months[key] || 0,
            season_end_elo: r.season_end_elo,
            awards: awards[key] || [], belts: belts[key] || [],
        };
    });
}

function renderStandings() {
    const val = (f, key) => key === 'pct' ? f.pctVal : (f[key] ?? -Infinity);
    const sign = sort.dir === 'desc' ? -1 : 1;
    const rows = [...standings].sort((a, b) => sign * (val(a, sort.key) - val(b, sort.key)) || (a.power_rank || 999) - (b.power_rank || 999));
    const shown = showAll ? rows : rows.slice(0, 10);

    document.querySelectorAll('#seasonRankingsTable .sortable').forEach(th => {
        const on = th.dataset.sort === sort.key;
        th.classList.toggle('active', on);
        th.classList.toggle('asc', on && sort.dir === 'asc');
    });

    $('seasonRankingsTbody').innerHTML = shown.map(f => {
        const chips = f.belts.map(t => `<span class="lb-belt">${esc(t)}</span>`).concat(f.awards.map(a => `<span class="lb-award">${esc(a)}</span>`)).join('');
        const ps = f.power_score;
        return `<tr data-name="${esc(f.name)}" class="${f.power_rank <= 3 ? 'is-top' : ''}">
            <td class="lb-col-rank"><span class="lb-rank">${f.power_rank ?? '—'}</span></td>
            <td class="lb-col-fighter"><a class="lb-fighter" href="${fighterLink(f.name)}">${portrait(f.name)}
                <span class="lb-fighter-text"><span class="lb-fighter-name">${esc(f.name)}</span>${chips ? `<span class="lb-fighter-titles">${chips}</span>` : ''}</span></a></td>
            <td class="lb-col-power">${ps != null ? `<div class="lb-power ${getPowerScoreClass(ps)}"><span class="lb-power-num">${ps.toFixed(1)}</span><span class="lb-power-track"><span class="lb-power-fill" style="width:${Math.max(2, Math.min(100, ps))}%"></span></span></div>` : '—'}</td>
            <td class="lb-num lb-record">${f.wins}<span class="lb-dash">–</span>${f.losses}</td>
            <td class="lb-num lb-col-pct ${getBandClass(f.pctVal, WIN_PCT_BANDS)}">${esc(f.pct)}</td>
            <td class="lb-num lb-col-elo">${f.champ_months || '<span class="lb-muted">—</span>'}</td>
            <td class="lb-num lb-col-elo ${getBandClass(f.season_end_elo, ELO_BANDS)}">${f.season_end_elo != null ? Math.round(f.season_end_elo) : '—'}</td>
        </tr>`;
    }).join('');

    const btn = $('showAllBtn');
    btn.hidden = rows.length <= 10;
    btn.textContent = showAll ? 'Show top 10' : `Show all ${rows.length} fighters`;
}

// ── Section nav (same behavior as the fighter and head-to-head pages) ──
function setupSectionNav() {
    const pills = document.querySelectorAll('#seasonPageNav .page-nav-pill');
    const jump = id => {
        const el = $(id);
        if (el) window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - (64 + 56), behavior: 'smooth' });
    };
    pills.forEach(p => p.addEventListener('click', e => { e.preventDefault(); jump(p.dataset.section); }));
    const spy = new IntersectionObserver(entries => entries.forEach(entry => {
        if (entry.isIntersecting) pills.forEach(p => p.classList.toggle('active', p.dataset.section === entry.target.id));
    }), { rootMargin: '-15% 0px -70% 0px' });
    pills.forEach(p => spy.observe($(p.dataset.section)));
}
