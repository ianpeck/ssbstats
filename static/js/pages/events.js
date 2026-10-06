// Events page and event history pages: season switcher, fight-card popup, section bar
// and the fight archive.

const $ = id => document.getElementById(id);
const EVENT_FIGHTS = (window.SSBStats && window.SSBStats.eventFights) || null;
// Event pages hide the event column (it's always this event); stage pages keep it.
const FIGHT_OPTS = (window.SSBStats && window.SSBStats.fightOpts) || { hideEvent: true };

// ── Season switcher (Events page) ──────────────────────────────
function initSeasonPills() {
    const pills = document.querySelectorAll('#ppvSeasonPills .season-pill');
    pills.forEach(pill => pill.addEventListener('click', () => {
        pills.forEach(p => p.classList.toggle('active', p === pill));
        document.querySelectorAll('.ppv-season[data-season]').forEach(block => {
            block.hidden = block.dataset.season !== pill.dataset.season;
        });
    }));
}

// ── Fight card popup ───────────────────────────────────────────
function initFightCard() {
    const overlay = $('fightCardOverlay');
    if (!overlay) return;
    const list = $('fightCardFights');
    let lastTrigger = null;

    const close = () => {
        overlay.hidden = true;
        document.body.classList.remove('belt-viewer-open');
        if (lastTrigger) lastTrigger.focus();
    };
    const render = fights => {
        $('fightCardLoading').style.display = 'none';
        list.innerHTML = '';
        if (!fights.length) { list.innerHTML = '<div class="fight-empty">No fights found.</div>'; return; }
        fights.forEach(fight => {
            const row = appendFight(list, fight, { hideEvent: true });
            row.classList.add('clickable-row');
            row.addEventListener('click', e => { if (!e.target.closest('a')) window.location.href = `/fight/${fight.fight_id}`; });
        });
    };

    document.querySelectorAll('.ppv-view-card').forEach(btn => btn.addEventListener('click', () => {
        lastTrigger = btn;
        const { ppv, season, month } = btn.dataset;
        $('fightCardTitle').textContent = ppv;
        $('fightCardMeta').textContent = `Season ${season} · Month ${month}`;
        $('fightCardLogo').src = assetVariant('ppv', stageToFilename(ppv), 'sm');
        list.innerHTML = '';
        $('fightCardLoading').style.display = 'flex';
        overlay.hidden = false;
        document.body.classList.add('belt-viewer-open');
        $('fightCardClose').focus();

        // Event pages already have every fight; the Events page asks the server for one night.
        if (EVENT_FIGHTS) {
            render(EVENT_FIGHTS.filter(f => String(f.season) === season && String(f.month) === month));
            return;
        }
        fetch(`/api/fights?${new URLSearchParams({ ppv, season, month, page: 1 })}`)
            .then(r => r.json())
            .then(fights => render(Array.isArray(fights) ? fights : []))
            .catch(() => { $('fightCardLoading').style.display = 'none'; list.innerHTML = '<div class="fight-empty">Couldn\'t load the fight card.</div>'; });
    }));
    $('fightCardClose').addEventListener('click', close);
    overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && !overlay.hidden) close(); });
}

// ── Section bar ────────────────────────────────────────────────
function initSectionNav() {
    const pills = document.querySelectorAll('#eventsPageNav .page-nav-pill');
    if (!pills.length) return;
    const jump = id => {
        const el = $(id);
        if (el) window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - (64 + 56), behavior: 'smooth' });
    };
    pills.forEach(p => p.addEventListener('click', e => { e.preventDefault(); jump(p.dataset.section); }));
    const spy = new IntersectionObserver(entries => entries.forEach(entry => {
        if (entry.isIntersecting) pills.forEach(p => p.classList.toggle('active', p.dataset.section === entry.target.id));
    }), { rootMargin: '-15% 0px -70% 0px' });
    pills.forEach(p => spy.observe($(p.dataset.section)));
}

// ── Event and stage pages: every fight, 20 at a time ──────────────────────
function initFightArchive() {
    const list = $('eventFights');
    if (!list || !EVENT_FIGHTS) return;
    if (!EVENT_FIGHTS.length) { list.innerHTML = '<div class="fight-empty">No fights found.</div>'; return; }
    const PAGE = 20;
    let shown = 0;
    const btn = $('moreFightsBtn');
    const more = () => {
        EVENT_FIGHTS.slice(shown, shown + PAGE).forEach(fight => {
            const row = appendFight(list, fight, FIGHT_OPTS);
            row.classList.add('clickable-row');
            row.addEventListener('click', e => { if (!e.target.closest('a')) window.location.href = `/fight/${fight.fight_id}`; });
        });
        shown = Math.min(EVENT_FIGHTS.length, shown + PAGE);
        btn.hidden = shown >= EVENT_FIGHTS.length;
        btn.textContent = `Show more (${EVENT_FIGHTS.length - shown} left)`;
    };
    btn.addEventListener('click', more);
    more();
}

document.addEventListener('DOMContentLoaded', () => {
    initSeasonPills();
    initFightCard();
    initSectionNav();
    initFightArchive();
});
