// Gamecast — ESPN-style live gamecast for synthesized SSB matches.
// Win probability blends an ELO prior with a live state estimate, with weight
// shifting toward state as the match resolves.

(function () {
    const $ = (id) => document.getElementById(id);

    // --- Per-match state (reset on each /gamecast/start) ---
    let activeMatch = null;
    let prevA = null, prevB = null;       // last seen fighter snapshots (for stock-loss detection)
    let stockHistA = [], stockHistB = [];
    let lastPhase = 'normal';
    let chart = null;
    const probSeries = { labels: [], a: [], b: [], flinkA: [] };
    let latestFlinkProbA = null;          // most recent p_a from the Flink win_probability job

    // ---------------- ELO + win prob math ----------------
    const FIGHTER_WEIGHTS = Object.freeze({
        'Banjo & Kazooie': 106,
        'Bayonetta': 81,
        'Bowser': 135,
        'Bowser Jr.': 108,
        'Captain Falcon': 104,
        'Chrom': 95,
        'Cloud': 100,
        'Corrin': 98,
        'Daisy': 89,
        'Dark Pit': 96,
        'Dark Samus': 108,
        'Diddy Kong': 90,
        'DK': 127,
        'Dr. Mario': 98,
        'Duck Hunt': 86,
        'Erdrick': 101,
        'Falco': 82,
        'Fox': 77,
        'Ganondorf': 118,
        'Greninja': 88,
        'Ice Climbers': 92,
        'Ike': 107,
        'Incineroar': 116,
        'Inkling': 94,
        'Isabelle': 88,
        'Jigglypuff': 68,
        'Joker': 93,
        'Ken': 103,
        'King Dedede': 127,
        'King K. Rool': 133,
        'Kirby': 79,
        'Link': 104,
        'Little Mac': 87,
        'Lucario': 92,
        'Lucas': 94,
        'Lucina': 90,
        'Luigi': 97,
        'Mario': 98,
        'Marth': 90,
        'Mega Man': 102,
        'Meta Knight': 80,
        'Mewtwo': 79,
        'Mr Game & Watch': 75,
        'Ness': 94,
        'Olimar': 79,
        'Pac-Man': 95,
        'Palutena': 91,
        'Peach': 89,
        'Pichu': 62,
        'Pikachu': 79,
        'Piranha Plant': 112,
        'Pit': 96,
        'Pokemon Trainer': 96,
        'ROB': 106,
        'Richter Belmont': 107,
        'Ridley': 107,
        'Robin': 95,
        'Rosalina & Luma': 82,
        'Roy': 95,
        'Ryu': 103,
        'Samus': 108,
        'Sheik': 78,
        'Shulk': 97,
        'Simon Belmont': 107,
        'Snake': 106,
        'Sonic': 86,
        'Toon Link': 91,
        'Villager': 92,
        'Wario': 107,
        'Wii Fit Trainer': 96,
        'Wolf': 92,
        'Yoshi': 104,
        'Young Link': 88,
        'Zelda': 85,
    });

    function clamp01(value) {
        return Math.max(0, Math.min(1, value));
    }

    function eloProb(myElo, oppElo) {
        if (myElo == null || oppElo == null) return 0.5;
        return 1 / (1 + Math.pow(10, (oppElo - myElo) / 400));
    }

    function normalDeathPercent(name) {
        const weight = FIGHTER_WEIGHTS[name] || 100;
        return Math.max(145, Math.min(225, 90 + weight));
    }

    function stockPressure(fighter, phase) {
        if (!fighter || fighter.stocks <= 0) return 1;
        if (phase === 'sudden_death') return fighter.damage >= 300 ? 0.95 : 0;

        const deathPercent = normalDeathPercent(fighter.name);
        // Cap damage pressure at the character's "basically dead" percent:
        // 250% and 600% should mean the same thing for win probability.
        const cappedDamageProgress = clamp01(fighter.damage / deathPercent);
        const lateKoPressure = cappedDamageProgress * cappedDamageProgress * (3 - 2 * cappedDamageProgress);
        return 0.68 * cappedDamageProgress + 0.24 * lateKoPressure;
    }

    function effectiveStocks(fighter, phase) {
        if (!fighter || fighter.stocks <= 0) return 0;
        return fighter.stocks - stockPressure(fighter, phase);
    }

    function damageAwareLiveStateProb(a, b, phase) {
        // Total damage difference matters from 0%, then accelerates as a fighter
        // nears their character-specific KO percent.
        const effectiveA = effectiveStocks(a, phase);
        const effectiveB = effectiveStocks(b, phase);
        const effectiveStockDiff = effectiveA - effectiveB;
        const logit = 2.3 * effectiveStockDiff;
        return 1 / (1 + Math.exp(-logit));
    }

    function damageAwareBlendWeight(effectiveStocksConsumed, totalStocksAtRisk) {
        if (totalStocksAtRisk <= 0) return 0.5;
        const progress = clamp01(effectiveStocksConsumed / totalStocksAtRisk);
        return 0.45 + progress * 0.5;
    }

    function computeWinProb(payload) {
        if (!activeMatch) return { a: 0.5, b: 0.5 };
        const a = payload.fighters[0], b = payload.fighters[1];

        if (payload.event === 'match_over') {
            const aWins = activeMatch.winner ? activeMatch.winner === a.name : a.stocks > b.stocks;
            return { a: aWins ? 1 : 0, b: aWins ? 0 : 1 };
        }

        const eloA = activeMatch.elo && activeMatch.elo.a_before;
        const eloB = activeMatch.elo && activeMatch.elo.b_before;
        const elo_a = eloProb(eloA, eloB);
        const state_a = damageAwareLiveStateProb(a, b, payload.phase);

        const total = activeMatch.total_stocks * 2;
        const consumed = total - (effectiveStocks(a, payload.phase) + effectiveStocks(b, payload.phase));
        const w = damageAwareBlendWeight(consumed, total);
        const blended = (1 - w) * elo_a + w * state_a;
        return { a: clamp01(blended), b: clamp01(1 - blended) };
    }

    // ---------------- Asset helper (matches utils.fighter_to_filename) ----------------
    function fighterToFilename(name) {
        if (!name) return '';
        const lower = name.toLowerCase();
        if (lower === 'banjo & kazooie' || lower === 'banjo and kazooie') return 'banjoandkazooie';
        return lower.replace(/ /g, '').replace(/\./g, '').replace(/&/g, 'and');
    }

    function setPortrait(imgEl, name) {
        const fname = fighterToFilename(name);
        imgEl.src = `/static/assets/fighters/${fname}.png`;
        imgEl.onerror = () => { imgEl.style.opacity = '0.2'; };
        imgEl.style.opacity = '1';
    }

    function setStartButton(label, disabled) {
        const btn = $('gcStart');
        btn.disabled = disabled;
        btn.innerHTML = `<i data-lucide="radio"></i><span>${label}</span>`;
        if (window.lucide) lucide.createIcons();
    }

    // ---------------- Chart ----------------
    function chartGradient(context, color, transparentColor) {
        const { chart: chartInstance } = context;
        const { ctx, chartArea } = chartInstance;
        if (!chartArea) return transparentColor;
        const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
        gradient.addColorStop(0, color);
        gradient.addColorStop(0.72, transparentColor);
        gradient.addColorStop(1, 'rgba(0,0,0,0)');
        return gradient;
    }

    function ensureChart() {
        if (chart) return chart;
        const ctx = $('gcProbChart').getContext('2d');
        chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'A',
                        data: [],
                        borderColor: '#6ee7ff',
                        backgroundColor: (context) => chartGradient(context, 'rgba(110,231,255,0.22)', 'rgba(110,231,255,0.02)'),
                        fill: true,
                        cubicInterpolationMode: 'monotone',
                        tension: 0.42,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        pointHoverBorderWidth: 2,
                        pointHoverBackgroundColor: '#080808',
                        pointHoverBorderColor: '#6ee7ff',
                        borderWidth: 3,
                    },
                    {
                        label: 'B',
                        data: [],
                        borderColor: '#ff9f7a',
                        backgroundColor: (context) => chartGradient(context, 'rgba(255,159,122,0.2)', 'rgba(255,159,122,0.02)'),
                        fill: true,
                        cubicInterpolationMode: 'monotone',
                        tension: 0.42,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        pointHoverBorderWidth: 2,
                        pointHoverBackgroundColor: '#080808',
                        pointHoverBorderColor: '#ff9f7a',
                        borderWidth: 3,
                    },
                    {
                        // Flink-computed p_a from the win_probability job.
                        // No ELO prior, no damage-pressure curve - just a logistic
                        // on stock_diff + damage_diff. Useful as a "what does the
                        // raw state say?" overlay against the ELO-blended traces.
                        label: 'Flink raw state (A)',
                        data: [],
                        borderColor: 'rgba(220, 224, 240, 0.85)',
                        borderDash: [5, 4],
                        borderWidth: 1.6,
                        fill: false,
                        cubicInterpolationMode: 'monotone',
                        tension: 0.35,
                        pointRadius: 0,
                        pointHoverRadius: 3,
                        pointHoverBorderWidth: 2,
                        pointHoverBackgroundColor: '#080808',
                        pointHoverBorderColor: 'rgba(220, 224, 240, 1)',
                        spanGaps: true,
                    },
                ],
            },
            options: {
                animation: { duration: 220, easing: 'easeOutQuart' },
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom',
                        labels: {
                            color: 'rgba(168,170,184,0.85)',
                            boxWidth: 18,
                            boxHeight: 3,
                            font: { size: 11 },
                            padding: 12,
                        },
                    },
                    tooltip: {
                        backgroundColor: 'rgba(8,8,8,0.94)',
                        borderColor: 'rgba(96,124,255,0.28)',
                        borderWidth: 1,
                        titleColor: '#ffffff',
                        bodyColor: '#d8dcff',
                        displayColors: true,
                        padding: 10,
                        callbacks: {
                            title: (items) => items.length ? items[0].label : '',
                            label: (context) => `${context.dataset.label}: ${Math.round(context.parsed.y * 100)}%`,
                        },
                    },
                },
                scales: {
                    x: {
                        display: true,
                        grid: { color: 'rgba(255,255,255,0.035)', drawBorder: false },
                        ticks: { color: 'rgba(168,170,184,0.72)', maxTicksLimit: 8 },
                    },
                    y: {
                        min: 0,
                        max: 1,
                        grid: { color: 'rgba(96,124,255,0.10)', drawBorder: false },
                        ticks: {
                            color: 'rgba(168,170,184,0.72)',
                            stepSize: 0.25,
                            callback: (v) => `${Math.round(v * 100)}%`,
                        },
                    },
                },
            },
        });
        return chart;
    }

    function pushChartPoint(elapsedSec, pa, pb, force = false) {
        const c = ensureChart();
        // Sample every ~0.5s of match time to keep the chart smooth without bloating points
        if (!force && probSeries.labels.length > 0) {
            const lastSec = probSeries.labels[probSeries.labels.length - 1];
            if (elapsedSec - lastSec < 0.5) return;
        }
        probSeries.labels.push(elapsedSec);
        probSeries.a.push(pa);
        probSeries.b.push(pb);
        // Sample the latest Flink reading at the same x-coordinate. Null until
        // Flink has emitted at least one tick - Chart.js draws a gap.
        probSeries.flinkA.push(latestFlinkProbA);
        c.data.labels = probSeries.labels.map(fmtChartClock);
        c.data.datasets[0].data = probSeries.a;
        c.data.datasets[1].data = probSeries.b;
        c.data.datasets[2].data = probSeries.flinkA;
        c.update();
    }

    function resetChart() {
        probSeries.labels.length = 0;
        probSeries.a.length = 0;
        probSeries.b.length = 0;
        probSeries.flinkA.length = 0;
        latestFlinkProbA = null;
        if (chart) {
            chart.data.labels = [];
            chart.data.datasets[0].data = [];
            chart.data.datasets[1].data = [];
            chart.data.datasets[2].data = [];
            chart.update('none');
        }
    }

    // ---------------- Stock history ----------------
    function renderStockHistory() {
        function render(listId, hist, totalStocks) {
            const el = $(listId);
            if (!hist.length) {
                el.innerHTML = '<div class="empty">No stocks lost yet</div>';
                return;
            }
            el.innerHTML = hist.map((h) => {
                const pctClass = h.damage >= 200 ? 'pct danger' : h.damage >= 150 ? 'pct clutch' : 'pct';
                const stockNum = (totalStocks - h.stockBefore) + 1;
                return `<div class="row">
                    <span class="lbl">Stock ${stockNum} of ${totalStocks} — at ${h.timeStr}</span>
                    <span class="${pctClass}">${Math.round(h.damage)}%</span>
                </div>`;
            }).join('');
        }
        const ts = activeMatch ? activeMatch.total_stocks : 3;
        render('gcStockHistA', stockHistA, ts);
        render('gcStockHistB', stockHistB, ts);
    }

    // ---------------- Banners ----------------
    function showStockLostBanner(name, damage) {
        const b = $('gcStockLostBanner');
        b.textContent = `${name} — STOCK LOST @ ${Math.round(damage)}%`;
        b.classList.add('show');
        clearTimeout(showStockLostBanner._t);
        showStockLostBanner._t = setTimeout(() => b.classList.remove('show'), 1800);
    }

    function setSuddenDeathBanner(on) {
        $('gcSuddenBanner').style.display = on ? 'block' : 'none';
    }

    // ---------------- Render ----------------
    function fmtClock(sec) {
        const m = Math.floor(sec / 60);
        const s = Math.floor(sec - m * 60);
        return `${m}:${String(s).padStart(2, '0')}`;
    }

    function fmtChartClock(sec) {
        return fmtClock(Number(sec) || 0);
    }

    function damageClass(d) {
        return 'gc-damage-big' + (d >= 150 ? ' danger' : d >= 100 ? ' high' : '');
    }

    function stockGlyphs(stocks, total) {
        const filled = '●'.repeat(Math.max(0, stocks));
        const empty = '<span class="gone">' + '●'.repeat(Math.max(0, total - stocks)) + '</span>';
        return filled + empty;
    }

    function renderLiveState(payload) {
        const total = activeMatch ? activeMatch.total_stocks : 3;
        const a = payload.fighters[0], b = payload.fighters[1];

        // Damage / stocks / clock
        $('gcDamageA').textContent = `${Math.round(a.damage)}%`;
        $('gcDamageB').textContent = `${Math.round(b.damage)}%`;
        $('gcDamageA').className = damageClass(a.damage);
        $('gcDamageB').className = damageClass(b.damage);
        $('gcStocksA').innerHTML = stockGlyphs(a.stocks, total);
        $('gcStocksB').innerHTML = stockGlyphs(b.stocks, total);
        $('gcClock').textContent = fmtClock(payload.elapsed_sec);
        const isSuddenDeathFinal = payload.event === 'match_over' && activeMatch && activeMatch.is_sudden_death;

        // Stock-loss detection — captures the damage from PREVIOUS tick
        // since by the current tick the synthesizer may have already reset to 0.
        if (!isSuddenDeathFinal && prevA && a.stocks < prevA.stocks) {
            stockHistA.push({
                stockBefore: prevA.stocks,
                damage: prevA.damage,
                sec: payload.elapsed_sec,
                timeStr: fmtClock(payload.elapsed_sec),
            });
            showStockLostBanner(a.name, prevA.damage);
            renderStockHistory();
        }
        if (!isSuddenDeathFinal && prevB && b.stocks < prevB.stocks) {
            stockHistB.push({
                stockBefore: prevB.stocks,
                damage: prevB.damage,
                sec: payload.elapsed_sec,
                timeStr: fmtClock(payload.elapsed_sec),
            });
            showStockLostBanner(b.name, prevB.damage);
            renderStockHistory();
        }
        prevA = a; prevB = b;

        // Phase change → SD banner
        if (payload.phase && payload.phase !== lastPhase) {
            lastPhase = payload.phase;
            setSuddenDeathBanner(payload.phase === 'sudden_death');
        }

        // Match over text — re-enable Start button
        if (payload.event === 'match_over') {
            const finalScore = `${a.stocks}–${b.stocks}`;
            $('gcMatchPill').textContent = `Final: ${a.name} ${finalScore} ${b.name}`;
            setSuddenDeathBanner(false);
            setStartButton('Start a Match', false);
        }

        // Win probability — compute client-side from ELO + state
        const wp = computeWinProb(payload);
        $('gcProbValA').textContent = `${Math.round(wp.a * 100)}%`;
        $('gcProbValB').textContent = `${Math.round(wp.b * 100)}%`;
        pushChartPoint(payload.elapsed_sec, wp.a, wp.b, payload.event === 'match_over');
    }

    function renderEvent(payload) {
        const list = $('gcEvents');
        if (list.firstChild && list.firstChild.style && list.firstChild.style.opacity === '0.4') {
            list.innerHTML = '';
        }
        const row = document.createElement('div');
        row.className = 'gc-event-row';
        row.innerHTML =
            `<span class="gc-event-kind ${payload.kind}">${payload.kind}</span>` +
            `<span style="opacity:0.7; min-width:48px;">${payload.elapsed_sec.toFixed(1)}s</span>` +
            `<span>${payload.note}</span>`;
        list.insertBefore(row, list.firstChild);
        while (list.childElementCount > 25) list.removeChild(list.lastChild);
    }

    // ---------------- SSE ----------------
    function connectStream() {
        const status = $('gcStatus');
        const es = new EventSource('/gamecast/stream');

        es.addEventListener('open', () => { status.textContent = 'Stream: connected'; });
        es.addEventListener('error', () => { status.textContent = 'Stream: reconnecting…'; });

        es.addEventListener('live_state', (e) => {
            try {
                const payload = JSON.parse(e.data);
                // Filter: only render the match we actually started
                if (!activeMatch || payload.match_id !== activeMatch.match_id) return;
                renderLiveState(payload);
            } catch {}
        });
        es.addEventListener('event', (e) => {
            try {
                const payload = JSON.parse(e.data);
                if (!activeMatch || payload.match_id !== activeMatch.match_id) return;
                renderEvent(payload);
            } catch {}
        });
        // Flink's raw-state win probability — drawn as a dashed overlay on the
        // chart so the audience can see how the ELO-blended view differs from
        // the pure stock+damage logistic.
        es.addEventListener('win_prob', (e) => {
            try {
                const payload = JSON.parse(e.data);
                if (!activeMatch || payload.match_id !== activeMatch.match_id) return;
                if (typeof payload.p_a === 'number') {
                    latestFlinkProbA = clamp01(payload.p_a);
                }
            } catch {}
        });
    }

    // ---------------- Start a match ----------------
    function describeScore(m) {
        if (m.is_sudden_death) return 'SUDDEN DEATH';
        const losses = m.total_stocks - m.winner_stocks_remaining;
        return `${m.total_stocks}–${losses}`;
    }

    function resetMatch(m) {
        activeMatch = m;
        prevA = null; prevB = null;
        stockHistA = []; stockHistB = [];
        lastPhase = 'normal';
        setSuddenDeathBanner(false);
        resetChart();

        const total = m.total_stocks;
        // Names + portraits (winner is fighter_a per picker)
        $('gcNameA').textContent = m.fighter_a;
        $('gcNameB').textContent = m.fighter_b;
        $('gcStockHistTitleA').textContent = m.fighter_a;
        $('gcStockHistTitleB').textContent = m.fighter_b;
        $('gcProbLabelA').textContent = m.fighter_a;
        $('gcProbLabelB').textContent = m.fighter_b;
        const probChart = ensureChart();
        probChart.data.datasets[0].label = `${m.fighter_a} (ELO-blended)`;
        probChart.data.datasets[1].label = `${m.fighter_b} (ELO-blended)`;
        probChart.data.datasets[2].label = `${m.fighter_a} (Flink raw state)`;
        probChart.update('none');
        setPortrait($('gcPortraitA'), m.fighter_a);
        setPortrait($('gcPortraitB'), m.fighter_b);

        // ELO display
        const ea = m.elo && m.elo.a_before, eb = m.elo && m.elo.b_before;
        $('gcEloA').textContent = ea != null ? Math.round(ea) : '—';
        $('gcEloB').textContent = eb != null ? Math.round(eb) : '—';
        const eaDelta = ea != null && eb != null ? Math.round(ea - eb) : null;
        if (eaDelta != null) {
            $('gcEloDeltaA').textContent = eaDelta > 0 ? `+${eaDelta} favored` : eaDelta < 0 ? `${Math.abs(eaDelta)} underdog` : 'even';
            $('gcEloDeltaB').textContent = -eaDelta > 0 ? `+${-eaDelta} favored` : -eaDelta < 0 ? `${eaDelta} underdog` : 'even';
        } else {
            $('gcEloDeltaA').textContent = ''; $('gcEloDeltaB').textContent = '';
        }

        // Reset stocks/damage display
        $('gcStocksA').innerHTML = stockGlyphs(total, total);
        $('gcStocksB').innerHTML = stockGlyphs(total, total);
        $('gcDamageA').textContent = '0%'; $('gcDamageA').className = 'gc-damage-big';
        $('gcDamageB').textContent = '0%'; $('gcDamageB').className = 'gc-damage-big';
        $('gcClock').textContent = '0:00';

        // Context strip
        const ctxParts = [m.fight_type, m.stage, m.ppv, m.championship].filter(Boolean);
        $('gcContext').innerHTML = ctxParts.join('<br>');
        $('gcMatchPill').textContent =
            `Now playing: Fight #${m.fight_id} — Season ${m.season || '?'} — historical result: ${m.winner} (${describeScore(m)})`;

        // Reset stock history rendering and seed initial 50/50 win prob
        renderStockHistory();
        $('gcProbValA').textContent = `${Math.round(eloProb(ea, eb) * 100)}%`;
        $('gcProbValB').textContent = `${Math.round((1 - eloProb(ea, eb)) * 100)}%`;
    }

    async function startMatch() {
        setStartButton('Picking...', true);
        try {
            const res = await fetch('/gamecast/start', { method: 'POST' });
            const m = await res.json();
            resetMatch(m);
            // Stay disabled - re-enables on match_over event from the stream
            setStartButton('Match in progress...', true);
        } catch (err) {
            $('gcMatchPill').textContent = 'Failed to pick a match — is Kafka running?';
            setStartButton('Start a Match', false);
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        ensureChart();
        connectStream();
        $('gcStart').addEventListener('click', startMatch);
    });
})();
