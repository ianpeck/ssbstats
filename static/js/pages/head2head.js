const PORTRAIT_PLACEHOLDER = {
    f1: `data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 287 300%22><rect fill=%22%2312122a%22 width=%22287%22 height=%22300%22/><text fill=%22%23607cff%22 x=%2250%25%22 y=%2250%25%22 text-anchor=%22middle%22 dy=%22.3em%22 font-size=%2224%22>Fighter 1</text></svg>`,
    f2: `data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 287 300%22><rect fill=%22%2312122a%22 width=%22287%22 height=%22300%22/><text fill=%22%23fb923c%22 x=%2250%25%22 y=%2250%25%22 text-anchor=%22middle%22 dy=%22.3em%22 font-size=%2224%22>Fighter 2</text></svg>`,
};

document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('[data-category]').forEach(input => {
        setupAutocomplete(input, input.dataset.category);
    });
    document.getElementById('f1Input').addEventListener('change', updatePortrait.bind(null, 'f1'));
    document.getElementById('f2Input').addEventListener('change', updatePortrait.bind(null, 'f2'));

    // Auto-run comparison from URL params (shareable links)
    const p = new URLSearchParams(window.location.search);
    const pf1 = p.get('f1'), pf2 = p.get('f2');
    const pMode = p.get('mode'), pS1 = p.get('s1'), pS2 = p.get('s2');
    if (pf1 && pf2) {
        document.getElementById('f1Input').value = pf1;
        document.getElementById('f2Input').value = pf2;
        updatePortrait('f1');
        updatePortrait('f2');
        if (pMode === 'season') {
            // Store season selections to apply after data loads
            window._pendingSeasonMode = { s1: pS1, s2: pS2 };
        }
        doCompare();
    }
});

function updatePortrait(slot) {
    const name = document.getElementById(slot + 'Input').value.trim();
    const img  = document.getElementById(slot + 'Img');
    if (!name) { img.src = PORTRAIT_PLACEHOLDER[slot]; return; }
    img.onerror = () => { img.onerror = null; img.src = PORTRAIT_PLACEHOLDER[slot]; };
    img.src = `/static/assets/fighters/${fighterToFilename(name)}.png`;
}

const charts = {};

const F1_COLOR  = '#607cff';
const F1_BG     = 'rgba(96,124,255,0.13)';
const F2_COLOR  = '#fb923c';
const F2_BG     = 'rgba(251,146,60,0.13)';
const EVENT_COLS = ['Won_Tournament','Won_Royal_Rumble','Won_Scramble','Won_Smash_Series','Won_Money_In_The_Bank','Won_Smash_Bros'];
const EVENT_NAMES = {
    Won_Tournament: 'Tournament', Won_Royal_Rumble: 'Royal Rumble',
    Won_Scramble: 'Scramble', Won_Smash_Series: 'Smash Series',
    Won_Money_In_The_Bank: 'Money in the Bank', Won_Smash_Bros: 'Smash Bros'
};

function doCompare() {
    const f1 = document.getElementById('f1Input').value.trim();
    const f2 = document.getElementById('f2Input').value.trim();
    const err = document.getElementById('compareError');
    if (!f1 || !f2) { err.textContent = 'Enter both fighters.'; return; }
    if (f1.toLowerCase() === f2.toLowerCase()) { err.textContent = 'Pick two different fighters.'; return; }
    err.textContent = '';
    updateH2HURL(f1, f2);

    document.getElementById('f1Img').src = `/static/assets/fighters/${fighterToFilename(f1)}.png`;
    document.getElementById('f2Img').src = `/static/assets/fighters/${fighterToFilename(f2)}.png`;

    document.getElementById('compareLoading').style.display = 'flex';
    document.getElementById('compareResults').style.display = 'none';
    document.getElementById('compareBtn').disabled = true;

    fetch('/api/compare', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({fighter1: f1, fighter2: f2})
    })
    .then(r => r.json())
    .then(data => {
        document.getElementById('compareLoading').style.display = 'none';
        document.getElementById('compareBtn').disabled = false;
        if (data.error) { document.getElementById('compareError').textContent = data.error; return; }
        currentData = data;
        populateSeasonPickers(data);
        if (window._pendingSeasonMode) {
            const { s1, s2 } = window._pendingSeasonMode;
            delete window._pendingSeasonMode;
            currentMode = 'season';
            document.getElementById('btnSeason').classList.add('active');
            document.getElementById('btnCareer').classList.remove('active');
            document.getElementById('seasonPickers').style.display = '';
            if (s1) document.getElementById('seasonF1').value = s1;
            if (s2) document.getElementById('seasonF2').value = s2;
            renderAll(data, 'season');
        } else {
            currentMode = 'career';
            document.getElementById('btnCareer').classList.add('active');
            document.getElementById('btnSeason').classList.remove('active');
            document.getElementById('seasonPickers').style.display = 'none';
            renderAll(data, 'career');
        }
        document.getElementById('compareResults').style.display = 'block';
        document.getElementById('compareResults').scrollIntoView({behavior: 'smooth', block: 'start'});
    })
    .catch(e => {
        document.getElementById('compareLoading').style.display = 'none';
        document.getElementById('compareBtn').disabled = false;
        document.getElementById('compareError').textContent = 'Error: ' + e.message;
    });
}

