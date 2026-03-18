const FIGHTER_PAGE = window.SSBStats?.fighterPage || {};
const FIGHTER_NAME = FIGHTER_PAGE.name || '';

// ── Compare Against ────────────────────────────────────────────
(function() {
    const currentFighter = FIGHTER_NAME;
    const PLACEHOLDER_SRC = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 60 60'%3E%3Crect fill='%2312122a' width='60' height='60'/%3E%3Ctext fill='%23607cff' x='50%25' y='50%25' text-anchor='middle' dy='.3em' font-size='28'%3E%3F%3C/text%3E%3C/svg%3E";
    const caInput    = document.getElementById('caInput');
    const caPortrait = document.getElementById('caOpponentPortrait');
    const caNameEl   = document.getElementById('caOpponentName');
    const caBtn      = document.getElementById('caBtn');

    caPortrait.src = PLACEHOLDER_SRC;

    function updateOpponent() {
        const val = caInput.value.trim();
        if (!val) {
            caPortrait.src = PLACEHOLDER_SRC;
            caPortrait.style.opacity = '0.15';
            caNameEl.textContent = '?';
            return;
        }
        caPortrait.onerror = () => { caPortrait.onerror = null; caPortrait.src = PLACEHOLDER_SRC; caPortrait.style.opacity = '0.15'; };
        caPortrait.src = `/static/assets/fighters/${fighterToFilename(val)}.png`;
        caPortrait.style.opacity = '1';
        caNameEl.textContent = val;
    }

    function goCompare() {
        const opponent = caInput.value.trim();
        if (!opponent) { caInput.focus(); return; }
        window.location.href = `/head2head?f1=${encodeURIComponent(currentFighter)}&f2=${encodeURIComponent(opponent)}`;
    }

    setupAutocomplete(caInput, 'fighters');
    caInput.addEventListener('change', updateOpponent);
    caInput.addEventListener('input', updateOpponent);
    caBtn.addEventListener('click', goCompare);
    caInput.addEventListener('keydown', e => { if (e.key === 'Enter') goCompare(); });
})();

document.addEventListener('DOMContentLoaded', function() {
    const name = FIGHTER_NAME;

    fetch(`/api/fighter/${encodeURIComponent(name)}`)
        .then(res => res.json())
        .then(data => {
            document.getElementById('loadingOverlay').style.display = 'none';
            document.getElementById('statsGrid').style.display = 'grid';

            if (data.error) return;

            animateCounter('totalWins', 0, parseInt(data.career.wins) || 0, 800);
            animateCounter('totalLosses', 0, parseInt(data.career.losses) || 0, 800);
            document.getElementById('winPct').textContent = data.career.win_pct;

            // Career power score badge
            const cps = data.career_power_score || {};
            if (cps.power_score != null) {
                document.getElementById('careerPowerScore').textContent = cps.power_score.toFixed(1);
                document.getElementById('careerPowerRank').textContent =
                    `#${cps.power_rank} of ${cps.total_fighters}`;
            }

            renderPowerScoreTable(data.power_scores_by_season || {});
            renderSeasonChart(data.by_season || []);
            renderFightTypeChart(data.by_fight_type || []);
            renderBrandChart(data.by_brand || []);
            renderPPVChart(data.by_ppv || []);
            renderLocationChart(data.by_location || []);

            const acc = data.accolades || {};
            window.fighterHolistic = acc.holistic || [];

            // --- Current champion titles ---
            renderCurrentTitleShowcase(data.current_titles || []);

            // --- Accolades section ---
            buildChampBadges(acc.champ_reigns || [], !!data.triple_crown, data.major_winner);
            buildEventBadges(acc.holistic || []);
            buildAwardBadges(acc.awards || []);
            if ((acc.champ_reigns || []).length > 0 || (acc.awards || []).length > 0 || (acc.holistic || []).length > 0 || data.triple_crown || data.major_winner) {
                document.getElementById('accoladesSection').style.display = 'block';
            }

            // --- Championship Stats by Title ---
            renderChampionshipChart(acc.champ_by_champ || []);

            // --- Streaks ---
            buildStreaks(acc.win_streaks || [], acc.loss_streaks || [], acc.active_win || [], acc.active_loss || []);

            // Auto-load advanced analytics
            setTimeout(() => {
                if (window._loadAdvancedAnalytics) window._loadAdvancedAnalytics();
            }, 150);
        })
        .catch(() => {
            document.getElementById('loadingOverlay').innerHTML = '<p>Error loading stats</p>';
        });
});

function renderCurrentTitleShowcase(titles) {
    const showcase = document.getElementById('currentTitlesShowcase');
    if (!showcase) return;

    showcase.innerHTML = '';
    if (!titles.length) {
        showcase.style.display = 'none';
        return;
    }

    showcase.style.display = 'grid';

    titles.forEach(title => {
        const asset = championshipToBeltAsset(title);
        const card = document.createElement('div');
        card.className = 'fighter-title-card';

        const beltMarkup = asset
            ? `<img src="${asset}" alt="${title} belt" class="fighter-title-belt" loading="lazy">`
            : `<div class="fighter-title-fallback" aria-hidden="true">🏆</div>`;

        card.innerHTML = `
            <div class="fighter-title-kicker">Current Champion</div>
            <div class="fighter-title-name">${title}</div>
            <div class="fighter-title-belt-wrap">
                ${beltMarkup}
            </div>
        `;
        showcase.appendChild(card);
    });
}

// Build championship reign badges — cols: Championship_Name, reign_count, total_months
function buildChampBadges(rows, hasTripleCrown, majorWinner) {
    if (!rows.length && !hasTripleCrown && !majorWinner) return;
    const container = document.getElementById('champBadges');
    if (majorWinner) {
        const mw = document.createElement('div');
        mw.className = majorWinner === 'super'
            ? 'accolade-badge super-major-winner-badge'
            : 'accolade-badge major-winner-badge';
        const icon = majorWinner === 'super' ? '🌟' : '⭐';
        const label = majorWinner === 'super' ? 'Super Major Winner' : 'Major Winner';
        mw.innerHTML = `<span class="badge-icon">${icon}</span><span class="badge-text">${label}</span>`;
        container.appendChild(mw);
    }
    if (hasTripleCrown) {
        const tc = document.createElement('div');
        tc.className = 'accolade-badge triple-crown-badge';
        tc.innerHTML = '<span class="badge-icon">👑</span><span class="badge-text">Triple Crown</span>';
        container.appendChild(tc);
    }
    rows.forEach(row => {
        const champ = row.Championship_Name || '?';
        const reigns = parseInt(row.reign_count) || 1;
        const months = row.total_months != null ? Math.round(parseFloat(row.total_months)) : 0;
        const badge = document.createElement('div');
        badge.className = 'accolade-badge champ-badge';
        const reignStr = reigns >= 1 ? `${reigns}x ` : '';
        const monthStr = months > 0 ? ` &mdash; ${months} mo.` : '';
        badge.innerHTML = `<span class="badge-icon">🏆</span><span class="badge-text">${reignStr}${champ} Champion${monthStr}</span>`;
        container.appendChild(badge);
    });
}

