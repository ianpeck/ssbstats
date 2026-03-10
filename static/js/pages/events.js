let allEvents = [];
let activeSeason = "";

function renderEventCards(events) {
    const container = document.getElementById("seasonGroups");
    container.innerHTML = "";

    const bySeason = {};
    const seasonOrder = [];
    events.forEach(event => {
        const season = event.Season;
        if (!bySeason[season]) {
            bySeason[season] = [];
            seasonOrder.push(season);
        }
        bySeason[season].push(event);
    });

    seasonOrder.forEach(season => {
        const group = document.createElement("div");
        group.className = "event-season-group";

        const heading = document.createElement("h2");
        heading.className = "event-season-heading";
        heading.textContent = `Season ${season}`;
        group.appendChild(heading);

        const grid = document.createElement("div");
        grid.className = "event-grid";

        bySeason[season].forEach(event => {
            const card = document.createElement("div");
            card.className = "event-card glass-card";
            const stageFile = event.Location_Name ? stageToFilename(event.Location_Name) : "";
            const imgHTML = stageFile
                ? `<div class="event-card-stage-wrap"><img src="/static/assets/stages/${stageFile}.png" alt="${event.Location_Name}" class="event-card-stage" onerror="this.parentElement.style.display='none'"></div>`
                : "";
            card.innerHTML = `
                ${imgHTML}
                <div class="event-card-body">
                    <div class="event-card-name">${event.PPV_Name}</div>
                    <div class="event-card-meta">Season ${event.Season} &bull; Month ${event.Month}${event.Location_Name ? ` &bull; ${event.Location_Name}` : ""}</div>
                    <div class="event-card-stats">
                        <span class="event-stat">${event.fight_count} fight${event.fight_count != 1 ? "s" : ""}</span>
                        ${parseInt(event.title_fights) > 0 ? `<span class="event-stat event-stat-title">👑 ${event.title_fights} title match${event.title_fights != 1 ? "es" : ""}</span>` : ""}
                    </div>
                    <div class="event-card-action">View Card &rsaquo;</div>
                </div>
            `;
            card.addEventListener("click", () => openEvent(event));
            grid.appendChild(card);
        });

        group.appendChild(grid);
        container.appendChild(group);
    });
}

function openEvent(ev) {
    document.getElementById("overlayTitle").textContent = ev.PPV_Name;
    document.getElementById("overlayMeta").textContent = `Season ${ev.Season} · Month ${ev.Month}`;
    document.getElementById("overlayFights").innerHTML = "";
    document.getElementById("overlayLoading").style.display = "flex";
    document.getElementById("eventOverlay").style.display = "flex";
    document.body.style.overflow = "hidden";

    fetch(`/api/fights?ppv=${encodeURIComponent(ev.PPV_Name)}&season=${ev.Season}&page=1`)
        .then(r => r.json())
        .then(fights => {
            document.getElementById("overlayLoading").style.display = "none";
            const list = document.getElementById("overlayFights");
            if (!Array.isArray(fights) || !fights.length) {
                list.innerHTML = '<div class="fight-empty">No fights found.</div>';
                return;
            }
            fights.forEach(fight => list.appendChild(renderFight(fight)));
        })
        .catch(() => {
            document.getElementById("overlayLoading").style.display = "none";
            document.getElementById("overlayFights").innerHTML = '<div class="fight-empty">Error loading fights.</div>';
        });
}

function closeOverlay(e) {
    if (e && e.target !== document.getElementById("eventOverlay")) return;
    document.getElementById("eventOverlay").style.display = "none";
    document.body.style.overflow = "";
}

document.addEventListener("DOMContentLoaded", () => {
    fetch("/api/events")
        .then(r => r.json())
        .then(data => {
            document.getElementById("loadingOverlay").style.display = "none";
            document.getElementById("eventsContent").style.display = "block";
            allEvents = data;

            const seasons = [...new Set(data.map(event => event.Season))].sort((a, b) => a - b);
            const pillsEl = document.getElementById("seasonPills");
            seasons.forEach(season => {
                const btn = document.createElement("button");
                btn.className = "season-pill";
                btn.dataset.season = season;
                btn.textContent = `S${season}`;
                pillsEl.appendChild(btn);
            });
            pillsEl.querySelectorAll(".season-pill").forEach(pill => {
                pill.addEventListener("click", function() {
                    pillsEl.querySelectorAll(".season-pill").forEach(p => p.classList.remove("active"));
                    this.classList.add("active");
                    activeSeason = this.dataset.season;
                    const filtered = activeSeason ? allEvents.filter(event => String(event.Season) === activeSeason) : allEvents;
                    renderEventCards(filtered);
                });
            });

            renderEventCards(data);
        })
        .catch(() => {
            document.getElementById("loadingOverlay").innerHTML = "<p>Error loading events.</p>";
        });

    document.addEventListener("keydown", event => {
        if (event.key === "Escape") closeOverlay();
    });
    window.closeOverlay = closeOverlay;
});
