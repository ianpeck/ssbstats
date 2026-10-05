// Fight page: the rest of the night's card, with this fight highlighted.

document.addEventListener('DOMContentLoaded', () => {
    const list = document.getElementById('fdCard');
    const card = (window.SSBStats && window.SSBStats.fightCard) || [];
    const current = window.SSBStats && window.SSBStats.fightId;
    if (!list) return;
    card.forEach(fight => {
        const row = appendFight(list, fight, { hideEvent: true });
        if (fight.fight_id === current) {
            row.classList.add('is-current');
            return;
        }
        row.classList.add('clickable-row');
        row.addEventListener('click', e => { if (!e.target.closest('a')) window.location.href = `/fight/${fight.fight_id}`; });
    });
});
