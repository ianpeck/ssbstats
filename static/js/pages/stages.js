// Stages page: search, debut-game filter and sort over the stage cards.

document.addEventListener('DOMContentLoaded', () => {
    const grid = document.getElementById('stageGrid');
    if (!grid) return;
    const cards = [...grid.querySelectorAll('.stage-card')];
    const search = document.getElementById('stageSearch');
    const empty = document.getElementById('stageEmpty');
    const filterBtns = document.querySelectorAll('#stageFilters button');
    const sortBtns = document.querySelectorAll('#stageSort button');
    let origin = '';
    let sort = 'fights';

    const comparators = {
        fights: (a, b) => a.dataset.order - b.dataset.order,
        titles: (a, b) => b.dataset.titles - a.dataset.titles || a.dataset.order - b.dataset.order,
        name: (a, b) => a.querySelector('.stage-card-name').textContent.localeCompare(b.querySelector('.stage-card-name').textContent),
    };

    const apply = () => {
        const q = search.value.trim().toLowerCase();
        let shown = 0;
        cards.forEach(card => {
            const match = (!q || card.dataset.name.includes(q)) && (!origin || card.dataset.origin === origin);
            card.hidden = !match;
            if (match) shown++;
        });
        empty.hidden = shown > 0;
    };
    const reorder = () => [...cards].sort(comparators[sort]).forEach(card => grid.appendChild(card));

    search.addEventListener('input', apply);
    filterBtns.forEach(btn => btn.addEventListener('click', () => {
        origin = btn.dataset.origin;
        filterBtns.forEach(b => b.classList.toggle('active', b === btn));
        apply();
    }));
    sortBtns.forEach(btn => btn.addEventListener('click', () => {
        sort = btn.dataset.sort;
        sortBtns.forEach(b => b.classList.toggle('active', b === btn));
        reorder();
    }));
});
