// Head to Head: two corners, the series score, tale of the tape, every shared fight, analytics.

const F1_COLOR = '#38bdf8';
const F1_BG    = 'rgba(56,189,248,0.14)';
const F2_COLOR = '#fb923c';
const F2_BG    = 'rgba(251,146,60,0.14)';
const GRID     = 'rgba(255,255,255,0.06)';
const TICK     = '#8b8fa3';
const TOOLTIP  = {
    backgroundColor: '#111318', borderColor: 'rgba(245,184,61,0.45)', borderWidth: 1,
    titleFont: { family: 'Inter' }, bodyFont: { family: 'Inter' }, padding: 10,
};
const LEGEND_LABELS = { padding: 14, font: { size: 12, family: 'Inter' }, color: '#c4c7d4', usePointStyle: true, pointStyle: 'circle' };

const EVENT_COLS = ['Won_Tournament','Won_Royal_Rumble','Won_Scramble','Won_Smash_Series','Won_Money_In_The_Bank','Won_Smash_Bros'];
const EVENT_NAMES = {
    Won_Tournament: 'Tournament', Won_Royal_Rumble: 'Royal Rumble',
    Won_Scramble: 'Scramble', Won_Smash_Series: 'Smash Series',
    Won_Money_In_The_Bank: 'Money in the Bank', Won_Smash_Bros: 'Smash Bros'
};

const charts = {};
let currentData = null;
let currentMode = 'career';

const $ = id => document.getElementById(id);
const sameName = (a, b) => String(a || '').toLowerCase() === String(b || '').toLowerCase();

document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.h2h-page [data-category]').forEach(input => setupAutocomplete(input, input.dataset.category));
    ['f1', 'f2'].forEach(side => {
        $(side + 'Input').addEventListener('change', () => previewCorner(side));
        $(side + 'Input').addEventListener('keydown', e => { if (e.key === 'Enter' && $('f1Input').value && $('f2Input').value) doCompare(); });
    });
    $('compareBtn').addEventListener('click', doCompare);
    $('swapBtn').addEventListener('click', () => {
        const a = $('f1Input').value;
        $('f1Input').value = $('f2Input').value;
        $('f2Input').value = a;
        previewCorner('f1');
        previewCorner('f2');
        if ($('f1Input').value && $('f2Input').value) doCompare();
    });

    $('btnCareer').addEventListener('click', () => setMode('career'));
    $('btnSeason').addEventListener('click', () => setMode('season'));
    ['seasonF1', 'seasonF2'].forEach(id => $(id).addEventListener('change', () => {
        if (currentMode === 'season' && currentData) { renderAll(currentData, 'season'); updateH2HURL(); }
    }));

    // Shareable links: /head2head?f1=Kirby&f2=Pikachu[&mode=season&s1=3&s2=3]
    const p = new URLSearchParams(window.location.search);
    const pf1 = p.get('f1'), pf2 = p.get('f2');
    ['f1', 'f2'].forEach(side => previewCorner(side));
    if (pf1 && pf2) {
        $('f1Input').value = pf1;
        $('f2Input').value = pf2;
        previewCorner('f1');
        previewCorner('f2');
        if (p.get('mode') === 'season') window._pendingSeasonMode = { s1: p.get('s1'), s2: p.get('s2') };
        doCompare();
    }
});

// ── Corners ───────────────────────────────────────────────────
function previewCorner(side) {
    const name = $(side + 'Input').value.trim();
    const frame = $(side + 'Frame');
    const img = $(side + 'Img');
    $(side + 'Name').textContent = name || (side === 'f1' ? 'Fighter 1' : 'Fighter 2');
    if (!name) {
        frame.classList.add('is-empty');
        img.removeAttribute('src');
        $(side + 'Brand').hidden = true;
        $(side + 'Sub').innerHTML = '&nbsp;';
        return;
    }
    img.onerror = () => { img.onerror = null; frame.classList.add('is-empty'); };
    img.onload = () => frame.classList.remove('is-empty');
    img.src = fighterImg(name, 'md');
    img.alt = name;
}

