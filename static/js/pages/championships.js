// Championships: fullscreen belt viewer (overview and title pages), plus the title page's
// section bar and title-fight archive.

const $ = id => document.getElementById(id);

// ── Fullscreen belt viewer ─────────────────────────────────────
function initBeltViewer() {
    const viewer = $('beltViewer');
    if (!viewer) return;
    const image = $('beltViewerImage');
    let lastTrigger = null;

    const open = trigger => {
        lastTrigger = trigger;
        const belt = trigger.dataset.belt;
        // Show the web-sized copy instantly, then swap in the full-resolution original.
        image.src = assetVariant('belts', belt, 'md');
        const full = new Image();
        full.onload = () => { if (lastTrigger === trigger) image.src = full.src; };
        full.src = `/static/assets/belts/${belt}.png`;
        image.alt = `${trigger.dataset.title} belt`;
        $('beltViewerTitle').textContent = trigger.dataset.title;
        $('beltViewerMeta').textContent = trigger.dataset.meta || '';
        const link = $('beltViewerLink');
        link.hidden = !trigger.dataset.href;
        if (trigger.dataset.href) link.href = trigger.dataset.href;
        viewer.hidden = false;
        document.body.classList.add('belt-viewer-open');
        $('beltViewerClose').focus();
    };
    const close = () => {
        viewer.hidden = true;
        document.body.classList.remove('belt-viewer-open');
        if (lastTrigger) lastTrigger.focus();
    };

    document.querySelectorAll('.belt-zoom').forEach(btn => btn.addEventListener('click', () => open(btn)));
    $('beltViewerClose').addEventListener('click', close);
    viewer.addEventListener('click', e => { if (e.target === viewer) close(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && !viewer.hidden) close(); });
}

// ── Title page: section bar ────────────────────────────────────
function initSectionNav() {
    const pills = document.querySelectorAll('#champPageNav .page-nav-pill');
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

// ── Title page: title fights, 20 at a time ─────────────────────
function initTitleFights() {
    const list = $('titleFights');
    const fights = (window.SSBStats && window.SSBStats.titleFights) || [];
    if (!list) return;
    if (!fights.length) {
        list.innerHTML = '<div class="fight-empty">No title fights recorded yet.</div>';
        return;
    }
    const PAGE = 20;
    let shown = 0;
    const btn = $('moreFightsBtn');
    const more = () => {
        fights.slice(shown, shown + PAGE).forEach(fight => {
            const row = appendFight(list, fight);
            row.classList.add('clickable-row');
            row.addEventListener('click', e => { if (!e.target.closest('a')) window.location.href = `/fight/${fight.fight_id}`; });
        });
        shown = Math.min(fights.length, shown + PAGE);
        btn.hidden = shown >= fights.length;
        btn.textContent = `Show more (${fights.length - shown} left)`;
    };
    btn.addEventListener('click', more);
    more();
}

document.addEventListener('DOMContentLoaded', () => {
    initBeltViewer();
    initSectionNav();
    initTitleFights();
});