// Build event accolade badges from holistic_view — groups by event+championship, lists seasons
function buildEventBadges(rows) {
    if (!rows.length) return;
    const container = document.getElementById('eventBadges');

    const accoladeMap = [
        { col: 'Won_Tournament',        label: 'Tournament Winner',   icon: '🎯' },
        { col: 'Won_Royal_Rumble',      label: 'Royal Rumble Winner', icon: '💥' },
        { col: 'Won_Scramble',          label: 'Scramble Winner',     icon: '🎲' },
        { col: 'Won_Smash_Series',      label: 'Smash Series Winner', icon: '⚡' },
        { col: 'Won_Money_In_The_Bank', label: 'Money in the Bank',   icon: '💰' },
        { col: 'Won_Smash_Bros',        label: 'Smash Bros Winner',   icon: '🎮' },
        { col: 'Successful_Cash_In',    label: 'Successful Cash-In',  icon: '💸' },
        { col: 'Defended_Cash_In',      label: 'Defended Cash-In',    icon: '🛡️' },
    ];

    // Group by col+value, collect seasons in order
    const groups = {};
    rows.forEach(row => {
        accoladeMap.forEach(({ col, label, icon }) => {
            const val = row[col];
            if (val == null) return;
            const champ = String(val);
            const key = `${col}|${champ}`;
            if (!groups[key]) groups[key] = { label, icon, champ, seasons: [] };
            groups[key].seasons.push(row.Season);
        });
    });

    // Render in accoladeMap order so layout is consistent
    accoladeMap.forEach(({ col }) => {
        Object.entries(groups).filter(([k]) => k.startsWith(col + '|')).forEach(([, info]) => {
            const { label, icon, champ, seasons } = info;
            const count = seasons.length;
            const seasonStr = seasons.map(s => `S${s}`).join(', ');
            const badge = document.createElement('div');
            badge.className = 'accolade-badge event-badge';
            const countStr = count > 1 ? `${count}x ` : '';
            // If value is a flag ('Y'), omit it from the label; otherwise prefix with championship name
            const prefix = (champ === 'Y' || champ === 'y') ? '' : `${champ} `;
            badge.innerHTML = `<span class="badge-icon">${icon}</span><span class="badge-text">${countStr}${prefix}${label} <span class="badge-season">${seasonStr}</span></span>`;
            container.appendChild(badge);
        });
    });
}

// Build award badges — groups by Award_Name, lists seasons won
function buildAwardBadges(rows) {
    if (!rows.length) return;
    const container = document.getElementById('awardBadges');

    // Group by award name, collect seasons
    const groups = {};
    rows.forEach(row => {
        const award = row.Award_Name || '?';
        if (!groups[award]) groups[award] = [];
        groups[award].push(row.Season_ID);
    });

    Object.entries(groups).forEach(([award, seasons]) => {
        const count = seasons.length;
        const seasonStr = seasons.map(s => `S${s}`).join(', ');
        const badge = document.createElement('div');
        badge.className = 'accolade-badge award-badge';
        const countStr = count > 1 ? `${count}x ` : '';
        badge.innerHTML = `<span class="badge-icon">🏅</span><span class="badge-text">${countStr}${award} <span class="badge-season">${seasonStr}</span></span>`;
        container.appendChild(badge);
    });
}

// Populate streak subtle cards + active streak badge
function buildStreaks(winRows, lossRows, activeWinRows, activeLossRows) {
    const winVal = winRows.length ? (winRows[0].longest_streak || 0) : 0;
    const lossVal = lossRows.length ? (lossRows[0].longest_streak || 0) : 0;
    animateCounter('winStreakVal', 0, parseInt(winVal), 800);
    animateCounter('lossStreakVal', 0, parseInt(lossVal), 800);

    const activeWin = activeWinRows.length ? parseInt(activeWinRows[0].Win_Streak) : 0;
    const activeLoss = activeLossRows.length ? parseInt(activeLossRows[0].Losing_Streak) : 0;

    if (activeWin || activeLoss) {
        const row = document.getElementById('activeStreakRow');
        const badge = document.getElementById('activeStreakBadge');
        row.style.display = 'flex';
        if (activeWin) {
            badge.innerHTML = `<span class="active-streak-pill win-streak-pill">W${activeWin} <span class="active-streak-label">Active Win Streak</span></span>`;
        } else {
            badge.innerHTML = `<span class="active-streak-pill loss-streak-pill">L${activeLoss} <span class="active-streak-label">Active Losing Streak</span></span>`;
        }
    }
}

// Generic table filler using dynamic column names from DB
function fillDynamicTable(tbodyId, theadId, rows, skipCols = []) {
    if (!rows.length) return;
    const cols = Object.keys(rows[0]).filter(c => c !== 'Fighter_Name' && c !== 'fighter_name' && !skipCols.includes(c));

    // Build header
    const thead = document.getElementById(theadId);
    if (thead) {
        thead.innerHTML = '<tr>' + cols.map(c => `<th>${c.replace(/_/g, ' ')}</th>`).join('') + '</tr>';
    }

    // Build rows
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;
    tbody.innerHTML = '';
    rows.forEach((row, i) => {
        const tr = document.createElement('tr');
        cols.forEach(col => {
            const td = document.createElement('td');
            td.textContent = row[col] !== null && row[col] !== undefined ? row[col] : '--';
            tr.appendChild(td);
        });
        tr.style.opacity = '0';
        tbody.appendChild(tr);
        setTimeout(() => { tr.style.transition = 'opacity 0.3s ease'; tr.style.opacity = '1'; }, i * 40);
    });
}

