const PER_PAGE = 100;
let currentPage = 1;
let currentFilters = {};
let hasMore = true;
let loadInProgress = false;

function updateFightFilterCount() {
    const countEl = document.getElementById("fightFilterCount");
    if (!countEl) return;
    const count = Object.entries(currentFilters).filter(([key, value]) => {
        if (!value) return false;
        if (key === "fighter_op2" || key === "fighter_op3" || key === "fighter_op4") {
            const rowIndex = key.slice(-1);
            const fighterValue = currentFilters[`fighter${rowIndex}`];
            return !!fighterValue;
        }
        return true;
    }).length;
    countEl.textContent = String(count);
}

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
        fighter2: document.getElementById("filterFighter2").value.trim(),
        fighter3: document.getElementById("filterFighter3").value.trim(),
        fighter4: document.getElementById("filterFighter4").value.trim(),
        fighter_op2: document.getElementById("filterFighterOp2").value,
        fighter_op3: document.getElementById("filterFighterOp3").value,
        fighter_op4: document.getElementById("filterFighterOp4").value,
        decision: document.getElementById("filterDecision").value,
        contender: document.getElementById("filterContender").value,
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

function syncFighterFilterRows() {
    const rowConfigs = [
        { row: document.querySelector('.fight-fighter-row[data-row="2"]'), input: document.getElementById("filterFighter2") },
        { row: document.querySelector('.fight-fighter-row[data-row="3"]'), input: document.getElementById("filterFighter3") },
        { row: document.querySelector('.fight-fighter-row[data-row="4"]'), input: document.getElementById("filterFighter4") },
    ];
    const highestFilledRow = rowConfigs.reduce((maxRow, { row, input }) => {
        if (input.value.trim()) {
            return Math.max(maxRow, Number(row.dataset.row));
        }
        return maxRow;
    }, 1);
    const highestVisibleRow = rowConfigs.reduce((maxRow, { row }) => {
        if (!row.classList.contains("is-hidden")) {
            return Math.max(maxRow, Number(row.dataset.row));
        }
        return maxRow;
    }, 1);
    const visibleThroughRow = Math.max(highestFilledRow, highestVisibleRow);

    rowConfigs.forEach(({ row }) => {
        row.classList.toggle("is-hidden", Number(row.dataset.row) > visibleThroughRow);
    });

    const visibleCount = 1 + rowConfigs.filter(({ row }) => !row.classList.contains("is-hidden")).length;
    document.getElementById("addFighterFilter").disabled = visibleCount >= 4;
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
    const dropdownIds = ["filterDecision", "filterContender", "filterSeason", "filterMonth", "filterFighterOp2", "filterFighterOp3", "filterFighterOp4"];
    dropdownIds.forEach(id => {
        document.getElementById(id).addEventListener("change", () => {
            currentFilters = getFightLogFilters();
            updateFightFilterCount();
            updateFightLogURL();
            loadFights(true);
        });
    });

    const fighterInputs = [
        document.getElementById("filterFighter"),
        document.getElementById("filterFighter2"),
        document.getElementById("filterFighter3"),
        document.getElementById("filterFighter4"),
    ];
    fighterInputs.forEach(input => setupAutocomplete(input, "fighters"));
    const textAutocompleteInputs = [
        [document.getElementById("filterFightType"), "fight_types"],
        [document.getElementById("filterLocation"), "locations"],
        [document.getElementById("filterPPV"), "ppvs"],
        [document.getElementById("filterChampionship"), "championships"],
        [document.getElementById("filterBrand"), "brands"],
    ];
    textAutocompleteInputs.forEach(([input, category]) => setupAutocomplete(input, category));

    const debouncedLoad = debounceFightLog(() => {
        currentFilters = getFightLogFilters();
        updateFightFilterCount();
        updateFightLogURL();
        loadFights(true);
    }, 350);
    fighterInputs.forEach(input => {
        input.addEventListener("input", debouncedLoad);
        input.addEventListener("change", () => {
            syncFighterFilterRows();
            currentFilters = getFightLogFilters();
            updateFightFilterCount();
            updateFightLogURL();
            loadFights(true);
        });
    });
    fighterInputs.forEach(input => {
        input.addEventListener("input", syncFighterFilterRows);
    });
    textAutocompleteInputs.forEach(([input]) => {
        input.addEventListener("input", debouncedLoad);
        input.addEventListener("change", () => {
            currentFilters = getFightLogFilters();
            updateFightFilterCount();
            updateFightLogURL();
            loadFights(true);
        });
    });

    document.getElementById("clearFilters").addEventListener("click", () => {
        dropdownIds.forEach(id => {
            const el = document.getElementById(id);
            el.selectedIndex = 0;
        });
        fighterInputs.forEach(input => {
            input.value = "";
        });
        textAutocompleteInputs.forEach(([input]) => {
            input.value = "";
        });
        document.querySelectorAll('.fight-fighter-row[data-row="2"], .fight-fighter-row[data-row="3"], .fight-fighter-row[data-row="4"]').forEach(row => {
            row.classList.add("is-hidden");
        });
        syncFighterFilterRows();
        currentFilters = {};
        updateFightFilterCount();
        updateFightLogURL();
        loadFights(true);
    });

    document.getElementById("addFighterFilter").addEventListener("click", () => {
        const nextRow = document.querySelector(".fight-fighter-row.is-hidden");
        if (!nextRow) return;
        nextRow.classList.remove("is-hidden");
        syncFighterFilterRows();
        const input = nextRow.querySelector("input");
        if (input) input.focus();
    });

    document.querySelectorAll(".fight-remove-filter-btn").forEach(button => {
        button.addEventListener("click", () => {
            const rowNumber = button.dataset.removeRow;
            const row = document.querySelector(`.fight-fighter-row[data-row="${rowNumber}"]`);
            if (!row) return;
            const input = row.querySelector("input");
            const operator = row.querySelector("select");
            if (input) input.value = "";
            if (operator) operator.value = "or";
            row.classList.add("is-hidden");
            const downstreamRows = Array.from(document.querySelectorAll(`.fight-fighter-row[data-row]`))
                .filter(candidate => Number(candidate.dataset.row) > Number(rowNumber));
            downstreamRows.forEach(candidate => {
                const candidateInput = candidate.querySelector("input");
                if (!candidateInput || !candidateInput.value.trim()) {
                    candidate.classList.add("is-hidden");
                }
            });
            currentFilters = getFightLogFilters();
            syncFighterFilterRows();
            updateFightFilterCount();
            updateFightLogURL();
            loadFights(true);
        });
    });

    document.getElementById("loadMoreBtn").addEventListener("click", () => {
        currentPage++;
        loadFights(false);
    });

    const urlParams = new URLSearchParams(window.location.search);
    const filterMap = {
        fighter: "filterFighter",
        fighter2: "filterFighter2",
        fighter3: "filterFighter3",
        fighter4: "filterFighter4",
        fighter_op2: "filterFighterOp2",
        fighter_op3: "filterFighterOp3",
        fighter_op4: "filterFighterOp4",
        decision: "filterDecision",
        contender: "filterContender",
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
    syncFighterFilterRows();
    updateFightFilterCount();

    loadFights(true);
});
