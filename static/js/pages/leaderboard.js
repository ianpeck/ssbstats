// Power Rankings: season switcher, top-three podium, and a sortable list that keeps
// each fighter's real power rank (with movement since the previous season).

let leaderboardData = [];
let previousRanks = null;            // lowercase name -> power rank last season (season view only)
let currentSort = { key: "power_score", dir: "desc" };
let currentSeason = "";
let minFights = 0;
let showMore = false;

const $ = id => document.getElementById(id);

const ELO_KEYS = {
    all:    { main: ["current_elo", "Elo"],     avg: ["avg_elo", "Avg Elo"],    peak: ["peak_elo", "Peak Elo"] },
    season: { main: ["season_end_elo", "End Elo"], avg: ["avg_elo", "Avg Elo"], peak: ["peak_season_elo", "Peak Elo"] },
};

function numeric(fighter, key) {
    if (key === "win_pct") return parseFloat(String(fighter.win_pct).replace("%", "")) || 0;
    return parseFloat(fighter[key]) || 0;
}

function getFiltered() {
    const q = $("leaderboardSearch").value.trim().toLowerCase();
    return leaderboardData.filter(f => f.name.toLowerCase().includes(q) && (f.total_fights || 0) >= minFights);
}

function applySort(rows) {
    const { key, dir } = currentSort;
    const sign = dir === "desc" ? -1 : 1;
    return [...rows].sort((a, b) => sign * (numeric(a, key) - numeric(b, key)) || (a.power_rank || 999) - (b.power_rank || 999));
}

function refreshLeaderboardPage() {
    const rows = applySort(getFiltered());
    renderTable(rows);
    $("lbEmpty").hidden = rows.length > 0;
    updateLeaderboardURL();
}

function updateLeaderboardURL() {
    const params = new URLSearchParams();
    if (currentSeason) params.set("season", currentSeason);
    if (minFights) params.set("min_fights", minFights);
    const search = $("leaderboardSearch").value.trim();
    if (search) params.set("search", search);
    if (currentSort.key !== "power_score") params.set("sort", currentSort.key);
    if (currentSort.dir !== "desc") params.set("dir", currentSort.dir);
    if (showMore) params.set("more", "1");
    const qs = params.toString();
    history.replaceState(null, "", "/leaderboard" + (qs ? "?" + qs : ""));
}

function fetchJSON(url) {
    return fetch(url).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
}

function loadRankings(season, { keepSort = false } = {}) {
    currentSeason = season;
    $("rankingsKicker").textContent = season ? `Season ${season}` : "All-time";
    const recap = $("seasonRecapLink");
    recap.hidden = !season;
    recap.href = `/seasons?season=${season}`;
    recap.querySelector("span").textContent = `Season ${season} recap`;
    $("loadingOverlay").style.display = "flex";
    $("leaderboardWrapper").hidden = true;

    const previous = season && +season > 1 ? fetchJSON(`/api/leaderboard?season=${+season - 1}`).catch(() => null) : Promise.resolve(null);
    Promise.all([fetchJSON(season ? `/api/leaderboard?season=${season}` : "/api/leaderboard"), previous])
        .then(([data, prev]) => {
            leaderboardData = data;
            previousRanks = prev ? new Map(prev.map(f => [f.name.toLowerCase(), f.power_rank])) : null;
            if (!keepSort) currentSort = { key: "power_score", dir: "desc" };
            setEloHeaders();
            markSortHeader();
            renderPodium();
            refreshLeaderboardPage();
            $("loadingOverlay").style.display = "none";
            $("leaderboardWrapper").hidden = false;
        })
        .catch(() => {
            $("loadingOverlay").innerHTML = "<p>Couldn't load the rankings. Refresh to try again.</p>";
        });
}

function eloKeys() { return currentSeason ? ELO_KEYS.season : ELO_KEYS.all; }

function setEloHeaders() {
    const keys = eloKeys();
    [["eloMainTh", keys.main], ["eloAvgTh", keys.avg], ["eloPeakTh", keys.peak]].forEach(([id, [key, label]]) => {
        const th = $(id);
        // keep an active Elo sort pointing at the matching column when switching views
        if (th.dataset.sort === currentSort.key) currentSort.key = key;
        th.dataset.sort = key;
        th.textContent = label;
    });
}