// --- Advanced Analytics ---
(function() {
    let loaded = false;
    const charts = {};

    window._loadAdvancedAnalytics = function() {
        if (loaded) return;
        loaded = true;
        loadAdvanced();
    };

    function loadAdvanced() {
        const loading = document.getElementById('advancedAnalyticsLoading');
        loading.style.display = 'flex';
        fetch(`/api/fighter/${encodeURIComponent(FIGHTER_NAME)}/advanced`)
            .then(r => r.json())
            .then(d => {
                loading.style.display = 'none';
                renderRunningWinRate(d.running_stats   || []);
                renderEloChart(      d.elo_history     || []);
                renderRivals(        d.by_opponent     || []);
                renderStreakTimeline(d.all_win_streaks  || [], d.all_loss_streaks || []);
                renderSeasonRadar(window.fighterHolistic || []);
            })
            .catch(() => { document.getElementById('advancedAnalyticsLoading').style.display = 'none'; });
    }

    // ── 1. Career Momentum ─────────────────────────────────────────────────
    function renderRunningWinRate(data) {
        if (!data.length) return;
        const xLabels = [], careerPcts = [], seasonPcts = [], ptColors = [], ptBorders = [];
        let prevSeason = null;
        data.forEach(d => {
            xLabels.push(d.season !== prevSeason ? (prevSeason = d.season, `S${d.season}`) : '');
            careerPcts.push(parseFloat(d.career_win_pct) || 0);
            seasonPcts.push(parseFloat(d.season_win_pct) || 0);
            ptColors.push( d.decision === 'w' ? '#4ade80' : '#f87171');
            ptBorders.push(d.decision === 'w' ? '#22c55e' : '#ef4444');
        });

        const W = Math.max(900, data.length * 10);
        const container = document.getElementById('runningWinRateContainer');
        container.style.width = W + 'px';
        const canvas = document.getElementById('runningWinRateChart');
        canvas.width = W; canvas.height = 400;

        if (charts.momentum) charts.momentum.destroy();
        charts.momentum = new Chart(canvas.getContext('2d'), {
            type: 'line',
            data: { labels: xLabels, datasets: [
                { label: 'Career Win Rate %', data: careerPcts, borderColor: '#607cff', backgroundColor: 'rgba(96,124,255,0.08)', borderWidth: 2, pointRadius: 4, pointHoverRadius: 7, pointBackgroundColor: ptColors, pointBorderColor: ptBorders, pointBorderWidth: 1.5, tension: 0.25, fill: true },
                { label: 'Season Win Rate %', data: seasonPcts, borderColor: 'rgba(251,191,36,0.65)', backgroundColor: 'transparent', borderWidth: 1.5, borderDash: [5,4], pointRadius: 0, pointHoverRadius: 5, tension: 0.25, fill: false },
                { label: '50% Baseline', data: new Array(data.length).fill(50), borderColor: 'rgba(176,184,209,0.22)', borderWidth: 1, borderDash: [6,4], pointRadius: 0, fill: false },
            ]},
            options: {
                responsive: false, maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { position: 'bottom', labels: { padding: 16, font: { size: 12, family: 'Inter' }, filter: i => i.text !== '50% Baseline' } },
                    tooltip: { backgroundColor: 'rgba(18,18,42,0.95)', titleFont: { family: 'Inter' }, bodyFont: { family: 'Inter' }, borderColor: '#607cff', borderWidth: 1,
                        callbacks: {
                            title:      (its) => { const d = data[its[0].dataIndex]; return `Fight #${its[0].dataIndex+1}  —  ${d.decision==='w' ? 'Win ✓' : 'Loss ✗'}`; },
                            beforeBody: (its) => { const d = data[its[0].dataIndex]; return `Season ${d.season}, Month ${d.month}, Week ${d.week}`; },
                            label:      (it)  => it.dataset.label === '50% Baseline' ? null : `  ${it.dataset.label}: ${it.raw.toFixed(2)}%`,
                            afterBody:  (its) => { const d = data[its[0].dataIndex]; return `Career Record: ${d.career_wins}-${d.career_losses}`; },
                        }
                    }
                },
                scales: {
                    y: { min: 0, max: 100, grid: { color: 'rgba(96,124,255,0.08)' }, ticks: { callback: v => v+'%', color: '#b0b8d1' }, title: { display: true, text: 'Win Rate', color: '#a8aab8', font: { size: 11 } } },
                    x: { grid: { color: 'rgba(96,124,255,0.05)' }, ticks: { color: 'rgba(251,191,36,0.85)', font: { size: 11, weight: 'bold' }, maxRotation: 0, autoSkip: false }, title: { display: true, text: 'Fight #', color: '#a8aab8', font: { size: 11 } } },
                },
                animation: { duration: 800 }
            }
        });
    }

    // ── 2. ELO Rating History ──────────────────────────────────────────────
    function renderEloChart(data) {
        if (!data.length) return;
        const xLabels = [], eloValues = [], ptColors = [], ptBorders = [];
        let prevSeason = null;
        data.forEach(d => {
            xLabels.push(d.season !== prevSeason ? (prevSeason = d.season, `S${d.season}`) : '');
            eloValues.push(parseFloat(d.elo_after));
            const isWin = parseFloat(d.elo_change) > 0;
            ptColors.push( isWin ? '#4ade80' : '#f87171');
            ptBorders.push(isWin ? '#22c55e' : '#ef4444');
        });

        const W = Math.max(900, data.length * 10);
        const container = document.getElementById('eloChartContainer');
        container.style.width = W + 'px';
        const canvas = document.getElementById('eloChart');
        canvas.width = W; canvas.height = 400;

        if (charts.elo) charts.elo.destroy();
        charts.elo = new Chart(canvas.getContext('2d'), {
            type: 'line',
            data: { labels: xLabels, datasets: [
                { label: 'ELO Rating', data: eloValues, borderColor: '#fbbf24', backgroundColor: 'rgba(251,191,36,0.07)', borderWidth: 2, pointRadius: 4, pointHoverRadius: 7, pointBackgroundColor: ptColors, pointBorderColor: ptBorders, pointBorderWidth: 1.5, tension: 0.25, fill: true },
                { label: '1500 Baseline', data: new Array(data.length).fill(1500), borderColor: 'rgba(176,184,209,0.22)', borderWidth: 1, borderDash: [6,4], pointRadius: 0, fill: false },
            ]},
            options: {
                responsive: false, maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { position: 'bottom', labels: { padding: 16, font: { size: 12, family: 'Inter' }, filter: i => i.text !== '1500 Baseline' } },
                    tooltip: { backgroundColor: 'rgba(18,18,42,0.95)', titleFont: { family: 'Inter' }, bodyFont: { family: 'Inter' }, borderColor: '#fbbf24', borderWidth: 1,
                        callbacks: {
                            title:      (its) => { const d = data[its[0].dataIndex]; const chg = parseFloat(d.elo_change); return `Fight #${its[0].dataIndex+1}  —  ${chg > 0 ? 'Win ✓' : 'Loss ✗'}`; },
                            beforeBody: (its) => { const d = data[its[0].dataIndex]; return `Season ${d.season}, Month ${d.month}, Week ${d.week}`; },
                            label:      (it)  => it.dataset.label === '1500 Baseline' ? null : `  ELO: ${it.raw.toFixed(1)}`,
                            afterBody:  (its) => { const d = data[its[0].dataIndex]; const chg = parseFloat(d.elo_change); return `  Change: ${chg >= 0 ? '+' : ''}${chg.toFixed(1)}  (${parseFloat(d.elo_before).toFixed(1)} → ${parseFloat(d.elo_after).toFixed(1)})`; },
                        }
                    }
                },
                scales: {
                    y: { grid: { color: 'rgba(96,124,255,0.08)' }, ticks: { color: '#b0b8d1' }, title: { display: true, text: 'ELO Rating', color: '#a8aab8', font: { size: 11 } } },
                    x: { grid: { color: 'rgba(96,124,255,0.05)' }, ticks: { color: 'rgba(251,191,36,0.85)', font: { size: 11, weight: 'bold' }, maxRotation: 0, autoSkip: false }, title: { display: true, text: 'Fight #', color: '#a8aab8', font: { size: 11 } } },
                },
                animation: { duration: 800 }
            }
        });
    }

    // ── 3. Rivals (Victims & Nemeses) ──────────────────────────────────────
    function ftf(name) {
        const ov = { 'banjo & kazooie': 'banjoandkazooie', 'banjo and kazooie': 'banjoandkazooie' };
        const l = name.toLowerCase();
        return ov[l] || l.replace(/\s/g,'').replace(/\./g,'').replace(/&/g,'and');
    }

    function renderRivals(opponents) {
        const section = document.getElementById('rivalsSection');
        if (!opponents.length) { section.innerHTML = '<p class="rivals-empty">Not enough matchup data yet.</p>'; return; }

        const nemeses = opponents.filter(o => o.losses > o.wins).sort((a,b) => b.losses - a.losses).slice(0,5);
        const victims = opponents.filter(o => o.wins   > o.losses).sort((a,b) => b.wins   - a.wins  ).slice(0,5);

        function makeCard(opp, rank, type) {
            const card = document.createElement('div');
            card.className = `rival-card ${type}-card`;

            const rankEl = document.createElement('span');
            rankEl.className = 'rival-rank';
            rankEl.textContent = `#${rank}`;

            const img = document.createElement('img');
            img.className = 'rival-portrait';
            img.src = `/static/assets/fighters/${ftf(opp.opponent)}.png`;
            img.alt = opp.opponent;
            img.onerror = function() { this.onerror=null; this.src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 60 60'%3E%3Crect fill='%2312122a' width='60' height='60'/%3E%3Ctext fill='%23607cff' x='50%25' y='50%25' text-anchor='middle' dy='.3em' font-size='22'%3E%3F%3C/text%3E%3C/svg%3E"; };

            const info = document.createElement('div');
            info.className = 'rival-info';
            info.innerHTML = `<div class="rival-name">${opp.opponent}</div><div class="rival-record">${opp.wins}W &ndash; ${opp.losses}L</div>`;

            const rate = document.createElement('span');
            rate.className = 'rival-winrate';
            rate.textContent = opp.win_pct;

            card.append(rankEl, img, info, rate);
            card.addEventListener('click', () => { window.location.href = `/fighter/${encodeURIComponent(opp.opponent)}`; });
            return card;
        }

        section.innerHTML = `
            <div class="rivals-column">
                <div class="rivals-column-title victim-title">&#9650; Victims</div>
                <div class="rival-cards" id="victimCards"></div>
            </div>
            <div class="rivals-column">
                <div class="rivals-column-title nemesis-title">&#9660; Nemeses</div>
                <div class="rival-cards" id="nemesisCards"></div>
            </div>`;

        if (!victims.length) document.getElementById('victimCards').innerHTML = '<p class="rivals-empty">No dominant matchups yet</p>';
        else victims.forEach((v,i) => document.getElementById('victimCards').appendChild(makeCard(v, i+1, 'victim')));

        if (!nemeses.length) document.getElementById('nemesisCards').innerHTML = '<p class="rivals-empty">No nemeses yet</p>';
        else nemeses.forEach((n,i) => document.getElementById('nemesisCards').appendChild(makeCard(n, i+1, 'nemesis')));
    }

    // ── 3. Streak History ──────────────────────────────────────────────────
    function renderStreakTimeline(winStreaks, lossStreaks) {
        if (!winStreaks.length && !lossStreaks.length) return;
        const all = [
            ...winStreaks.map( s => ({ v:  (parseInt(s.Win_Streak)    ||0), type:'win',  active: s.Active_Win_Streak    ==='Active', season: s.Season_Started, month: s.Month_Started, week: s.Week_Started })),
            ...lossStreaks.map(s => ({ v: -(parseInt(s.Losing_Streak) ||0), type:'loss', active: s.Active_Losing_Streak ==='Active', season: s.Season_Started, month: s.Month_Started, week: s.Week_Started })),
        ].sort((a,b) => a.season-b.season || a.month-b.month || a.week-b.week);

        const labels = all.map((s,i) => (i===0 || all[i-1].season!==s.season) ? `S${s.season}` : '');
        const values = all.map(s => s.v);
        const colors = all.map(s => s.type==='win'
            ? (s.active ? 'rgba(74,222,128,0.95)' : 'rgba(74,222,128,0.55)')
            : (s.active ? 'rgba(248,113,113,0.95)' : 'rgba(248,113,113,0.55)'));

        if (charts.streak) charts.streak.destroy();
        charts.streak = new Chart(document.getElementById('streakChart').getContext('2d'), {
            type: 'bar',
            data: { labels, datasets: [{ data: values, backgroundColor: colors, borderColor: colors, borderWidth: 1, borderRadius: 4 }] },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { backgroundColor: 'rgba(18,18,42,0.95)', titleFont: { family:'Inter' }, bodyFont: { family:'Inter' }, borderColor:'#607cff', borderWidth:1,
                        callbacks: {
                            title: (its) => { const s=all[its[0].dataIndex]; return `${s.type==='win'?'✓ Win':'✗ Losing'} Streak${s.active?' (Active)':''}: ${Math.abs(s.v)}`; },
                            label: (it)  => { const s=all[it.dataIndex]; return `  S${s.season} M${s.month} W${s.week}`; },
                        }
                    }
                },
                scales: {
                    y: { grid: { color: 'rgba(96,124,255,0.08)' }, ticks: { callback: v => Math.abs(v), color: '#b0b8d1' }, title: { display:true, text:'Streak Length', color:'#a8aab8', font:{size:11} } },
                    x: { grid: { color: 'rgba(96,124,255,0.04)' }, ticks: { color:'#607cff', font:{size:11,weight:'bold'}, maxRotation:0, autoSkip:false } },
                },
                animation: { duration: 600 }
            }
        });
    }

    // ── 4. Season Radar ────────────────────────────────────────────────────
    const PALETTE = [
        { b:'#607cff', bg:'rgba(96,124,255,0.12)'  },
        { b:'#4ade80', bg:'rgba(74,222,128,0.12)'  },
        { b:'#fbbf24', bg:'rgba(251,191,36,0.12)'  },
        { b:'#f87171', bg:'rgba(248,113,113,0.12)' },
        { b:'#a78bfa', bg:'rgba(167,139,250,0.12)' },
        { b:'#22d3ee', bg:'rgba(34,211,238,0.12)'  },
        { b:'#fb923c', bg:'rgba(251,146,60,0.12)'  },
    ];
    const EVENT_COLS = ['Won_Tournament','Won_Royal_Rumble','Won_Scramble','Won_Smash_Series','Won_Money_In_The_Bank','Won_Smash_Bros'];

    function renderSeasonRadar(holistic) {
        if (!holistic || !holistic.length) return;

        function parseRow(row) {
            const wr = parseFloat(String(row.Win_Percentage||0).replace('%','')) || 0;
            const mm = Math.min((parseInt(row.Months_With_Major)||0) / 7 * 100, 100);
            const tm = Math.min((parseInt(row.Months_With_Title)||0) / 7 * 100, 100);
            const ev = EVENT_COLS.filter(c => row[c]!=null && row[c]!=='').length / EVENT_COLS.length * 100;
            const tc = Math.min((parseInt(row.Title_Count)||0) / 5 * 100, 100);
            return [wr, tm, mm, ev, tc];
        }

        const datasets = holistic.map((row, i) => {
            const c = PALETTE[(parseInt(row.Season)-1) % PALETTE.length];
            return { label: `Season ${row.Season}`, data: parseRow(row), _row: row, borderColor: c.b, backgroundColor: c.bg, borderWidth: 2, pointRadius: 4, pointBackgroundColor: c.b };
        });

        if (charts.radar) charts.radar.destroy();
        charts.radar = new Chart(document.getElementById('radarChart').getContext('2d'), {
            type: 'radar',
            data: { labels: ['Win Rate', 'Title Reign', 'Major Title Reign', 'Event Wins', 'Unique Titles Held'], datasets },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: { r: { min:0, max:100, grid:{color:'rgba(96,124,255,0.15)'}, angleLines:{color:'rgba(96,124,255,0.15)'}, ticks:{display:false}, pointLabels:{color:'#b0b8d1', font:{size:12,family:'Inter'}} } },
                plugins: {
                    legend: { position:'bottom', labels:{padding:16, font:{size:12,family:'Inter'}} },
                    tooltip: { backgroundColor:'rgba(18,18,42,0.95)', titleFont:{family:'Inter'}, bodyFont:{family:'Inter'}, borderColor:'#607cff', borderWidth:1,
                        callbacks: { label: (it) => {
                            const row = it.dataset._row;
                            const axis = it.chart.data.labels[it.dataIndex];
                            const s = it.dataset.label;
                            if (axis === 'Win Rate') return `  ${s}: ${row.Win_Percentage}`;
                            if (axis === 'Major Title Reign') return `  ${s}: ${row.Months_With_Major || 0} month(s)`;
                            if (axis === 'Title Reign') return `  ${s}: ${row.Months_With_Title || 0} month(s)`;
                            if (axis === 'Event Wins') {
                                const NAMES = {'Won_Tournament':'Tournament','Won_Royal_Rumble':'Royal Rumble','Won_Scramble':'Scramble','Won_Smash_Series':'Smash Series','Won_Money_In_The_Bank':'Money in the Bank','Won_Smash_Bros':'Smash Bros'};
                                const won = EVENT_COLS.filter(c => row[c]!=null && row[c]!=='').map(c => NAMES[c]);
                                return `  ${s}: ${won.length ? won.join(', ') : 'None'}`;
                            }
                            if (axis === 'Unique Titles Held') return `  ${s}: ${row.Titles_Held || 'None'}`;
                            return `  ${s}: ${it.raw.toFixed(0)}`;
                        }}
                    }
                },
                animation: { duration: 800 }
            }
        });
    }
})();

