let champCurrentSeason = null;
let champCurrentMonth = null;

function renderChampionshipBeltIcon(champName) {
    const beltAsset = championshipToBeltAsset(champName);
    if (!beltAsset) {
        return '<span class="champ-belt-icon champ-belt-icon-fallback" aria-hidden="true">🏆</span>';
    }
    return `
        <button
            type="button"
            class="champ-belt-icon champ-belt-icon-image-wrap champ-belt-button"
            data-belt-image="${beltAsset}"
            data-belt-name="${champName.replace(/"/g, "&quot;")}"
            aria-label="Open full-size ${champName} belt"
        >
            <img src="${beltAsset}" alt="${champName} belt" class="champ-belt-image" loading="lazy">
        </button>
    `;
}

function initBeltOverlay() {
    const overlay = document.getElementById("champBeltOverlay");
    const image = document.getElementById("champBeltOverlayImage");
    const title = document.getElementById("champBeltOverlayTitle");
    const meta = document.getElementById("champBeltOverlayMeta");
    const closeButton = document.getElementById("champBeltOverlayClose");
    if (!overlay || !image || !title || !meta || !closeButton) return;

    const closeOverlay = () => {
        overlay.style.display = "none";
        overlay.setAttribute("aria-hidden", "true");
        image.removeAttribute("src");
        image.alt = "";
    };

    document.addEventListener("click", event => {
        const trigger = event.target.closest(".champ-belt-button");
        if (!trigger) return;
        image.src = trigger.dataset.beltImage || "";
        image.alt = `${trigger.dataset.beltName || "Championship"} belt`;
        title.textContent = trigger.dataset.beltName || "Championship Belt";
        meta.textContent = "Full-size title render";
        overlay.style.display = "flex";
        overlay.setAttribute("aria-hidden", "false");
    });

    closeButton.addEventListener("click", closeOverlay);
    overlay.addEventListener("click", event => {
        if (event.target === overlay) closeOverlay();
    });
    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && overlay.style.display !== "none") {
            closeOverlay();
        }
    });
}

function splitReign(seasonWon, monthWon, seasonLost, monthLost) {
    const isCurrent = seasonLost == null;
    const endSeason = isCurrent ? champCurrentSeason : seasonLost;
    const endMonth = isCurrent ? champCurrentMonth : monthLost;

    if (endSeason == null) {
        return [{ season: seasonWon, months: 0, isCurrent: true }];
    }

    const absStart = (seasonWon - 1) * 12 + monthWon + 1;
    const absEnd = (endSeason - 1) * 12 + endMonth + 1;
    if (absEnd <= absStart) return [{ season: seasonWon, months: 0, isCurrent }];

    const subs = [];
    let pos = absStart;
    while (pos < absEnd) {
        const season = Math.ceil(pos / 12);
        const seasonEnd = season * 12;
        const months = Math.min(seasonEnd + 1, absEnd) - pos;
        subs.push({ season, months, isCurrent: false });
        pos = seasonEnd + 1;
    }
    if (subs.length > 0) subs[subs.length - 1].isCurrent = isCurrent;
    return subs;
}