function markSortHeader() {
    document.querySelectorAll(".lb-table .sortable").forEach(th => {
        const on = th.dataset.sort === currentSort.key;
        th.classList.toggle("active", on);
        th.classList.toggle("asc", on && currentSort.dir === "asc");
        th.setAttribute("aria-sort", on ? (currentSort.dir === "asc" ? "ascending" : "descending") : "none");
    });
}

// ── Pieces ─────────────────────────────────────────────────────
function titleChips(fighter) {
    const belts = (fighter.titles || []).map(t => {
        const belt = championshipToBeltAsset(t, 'sm');
        return `<span class="lb-belt" title="Current ${escapeHTML(t)} Champion">${belt ? `<img src="${belt}" alt="" onerror="this.remove()">` : ""}${escapeHTML(t)}</span>`;
    });
    const awards = currentSeason ? (fighter.season_awards || []).map(a => `<span class="lb-award">${escapeHTML(a)}</span>`) : [];
    return belts.concat(awards).join("");
}

function movement(fighter) {
    if (!previousRanks) return "";
    const before = previousRanks.get(fighter.name.toLowerCase());
    if (!before) return `<span class="lb-move is-new" title="Didn't fight last season">New</span>`;
    const change = before - fighter.power_rank;
    if (!change) return `<span class="lb-move is-same" title="Same rank as last season">–</span>`;
    return change > 0
        ? `<span class="lb-move is-up" title="Up ${change} from #${before} last season">▲${change}</span>`
        : `<span class="lb-move is-down" title="Down ${-change} from #${before} last season">▼${-change}</span>`;
}

function powerCell(score) {
    if (score == null) return '<span class="lb-muted">—</span>';
    return `<div class="lb-power ${getPowerScoreClass(score)}">
        <span class="lb-power-num">${score.toFixed(1)}</span>
        <span class="lb-power-track"><span class="lb-power-fill" style="width:${Math.max(2, Math.min(100, score))}%"></span></span>
    </div>`;
}

function renderPodium() {
    const top = [...leaderboardData].filter(f => f.power_rank).sort((a, b) => a.power_rank - b.power_rank).slice(0, 3);
    const order = [top[1], top[0], top[2]].filter(Boolean);   // 2nd, 1st, 3rd
    $("lbPodium").innerHTML = order.map(f => {
        const pct = parseFloat(String(f.win_pct).replace("%", "")) || 0;
        return `<a class="lb-podium-card is-rank-${f.power_rank}" href="/fighter/${encodeURIComponent(f.name)}">
            <span class="lb-podium-rank">${f.power_rank}</span>
            <img class="lb-podium-portrait" src="${fighterImg(f.name, 'md')}" alt="">
            <span class="lb-podium-name">${escapeHTML(f.name)}</span>
            <span class="lb-podium-score ${getPowerScoreClass(f.power_score)}">${f.power_score != null ? f.power_score.toFixed(1) : "—"}</span>
            <span class="lb-podium-meta">${f.wins}–${f.losses} · <span class="${getBandClass(pct, WIN_PCT_BANDS)}">${escapeHTML(f.win_pct)}</span>${movement(f) ? " · " + movement(f) : ""}</span>
            ${titleChips(f) ? `<span class="lb-podium-titles">${titleChips(f)}</span>` : ""}
        </a>`;
    }).join("");
}