function fillCorner(side, fighter) {
    $(side + 'Name').textContent = fighter.name;
    const brand = $(side + 'Brand');
    brand.hidden = !fighter.brand;
    brand.textContent = fighter.brand || '';
    $(side + 'Corner').className = `h2h-corner h2h-${side}` + (fighter.brand ? ` brand-${fighter.brand.toLowerCase()}` : '');
    const cps = fighter.career_power_score || {};
    const parts = [];
    if (cps.power_rank) parts.push(`<a href="/leaderboard">#${cps.power_rank} power score</a>`);
    parts.push(`${fighter.career.wins}–${fighter.career.losses}`);
    $(side + 'Sub').innerHTML = parts.join(' · ') +
        ` · <a href="/fighter/${encodeURIComponent(fighter.name)}">Profile</a>`;
}

// ── Load ──────────────────────────────────────────────────────
function doCompare() {
    const f1 = $('f1Input').value.trim();
    const f2 = $('f2Input').value.trim();
    const err = $('compareError');
    if (!f1 || !f2) { err.textContent = 'Pick two fighters.'; return; }
    if (sameName(f1, f2)) { err.textContent = 'Pick two different fighters.'; return; }
    err.textContent = '';

    $('compareLoading').style.display = 'flex';
    $('compareBtn').disabled = true;

    fetch('/api/compare', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({fighter1: f1, fighter2: f2})
    })
    .then(r => r.json())
    .then(data => {
        $('compareLoading').style.display = 'none';
        $('compareBtn').disabled = false;
        if (data.error) { err.textContent = data.error; return; }
        currentData = data;
        // Use the canonical spellings the server matched.
        $('f1Input').value = data.fighter1.name;
        $('f2Input').value = data.fighter2.name;
        fillCorner('f1', data.fighter1);
        fillCorner('f2', data.fighter2);
        populateSeasonPickers(data);
        const pending = window._pendingSeasonMode;
        delete window._pendingSeasonMode;
        if (pending) {
            if (pending.s1) $('seasonF1').value = pending.s1;
            if (pending.s2) $('seasonF2').value = pending.s2;
        }
        $('compareResults').hidden = false;
        setMode(pending ? 'season' : 'career');
    })
    .catch(e => {
        $('compareLoading').style.display = 'none';
        $('compareBtn').disabled = false;
        err.textContent = 'Could not load the comparison. ' + e.message;
    });
}

function setMode(mode) {
    currentMode = mode;
    $('btnCareer').classList.toggle('active', mode === 'career');
    $('btnSeason').classList.toggle('active', mode === 'season');
    $('seasonPickers').hidden = mode !== 'season';
    if (currentData) { renderAll(currentData, mode); updateH2HURL(); }
}

function updateH2HURL() {
    const params = new URLSearchParams();
    params.set('f1', $('f1Input').value.trim());
    params.set('f2', $('f2Input').value.trim());
    if (currentMode === 'season') {
        params.set('mode', 'season');
        params.set('s1', $('seasonF1').value);
        params.set('s2', $('seasonF2').value);
    }
    history.replaceState(null, '', `/head2head?${params}`);
}

function populateSeasonPickers(d) {
    $('seasonF1Name').textContent = d.fighter1.name;
    $('seasonF2Name').textContent = d.fighter2.name;
    const fill = (id, seasons) => {
        const sel = $(id);
        sel.innerHTML = seasons.map(s => `<option value="${s.season}">Season ${s.season}</option>`).join('');
        if (seasons.length) sel.value = seasons[seasons.length - 1].season;
    };
    fill('seasonF1', d.fighter1.by_season);
    fill('seasonF2', d.fighter2.by_season);
}

function filterToSeason(fighter, season) {
    const s = String(season);
    const seasonRow = fighter.by_season.find(r => String(r.season) === s) || {};
    return {
        ...fighter,
        holistic:  fighter.holistic.filter(r => String(r.Season) === s),
        by_season: fighter.by_season.filter(r => String(r.season) === s),
        running:   fighter.running.filter(r => String(r.season) === s),
        awards:    (fighter.awards || []).filter(r => r.season === parseInt(season)),
        career: { wins: seasonRow.wins || 0, losses: seasonRow.losses || 0, win_pct: seasonRow.win_pct || '0.00%' },
    };
}