let currentData = null;
let currentMode = 'career';

function updateH2HURL(f1, f2) {
    const params = new URLSearchParams();
    if (f1) params.set('f1', f1);
    if (f2) params.set('f2', f2);
    if (currentMode === 'season') {
        params.set('mode', 'season');
        const s1 = document.getElementById('seasonF1')?.value;
        const s2 = document.getElementById('seasonF2')?.value;
        if (s1) params.set('s1', s1);
        if (s2) params.set('s2', s2);
    }
    history.replaceState(null, '', `/head2head?${params}`);
}

function populateSeasonPickers(d) {
    document.getElementById('seasonF1Name').textContent = d.fighter1.name;
    document.getElementById('seasonF2Name').textContent = d.fighter2.name;
    const populate = (selId, seasons) => {
        const sel = document.getElementById(selId);
        sel.innerHTML = seasons.map(s => `<option value="${s.season}">Season ${s.season}</option>`).join('');
        if (seasons.length) sel.value = seasons[seasons.length - 1].season;
    };
    populate('seasonF1', d.fighter1.by_season);
    populate('seasonF2', d.fighter2.by_season);
}

function filterToSeason(fighter, season) {
    const s = String(season);
    const sInt = parseInt(season);
    const seasonRow = fighter.by_season.find(r => String(r.season) === s) || {};
    return {
        ...fighter,
        holistic:  fighter.holistic.filter(r => String(r.Season) === s),
        by_season: fighter.by_season.filter(r => String(r.season) === s),
        running:   fighter.running.filter(r => String(r.season) === s),
        awards:    (fighter.awards || []).filter(r => r.season === sInt),
        career: {
            wins:    seasonRow.wins    || 0,
            losses:  seasonRow.losses  || 0,
            win_pct: seasonRow.win_pct || '0.00%',
        },
    };
}

function renderAll(d, mode) {
    mode = mode || 'career';
    const isSeason = mode === 'season';
    const f1Season = document.getElementById('seasonF1')?.value;
    const f2Season = document.getElementById('seasonF2')?.value;
    const d1 = isSeason ? filterToSeason(d.fighter1, f1Season) : d.fighter1;
    const d2 = isSeason ? filterToSeason(d.fighter2, f2Season) : d.fighter2;
    const maxes = isSeason ? {
        ...d.season_roster_maxes,
        max_title: 12,   // hard cap: max possible months in a single season
        max_major: 12,
        max_ev:    6,    // normalize against all 6 event types
    } : d.roster_maxes;

    document.getElementById('momentumTitle').textContent     = isSeason ? 'Season Win Rate Momentum' : 'Career Win Rate Momentum';
    document.getElementById('momentumSubtitle').textContent  = isSeason ? 'Running win rate within the selected season — fight number as x-axis' : 'Running career win rate after each fight — fight number as x-axis';

    renderScoreboard(d, isSeason ? { f1Season, f2Season } : null);
    renderStatsGrid({ fighter1: d1, fighter2: d2, h2h: d }, isSeason);
    renderRadar({ fighter1: d1, fighter2: d2, roster_maxes: maxes });
    renderMomentum({ fighter1: d1, fighter2: d2 }, isSeason);
    document.getElementById('eloSection').style.display        = isSeason ? 'none' : '';
    document.getElementById('seasonsSection').style.display    = isSeason ? 'none' : '';
    document.getElementById('fightsSection').style.display     = isSeason ? 'none' : '';
    if (!isSeason) {
        renderEloComparison(d);
        renderPowerScoreCompare(d);
        renderSeasons(d);
        renderFights(d);
    } else {
        renderPowerScoreSeasonMode(d, f1Season, f2Season);
    }
}

document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('btnCareer').addEventListener('click', () => {
        currentMode = 'career';
        document.getElementById('btnCareer').classList.add('active');
        document.getElementById('btnSeason').classList.remove('active');
        document.getElementById('seasonPickers').style.display = 'none';
        if (currentData) {
            renderAll(currentData, 'career');
            updateH2HURL(document.getElementById('f1Input').value.trim(), document.getElementById('f2Input').value.trim());
        }
    });
    document.getElementById('btnSeason').addEventListener('click', () => {
        currentMode = 'season';
        document.getElementById('btnSeason').classList.add('active');
        document.getElementById('btnCareer').classList.remove('active');
        document.getElementById('seasonPickers').style.display = '';
        if (currentData) {
            renderAll(currentData, 'season');
            updateH2HURL(document.getElementById('f1Input').value.trim(), document.getElementById('f2Input').value.trim());
        }
    });
    ['seasonF1', 'seasonF2'].forEach(id => {
        document.getElementById(id).addEventListener('change', () => {
            if (currentMode === 'season' && currentData) {
                renderAll(currentData, 'season');
                updateH2HURL(document.getElementById('f1Input').value.trim(), document.getElementById('f2Input').value.trim());
            }
        });
    });
});