function renderHistory(rows) {
    const container = document.getElementById("champHistoryContainer");
    container.innerHTML = "";
    const fighterTitlesMap = {};
    rows.forEach(row => {
        const name = row.Fighter_Name || "?";
        const champ = row.Championship_Name || "?";
        if (!fighterTitlesMap[name]) fighterTitlesMap[name] = new Set();
        fighterTitlesMap[name].add(champ);
    });

    const byChamp = {};
    const champOrder = [];
    rows.forEach(row => {
        const champ = row.Championship_Name || "?";
        if (!byChamp[champ]) {
            byChamp[champ] = [];
            champOrder.push(champ);
        }
        byChamp[champ].push(row);
    });

    renderChampionshipSummary(byChamp);

    champOrder.forEach(champName => {
        const reigns = byChamp[champName];
        const beltSummary = buildChampionshipSummary(reigns);
        const wrapper = document.createElement("div");
        wrapper.className = "champ-timeline-row champ-belt-card";

        const header = document.createElement("div");
        header.className = "champ-belt-header";
        header.innerHTML = `
            <div class="champ-belt-title-wrap">
                ${renderChampionshipBeltIcon(champName)}
                <div>
                    <div class="champ-timeline-label">${champName}</div>
                    <div class="champ-belt-subtitle">
                        ${
                            beltSummary.hasCurrent
                                ? `<button type="button" class="champ-belt-fact champ-belt-fact-button champ-current-link">
                                    <span class="champ-belt-fact-label">Current</span>
                                    <span class="champ-belt-fact-value">${beltSummary.currentChampionsLabel}</span>
                                   </button>`
                                : `<span class="champ-belt-fact">
                                    <span class="champ-belt-fact-label">Current</span>
                                    <span class="champ-belt-fact-value">${beltSummary.currentChampionsLabel}</span>
                                   </span>`
                        }
                        ${
                            beltSummary.hasLongest
                                ? `<button type="button" class="champ-belt-fact champ-belt-fact-button champ-longest-link">
                                    <span class="champ-belt-fact-label">Longest reign</span>
                                    <span class="champ-belt-fact-value">${beltSummary.longestReignLabel}</span>
                                   </button>`
                                : `<span class="champ-belt-fact">
                                    <span class="champ-belt-fact-label">Longest reign</span>
                                    <span class="champ-belt-fact-value">${beltSummary.longestReignLabel}</span>
                                   </span>`
                        }
                        <span class="champ-belt-fact">
                            <span class="champ-belt-fact-label">Most reigns</span>
                            <span class="champ-belt-fact-value">${beltSummary.mostReignsLabel}</span>
                        </span>
                    </div>
                </div>
            </div>
            <div class="champ-belt-stats">
                <span class="champ-belt-stat"><strong>${beltSummary.totalReigns}</strong> reigns</span>
                <span class="champ-belt-stat"><strong>${beltSummary.uniqueChampions}</strong> champions</span>
            </div>
        `;
        wrapper.appendChild(header);

        const bar = document.createElement("div");
        bar.className = "champ-timeline-bar";

        const groups = [];
        let i = 0;
        while (i < reigns.length) {
            const cur = reigns[i];
            const partners = [cur];
            let j = i + 1;
            while (
                j < reigns.length &&
                reigns[j].Season_Won === cur.Season_Won &&
                reigns[j].Month_Won === cur.Month_Won &&
                reigns[j].Season_Lost === cur.Season_Lost &&
                reigns[j].Month_Lost === cur.Month_Lost
            ) {
                partners.push(reigns[j]);
                j++;
            }
            groups.push({
                seasonWon: cur.Season_Won,
                monthWon: cur.Month_Won,
                seasonLost: cur.Season_Lost,
                monthLost: cur.Month_Lost,
                fighters: partners.map(p => p.Fighter_Name || "?"),
            });
            i = j;
        }

        const showLongest = !champName.toLowerCase().includes("smash bros");
        const groupTotals = groups.map(group => splitReign(group.seasonWon, group.monthWon, group.seasonLost, group.monthLost).reduce((sum, sub) => sum + sub.months, 0));
        const maxMonths = showLongest ? Math.max(...groupTotals) : -1;
        groups.forEach((group, index) => {
            group._isLongest = maxMonths > 0 && groupTotals[index] === maxMonths;
        });

        const allSegs = [];
        groups.forEach(group => {
            splitReign(group.seasonWon, group.monthWon, group.seasonLost, group.monthLost).forEach(sub => {
                allSegs.push({ season: sub.season, months: sub.months, isCurrent: sub.isCurrent, fighters: group.fighters, isLongest: group._isLongest });
            });
        });

        let lastSeason = null;
        allSegs.forEach((seg, index) => {
            const { season, months, isCurrent, fighters, isLongest } = seg;
            const isLast = index === allSegs.length - 1;
            const flexVal = months > 0 ? months : (isCurrent ? 3 : 0.4);
            const monthLabel = isCurrent ? (months > 0 ? `${months} mo. (active)` : "active") : (months > 0 ? `${months} mo.` : "<1 mo.");
            const isTag = fighters.length > 1;

            if (lastSeason !== null && season !== lastSeason) {
                const divider = document.createElement("div");
                divider.className = "champ-season-divider";
                divider.textContent = `Season ${season}`;
                bar.appendChild(divider);
            } else if (lastSeason === null) {
                const divider = document.createElement("div");
                divider.className = "champ-season-divider champ-season-divider-first";
                divider.textContent = `Season ${season}`;
                bar.appendChild(divider);
            }
            lastSeason = season;

            const segEl = document.createElement("div");
            segEl.className =
                "champ-segment" +
                (isLast ? " champ-segment-last" : "") +
                (isTag ? " champ-segment-tag" : "") +
                (isLongest ? " champ-segment-longest" : "");
            segEl.style.flex = flexVal;

            const starHTML = isLongest ? '<span class="champ-longest-star" title="Longest reign for this title">⭐</span>' : "";
            const fighterHTML = fighters.map(name => {
                const filename = fighterToFilename(name);
                const titles = fighterTitlesMap[name] ? [...fighterTitlesMap[name]].join("\n") : "";
                const tooltipText = titles ? `${name}\nTitles held:\n${titles}` : name;
                return `<span class="champ-tag-fighter" title="${tooltipText.replace(/"/g, "&quot;")}">` +
                    `<img src="/static/assets/fighters/${filename}.png" alt="${name}" class="champ-seg-portrait" onerror="this.style.display='none'">` +
                    `<a href="/fighter/${encodeURIComponent(name)}" class="champ-seg-name fighter-link">${name}</a>` +
                    `</span>`;
            }).join('<span class="champ-tag-amp">&amp;</span>');

            segEl.innerHTML = starHTML + fighterHTML + `<span class="champ-seg-months">${monthLabel}</span>`;
            bar.appendChild(segEl);
        });

        const scrollWrap = document.createElement("div");
        scrollWrap.className = "champ-scroll-wrapper";
        const scrollEl = document.createElement("div");
        scrollEl.className = "champ-scroll-container";
        scrollEl.appendChild(bar);
        scrollWrap.appendChild(scrollEl);
        wrapper.appendChild(scrollWrap);
        const focusSegment = (segment, scrollTarget = scrollEl.scrollWidth) => {
            scrollEl.scrollTo({ left: scrollTarget, behavior: "smooth" });
            if (segment) {
                segment.classList.remove("champ-segment-focus");
                void segment.offsetWidth;
                segment.classList.add("champ-segment-focus");
                window.setTimeout(() => segment.classList.remove("champ-segment-focus"), 1800);
            }
        };
        const currentLink = header.querySelector(".champ-current-link");
        if (currentLink) {
            currentLink.addEventListener("click", () => {
                const activeSeg = bar.querySelector(".champ-segment-last");
                focusSegment(activeSeg);
            });
        }
        const longestLink = header.querySelector(".champ-longest-link");
        if (longestLink) {
            longestLink.addEventListener("click", () => {
                const longestSeg = bar.querySelector(".champ-segment-longest");
                const scrollTarget = longestSeg
                    ? Math.max(0, longestSeg.offsetLeft - Math.max(24, scrollEl.clientWidth * 0.2))
                    : scrollEl.scrollLeft;
                focusSegment(longestSeg, scrollTarget);
            });
        }
        container.appendChild(wrapper);
    });

    initEdgeScroll();
}

