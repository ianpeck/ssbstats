const PER_PAGE = 100;
let currentPage = 1;
let currentFilters = {};
let hasMore = true;
let loadInProgress = false;

function debounceFightLog(fn, ms) {
    let t;
    return (...args) => {
        clearTimeout(t);
        t = setTimeout(() => fn(...args), ms);
    };
}

function getFightLogFilters() {
    return {
        fighter: document.getElementById("filterFighter").value.trim(),
        decision: document.getElementById("filterDecision").value,
        season: document.getElementById("filterSeason").value,
        month: document.getElementById("filterMonth").value,
        fight_type: document.getElementById("filterFightType").value,
        location: document.getElementById("filterLocation").value,
        ppv: document.getElementById("filterPPV").value,
        championship: document.getElementById("filterChampionship").value,
        brand: document.getElementById("filterBrand").value,
    };
}

function buildFightLogQuery(page) {
    const params = new URLSearchParams();
    Object.entries(currentFilters).forEach(([k, v]) => {
        if (v) params.set(k, v);
    });
    params.set("page", page);
    return `/api/fights?${params}`;
}

function updateFightLogURL() {
    const params = new URLSearchParams();
    Object.entries(currentFilters).forEach(([k, v]) => {
        if (v) params.set(k, v);
    });
    const qs = params.toString();
    history.replaceState(null, "", "/fights" + (qs ? "?" + qs : ""));
}

function showFightLogLoading() {
    document.getElementById("loadingOverlay").style.display = "flex";
    document.getElementById("fightList").style.display = "none";
    document.getElementById("loadMoreContainer").style.display = "none";
}

function hideFightLogLoading() {
    document.getElementById("loadingOverlay").style.display = "none";
    document.getElementById("fightList").style.display = "flex";
}

function loadFights(reset = false) {
    if (loadInProgress) return;
    if (reset) {
        currentPage = 1;
        hasMore = true;
        document.getElementById("fightList").innerHTML = "";
    }
    loadInProgress = true;
    showFightLogLoading();

    fetch(buildFightLogQuery(currentPage))
        .then(r => r.json())
        .then(fights => {
            hideFightLogLoading();
            loadInProgress = false;
            const list = document.getElementById("fightList");

            if (fights.error) {
                list.innerHTML = `<div class="fight-empty">Error: ${fights.error}</div>`;
                return;
            }
            if (!Array.isArray(fights) || fights.length === 0) {
                if (reset) list.innerHTML = '<div class="fight-empty">No fights found for these filters.</div>';
                hasMore = false;
                document.getElementById("loadMoreContainer").style.display = "none";
                return;
            }

            fights.forEach(fight => list.appendChild(renderFight(fight)));
            hasMore = fights.length >= PER_PAGE;
            document.getElementById("loadMoreContainer").style.display = hasMore ? "block" : "none";
        })
        .catch(() => {
            hideFightLogLoading();
            loadInProgress = false;
            document.getElementById("fightList").innerHTML = '<div class="fight-empty">Failed to load fights. Check your connection and try again.</div>';
        });
}

document.addEventListener("DOMContentLoaded", () => {
    const dropdownIds = ["filterDecision", "filterSeason", "filterMonth", "filterFightType", "filterLocation", "filterPPV", "filterChampionship", "filterBrand"];
    dropdownIds.forEach(id => {
        document.getElementById(id).addEventListener("change", () => {
            currentFilters = getFightLogFilters();
            updateFightLogURL();
            loadFights(true);
        });
    });

    const fighterInput = document.getElementById("filterFighter");
    setupAutocomplete(fighterInput, "fighters");

    const debouncedLoad = debounceFightLog(() => {
        currentFilters = getFightLogFilters();
        updateFightLogURL();
        loadFights(true);
    }, 350);
    fighterInput.addEventListener("input", debouncedLoad);
    fighterInput.addEventListener("change", () => {
        currentFilters = getFightLogFilters();
        updateFightLogURL();
        loadFights(true);
    });

    document.getElementById("clearFilters").addEventListener("click", () => {
        dropdownIds.forEach(id => {
            document.getElementById(id).selectedIndex = 0;
        });
        fighterInput.value = "";
        currentFilters = {};
        updateFightLogURL();
        loadFights(true);
    });

    document.getElementById("loadMoreBtn").addEventListener("click", () => {
        currentPage++;
        loadFights(false);
    });

    const urlParams = new URLSearchParams(window.location.search);
    const filterMap = {
        fighter: "filterFighter",
        decision: "filterDecision",
        season: "filterSeason",
        month: "filterMonth",
        fight_type: "filterFightType",
        location: "filterLocation",
        ppv: "filterPPV",
        championship: "filterChampionship",
        brand: "filterBrand",
    };
    Object.entries(filterMap).forEach(([param, elId]) => {
        const val = urlParams.get(param);
        if (val) document.getElementById(elId).value = val;
    });
    currentFilters = getFightLogFilters();
    if (urlParams.get("fight_id")) currentFilters.fight_id = urlParams.get("fight_id");

    loadFights(true);
});