// ── Scoreboard ────────────────────────────────────────────────
function renderScoreboard(d, seasonOpts) {
    const f1 = d.fighter1, f2 = d.fighter2;
    document.getElementById('sbImg1').src = `/static/assets/fighters/${f1.image}`;
    document.getElementById('sbImg2').src = `/static/assets/fighters/${f2.image}`;
    document.getElementById('sbName1').textContent = f1.name;
    document.getElementById('sbName2').textContent = f2.name;

    let w1, w2, label;
    if (seasonOpts) {
        if (String(seasonOpts.f1Season) !== String(seasonOpts.f2Season)) {
            w1 = 0; w2 = 0;
            label = `Seasons don't match — no shared H2H`;
        } else {
            const s = String(seasonOpts.f1Season);
            const seasonFights = (d.fights_between || []).filter(r => String(r.Season) === s);
            const f1name = f1.name.toLowerCase();
            w1 = seasonFights.filter(r => r.Fighter_Name?.toLowerCase() === f1name && r.Decision?.toLowerCase() === 'w').length;
            w2 = seasonFights.filter(r => r.Fighter_Name?.toLowerCase() === f2.name.toLowerCase() && r.Decision?.toLowerCase() === 'w').length;
            const totalFights = w1 + w2;
            label = `${totalFights} fight${totalFights !== 1 ? 's' : ''} on record (S${s})`;
        }
    } else {
        w1 = f1.h2h_wins; w2 = f2.h2h_wins;
        label = (w1 + w2) + ' total fights on record';
    }

    document.getElementById('sbScore1').textContent = w1;
    document.getElementById('sbScore2').textContent = w2;
    const total = (w1 + w2) || 1;
    const f1pct = Math.round(w1 / total * 100);
    setTimeout(() => {
        document.getElementById('sbBarF1').style.width = f1pct + '%';
        document.getElementById('sbBarF2').style.width = (100 - f1pct) + '%';
    }, 120);
    document.getElementById('sbLabel').textContent = label;

    // Winner glow
    document.getElementById('f1Frame').classList.toggle('winner-glow', w1 > w2);
    document.getElementById('f2Frame').classList.toggle('winner-glow', w2 > w1);
    document.getElementById('f1Frame').classList.toggle('loser-dim', w1 < w2);
    document.getElementById('f2Frame').classList.toggle('loser-dim', w2 < w1);
}