// --- Fight History (uses renderFight from app.js) ---
(function() {
    const PER_PAGE = 100;
    let page = 1, hasMore = true, loading = false, loaded = false;

    document.getElementById('fightHistoryToggle').addEventListener('click', () => {
        const body    = document.getElementById('fightHistoryBody');
        const chevron = document.getElementById('fightHistoryChevron');
        const toggle  = document.getElementById('fightHistoryToggle');
        const open    = body.style.display !== 'none';
        body.style.display        = open ? 'none' : 'block';
        chevron.style.transform   = open ? '' : 'rotate(180deg)';
        toggle.setAttribute('aria-expanded', String(!open));
        if (!open && !loaded) { loaded = true; loadPage(true); }
    });

    document.getElementById('fightHistoryLoadMoreBtn').addEventListener('click', () => {
        page++;
        loadPage(false);
    });

    function loadPage(reset) {
        if (loading) return;
        loading = true;
        const loadingEl = document.getElementById('fightHistoryLoading');
        loadingEl.style.display = 'flex';

        const params = new URLSearchParams({ fighter: FIGHTER_NAME, page });
        fetch(`/api/fights?${params}`)
            .then(r => r.json())
            .then(fights => {
                loadingEl.style.display = 'none';
                loading = false;
                const list = document.getElementById('fightHistoryList');
                if (!Array.isArray(fights) || fights.length === 0) {
                    if (reset) list.innerHTML = '<div class="fight-empty">No fight history found.</div>';
                    hasMore = false;
                    document.getElementById('fightHistoryLoadMore').style.display = 'none';
                    return;
                }
                fights.forEach(f => {
                    const row = renderFight(f);
                    // Add W/L perspective indicator based on this fighter's result
                    const me = f.fighters.find(x => x.name === FIGHTER_NAME);
                    if (me) row.classList.add(isWinner(me) ? 'perspective-win' : 'perspective-loss');
                    list.appendChild(row);
                });
                hasMore = fights.length >= PER_PAGE;
                document.getElementById('fightHistoryLoadMore').style.display = hasMore ? 'block' : 'none';
            })
            .catch(() => {
                document.getElementById('fightHistoryLoading').style.display = 'none';
                loading = false;
                document.getElementById('fightHistoryList').innerHTML =
                    '<div class="fight-empty">Error loading fight history.</div>';
            });
    }
})();