function renderAll(d, mode) {
    const isSeason = mode === 'season';
    const f1Season = $('seasonF1').value;
    const f2Season = $('seasonF2').value;
    const d1 = isSeason ? filterToSeason(d.fighter1, f1Season) : d.fighter1;
    const d2 = isSeason ? filterToSeason(d.fighter2, f2Season) : d.fighter2;
    const maxes = isSeason
        ? { ...d.season_roster_maxes, max_title: 12, max_major: 12, max_ev: 6 }  // a season has 12 months and 6 event types
        : d.roster_maxes;
    // In season mode the rivalry only makes sense when both sides are the same season.
    const fights = !isSeason ? d.shared_fights
        : (String(f1Season) === String(f2Season) ? d.shared_fights.filter(f => String(f.season) === String(f1Season)) : null);

    $('momentumTitle').textContent = isSeason ? 'Season Win Rate Momentum' : 'Career Win Rate Momentum';
    $('momentumSubtitle').textContent = isSeason ? 'Running win rate through the selected season' : 'Running career win rate after each fight';
    $('tapeTitle').textContent = isSeason ? 'Tale of the Tape · Season' : 'Tale of the Tape';

    renderScoreboard(d, fights, isSeason ? f1Season : null);
    renderTape(d, d1, d2, isSeason);
    renderRadar({ fighter1: d1, fighter2: d2, roster_maxes: maxes }, isSeason);
    renderMomentum({ fighter1: d1, fighter2: d2 }, isSeason);
    $('fightsSection').hidden = !fights;
    if (fights) renderFights(d, fights);
    $('seasonsSection').hidden = isSeason;
    if (isSeason) {
        renderEloComparison(d, f1Season, f2Season);
        renderPowerScoreSeasonMode(d, f1Season, f2Season);
    } else {
        renderEloComparison(d);
        renderPowerScoreCompare(d);
        renderSeasons(d);
    }
}

// Only fights where one of them beat the other count toward the series.
function directResult(fight, f1Name, f2Name) {
    const a = fight.fighters.find(f => sameName(f.name, f1Name));
    const b = fight.fighters.find(f => sameName(f.name, f2Name));
    if (!a || !b) return null;
    if (isWinner(a) && !isWinner(b) && !isNoContest(b)) return 'f1';
    if (isWinner(b) && !isWinner(a) && !isNoContest(a)) return 'f2';
    return null;
}

// ── Series score ──────────────────────────────────────────────
function renderScoreboard(d, fights, season) {
    let w1, w2, label;
    if (!fights) {
        w1 = w2 = 0;
        label = 'Different seasons, so no shared fights';
    } else if (season) {
        const results = fights.map(f => directResult(f, d.fighter1.name, d.fighter2.name));
        w1 = results.filter(r => r === 'f1').length;
        w2 = results.filter(r => r === 'f2').length;
        label = `${w1 + w2} meeting${w1 + w2 === 1 ? '' : 's'} in Season ${season}`;
    } else {
        w1 = d.fighter1.h2h_wins;
        w2 = d.fighter2.h2h_wins;
        label = w1 + w2 ? `${w1 + w2} head-to-head meeting${w1 + w2 === 1 ? '' : 's'}` : 'They have never met head to head';
    }
    $('h2hVs').hidden = true;
    $('h2hScore').hidden = $('h2hSplit').hidden = $('sbLabel').hidden = false;
    $('sbScore1').textContent = w1;
    $('sbScore2').textContent = w2;
    const pct = w1 + w2 ? Math.round(w1 / (w1 + w2) * 100) : 50;
    requestAnimationFrame(() => {
        $('sbBarF1').style.width = pct + '%';
        $('sbBarF2').style.width = (100 - pct) + '%';
    });
    $('sbLabel').textContent = label;
    $('f1Corner').classList.toggle('is-leading', w1 > w2);
    $('f2Corner').classList.toggle('is-leading', w2 > w1);
}