// ── Stats Grid ────────────────────────────────────────────────
function renderStatsGrid(d, isSeason) {
    const f1 = d.fighter1, f2 = d.fighter2;
    const h2h = d.h2h || d;  // career h2h data passed separately in season mode

    // Compute derived values
    const f1TotalMajor = f1.holistic.reduce((s, r) => s + (parseInt(r.Months_With_Major)||0), 0);
    const f2TotalMajor = f2.holistic.reduce((s, r) => s + (parseInt(r.Months_With_Major)||0), 0);
    const f1TotalTitle = f1.holistic.reduce((s, r) => s + (parseInt(r.Months_With_Title)||0), 0);
    const f2TotalTitle = f2.holistic.reduce((s, r) => s + (parseInt(r.Months_With_Title)||0), 0);
    const evWon = (hol) => { const s = new Set(); hol.forEach(r => EVENT_COLS.forEach(c => { if (r[c] != null && r[c] !== '') s.add(c); })); return s.size; };

    const wrLabel      = isSeason ? 'Season Win Rate'   : 'Career Win Rate';
    const recordLabel  = isSeason ? 'Season Record'     : 'Career Record';

    // Power score row
    let psRow = null;
    if (isSeason) {
        const f1Season = document.getElementById('seasonF1')?.value;
        const f2Season = document.getElementById('seasonF2')?.value;
        const ps1 = (h2h.fighter1.power_scores_by_season || {})[f1Season];
        const ps2 = (h2h.fighter2.power_scores_by_season || {})[f2Season];
        const s1 = ps1 ? ps1.power_score : null;
        const s2 = ps2 ? ps2.power_score : null;
        const r1 = ps1 ? `#${ps1.power_rank}` : '--';
        const r2 = ps2 ? `#${ps2.power_rank}` : '--';
        psRow = ['Season Power Score', s1 != null ? `${s1.toFixed(1)} (${r1})` : '--', s2 != null ? `${s2.toFixed(1)} (${r2})` : '--', 'num', s1 || 0, s2 || 0];
    } else {
        const cps1 = h2h.fighter1.career_power_score || {};
        const cps2 = h2h.fighter2.career_power_score || {};
        const s1 = cps1.power_score != null ? cps1.power_score : null;
        const s2 = cps2.power_score != null ? cps2.power_score : null;
        const r1 = cps1.power_rank != null ? `#${cps1.power_rank}` : '--';
        const r2 = cps2.power_rank != null ? `#${cps2.power_rank}` : '--';
        psRow = ['Career Power Score', s1 != null ? `${s1.toFixed(1)} (${r1})` : '--', s2 != null ? `${s2.toFixed(1)} (${r2})` : '--', 'num', s1 || 0, s2 || 0];
    }

    const rows = [
        psRow,
        [wrLabel,          f1.career.win_pct,                        f2.career.win_pct,                        'pct'],
        [recordLabel,      `${f1.career.wins}W – ${f1.career.losses}L`, `${f2.career.wins}W – ${f2.career.losses}L`, 'wins'],
        ...(!isSeason ? [
            ['H2H Record',  `${h2h.fighter1.h2h_wins}W – ${h2h.fighter1.h2h_losses}L`, `${h2h.fighter2.h2h_wins}W – ${h2h.fighter2.h2h_losses}L`, 'wins'],
            ['Champ Match Record', `${h2h.fighter1.champ_stats.wins}W – ${h2h.fighter1.champ_stats.losses}L`, `${h2h.fighter2.champ_stats.wins}W – ${h2h.fighter2.champ_stats.losses}L`, 'wins'],
        ] : []),
        ['Major Title Reign',  f1TotalMajor + ' month' + (f1TotalMajor !== 1 ? 's' : ''), f2TotalMajor + ' month' + (f2TotalMajor !== 1 ? 's' : ''), 'num', f1TotalMajor, f2TotalMajor],
        ['Title Reign',        f1TotalTitle + ' month' + (f1TotalTitle !== 1 ? 's' : ''), f2TotalTitle + ' month' + (f2TotalTitle !== 1 ? 's' : ''), 'num', f1TotalTitle, f2TotalTitle],
        ['Unique Titles Held', f1.unique_champs,                          f2.unique_champs,                          'num', f1.unique_champs, f2.unique_champs],
        ...(isSeason ? (() => {
            const f1aw = (f1.awards || []).map(a => '🏅 ' + a.name).join(', ') || '—';
            const f2aw = (f2.awards || []).map(a => '🏅 ' + a.name).join(', ') || '—';
            return [['Awards', f1aw, f2aw, 'num', (f1.awards||[]).length, (f2.awards||[]).length]];
        })() : []),
        ['Event Wins',         evWon(f1.holistic) + '/6',                 evWon(f2.holistic) + '/6',                 'num', evWon(f1.holistic), evWon(f2.holistic)],
    ];

    function numericVal(row, side) {
        if (row[3] === 'num') return side === 'f1' ? row[4] : row[5];
        if (row[3] === 'pct') return parseFloat(String(side === 'f1' ? row[1] : row[2]).replace('%','')) || 0;
        if (row[3] === 'wins') {
            const v = side === 'f1' ? row[1] : row[2];
            return parseInt(v) || 0;
        }
        return 0;
    }

    const tbl = document.getElementById('statsGrid');
    tbl.innerHTML = `<thead><tr>
        <th class="grid-name f1-color">${f1.name}</th>
        <th class="grid-metric">Metric</th>
        <th class="grid-name f2-color">${f2.name}</th>
    </tr></thead><tbody>` +
    rows.map(row => {
        const n1 = numericVal(row, 'f1'), n2 = numericVal(row, 'f2');
        const f1win = n1 > n2, f2win = n2 > n1;
        return `<tr>
            <td class="grid-val ${f1win ? 'grid-winner f1-winner-cell' : ''}">${row[1]}</td>
            <td class="grid-metric">${row[0]}</td>
            <td class="grid-val ${f2win ? 'grid-winner f2-winner-cell' : ''}">${row[2]}</td>
        </tr>`;
    }).join('') + '</tbody>';
}

// ── Career Fingerprint Radar ──────────────────────────────────
function careerRawValues(fighter) {
    const h = fighter.holistic;
    const wr = parseFloat(String(fighter.career.win_pct).replace('%','')) || 0;
    const totalMajor = h.reduce((s,r) => s+(parseInt(r.Months_With_Major)||0), 0);
    const totalTitle = h.reduce((s,r) => s+(parseInt(r.Months_With_Title)||0), 0);
    const wonSet = new Set();
    h.forEach(r => EVENT_COLS.forEach(c => { if (r[c]!=null && r[c]!=='') wonSet.add(c); }));
    const ev = wonSet.size;
    const tc = fighter.unique_champs || 0;
    return { wr, totalMajor, totalTitle, ev, tc, wonSet, fighter };
}