// ── Page Nav (TOC) ────────────────────────────────────────────
(function() {
    const SECTION_IDS = ['section-analytics', 'section-stats', 'section-history'];
    const pills = document.querySelectorAll('.page-nav-pill[data-section]');

    const obs = new IntersectionObserver(entries => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const id = entry.target.id;
                pills.forEach(p => p.classList.toggle('active', p.dataset.section === id));
            }
        });
    }, { rootMargin: '-10% 0px -70% 0px' });

    SECTION_IDS.forEach(id => {
        const el = document.getElementById(id);
        if (el) obs.observe(el);
    });

    pills.forEach(pill => {
        pill.addEventListener('click', e => {
            e.preventDefault();
            const el = document.getElementById(pill.dataset.section);
            if (!el) return;
            const offset = 64 + 50; // navbar + page-nav height
            const top = el.getBoundingClientRect().top + window.scrollY - offset;
            window.scrollTo({ top, behavior: 'smooth' });
        });
    });
})();

// ── Power Score Table ──────────────────────────────────────────
function renderPowerScoreTable(bySeasonMap) {
    const wrap = document.getElementById('powerScoreTableWrap');
    const entries = Object.entries(bySeasonMap)
        .map(([s, v]) => ({ season: parseInt(s), score: v.power_score, rank: v.power_rank }))
        .sort((a, b) => a.season - b.season);
    if (!entries.length) { wrap.innerHTML = '<p style="color:var(--text-muted);padding:1rem;">No data</p>'; return; }

    const rows = entries.map(e => {
        const cls = getPowerScoreClass(e.score);
        return `<tr>
            <td>S${e.season}</td>
            <td class="${cls} ps-score-cell">${e.score.toFixed(1)}</td>
            <td class="ps-rank-cell">#${e.rank}</td>
        </tr>`;
    }).join('');

    wrap.innerHTML = `<table class="ps-season-table">
        <thead><tr><th>Season</th><th>Score</th><th>Rank</th></tr></thead>
        <tbody>${rows}</tbody>
    </table>`;
}

