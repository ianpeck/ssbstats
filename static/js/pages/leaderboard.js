let leaderboardData = [];
let currentSort = { key: "power_score", dir: "desc" };
let currentSeason = "";
let minFights = 0;

function getFiltered() {
    const q = document.getElementById("leaderboardSearch").value.toLowerCase();
    return leaderboardData.filter(f => f.name.toLowerCase().includes(q) && (f.total_fights || 0) >= minFights);
}

function applySort(data) {
    const key = currentSort.key;
    return [...data].sort((a, b) => {
        let av = a[key];
        let bv = b[key];
        if (key === "power_score") {
            av = parseFloat(String(av).replace("%", "")) || 0;
            bv = parseFloat(String(bv).replace("%", "")) || 0;
        } else {
            av = parseFloat(av) || 0;
            bv = parseFloat(bv) || 0;
        }
        return currentSort.dir === "desc" ? bv - av : av - bv;
    });
}

function refreshLeaderboardPage() {
    renderLeaderboard(applySort(getFiltered()));
    updateLeaderboardURL();
}

function updateLeaderboardURL() {
    const params = new URLSearchParams();
    if (currentSeason) params.set("season", currentSeason);
    if (minFights) params.set("min_fights", minFights);
    const search = document.getElementById("leaderboardSearch").value.trim();
    if (search) params.set("search", search);
    if (currentSort.key !== "power_score") params.set("sort", currentSort.key);
    if (currentSort.dir !== "desc") params.set("dir", currentSort.dir);
    const qs = params.toString();
    history.replaceState(null, "", "/leaderboard" + (qs ? "?" + qs : ""));
}

function loadRankings(season) {
    currentSeason = season;
    const url = season ? `/api/leaderboard?season=${season}` : "/api/leaderboard";
    document.getElementById("rankingsSubtitle").textContent = season ? `Season ${season} rankings` : "All-time rankings";
    document.getElementById("loadingOverlay").style.display = "flex";
    document.getElementById("leaderboardWrapper").style.display = "none";

    fetch(url)
        .then(res => res.json())
        .then(data => {
            document.getElementById("loadingOverlay").style.display = "none";
            document.getElementById("leaderboardWrapper").style.display = "block";
            leaderboardData = data;
            updateEloHeaders();
            if (!window._lbSortRestored) {
                window._lbSortRestored = true;
            } else {
                currentSort = { key: "power_score", dir: "desc" };
            }
            document.querySelectorAll(".sortable").forEach(s => s.classList.remove("active", "asc"));
            const activeTh = document.querySelector(`.sortable[data-sort="${currentSort.key}"]`);
            if (activeTh) {
                activeTh.classList.add("active");
                if (currentSort.dir === "asc") activeTh.classList.add("asc");
            }
            refreshLeaderboardPage();
        })
        .catch(() => {
            document.getElementById("loadingOverlay").innerHTML = "<p>Error loading rankings</p>";
        });
}

function updateEloHeaders() {
    const isSeason = !!currentSeason;
    const th1 = document.getElementById("eloCol1Th");
    const th2 = document.getElementById("eloCol2Th");
    const th3 = document.getElementById("eloCol3Th");
    if (isSeason) {
        th1.textContent = "Peak Season ELO";
        th1.dataset.sort = "peak_season_elo";
        th2.textContent = "Season Avg ELO";
        th3.textContent = "End of Season ELO";
        th3.dataset.sort = "season_end_elo";
    } else {
        th1.textContent = "Current ELO";
        th1.dataset.sort = "current_elo";
        th2.textContent = "Career ELO";
        th3.textContent = "Peak ELO";
        th3.dataset.sort = "peak_elo";
    }
}