function careerRadarData(raw, maxWR, maxMajor, maxTitle, maxEv, maxTc) {
    const norm = v => max => max > 0 ? (v / max) * 100 : 0;
    return {
        data: [
            norm(raw.wr)(maxWR),
            norm(raw.totalTitle)(maxTitle),
            norm(raw.totalMajor)(maxMajor),
            norm(raw.ev)(maxEv),
            norm(raw.tc)(maxTc),
        ],
        wonSet: raw.wonSet,
        fighter: raw.fighter,
    };
}

function renderRadar(d) {
    const raw1 = careerRawValues(d.fighter1);
    const raw2 = careerRawValues(d.fighter2);
    const m = d.roster_maxes;
    const r1 = careerRadarData(raw1, m.max_wr, m.max_major, m.max_title, m.max_ev, m.max_champs);
    const r2 = careerRadarData(raw2, m.max_wr, m.max_major, m.max_title, m.max_ev, m.max_champs);

    if (charts.radar) charts.radar.destroy();
    charts.radar = new Chart(document.getElementById('compareRadar').getContext('2d'), {
        type: 'radar',
        data: {
            labels: ['Win Rate', 'Title Reign', 'Major Title Reign', 'Event Wins', 'Unique Titles'],
            datasets: [
                { label: d.fighter1.name, data: r1.data, borderColor: F1_COLOR, backgroundColor: F1_BG, borderWidth: 2.5, pointRadius: 5, pointBackgroundColor: F1_COLOR, _r: r1 },
                { label: d.fighter2.name, data: r2.data, borderColor: F2_COLOR, backgroundColor: F2_BG, borderWidth: 2.5, pointRadius: 5, pointBackgroundColor: F2_COLOR, _r: r2 },
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: { r: { min:0, max:100, grid:{color:'rgba(96,124,255,0.15)'}, angleLines:{color:'rgba(96,124,255,0.15)'}, ticks:{display:false}, pointLabels:{color:'#b0b8d1', font:{size:12,family:'Inter'}} } },
            plugins: {
                legend: { position:'bottom', labels:{padding:16, font:{size:12,family:'Inter'}, color:'#b0b8d1'} },
                tooltip: { backgroundColor:'rgba(18,18,42,0.95)', titleFont:{family:'Inter'}, bodyFont:{family:'Inter'}, borderColor:'#607cff', borderWidth:1,
                    callbacks: { label: (it) => {
                        const r = it.dataset._r;
                        const f = r.fighter;
                        const axis = it.chart.data.labels[it.dataIndex];
                        const s = it.dataset.label;
                        if (axis === 'Win Rate') return `  ${s}: ${f.career.win_pct}`;
                        if (axis === 'Major Title Reign') return `  ${s}: ${f.holistic.reduce((a,x) => a+(parseInt(x.Months_With_Major)||0), 0)} month(s)`;
                        if (axis === 'Title Reign') return `  ${s}: ${f.holistic.reduce((a,x) => a+(parseInt(x.Months_With_Title)||0), 0)} month(s)`;
                        if (axis === 'Event Wins') return `  ${s}: ${[...r.wonSet].map(c => EVENT_NAMES[c]).join(', ') || 'None'}`;
                        if (axis === 'Unique Titles') return `  ${s}: ${f.unique_champs} title(s)`;
                        return `  ${s}: ${it.raw.toFixed(0)}`;
                    }}
                }
            },
            animation: { duration: 900 }
        }
    });
}

// ── Win Rate Momentum ─────────────────────────────────────────
function renderMomentum(d, isSeason) {
    const parseCareer = arr => arr.map((r, i) => ({x: i+1, y: parseFloat(String(r.career_win_pct).replace('%','')) || 0}));
    const parseSeason = arr => {
        let wins = 0, total = 0;
        return arr.map((r, i) => { total++; if (r.decision === 'w') wins++; return {x: i+1, y: (wins/total)*100}; });
    };
    const parse = arr => isSeason ? parseSeason(arr) : parseCareer(arr);
    const f1pts = parse(d.fighter1.running);
    const f2pts = parse(d.fighter2.running);
    const maxFights = Math.max(f1pts.length, f2pts.length, 1);
    const w = Math.max(900, maxFights * 10);

    const canvas = document.getElementById('compareMomentum');
    canvas.width = w; canvas.height = 260;

    if (charts.momentum) charts.momentum.destroy();
    charts.momentum = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: { datasets: [
            { label: d.fighter1.name, data: f1pts, borderColor: F1_COLOR, backgroundColor: F1_BG, borderWidth: 2, pointRadius: 0, pointHoverRadius: 5, tension: 0.3, fill: true },
            { label: d.fighter2.name, data: f2pts, borderColor: F2_COLOR, backgroundColor: F2_BG, borderWidth: 2, pointRadius: 0, pointHoverRadius: 5, tension: 0.3, fill: true },
            { label: '50%', data: [{x:1,y:50},{x:maxFights,y:50}], borderColor:'rgba(176,184,209,0.2)', borderWidth:1, borderDash:[6,4], pointRadius:0, fill:false },
        ]},
        options: {
            responsive: false, maintainAspectRatio: false,
            parsing: false,
            scales: {
                y: { min:0, max:100, grid:{color:'rgba(96,124,255,0.08)'}, ticks:{callback:v=>v+'%', color:'#b0b8d1'}, title:{display:true, text:'Win Rate', color:'#a8aab8', font:{size:11}} },
                x: { type:'linear', min:1, grid:{color:'rgba(96,124,255,0.05)'}, ticks:{color:'#607cff', font:{size:11}}, title:{display:true, text:'Fight #', color:'#a8aab8', font:{size:11}} },
            },
            plugins: {
                legend: { position:'top', labels:{padding:14, font:{size:12,family:'Inter'}, color:'#b0b8d1'} },
                tooltip: { backgroundColor:'rgba(18,18,42,0.95)', titleFont:{family:'Inter'}, bodyFont:{family:'Inter'}, borderColor:'#607cff', borderWidth:1,
                    callbacks: { label: it => `  ${it.dataset.label}: ${it.parsed.y.toFixed(1)}%` }
                }
            },
            animation: { duration: 800 }
        }
    });
}