// ── Stats Tables ──────────────────────────────────────────────
function renderStatsTable(wrapId, rows, labelKey, winsKey, lossesKey, pctKey, sortByTotal) {
    const wrap = document.getElementById(wrapId);
    if (!rows.length) { wrap.innerHTML = '<p style="color:var(--text-muted);padding:1rem;">No data</p>'; return; }
    const data = sortByTotal
        ? [...rows].sort((a,b) => (parseInt(b[winsKey])||0)+(parseInt(b[lossesKey])||0) - (parseInt(a[winsKey])||0) - (parseInt(a[lossesKey])||0))
        : rows;
    const pctClass = v => { const n = parseFloat(String(v).replace('%','')) || 0; return n >= 60 ? 'pct-high' : n < 40 ? 'pct-low' : 'pct-mid'; };
    const html = data.map(r => {
        const w = parseInt(r[winsKey]) || 0;
        const l = parseInt(r[lossesKey]) || 0;
        const pct = r[pctKey] || '0.00%';
        return `<tr>
            <td>${r[labelKey]}</td>
            <td class="stat-cell">${w}</td>
            <td class="stat-cell">${l}</td>
            <td class="stat-cell ${pctClass(pct)}">${pct}</td>
        </tr>`;
    }).join('');
    wrap.innerHTML = `<table class="ps-season-table fighter-record-table">
        <thead><tr><th></th><th>W</th><th>L</th><th>Win%</th></tr></thead>
        <tbody>${html}</tbody>
    </table>`;
}