function buildChampionshipSummary(reigns) {
    const grouped = [];
    let i = 0;
    while (i < reigns.length) {
        const cur = reigns[i];
        const partners = [cur];
        let j = i + 1;
        while (
            j < reigns.length &&
            reigns[j].Season_Won === cur.Season_Won &&
            reigns[j].Month_Won === cur.Month_Won &&
            reigns[j].Season_Lost === cur.Season_Lost &&
            reigns[j].Month_Lost === cur.Month_Lost
        ) {
            partners.push(reigns[j]);
            j++;
        }
        const fighters = partners.map(p => p.Fighter_Name || "?");
        const months = splitReign(cur.Season_Won, cur.Month_Won, cur.Season_Lost, cur.Month_Lost)
            .reduce((sum, sub) => sum + sub.months, 0);
        grouped.push({
            fighters,
            isCurrent: cur.Season_Lost == null,
            months,
        });
        i = j;
    }

    const reignCountByFighter = {};
    const uniqueChampions = new Set();
    grouped.forEach(group => {
        group.fighters.forEach(name => {
            uniqueChampions.add(name);
            reignCountByFighter[name] = (reignCountByFighter[name] || 0) + 1;
        });
    });

    let mostReignsName = "—";
    let mostReignsCount = 0;
    Object.entries(reignCountByFighter).forEach(([name, count]) => {
        if (count > mostReignsCount) {
            mostReignsCount = count;
            mostReignsName = name;
        }
    });

    const longest = grouped.reduce((best, group) => {
        if (!best || group.months > best.months) return group;
        return best;
    }, null);
    const currentGroups = grouped.filter(group => group.isCurrent);

    return {
        totalReigns: grouped.length,
        uniqueChampions: uniqueChampions.size,
        hasCurrent: currentGroups.length > 0,
        hasLongest: !!longest,
        currentChampionsLabel: currentGroups.length
            ? currentGroups.map(group => group.fighters.join(" & ")).join(", ")
            : "Vacant",
        longestReignLabel: longest
            ? `${longest.fighters.join(" & ")} (${longest.months || 0} mo.)`
            : "—",
        mostReignsLabel: mostReignsCount > 0
            ? `${mostReignsName} (${mostReignsCount})`
            : "—",
    };
}