// ── ELO Rating History ────────────────────────────────────────
function renderEloComparison(d) {
    const f1hist = d.fighter1.elo_history || [];
    const f2hist = d.fighter2.elo_history || [];

    const toPoints = arr => arr.map(r => ({ x: r.fight_id, y: r.elo_after, season: r.season, month: r.month }));
    const f1pts = toPoints(f1hist);
    const f2pts = toPoints(f2hist);

    const allFightIds = [...f1pts.map(p => p.x), ...f2pts.map(p => p.x)];
    if (!allFightIds.length) return;

    const minX = Math.min(...allFightIds);
    const maxX = Math.max(...allFightIds);
    const w    = Math.max(900, (maxX - minX) * 0.4);

    const canvas = document.getElementById('compareElo');
    canvas.width = w; canvas.height = 280;

    if (charts.elo) charts.elo.destroy();
    charts.elo = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: { datasets: [
            {
                label: d.fighter1.name,
                data: f1pts,
                borderColor: F1_COLOR,
                backgroundColor: 'rgba(96,124,255,0.08)',
                borderWidth: 2,
                pointRadius: 2,
                pointHoverRadius: 6,
                pointBackgroundColor: F1_COLOR,
                tension: 0.25,
                fill: false,
            },
            {
                label: d.fighter2.name,
                data: f2pts,
                borderColor: F2_COLOR,
                backgroundColor: 'rgba(251,146,60,0.08)',
                borderWidth: 2,
                pointRadius: 2,
                pointHoverRadius: 6,
                pointBackgroundColor: F2_COLOR,
                tension: 0.25,
                fill: false,
            },
            {
                label: 'Baseline (1500)',
                data: [{ x: minX, y: 1500 }, { x: maxX, y: 1500 }],
                borderColor: 'rgba(176,184,209,0.25)',
                borderWidth: 1,
                borderDash: [6, 4],
                pointRadius: 0,
                fill: false,
            },
        ]},
        options: {
            responsive: false,
            maintainAspectRatio: false,
            parsing: false,
            scales: {
                x: {
                    type: 'linear',
                    min: minX,
                    grid: { color: 'rgba(96,124,255,0.05)' },
                    ticks: { display: false },
                    title: { display: true, text: 'Fight (chronological)', color: '#a8aab8', font: { size: 11 } },
                },
                y: {
                    grid: { color: 'rgba(96,124,255,0.08)' },
                    ticks: { color: '#b0b8d1', callback: v => v.toFixed(0) },
                    title: { display: true, text: 'ELO', color: '#a8aab8', font: { size: 11 } },
                },
            },
            plugins: {
                legend: { position: 'top', labels: { padding: 14, font: { size: 12, family: 'Inter' }, color: '#b0b8d1' } },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    backgroundColor: 'rgba(18,18,42,0.95)',
                    titleFont: { family: 'Inter' },
                    bodyFont: { family: 'Inter' },
                    borderColor: '#607cff',
                    borderWidth: 1,
                    callbacks: {
                        title: items => {
                            const p = items[0]?.raw;
                            return p ? `S${p.season} M${p.month} · Fight #${p.x}` : '';
                        },
                        label: it => it.dataset.label === 'Baseline (1500)' ? null
                            : `  ${it.dataset.label}: ${it.parsed.y.toFixed(1)}`,
                    }
                },
            },
            animation: { duration: 800 },
        }
    });
}