function renderSeasonChart(data) {
    const wrap = document.getElementById('seasonTableWrap');
    if (!data.length) { wrap.innerHTML = '<p style="color:var(--text-muted);padding:1rem;">No data</p>'; return; }

    const sorted = [...data].sort((a, b) => parseInt(a.season) - parseInt(b.season));
    const labels = sorted.map(r => 'S' + r.season);
    const wins = sorted.map(r => parseInt(r.wins) || 0);
    const losses = sorted.map(r => parseInt(r.losses) || 0);
    const pcts = sorted.map(r => parseFloat(String(r.win_pct).replace('%', '')) || 0);

    wrap.innerHTML = '<canvas id="seasonComboChart"></canvas>';
    const ctx = document.getElementById('seasonComboChart').getContext('2d');

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                {
                    label: 'Wins',
                    data: wins,
                    backgroundColor: 'rgba(34,197,94,0.7)',
                    borderColor: 'rgba(34,197,94,1)',
                    borderWidth: 1,
                    borderRadius: 3,
                    stack: 'record',
                    order: 2,
                },
                {
                    label: 'Losses',
                    data: losses,
                    backgroundColor: 'rgba(239,68,68,0.7)',
                    borderColor: 'rgba(239,68,68,1)',
                    borderWidth: 1,
                    borderRadius: 3,
                    stack: 'record',
                    order: 2,
                },
                {
                    label: 'Win %',
                    data: pcts,
                    type: 'line',
                    yAxisID: 'yPct',
                    borderColor: 'rgba(96,124,255,1)',
                    backgroundColor: 'rgba(96,124,255,0.15)',
                    pointBackgroundColor: 'rgba(96,124,255,1)',
                    pointRadius: 5,
                    pointHoverRadius: 7,
                    borderWidth: 2.5,
                    tension: 0.3,
                    fill: false,
                    order: 1,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            aspectRatio: 2.2,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    labels: { color: 'rgba(255,255,255,0.7)', font: { size: 11 }, usePointStyle: true, pointStyle: 'circle', padding: 16 }
                },
                tooltip: {
                    backgroundColor: 'rgba(15,15,35,0.95)',
                    titleColor: '#fff',
                    bodyColor: 'rgba(255,255,255,0.85)',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    cornerRadius: 8,
                    padding: 10,
                    callbacks: {
                        label: ctx => {
                            if (ctx.dataset.label === 'Win %') return `Win %: ${ctx.raw.toFixed(1)}%`;
                            return `${ctx.dataset.label}: ${ctx.raw}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    ticks: { color: 'rgba(255,255,255,0.5)', font: { size: 11 } },
                    grid: { color: 'rgba(255,255,255,0.04)' }
                },
                y: {
                    stacked: true,
                    title: { display: true, text: 'Matches', color: 'rgba(255,255,255,0.45)', font: { size: 11 } },
                    ticks: { color: 'rgba(255,255,255,0.5)', font: { size: 10 }, stepSize: 1 },
                    grid: { color: 'rgba(255,255,255,0.04)' },
                    beginAtZero: true,
                },
                yPct: {
                    position: 'right',
                    title: { display: true, text: 'Win %', color: 'rgba(96,124,255,0.7)', font: { size: 11 } },
                    ticks: { color: 'rgba(96,124,255,0.7)', font: { size: 10 }, callback: v => v + '%' },
                    grid: { drawOnChartArea: false },
                    min: 0,
                    max: 100,
                }
            }
        }
    });
}

function renderFightTypeChart(data) {
    const wrap = document.getElementById('fightTypeTableWrap');
    if (!data.length) {
        wrap.innerHTML = '<p style="color:var(--text-muted);padding:1rem;">No data</p>';
        return;
    }

    const parsed = normalizePerformanceRows(data, 'type', 'wins', 'losses', 'win_pct');
    const featured = parsed.slice(0, 4);
    const rows = parsed.map(row => `
        <tr>
            <td>${escapeHtml(row.name)}</td>
            <td class="stat-cell">${row.wins}</td>
            <td class="stat-cell">${row.losses}</td>
            <td class="stat-cell">${row.total}</td>
            <td class="stat-cell">${row.pct.toFixed(2)}%</td>
        </tr>
    `).join('');

    const cards = featured.map(row => `
        <article class="format-spotlight-card" style="--format-tint:${ppvHeatColor(row.pct)};--format-border:${ppvHeatBorder(row.pct)};">
            <div class="format-spotlight-top">
                <div class="format-spotlight-name">${escapeHtml(row.name)}</div>
                <div class="format-spotlight-pct">${row.pct.toFixed(0)}%</div>
            </div>
            <div class="format-spotlight-bar">
                <div class="format-spotlight-bar-fill" style="width:${row.pct}%;"></div>
            </div>
            <div class="format-spotlight-meta">
                <span>${row.wins}-${row.losses}</span>
                <span>${row.total} fights</span>
            </div>
        </article>
    `).join('');

    wrap.innerHTML = `
        <div class="format-spotlight-grid">${cards}</div>
        <div class="format-table-note">Most-used formats are highlighted above. Full breakdown stays below for exact record lookup.</div>
        <table class="ps-season-table fighter-record-table fighter-record-table-compact">
            <thead><tr><th>Format</th><th>W</th><th>L</th><th>Total</th><th>Win%</th></tr></thead>
            <tbody>${rows}</tbody>
        </table>
    `;
}

function renderBrandChart(data) {
    const wrap = document.getElementById('brandTableWrap');
    if (!data.length) {
        wrap.innerHTML = '<p style="color:var(--text-muted);padding:1rem;">No data</p>';
        return;
    }

    const parsed = normalizePerformanceRows(data, 'brand', 'wins', 'losses', 'win_pct');
    const cards = parsed.map(row => `
        <article class="brand-performance-card" style="--brand-tint:${ppvHeatColor(row.pct)};--brand-border:${ppvHeatBorder(row.pct)};">
            <div class="brand-performance-header">
                <div class="brand-performance-name">${escapeHtml(row.name)}</div>
                <div class="brand-performance-pct">${row.pct.toFixed(0)}%</div>
            </div>
            <div class="brand-performance-bar">
                <div class="brand-performance-bar-fill" style="width:${row.pct}%;"></div>
            </div>
            <div class="brand-performance-meta">
                <span>${row.wins}-${row.losses}</span>
                <span>${row.total} fight${row.total !== 1 ? 's' : ''}</span>
            </div>
        </article>
    `).join('');

    wrap.innerHTML = `<div class="brand-performance-grid">${cards}</div>`;
}

function renderPPVChart(data) {
    renderPPVLogoGrid(data);
}

function normalizePerformanceRows(data, nameKey, winsKey, lossesKey, pctKey) {
    return [...data]
        .map(row => {
            const wins = parseInt(row[winsKey]) || 0;
            const losses = parseInt(row[lossesKey]) || 0;
            const total = wins + losses;
            const pct = parseFloat(String(row[pctKey]).replace('%', '')) || 0;
            return {
                name: row[nameKey],
                wins,
                losses,
                total,
                pct,
            };
        })
        .sort((a, b) => b.total - a.total || b.pct - a.pct || (a.name || '').localeCompare(b.name || ''));
}

function ppvHeatColor(pct) {
    if (pct >= 75) return 'rgba(34, 197, 94, 0.16)';
    if (pct >= 60) return 'rgba(132, 204, 22, 0.15)';
    if (pct >= 45) return 'rgba(250, 204, 21, 0.14)';
    if (pct >= 30) return 'rgba(249, 115, 22, 0.15)';
    return 'rgba(239, 68, 68, 0.16)';
}

function ppvHeatBorder(pct) {
    if (pct >= 75) return 'rgba(34, 197, 94, 0.42)';
    if (pct >= 60) return 'rgba(132, 204, 22, 0.38)';
    if (pct >= 45) return 'rgba(250, 204, 21, 0.34)';
    if (pct >= 30) return 'rgba(249, 115, 22, 0.36)';
    return 'rgba(239, 68, 68, 0.4)';
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function normalizeLookupValue(value) {
    return String(value ?? '').trim().toLowerCase();
}

function renderPPVLogoGrid(data) {
    const wrap = document.getElementById('ppvLogoGridWrap');
    if (!wrap) return;
    if (!data.length) {
        wrap.innerHTML = '<p style="color:var(--text-muted);padding:1rem;">No data</p>';
        return;
    }

    const parsed = normalizePerformanceRows(data, 'ppv', 'wins', 'losses', 'win_pct').map(item => ({
        ...item,
        file: stageToFilename(item.name || ''),
    }));

    const tiles = parsed.map(item => {
        const tileClass = item.total < 3 ? 'ppv-performance-tile ppv-performance-tile--low-sample' : 'ppv-performance-tile';
        const heat = ppvHeatColor(item.pct);
        const border = ppvHeatBorder(item.pct);
        const safeName = escapeHtml(item.name);
        return `
            <article class="${tileClass}" style="--ppv-tint:${heat};--ppv-border:${border};" title="${safeName}: ${item.wins}-${item.losses} (${item.pct.toFixed(1)}%)">
                <div class="ppv-performance-logo-wrap">
                    <img
                        src="/static/assets/ppv/${item.file}.png"
                        alt="${safeName}"
                        class="ppv-performance-logo"
                        loading="lazy"
                        onerror="this.style.display='none';this.parentElement.classList.add('ppv-performance-logo-wrap--fallback');this.parentElement.innerHTML='<span class=&quot;ppv-performance-fallback&quot;>${safeName}</span>';"
                    >
                    <div class="ppv-performance-overlay" style="background:${heat};"></div>
                    <div class="ppv-performance-pct">${item.pct.toFixed(0)}%</div>
                </div>
                <div class="ppv-performance-meta">
                    <div class="ppv-performance-name">${safeName}</div>
                    <div class="ppv-performance-record">${item.wins}-${item.losses} <span>${item.total} fight${item.total !== 1 ? 's' : ''}</span></div>
                </div>
            </article>
        `;
    }).join('');

    wrap.innerHTML = `
        <div class="ppv-performance-intro">
            <span class="ppv-performance-intro-copy">A soft green-to-red tint shows how strong the fighter has been at each PPV. Lower-sample events are slightly softened.</span>
        </div>
        <div class="ppv-performance-grid">${tiles}</div>
    `;
}

function renderChampionshipChart(data) {
    renderChampionshipBeltGrid(data);
}

function renderChampionshipBeltGrid(data) {
    const wrap = document.getElementById('champLogoGridWrap');
    if (!wrap) return;
    if (!data.length) {
        wrap.innerHTML = '<p style="color:var(--text-muted);padding:1rem;">No data</p>';
        return;
    }

    const parsed = normalizePerformanceRows(data, 'Championship_Name', 'Wins', 'Losses', 'Win Percentage');
    const tiles = parsed.map(item => {
        const tileClass = item.total < 3 ? 'ppv-performance-tile ppv-performance-tile--low-sample ppv-performance-tile--belt' : 'ppv-performance-tile ppv-performance-tile--belt';
        const heat = ppvHeatColor(item.pct);
        const border = ppvHeatBorder(item.pct);
        const safeName = escapeHtml(item.name);
        const asset = championshipToBeltAsset(item.name);
        const media = asset
            ? `<img src="${asset}" alt="${safeName}" class="ppv-performance-logo ppv-performance-logo--belt" loading="lazy">`
            : `<span class="ppv-performance-fallback">${safeName}</span>`;

        return `
            <article class="${tileClass}" style="--ppv-tint:${heat};--ppv-border:${border};" title="${safeName}: ${item.wins}-${item.losses} (${item.pct.toFixed(1)}%)">
                <div class="ppv-performance-logo-wrap ppv-performance-logo-wrap--belt">
                    ${media}
                    <div class="ppv-performance-overlay"></div>
                    <div class="ppv-performance-pct">${item.pct.toFixed(0)}%</div>
                </div>
                <div class="ppv-performance-meta">
                    <div class="ppv-performance-name">${safeName}</div>
                    <div class="ppv-performance-record">${item.wins}-${item.losses} <span>${item.total} title fight${item.total !== 1 ? 's' : ''}</span></div>
                </div>
            </article>
        `;
    }).join('');

    wrap.innerHTML = `
        <div class="ppv-performance-intro">
            <span class="ppv-performance-intro-copy">Each belt tile uses a soft green-to-red tint to show how well the fighter has performed in matches for that championship.</span>
        </div>
        <div class="ppv-performance-grid ppv-performance-grid--belt">${tiles}</div>
    `;
}

function stageHeatColor(pct) {
    if (pct >= 75) return '#16a34a';
    if (pct >= 60) return '#65a30d';
    if (pct >= 45) return '#ca8a04';
    if (pct >= 30) return '#ea580c';
    return '#dc2626';
}

function renderLocationChart(data) {
    const wrap = document.getElementById('locationHeatmapWrap');
    if (!data.length) { wrap.innerHTML = '<p style="color:var(--text-muted);padding:1rem;">No data</p>'; return; }

    const parsed = data.map(r => {
        const w = parseInt(r.wins) || 0;
        const l = parseInt(r.losses) || 0;
        return {
            name: r.location,
            key: normalizeLookupValue(r.location),
            w,
            l,
            total: w + l,
            pct: parseFloat(String(r.win_pct).replace('%', '')) || 0,
        };
    }).sort((a, b) => b.total - a.total);

    // Squarified treemap layout
    function squarify(items, x, y, width, height) {
        const rects = [];
        if (!items.length || width <= 0 || height <= 0) return rects;
        const totalVal = items.reduce((s, i) => s + i.total, 0);
        if (totalVal <= 0) return rects;

        let remaining = [...items];
        let cx = x, cy = y, cw = width, ch = height;

        while (remaining.length) {
            const isWide = cw >= ch;
            const side = isWide ? ch : cw;
            const areaLeft = remaining.reduce((s, i) => s + i.total, 0);
            const scaleFactor = (cw * ch) / areaLeft;

            let row = [remaining[0]];
            let rowArea = remaining[0].total * scaleFactor;
            let bestAspect = Math.max(side * side * remaining[0].total * scaleFactor / (rowArea * rowArea), (rowArea * rowArea) / (side * side * remaining[0].total * scaleFactor));

            for (let i = 1; i < remaining.length; i++) {
                const newArea = rowArea + remaining[i].total * scaleFactor;
                const worstNew = row.concat(remaining[i]).reduce((worst, item) => {
                    const a = item.total * scaleFactor;
                    const rowLen = newArea / side;
                    const itemLen = a / rowLen;
                    const aspect = Math.max(rowLen / itemLen, itemLen / rowLen);
                    return Math.max(worst, aspect);
                }, 0);
                if (worstNew < bestAspect) {
                    row.push(remaining[i]);
                    rowArea = newArea;
                    bestAspect = worstNew;
                } else break;
            }

            remaining = remaining.slice(row.length);
            const rowLen = rowArea / side;

            let offset = 0;
            for (const item of row) {
                const itemArea = item.total * scaleFactor;
                const itemLen = itemArea / rowLen;
                if (isWide) {
                    rects.push({ ...item, rx: cx, ry: cy + offset, rw: rowLen, rh: itemLen });
                } else {
                    rects.push({ ...item, rx: cx + offset, ry: cy, rw: itemLen, rh: rowLen });
                }
                offset += itemLen;
            }

            if (isWide) { cx += rowLen; cw -= rowLen; }
            else { cy += rowLen; ch -= rowLen; }
        }
        return rects;
    }

    const containerW = 800;
    const containerH = 420;
    const rects = squarify(parsed, 0, 0, containerW, containerH);

    const tiles = rects.map(r => {
        const color = stageHeatColor(r.pct);
        const showLabel = r.rw > 40 && r.rh > 28;
        const showRecord = r.rw > 50 && r.rh > 40;
        const fontSize = Math.max(0.55, Math.min(0.85, r.rw / 90));
        const imgSrc = `/static/assets/stages/${stageToFilename(r.name)}.png`;
        return `<div class="treemap-tile" data-location-key="${escapeHtml(r.key)}" style="left:${r.rx / containerW * 100}%;top:${r.ry / containerH * 100}%;width:${r.rw / containerW * 100}%;height:${r.rh / containerH * 100}%;" title="${escapeHtml(r.name)}\n${r.w}W-${r.l}L (${r.pct.toFixed(1)}%)">
            <img class="treemap-img" src="${imgSrc}" alt="" onerror="this.style.display='none'">
            <div class="treemap-overlay" style="background:${color}"></div>
            ${showLabel ? `<span class="treemap-label" style="font-size:${fontSize}rem">${escapeHtml(r.name)}</span>` : ''}
            ${showRecord ? `<span class="treemap-record">${r.w}-${r.l}</span>` : ''}
        </div>`;
    }).join('');

    const stageLookup = new Map(parsed.map(item => [item.key, item]));

    wrap.innerHTML = `
        <div class="stage-heatmap-controls">
            <div class="autocomplete-wrapper stage-heatmap-search">
                <input type="text" id="stageHeatmapSearch" class="fighter-input stage-heatmap-input" placeholder="Search a stage..." autocomplete="off">
                <div class="autocomplete-dropdown"></div>
            </div>
            <div id="stageHeatmapResult" class="stage-heatmap-result">Search for a stage to highlight it and see the record.</div>
        </div>
        <div class="stage-bubble-legend" style="padding:10px 16px;">
            <span class="stage-legend-item"><span class="stage-legend-dot" style="background:#16a34a"></span>75%+</span>
            <span class="stage-legend-item"><span class="stage-legend-dot" style="background:#65a30d"></span>60-74%</span>
            <span class="stage-legend-item"><span class="stage-legend-dot" style="background:#ca8a04"></span>45-59%</span>
            <span class="stage-legend-item"><span class="stage-legend-dot" style="background:#ea580c"></span>30-44%</span>
            <span class="stage-legend-item"><span class="stage-legend-dot" style="background:#dc2626"></span>&lt;30%</span>
        </div>
        <div class="treemap-container">${tiles}</div>
    `;

    const input = document.getElementById('stageHeatmapSearch');
    const result = document.getElementById('stageHeatmapResult');
    const tileNodes = [...wrap.querySelectorAll('.treemap-tile')];
    setupAutocomplete(input, 'locations');

    function clearHighlight() {
        tileNodes.forEach(tile => tile.classList.remove('treemap-tile-highlighted', 'treemap-tile-dimmed'));
        result.textContent = 'Search for a stage to highlight it and see the record.';
    }

    function focusStage(rawValue) {
        const key = normalizeLookupValue(rawValue);
        if (!key) {
            clearHighlight();
            return;
        }

        const match = stageLookup.get(key);
        tileNodes.forEach(tile => {
            const isMatch = tile.dataset.locationKey === key;
            tile.classList.toggle('treemap-tile-highlighted', isMatch);
            tile.classList.toggle('treemap-tile-dimmed', !!match && !isMatch);
            if (isMatch) tile.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
        });

        if (!match) {
            result.textContent = `No recorded fights for this fighter at ${rawValue}.`;
            return;
        }

        result.textContent = `${match.name}: ${match.w}-${match.l} record across ${match.total} fight${match.total !== 1 ? 's' : ''} (${match.pct.toFixed(1)}% win rate).`;
    }

    input.addEventListener('change', event => focusStage(event.target.value));
    input.addEventListener('keydown', event => {
        if (event.key === 'Enter') focusStage(event.target.value);
        if (event.key === 'Escape') {
            input.value = '';
            clearHighlight();
        }
    });
    input.addEventListener('blur', () => {
        input.value = '';
        clearHighlight();
    });
}


function fillTable(tbodyId, rows, keys) {
    const tbody = document.getElementById(tbodyId);
    if (!rows || rows.length === 0) return;
    tbody.innerHTML = '';
    rows.forEach((row, i) => {
        const tr = document.createElement('tr');
        keys.forEach(key => {
            const td = document.createElement('td');
            td.textContent = row[key] !== undefined ? row[key] : '--';
            td.className = key === 'wins' || key === 'losses' || key === 'win_pct' ? 'stat-cell' : '';
            tr.appendChild(td);
        });
        tr.style.opacity = '0';
        tbody.appendChild(tr);
        setTimeout(() => {
            tr.style.transition = 'opacity 0.3s ease';
            tr.style.opacity = '1';
        }, i * 40);
    });
}