function renderChampionshipSummary(byChamp) {
    const strip = document.getElementById("champSummaryStrip");
    if (!strip) return;
    strip.innerHTML = "";

    const allRows = Object.values(byChamp).flat();
    if (!allRows.length) return;

    let totalReigns = 0;

    Object.entries(byChamp).forEach(([champName, reigns]) => {
        const summary = buildChampionshipSummary(reigns);
        totalReigns += summary.totalReigns;
    });

    const uniqueChampions = new Set(allRows.map(row => row.Fighter_Name || "?")).size;

    const cards = [
        { label: "Titles Tracked", value: Object.keys(byChamp).length, note: "active lineages on the page" },
        { label: "Total Reigns", value: totalReigns, note: "all-time championship changes" },
        { label: "Unique Champions", value: uniqueChampions, note: "fighters who have held gold" },
    ];

    cards.forEach(card => {
        const el = document.createElement("div");
        el.className = "champ-summary-card glass-card";
        el.innerHTML = `
            <div class="champ-summary-label">${card.label}</div>
            <div class="champ-summary-value">${card.value}</div>
            <div class="champ-summary-note">${card.note}</div>
        `;
        strip.appendChild(el);
    });
}

function initEdgeScroll() {
    document.querySelectorAll(".champ-scroll-container").forEach(el => {
        const wrap = el.parentElement;
        let animFrame = null;

        function updateFades() {
            const atEnd = el.scrollLeft + el.clientWidth >= el.scrollWidth - 4;
            const hasLeft = el.scrollLeft > 4;
            wrap.classList.toggle("champ-scroll-at-end", atEnd);
            wrap.classList.toggle("champ-scroll-has-left", hasLeft);
        }

        el.addEventListener("scroll", updateFades);
        updateFades();

        function step(speed) {
            el.scrollLeft += speed;
            updateFades();
            animFrame = requestAnimationFrame(() => step(speed));
        }

        el.addEventListener("mousemove", event => {
            cancelAnimationFrame(animFrame);
            animFrame = null;

            const rect = el.getBoundingClientRect();
            const x = event.clientX - rect.left;
            const w = rect.width;
            const zone = Math.min(w * 0.15, 80);

            if (x < zone && el.scrollLeft > 0) {
                el.style.cursor = "w-resize";
                animFrame = requestAnimationFrame(() => step(-10 * (1 - x / zone)));
            } else if (x > w - zone && el.scrollLeft + el.clientWidth < el.scrollWidth - 2) {
                el.style.cursor = "e-resize";
                animFrame = requestAnimationFrame(() => step(10 * ((x - (w - zone)) / zone)));
            } else {
                el.style.cursor = "";
            }
        });

        el.addEventListener("mouseleave", () => {
            cancelAnimationFrame(animFrame);
            animFrame = null;
            el.style.cursor = "";
        });
    });
}

document.addEventListener("DOMContentLoaded", () => {
    initBeltOverlay();
    fetch("/api/championships")
        .then(r => r.json())
        .then(data => {
            champCurrentSeason = data.current_season;
            champCurrentMonth = data.current_month;
            document.getElementById("loadingOverlay").style.display = "none";
            document.getElementById("champContent").style.display = "block";
            renderHistory(data.rows);
        })
        .catch(() => {
            document.getElementById("loadingOverlay").innerHTML = "<p>Error loading championship history.</p>";
        });
});