// ── Tale of the tape ──────────────────────────────────────────
function renderTape(d, f1, f2, isSeason) {
    const sum = (rows, col) => rows.reduce((s, r) => s + (parseInt(r[col]) || 0), 0);
    const events = hol => { const s = new Set(); hol.forEach(r => EVENT_COLS.forEach(c => { if (r[c] != null && r[c] !== '') s.add(c); })); return s.size; };
    const titles = fighter => {
        if (!isSeason) return fighter.unique_champs;
        const s = new Set();
        fighter.holistic.forEach(r => (r.Titles_Held || '').split(',').forEach(t => { if (t.trim()) s.add(t.trim()); }));
        return s.size;
    };
    const pct = v => parseFloat(String(v).replace('%', '')) || 0;
    const months = n => `${n} <small>mo</small>`;

    let ps1, ps2;
    if (isSeason) {
        ps1 = (d.fighter1.power_scores_by_season || {})[$('seasonF1').value] || {};
        ps2 = (d.fighter2.power_scores_by_season || {})[$('seasonF2').value] || {};
    } else {
        ps1 = d.fighter1.career_power_score || {};
        ps2 = d.fighter2.career_power_score || {};
    }
    const psText = ps => ps.power_score != null ? `${ps.power_score.toFixed(1)} <small>#${ps.power_rank}</small>` : '—';

    // [label, f1 html, f2 html, f1 number, f2 number] (higher number leads)
    const rows = [
        [isSeason ? 'Season power score' : 'Power score', psText(ps1), psText(ps2), ps1.power_score || 0, ps2.power_score || 0],
        ['Win rate', f1.career.win_pct, f2.career.win_pct, pct(f1.career.win_pct), pct(f2.career.win_pct)],
        ['Record', `${f1.career.wins}–${f1.career.losses}`, `${f2.career.wins}–${f2.career.losses}`, +f1.career.wins || 0, +f2.career.wins || 0],
        ...(isSeason ? [] : [
            ['Title fights', `${d.fighter1.champ_stats.wins}–${d.fighter1.champ_stats.losses}`, `${d.fighter2.champ_stats.wins}–${d.fighter2.champ_stats.losses}`, +d.fighter1.champ_stats.wins || 0, +d.fighter2.champ_stats.wins || 0],
        ]),
        ['Months as a major champion', months(sum(f1.holistic, 'Months_With_Major')), months(sum(f2.holistic, 'Months_With_Major')), sum(f1.holistic, 'Months_With_Major'), sum(f2.holistic, 'Months_With_Major')],
        ['Months holding any title', months(sum(f1.holistic, 'Months_With_Title')), months(sum(f2.holistic, 'Months_With_Title')), sum(f1.holistic, 'Months_With_Title'), sum(f2.holistic, 'Months_With_Title')],
        ['Different titles won', titles(f1), titles(f2), titles(f1), titles(f2)],
        ['Event types won', `${events(f1.holistic)}<small>/6</small>`, `${events(f2.holistic)}<small>/6</small>`, events(f1.holistic), events(f2.holistic)],
        ...(isSeason ? [[
            'Awards',
            (f1.awards || []).map(a => escapeHTML(a.name)).join('<br>') || '—',
            (f2.awards || []).map(a => escapeHTML(a.name)).join('<br>') || '—',
            (f1.awards || []).length, (f2.awards || []).length,
        ]] : []),
    ];

    let lead1 = 0, lead2 = 0;
    $('statsGrid').innerHTML = rows.map(([label, v1, v2, n1, n2]) => {
        const total = n1 + n2;
        const share = total > 0 ? n1 / total * 100 : 50;
        if (n1 > n2) lead1++; else if (n2 > n1) lead2++;
        return `<div class="h2h-tape-row">
            <div class="h2h-tape-val h2h-f1-val${n1 > n2 ? ' is-lead' : ''}">${v1}</div>
            <div class="h2h-tape-label">${label}</div>
            <div class="h2h-tape-val h2h-f2-val${n2 > n1 ? ' is-lead' : ''}">${v2}</div>
            <div class="h2h-tape-bar"><span class="h2h-tape-f1" style="width:${share}%"></span><span class="h2h-tape-f2" style="width:${100 - share}%"></span></div>
        </div>`;
    }).join('');

    const n1 = escapeHTML(d.fighter1.name), n2 = escapeHTML(d.fighter2.name);
    $('tapeSummary').innerHTML = lead1 === lead2
        ? `Dead even: ${lead1} categories each`
        : `<strong class="${lead1 > lead2 ? 'h2h-f1-text' : 'h2h-f2-text'}">${lead1 > lead2 ? n1 : n2}</strong> leads ${Math.max(lead1, lead2)} of ${rows.length} categories`;
}