function renderLeaderboard(data) {
    const tbody = document.getElementById("leaderboardTbody");
    tbody.innerHTML = "";
    const fragment = document.createDocumentFragment();
    const isSeason = !!currentSeason;
    const eloKey1 = isSeason ? "peak_season_elo" : "current_elo";
    const eloKey3 = isSeason ? "season_end_elo" : "peak_elo";

    data.forEach((fighter, i) => {
        const pct = parseFloat(String(fighter.win_pct).replace("%", "")) || 0;
        const pctClass = pct >= 60 ? "pct-high" : pct < 40 ? "pct-low" : "pct-mid";
        const rankClass = i < 3 ? `rank-${i + 1}` : "";
        const filename = fighterToFilename(fighter.name);
        const titleBadges = (fighter.titles || []).map(t => `<span class="lb-champ-tag">👑 ${t}</span>`).join("");
        const awardBadges = isSeason ? (fighter.season_awards || []).map(a => `<span class="lb-award-tag">🏅 ${a}</span>`).join("") : "";
        const fmtElo = v => (v != null ? v.toFixed(1) : "--");
        const eloClass = v => (v == null ? "" : v >= 1600 ? "pct-high" : v < 1400 ? "pct-low" : "");
        const ps = fighter.power_score;
        const psClass = getPowerScoreClass(ps);
        const extraCells = `
            <td class="stat-cell">${fighter.total_fights ?? ""}</td>
            <td class="stat-cell">${fighter.major_months ?? 0}</td>
            <td class="stat-cell">${fighter.champ_months ?? 0}</td>
            <td class="stat-cell">${fighter.event_count != null ? fighter.event_count + "/6" : ""}</td>
            <td class="stat-cell">${fighter.unique_titles ?? 0}</td>
            <td class="stat-cell ${eloClass(fighter[eloKey1])}">${fmtElo(fighter[eloKey1])}</td>
            <td class="stat-cell ${eloClass(fighter.avg_elo)}">${fmtElo(fighter.avg_elo)}</td>
            <td class="stat-cell ${eloClass(fighter[eloKey3])}">${fmtElo(fighter[eloKey3])}</td>
        `;
        const row = document.createElement("tr");
        row.innerHTML = `
            <td class="rank-cell ${rankClass}">${i + 1}</td>
            <td class="fighter-cell">
                <img src="/static/assets/fighters/${filename}.png" alt="${fighter.name}"
                     class="leaderboard-portrait" onerror="this.style.display='none'">
                <div class="fighter-cell-inner">
                    <a href="/fighter/${encodeURIComponent(fighter.name)}" class="fighter-link">${fighter.name}</a>
                    ${titleBadges}${awardBadges}
                </div>
            </td>
            <td class="stat-cell power-col ${psClass}">${ps != null ? `<span class="ps-dot"></span>${ps.toFixed(1)}` : "--"}</td>
            <td class="stat-cell">${fighter.wins}</td>
            <td class="stat-cell">${fighter.losses}</td>
            <td class="stat-cell ${pctClass}">${fighter.win_pct}</td>
            ${extraCells}
        `;
        fragment.appendChild(row);
    });

    tbody.appendChild(fragment);
}

document.addEventListener("DOMContentLoaded", () => {
    fetch("/api/seasons")
        .then(r => r.json())
        .then(seasons => {
            const pillsEl = document.getElementById("seasonPills");
            seasons.forEach(s => {
                const btn = document.createElement("button");
                btn.className = "season-pill";
                btn.dataset.season = s;
                btn.textContent = `S${s}`;
                pillsEl.appendChild(btn);
            });
            pillsEl.querySelectorAll(".season-pill").forEach(pill => {
                pill.addEventListener("click", function() {
                    pillsEl.querySelectorAll(".season-pill").forEach(p => p.classList.remove("active"));
                    this.classList.add("active");
                    loadRankings(this.dataset.season);
                });
                if (window._pendingLBSeason && pill.dataset.season === window._pendingLBSeason) {
                    pill.classList.add("active");
                }
            });
            delete window._pendingLBSeason;
        });

    const urlParams = new URLSearchParams(window.location.search);
    const urlSeason = urlParams.get("season") || "";
    const urlMinFights = parseInt(urlParams.get("min_fights")) || 0;
    const urlSearch = urlParams.get("search") || "";
    const urlSort = urlParams.get("sort") || "power_score";
    const urlDir = urlParams.get("dir") || "desc";

    if (urlMinFights) {
        minFights = urlMinFights;
        document.querySelectorAll(".lb-min-pill").forEach(button => {
            button.classList.toggle("active", (parseInt(button.dataset.min) || 0) === urlMinFights);
        });
    }
    if (urlSearch) document.getElementById("leaderboardSearch").value = urlSearch;
    currentSort = { key: urlSort, dir: urlDir };
    if (urlSeason) {
        window._pendingLBSeason = urlSeason;
    }
    loadRankings(urlSeason);

    document.getElementById("leaderboardSearch").addEventListener("input", refreshLeaderboardPage);
    document.querySelectorAll(".lb-min-pill").forEach(btn => {
        btn.addEventListener("click", function() {
            document.querySelectorAll(".lb-min-pill").forEach(b => b.classList.remove("active"));
            this.classList.add("active");
            minFights = parseInt(this.dataset.min) || 0;
            refreshLeaderboardPage();
        });
    });
    document.querySelectorAll(".sortable").forEach(th => {
        th.addEventListener("click", function() {
            const key = this.dataset.sort;
            currentSort.dir = currentSort.key === key && currentSort.dir === "desc" ? "asc" : "desc";
            currentSort.key = key;
            document.querySelectorAll(".sortable").forEach(s => s.classList.remove("active", "asc"));
            this.classList.add("active");
            if (currentSort.dir === "asc") this.classList.add("asc");
            refreshLeaderboardPage();
        });
    });
});
