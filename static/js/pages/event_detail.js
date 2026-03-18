const EVENT_DETAIL = window.SSBStats?.eventDetail || {};

document.addEventListener("DOMContentLoaded", () => {
    const fights = Array.isArray(EVENT_DETAIL.fights) ? EVENT_DETAIL.fights : [];
    const container = document.getElementById("eventDetailFights");
    if (!container) return;
    if (!fights.length) {
        container.innerHTML = '<div class="fight-empty">No fights found.</div>';
        return;
    }
    fights.forEach(fight => container.appendChild(renderFight(fight)));
});