// ── The rivalry: every meeting, then every shared fight ───────
function renderFights(d, fights) {
    const f1Name = d.fighter1.name, f2Name = d.fighter2.name;
    const list = $('fightsBetweenWrap');
    list.innerHTML = '';
    const results = fights.map(f => directResult(f, f1Name, f2Name));
    const direct = results.filter(Boolean).length;

    $('fightCountLabel').textContent = !fights.length ? 'No shared fights'
        : fights.length === direct ? `${direct} meeting${direct === 1 ? '' : 's'}, newest first`
        : `${fights.length} shared fights · ${direct} head to head, ${fights.length - direct} won by someone else or as teammates`;

    // Oldest to newest, one square per head-to-head meeting, colored by who won.
    const meetings = fights.map((f, i) => ({ f, r: results[i] })).filter(m => m.r).reverse();
    $('h2hMeetings').innerHTML = meetings.length ? `
        <span class="h2h-meetings-label">First</span>
        <div class="h2h-meetings-track">${meetings.map(({ f, r }) => {
            const who = r === 'f1' ? f1Name : f2Name;
            const title = `S${f.season} M${f.month}${f.championship ? ' · ' + f.championship + ' title' : ''} · ${who} won`;
            return `<a href="/fight/${f.fight_id}" class="h2h-meeting h2h-meeting-${r}${f.championship ? ' is-title' : ''}" title="${escapeHTML(title)}" aria-label="${escapeHTML(title)}"></a>`;
        }).join('')}</div>
        <span class="h2h-meetings-label">Latest</span>` : '';

    if (!fights.length) {
        list.innerHTML = '<div class="fight-empty">These two have never shared a fight.</div>';
        return;
    }
    fights.forEach(fight => {
        const row = appendFight(list, fight);
        row.classList.add('clickable-row');
        row.addEventListener('click', () => { window.location.href = `/fight/${fight.fight_id}`; });
    });
}

// ── Fingerprint radar ─────────────────────────────────────────
function radarRawValues(fighter) {
    const h = fighter.holistic;
    const wr = parseFloat(String(fighter.career.win_pct).replace('%','')) || 0;
    const totalMajor = h.reduce((s,r) => s+(parseInt(r.Months_With_Major)||0), 0);
    const totalTitle = h.reduce((s,r) => s+(parseInt(r.Months_With_Title)||0), 0);
    const wonSet = new Set();
    h.forEach(r => EVENT_COLS.forEach(c => { if (r[c]!=null && r[c]!=='') wonSet.add(c); }));
    const titleSet = new Set();
    h.forEach(r => { if (r.Titles_Held) r.Titles_Held.split(',').forEach(t => { const v = t.trim(); if (v) titleSet.add(v); }); });
    const tc = titleSet.size || fighter.unique_champs || 0;
    return { wr, totalMajor, totalTitle, ev: wonSet.size, tc, wonSet, fighter };
}