// ── Season Power Score Comparison ─────────────────────────────
function renderPowerScoreCompare(d) {
    const wrap = document.getElementById('powerScoreCompareWrap');
    const ps1  = d.fighter1.power_scores_by_season || {};
    const ps2  = d.fighter2.power_scores_by_season || {};
    const seasons = [...new Set([...Object.keys(ps1), ...Object.keys(ps2)])].map(Number).sort((a,b) => a - b);
    if (!seasons.length) { wrap.innerHTML = ''; return; }

    const f1Name = d.fighter1.name, f2Name = d.fighter2.name;
    const tierCls = s => getPowerScoreClass(s);

    const rows = seasons.map(s => {
        const v1 = ps1[s], v2 = ps2[s];
        const s1 = v1 ? v1.power_score : null, s2 = v2 ? v2.power_score : null;
        const r1 = v1 ? `#${v1.power_rank}` : '--', r2 = v2 ? `#${v2.power_rank}` : '--';
        const win1 = s1 != null && s2 != null && s1 > s2;
        const win2 = s1 != null && s2 != null && s2 > s1;
        return `<tr>
            <td class="${tierCls(s1)} ps-score-cell ${win1 ? 'ps-winner' : ''}">${s1 != null ? s1.toFixed(1) : '--'}</td>
            <td class="ps-rank-cell">${r1}</td>
            <td class="ps-season-label">S${s}</td>
            <td class="ps-rank-cell" style="text-align:right">${r2}</td>
            <td class="${tierCls(s2)} ps-score-cell ps-right ${win2 ? 'ps-winner' : ''}">${s2 != null ? s2.toFixed(1) : '--'}</td>
        </tr>`;
    }).join('');

    wrap.innerHTML = `<table class="ps-compare-table">
        <thead>
            <tr class="ps-name-row">
                <th colspan="2" class="ps-fighter-name ps-fighter-left">${f1Name}</th>
                <th></th>
                <th colspan="2" class="ps-fighter-name ps-fighter-right">${f2Name}</th>
            </tr>
            <tr class="ps-subheader-row">
                <th class="ps-col-label">Power Score</th>
                <th class="ps-col-label">Season Rank</th>
                <th class="ps-season-label-th">Season</th>
                <th class="ps-col-label">Season Rank</th>
                <th class="ps-col-label">Power Score</th>
            </tr>
        </thead>
        <tbody>${rows}</tbody>
    </table>`;
}

// ── Season Mode Power Score (simple side-by-side) ─────────────
function renderPowerScoreSeasonMode(d, s1, s2) {
    const wrap = document.getElementById('powerScoreCompareWrap');
    const section = document.getElementById('powerScoreSection');
    const ps1map = d.fighter1.power_scores_by_season || {};
    const ps2map = d.fighter2.power_scores_by_season || {};
    const v1 = ps1map[s1], v2 = ps2map[s2];
    if (!v1 && !v2) { section.style.display = 'none'; return; }
    section.style.display = '';

    const f1Name = d.fighter1.name, f2Name = d.fighter2.name;
    const tierCls = s => getPowerScoreClass(s);

    const sc1 = v1 ? v1.power_score : null, sc2 = v2 ? v2.power_score : null;
    const r1  = v1 ? `#${v1.power_rank}` : '--', r2 = v2 ? `#${v2.power_rank}` : '--';
    const win1 = sc1 != null && sc2 != null && sc1 > sc2;
    const win2 = sc1 != null && sc2 != null && sc2 > sc1;
    const sameSeason = String(s1) === String(s2);

    wrap.innerHTML = `<div class="ps-season-sidebyside">
        <div class="ps-sb-card ${win1 ? 'ps-winner' : ''}">
            <div class="ps-sb-fighter">${f1Name}</div>
            <div class="ps-sb-season">Season ${s1}</div>
            <div class="ps-sb-label">Power Score</div>
            <div class="ps-sb-score ${tierCls(sc1)}">${sc1 != null ? sc1.toFixed(1) : '--'}</div>
            <div class="ps-sb-label">Season Ranking</div>
            <div class="ps-sb-rank">${r1}</div>
        </div>
        ${sameSeason ? '' : '<div class="ps-sb-vs">vs</div>'}
        <div class="ps-sb-card ${win2 ? 'ps-winner' : ''}">
            <div class="ps-sb-fighter">${f2Name}</div>
            <div class="ps-sb-season">Season ${s2}</div>
            <div class="ps-sb-label">Power Score</div>
            <div class="ps-sb-score ${tierCls(sc2)}">${sc2 != null ? sc2.toFixed(1) : '--'}</div>
            <div class="ps-sb-label">Season Ranking</div>
            <div class="ps-sb-rank">${r2}</div>
        </div>
    </div>`;
}

