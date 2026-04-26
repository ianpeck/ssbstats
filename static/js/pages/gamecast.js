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
    const probSeries = { labels: [], a: [], b: [] };

    // ---------------- ELO + win prob math ----------------
    function eloProb(myElo, oppElo) {
        if (myElo == null || oppElo == null) return 0.5;
        return 1 / (1 + Math.pow(10, (oppElo - myElo) / 400));
    }

    function liveStateProb(stockDiff, damageDiff) {
        // Stocks dominate hard — each stock advantage = +2.0 in logit space (~88/12
        // odds for a 1-stock lead). Damage is a small secondary signal.
        const logit = 2.0 * stockDiff + 0.004 * (-damageDiff);
        return 1 / (1 + Math.exp(-logit));
    }

    function blendWeight(stocksConsumed, totalStocksAtRisk) {
        // Start with state mattering meaningfully so a stock change swings the line.
        // 1-stock lead with even ELO → ~70%, 2-stock lead → ~80%.
        if (totalStocksAtRisk <= 0) return 0.5;
        const progress = Math.max(0, Math.min(1, stocksConsumed / totalStocksAtRisk));
        return 0.45 + progress * 0.5;
    }

    function computeWinProb(payload) {
        if (!activeMatch || !activeMatch.elo) return { a: 0.5, b: 0.5 };
        const a = payload.fighters[0], b = payload.fighters[1];
        const eloA = activeMatch.elo.a_before, eloB = activeMatch.elo.b_before;

        const elo_a = eloProb(eloA, eloB);
        const stockDiff = a.stocks - b.stocks;
        const damageDiff = a.damage - b.damage;
        const state_a = liveStateProb(stockDiff, damageDiff);

        const total = activeMatch.total_stocks * 2;
        const consumed = total - (a.stocks + b.stocks);
        const w = blendWeight(consumed, total);

        const blended = (1 - w) * elo_a + w * state_a;
        return { a: blended, b: 1 - blended };
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

    // ---------------- Chart ----------------
    function ensureChart() {
        if (chart) return chart;
        const ctx = $('gcProbChart').getContext('2d');
        chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    { label: 'A', data: [], borderColor: '#6cf', backgroundColor: 'rgba(102,204,255,0.12)',
                      fill: true, tension: 0.25, pointRadius: 0, borderWidth: 2 },
                    { label: 'B', data: [], borderColor: '#f97', backgroundColor: 'rgba(255,153,119,0.12)',
                      fill: true, tension: 0.25, pointRadius: 0, borderWidth: 2 },
                ],
            },
            options: {
                animation: false, responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { display: true, title: { display: false }, ticks: { color: 'rgba(255,255,255,0.4)' } },
                    y: { min: 0, max: 1, ticks: {
                        color: 'rgba(255,255,255,0.4)',
                        callback: (v) => `${Math.round(v * 100)}%`
                    } },
                },
            },
        });
        return chart;
    }

    function pushChartPoint(elapsedSec, pa, pb) {
        const c = ensureChart();
        // Sample every ~0.5s of match time to keep the chart smooth without bloating points
        if (probSeries.labels.length > 0) {
            const lastSec = probSeries.labels[probSeries.labels.length - 1];
            if (elapsedSec - lastSec < 0.5) return;
        }
        probSeries.labels.push(elapsedSec);
        probSeries.a.push(pa);
        probSeries.b.push(pb);
        c.data.labels = probSeries.labels.map((s) => `${s.toFixed(0)}s`);
        c.data.datasets[0].data = probSeries.a;
        c.data.datasets[1].data = probSeries.b;
        c.update('none');
    }

    function resetChart() {
        probSeries.labels.length = 0; probSeries.a.length = 0; probSeries.b.length = 0;
        if (chart) {
            chart.data.labels = []; chart.data.datasets[0].data = []; chart.data.datasets[1].data = [];
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

        // Stock-loss detection — captures the damage from PREVIOUS tick
        // since by the current tick the synthesizer may have already reset to 0.
        if (prevA && a.stocks < prevA.stocks) {
            stockHistA.push({
                stockBefore: prevA.stocks,
                damage: prevA.damage,
                sec: payload.elapsed_sec,
                timeStr: fmtClock(payload.elapsed_sec),
            });
            showStockLostBanner(a.name, prevA.damage);
            renderStockHistory();
        }
        if (prevB && b.stocks < prevB.stocks) {
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
            const btn = $('gcStart');
            btn.disabled = false;
            btn.textContent = 'Start a Match';
        }

        // Win probability — compute client-side from ELO + state
        const wp = computeWinProb(payload);
        $('gcProbValA').textContent = `${Math.round(wp.a * 100)}%`;
        $('gcProbValB').textContent = `${Math.round(wp.b * 100)}%`;
        pushChartPoint(payload.elapsed_sec, wp.a, wp.b);
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
        // win_prob from Flink is currently overridden by client-side ELO blend;
        // ignore it for now. Could re-enable as a separate "raw state" trace.
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
        const btn = $('gcStart');
        btn.disabled = true;
        btn.textContent = 'Picking…';
        try {
            const res = await fetch('/gamecast/start', { method: 'POST' });
            const m = await res.json();
            resetMatch(m);
            // Stay disabled — re-enables on match_over event from the stream
            btn.textContent = 'Match in progress…';
        } catch (err) {
            $('gcMatchPill').textContent = 'Failed to pick a match — is Kafka running?';
            btn.disabled = false;
            btn.textContent = 'Start a Match';
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        ensureChart();
        connectStream();
        $('gcStart').addEventListener('click', startMatch);
    });
})();