function renderRadar(d, isSeason) {
    const m = d.roster_maxes;
    const norm = (v, max) => max > 0 ? (v / max) * 100 : 0;
    const shape = raw => ({
        data: [norm(raw.wr, m.max_wr), norm(raw.totalTitle, m.max_title), norm(raw.totalMajor, m.max_major), norm(raw.ev, m.max_ev), norm(raw.tc, m.max_champs)],
        raw,
    });
    const r1 = shape(radarRawValues(d.fighter1));
    const r2 = shape(radarRawValues(d.fighter2));

    const panel = $('compareRadar').closest('.h2h-panel');
    panel.querySelector('.h2h-panel-title').textContent = isSeason ? 'Season Fingerprint' : 'Career Fingerprint';
    panel.querySelector('.h2h-panel-sub').textContent = isSeason ? 'Normalized season performance across five dimensions' : 'Normalized career performance across five dimensions';

    if (charts.radar) charts.radar.destroy();
    charts.radar = new Chart($('compareRadar').getContext('2d'), {
        type: 'radar',
        data: {
            labels: ['Win Rate', 'Title Reign', 'Major Title Reign', 'Event Wins', 'Unique Titles'],
            datasets: [
                { label: d.fighter1.name, data: r1.data, borderColor: F1_COLOR, backgroundColor: F1_BG, borderWidth: 2.5, pointRadius: 4, pointBackgroundColor: F1_COLOR, _r: r1.raw },
                { label: d.fighter2.name, data: r2.data, borderColor: F2_COLOR, backgroundColor: F2_BG, borderWidth: 2.5, pointRadius: 4, pointBackgroundColor: F2_COLOR, _r: r2.raw },
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: { r: { min: 0, max: 100, grid: { color: GRID }, angleLines: { color: GRID }, ticks: { display: false }, pointLabels: { color: '#c4c7d4', font: { size: 12, family: 'Inter' } } } },
            plugins: {
                legend: { position: 'bottom', labels: LEGEND_LABELS },
                tooltip: { ...TOOLTIP, callbacks: { label: it => {
                    const r = it.dataset._r, f = r.fighter, s = it.dataset.label;
                    const axis = it.chart.data.labels[it.dataIndex];
                    if (axis === 'Win Rate') return `  ${s}: ${f.career.win_pct}`;
                    if (axis === 'Major Title Reign') return `  ${s}: ${r.totalMajor} month(s)`;
                    if (axis === 'Title Reign') return `  ${s}: ${r.totalTitle} month(s)`;
                    if (axis === 'Event Wins') return `  ${s}: ${[...r.wonSet].map(c => EVENT_NAMES[c]).join(', ') || 'None'}`;
                    if (axis === 'Unique Titles') return `  ${s}: ${r.tc} title(s)`;
                    return `  ${s}: ${it.raw.toFixed(0)}`;
                }}}
            },
            animation: { duration: 700 }
        }
    });
}

// ── Win rate momentum ─────────────────────────────────────────
function renderMomentum(d, isSeason) {
    const parseCareer = arr => arr.map((r, i) => ({x: i+1, y: parseFloat(String(r.career_win_pct).replace('%','')) || 0}));
    const parseSeason = arr => {
        let wins = 0, total = 0;
        // No-contests count as neither a win nor a loss (same as the database's running stats).
        return arr.map((r, i) => {
            if (r.decision === 'w' || r.decision === 'l') total++;
            if (r.decision === 'w') wins++;
            return {x: i+1, y: total ? (wins/total)*100 : null};
        });
    };
    const parse = isSeason ? parseSeason : parseCareer;
    const f1pts = parse(d.fighter1.running);
    const f2pts = parse(d.fighter2.running);
    const maxFights = Math.max(f1pts.length, f2pts.length, 1);

    const canvas = $('compareMomentum');
    canvas.width = Math.max(900, maxFights * 10);
    canvas.height = 260;

    if (charts.momentum) charts.momentum.destroy();
    charts.momentum = new Chart(canvas.getContext('2d'), {
        plugins: [stickyYAxisPlugin],
        type: 'line',
        data: { datasets: [
            { label: d.fighter1.name, data: f1pts, borderColor: F1_COLOR, backgroundColor: F1_BG, borderWidth: 2, pointRadius: 0, pointHoverRadius: 5, tension: 0.3, fill: true },
            { label: d.fighter2.name, data: f2pts, borderColor: F2_COLOR, backgroundColor: F2_BG, borderWidth: 2, pointRadius: 0, pointHoverRadius: 5, tension: 0.3, fill: true },
            { label: '50%', data: [{x: 1, y: 50}, {x: maxFights, y: 50}], borderColor: 'rgba(255,255,255,0.18)', borderWidth: 1, borderDash: [6, 4], pointRadius: 0, fill: false },
        ]},
        options: {
            responsive: false, maintainAspectRatio: false, parsing: false,
            scales: {
                y: { min: 0, max: 100, grid: { color: GRID }, ticks: { callback: v => v + '%', color: TICK } },
                x: { type: 'linear', min: 1, grid: { color: GRID }, ticks: { color: TICK, font: { size: 11 } }, title: { display: true, text: 'Fight #', color: TICK, font: { size: 11 } } },
            },
            plugins: {
                legend: { position: 'top', align: 'end', labels: { ...LEGEND_LABELS, filter: item => item.text !== '50%' } },
                tooltip: { ...TOOLTIP, callbacks: { label: it => it.dataset.label === '50%' ? null : `  ${it.dataset.label}: ${it.parsed.y.toFixed(1)}%` } }
            },
            animation: { duration: 700 }
        }
    });
}

// ── Elo history ───────────────────────────────────────────────
function renderEloComparison(d, f1Season, f2Season) {
    const isSeason = f1Season != null;
    let f1hist = d.fighter1.elo_history || [];
    let f2hist = d.fighter2.elo_history || [];
    if (isSeason) {
        f1hist = f1hist.filter(r => String(r.season) === String(f1Season));
        f2hist = f2hist.filter(r => String(r.season) === String(f2Season));
    }
    const section = $('eloSection');
    section.querySelector('.h2h-panel-title').textContent = isSeason ? 'Season Elo Rating History' : 'Elo Rating History';

    const toPoints = arr => arr.map(r => ({ x: r.fight_id, y: r.elo_after, season: r.season, month: r.month }));
    const f1pts = toPoints(f1hist), f2pts = toPoints(f2hist);
    const ids = [...f1pts, ...f2pts].map(p => p.x);
    if (!ids.length) { section.hidden = true; return; }
    section.hidden = false;
    const minX = Math.min(...ids), maxX = Math.max(...ids);

    const canvas = $('compareElo');
    canvas.width = Math.max(900, (maxX - minX) * 0.4);
    canvas.height = 280;

    const line = (label, data, color) => ({ label, data, borderColor: color, borderWidth: 2, pointRadius: 1.5, pointHoverRadius: 5, pointBackgroundColor: color, tension: 0.25, fill: false });
    if (charts.elo) charts.elo.destroy();
    charts.elo = new Chart(canvas.getContext('2d'), {
        plugins: [stickyYAxisPlugin],
        type: 'line',
        data: { datasets: [
            line(d.fighter1.name, f1pts, F1_COLOR),
            line(d.fighter2.name, f2pts, F2_COLOR),
            { label: 'Baseline (1500)', data: [{ x: minX, y: 1500 }, { x: maxX, y: 1500 }], borderColor: 'rgba(255,255,255,0.18)', borderWidth: 1, borderDash: [6, 4], pointRadius: 0, fill: false },
        ]},
        options: {
            responsive: false, maintainAspectRatio: false, parsing: false,
            scales: {
                x: { type: 'linear', min: minX, grid: { color: GRID }, ticks: { display: false }, title: { display: true, text: 'Fight (chronological)', color: TICK, font: { size: 11 } } },
                y: { grid: { color: GRID }, ticks: { color: TICK, callback: v => v.toFixed(0) } },
            },
            plugins: {
                legend: { position: 'top', align: 'end', labels: { ...LEGEND_LABELS, filter: item => !item.text.startsWith('Baseline') } },
                tooltip: { ...TOOLTIP, mode: 'index', intersect: false, callbacks: {
                    title: items => { const p = items[0]?.raw; return p ? `S${p.season} M${p.month}` : ''; },
                    label: it => it.dataset.label.startsWith('Baseline') ? null : `  ${it.dataset.label}: ${it.parsed.y.toFixed(0)}`,
                }},
            },
            animation: { duration: 700 },
        }
    });
}

// ── Power score by season ─────────────────────────────────────
function renderPowerScoreCompare(d) {
    const wrap = $('powerScoreCompareWrap');
    $('powerScoreSection').hidden = false;
    $('powerScoreSection').querySelector('.h2h-panel-sub').textContent = 'End-of-season composite score and rank';
    const ps1 = d.fighter1.power_scores_by_season || {};
    const ps2 = d.fighter2.power_scores_by_season || {};
    const seasons = [...new Set([...Object.keys(ps1), ...Object.keys(ps2)])].map(Number).sort((a, b) => a - b);
    if (!seasons.length) { wrap.innerHTML = '<p class="h2h-panel-sub">No power scores yet.</p>'; return; }

    const cell = (v, other, side) => {
        if (!v) return `<td class="h2h-ps-cell h2h-ps-${side} is-empty">—</td>`;
        const lead = other && v.power_score > other.power_score;
        return `<td class="h2h-ps-cell h2h-ps-${side}${lead ? ' is-lead' : ''}"><span class="${getPowerScoreClass(v.power_score)}">${v.power_score.toFixed(1)}</span> <small>#${v.power_rank}</small></td>`;
    };
    wrap.innerHTML = `<table class="h2h-ps-table">
        <thead><tr><th class="h2h-f1-text">${escapeHTML(d.fighter1.name)}</th><th>Season</th><th class="h2h-f2-text">${escapeHTML(d.fighter2.name)}</th></tr></thead>
        <tbody>${seasons.map(s => `<tr>${cell(ps1[s], ps2[s], 'f1')}<td class="h2h-ps-season">S${s}</td>${cell(ps2[s], ps1[s], 'f2')}</tr>`).join('')}</tbody>
    </table>`;
}

function renderPowerScoreSeasonMode(d, s1, s2) {
    const v1 = (d.fighter1.power_scores_by_season || {})[s1];
    const v2 = (d.fighter2.power_scores_by_season || {})[s2];
    const section = $('powerScoreSection');
    if (!v1 && !v2) { section.hidden = true; return; }
    section.hidden = false;
    section.querySelector('.h2h-panel-sub').textContent = 'Power score and rank in the selected season';
    const card = (v, other, name, season, side) => `<div class="h2h-ps-card h2h-ps-${side}${v && other && v.power_score > other.power_score ? ' is-lead' : ''}">
        <span class="h2h-ps-card-name">${escapeHTML(name)} · S${season}</span>
        <span class="h2h-ps-card-score ${v ? getPowerScoreClass(v.power_score) : ''}">${v ? v.power_score.toFixed(1) : '—'}</span>
        <span class="h2h-ps-card-rank">${v ? `#${v.power_rank} that season` : 'No score'}</span>
    </div>`;
    $('powerScoreCompareWrap').innerHTML = `<div class="h2h-ps-cards">
        ${card(v1, v2, d.fighter1.name, s1, 'f1')}${card(v2, v1, d.fighter2.name, s2, 'f2')}
    </div>`;
}

// ── Season by season ──────────────────────────────────────────
function renderSeasons(d) {
    const a = d.fighter1.by_season, b = d.fighter2.by_season;
    const seasons = [...new Set([...a.map(r => r.season), ...b.map(r => r.season)])].sort((x, y) => +x - +y);
    const pick = (rows, s, key) => (rows.find(r => r.season == s) || {})[key] || 0;
    const bar = (label, data, color, stack) => ({ label, data, backgroundColor: color, borderRadius: 4, stack });

    if (charts.seasons) charts.seasons.destroy();
    charts.seasons = new Chart($('compareSeasons').getContext('2d'), {
        type: 'bar',
        data: {
            labels: seasons.map(s => 'S' + s),
            datasets: [
                bar(d.fighter1.name + ' wins', seasons.map(s => pick(a, s, 'wins')), F1_COLOR, 'f1'),
                bar(d.fighter1.name + ' losses', seasons.map(s => pick(a, s, 'losses')), 'rgba(56,189,248,0.25)', 'f1'),
                bar(d.fighter2.name + ' wins', seasons.map(s => pick(b, s, 'wins')), F2_COLOR, 'f2'),
                bar(d.fighter2.name + ' losses', seasons.map(s => pick(b, s, 'losses')), 'rgba(251,146,60,0.25)', 'f2'),
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: {
                y: { grid: { color: GRID }, ticks: { color: TICK } },
                x: { grid: { display: false }, ticks: { color: TICK } },
            },
            plugins: {
                legend: { position: 'bottom', labels: { ...LEGEND_LABELS, pointStyle: 'rectRounded' } },
                tooltip: TOOLTIP,
            },
            animation: { duration: 600 }
        }
    });
}