function renderTable(rows) {
    const keys = eloKeys();
    const fmtElo = v => (v != null ? Math.round(v) : "—");
    const eloCell = v => `<td class="lb-num lb-col-elo ${getBandClass(v, ELO_BANDS)}">${fmtElo(v)}</td>`;
    const extraElo = v => `<td class="lb-num lb-extra ${getBandClass(v, ELO_BANDS)}">${fmtElo(v)}</td>`;

    $("leaderboardTbody").innerHTML = rows.map(f => {
        const pct = parseFloat(String(f.win_pct).replace("%", "")) || 0;
        const rank = f.power_rank || "—";
        return `<tr data-name="${escapeHTML(f.name)}" class="${f.power_rank && f.power_rank <= 3 ? "is-top" : ""}">
            <td class="lb-col-rank"><span class="lb-rank">${rank}</span>${movement(f)}</td>
            <td class="lb-col-fighter">
                <a class="lb-fighter" href="/fighter/${encodeURIComponent(f.name)}">
                    <img src="${fighterImg(f.name)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">
                    <span class="lb-fighter-text">
                        <span class="lb-fighter-name">${escapeHTML(f.name)}</span>
                        ${titleChips(f) ? `<span class="lb-fighter-titles">${titleChips(f)}</span>` : ""}
                    </span>
                </a>
            </td>
            <td class="lb-col-power">${powerCell(f.power_score)}</td>
            <td class="lb-num lb-record">${f.wins}<span class="lb-dash">–</span>${f.losses}</td>
            <td class="lb-num lb-col-pct ${getBandClass(pct, WIN_PCT_BANDS)}">${escapeHTML(f.win_pct)}</td>
            ${eloCell(f[keys.main[0]])}
            <td class="lb-num lb-extra">${f.total_fights ?? "—"}</td>
            <td class="lb-num lb-extra">${f.major_months ?? 0}</td>
            <td class="lb-num lb-extra">${f.champ_months ?? 0}</td>
            <td class="lb-num lb-extra">${f.event_count != null ? `${f.event_count}<span class="lb-muted">/6</span>` : "—"}</td>
            <td class="lb-num lb-extra">${f.unique_titles ?? 0}</td>
            ${extraElo(f[keys.avg[0]])}
            ${extraElo(f[keys.peak[0]])}
        </tr>`;
    }).join("");
}

function setShowMore(on) {
    showMore = on;
    $("lbTableWrap").classList.toggle("show-more", on);
    $("moreStatsBtn").setAttribute("aria-pressed", String(on));
    $("moreStatsBtn").querySelector("span").textContent = on ? "Fewer stats" : "More stats";
}

// ── Setup ──────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    const params = new URLSearchParams(window.location.search);
    const urlSeason = params.get("season") || "";
    minFights = parseInt(params.get("min_fights")) || 0;
    document.querySelectorAll(".lb-min-pill").forEach(b => b.classList.toggle("active", (parseInt(b.dataset.min) || 0) === minFights));
    $("leaderboardSearch").value = params.get("search") || "";
    currentSort = { key: params.get("sort") || "power_score", dir: params.get("dir") === "asc" ? "asc" : "desc" };
    setShowMore(params.get("more") === "1");

    fetchJSON("/api/seasons").then(seasons => {
        const pills = $("seasonPills");
        seasons.forEach(s => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "season-pill";
            btn.dataset.season = s;
            btn.textContent = `S${s}`;
            pills.appendChild(btn);
        });
        pills.querySelectorAll(".season-pill").forEach(pill => {
            pill.classList.toggle("active", pill.dataset.season === urlSeason);
            pill.addEventListener("click", () => {
                pills.querySelectorAll(".season-pill").forEach(p => p.classList.toggle("active", p === pill));
                loadRankings(pill.dataset.season);
            });
        });
    }).catch(() => {});

    loadRankings(urlSeason, { keepSort: true });

    $("leaderboardSearch").addEventListener("input", refreshLeaderboardPage);
    document.querySelectorAll(".lb-min-pill").forEach(btn => btn.addEventListener("click", () => {
        document.querySelectorAll(".lb-min-pill").forEach(b => b.classList.toggle("active", b === btn));
        minFights = parseInt(btn.dataset.min) || 0;
        refreshLeaderboardPage();
    }));
    $("moreStatsBtn").addEventListener("click", () => { setShowMore(!showMore); updateLeaderboardURL(); });
    document.querySelectorAll(".lb-table .sortable").forEach(th => th.addEventListener("click", () => {
        const key = th.dataset.sort;
        // rank sorts best-first ascending; everything else starts high-to-low
        const firstDir = key === "power_rank" ? "asc" : "desc";
        currentSort = currentSort.key === key
            ? { key, dir: currentSort.dir === "desc" ? "asc" : "desc" }
            : { key, dir: firstDir };
        markSortHeader();
        refreshLeaderboardPage();
    }));
    $("leaderboardTbody").addEventListener("click", e => {
        const row = e.target.closest("tr[data-name]");
        if (row && !e.target.closest("a")) window.location.href = `/fighter/${encodeURIComponent(row.dataset.name)}`;
    });
});