// ── Season by Season ──────────────────────────────────────────
function renderSeasons(d) {
    const f1Seasons = d.fighter1.by_season, f2Seasons = d.fighter2.by_season;
    const allSeasons = [...new Set([...f1Seasons.map(r=>r.season), ...f2Seasons.map(r=>r.season)])].sort((a,b) => +a - +b);
    const f1Wins = allSeasons.map(s => (f1Seasons.find(r=>r.season==s)||{wins:0}).wins);
    const f2Wins = allSeasons.map(s => (f2Seasons.find(r=>r.season==s)||{wins:0}).wins);
    const f1Losses = allSeasons.map(s => (f1Seasons.find(r=>r.season==s)||{losses:0}).losses);
    const f2Losses = allSeasons.map(s => (f2Seasons.find(r=>r.season==s)||{losses:0}).losses);

    if (charts.seasons) charts.seasons.destroy();
    charts.seasons = new Chart(document.getElementById('compareSeasons').getContext('2d'), {
        type: 'bar',
        data: {
            labels: allSeasons.map(s => 'S' + s),
            datasets: [
                { label: d.fighter1.name + ' (W)', data: f1Wins,   backgroundColor: F1_COLOR, borderRadius: 4, stack: 'f1' },
                { label: d.fighter1.name + ' (L)', data: f1Losses,  backgroundColor: 'rgba(96,124,255,0.25)', borderRadius: 4, stack: 'f1' },
                { label: d.fighter2.name + ' (W)', data: f2Wins,   backgroundColor: F2_COLOR, borderRadius: 4, stack: 'f2' },
                { label: d.fighter2.name + ' (L)', data: f2Losses,  backgroundColor: 'rgba(251,146,60,0.25)',  borderRadius: 4, stack: 'f2' },
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: {
                y: { grid:{color:'rgba(96,124,255,0.08)'}, ticks:{color:'#b0b8d1'}, title:{display:true, text:'Fights', color:'#a8aab8', font:{size:11}} },
                x: { grid:{display:false}, ticks:{color:'#b0b8d1'} },
            },
            plugins: {
                legend: { position:'bottom', labels:{padding:14, font:{size:12,family:'Inter'}, color:'#b0b8d1'} },
                tooltip: { backgroundColor:'rgba(18,18,42,0.95)', titleFont:{family:'Inter'}, bodyFont:{family:'Inter'}, borderColor:'#607cff', borderWidth:1 }
            },
            animation: { duration: 700 }
        }
    });
}

// ── Their Fights ──────────────────────────────────────────────
function renderFights(d) {
    const rows = d.fights_between || [];
    const f1Name = d.fighter1.name, f2Name = d.fighter2.name;
    const wrap = document.getElementById('fightsBetweenWrap');
    const label = document.getElementById('fightCountLabel');

    // Group by Fight_ID
    const byFight = new Map();
    rows.forEach(row => {
        const fid = row.Fight_ID;
        if (!byFight.has(fid)) byFight.set(fid, {meta: row, f1Row: null, f2Row: null});
        const f = byFight.get(fid);
        if (row.Fighter_Name === f1Name) f.f1Row = row;
        else f.f2Row = row;
    });

    if (!byFight.size) {
        label.textContent = '0 total fights between them';
        wrap.innerHTML = '<p style="color:#b0b8d1;padding:0.5rem 0;">No direct fights found.</p>';
        return;
    }

    const tableRows = [...byFight.values()].map(({meta, f1Row, f2Row}) => {
        const d1 = String(f1Row?.Decision || '').trim().toUpperCase();
        const d2 = String(f2Row?.Decision || '').trim().toUpperCase();
        // Skip tag-team fights (same decision = same side) and multi-person where neither wins (both L)
        if (d1 === d2) return null;
        const winner = d1 === 'W' ? f1Name : d2 === 'W' ? f2Name : '—';
        const isF1 = winner === f1Name;
        const champ = meta.Championship_Name || '—';
        const date = `S${meta.Season} M${meta.Month}${meta.Week ? ' W'+meta.Week : ''}`;
        return `<tr class="clickable-row" onclick="window.open('/fights?fight_id=${meta.Fight_ID}','_blank')" title="View in Fight Log">
            <td>${date}</td>
            <td>${meta.PPV_Name || '—'}</td>
            <td>${meta.Description || '—'}</td>
            <td>${champ}</td>
            <td class="${isF1 ? 'f1-winner-cell' : winner === '—' ? '' : 'f2-winner-cell'}" style="font-weight:600">${winner}</td>
        </tr>`;
    }).filter(Boolean);

    label.textContent = tableRows.length + ' total fights between them';

    wrap.innerHTML = `<table class="stats-table compare-fights-table">
        <thead><tr><th>Date</th><th>PPV</th><th>Type</th><th>Title</th><th>Winner</th></tr></thead>
        <tbody>${tableRows.join('')}</tbody>
    </table>`;
}
