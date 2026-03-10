document.addEventListener("DOMContentLoaded", () => {
    const searchInput = document.getElementById("rosterSearch");
    const cards = document.querySelectorAll(".fighter-card");

    searchInput.addEventListener("input", function() {
        const query = this.value.toLowerCase();
        cards.forEach(card => {
            const name = card.dataset.name;
            card.style.display = name.includes(query) ? "" : "none";
        });
    });

    cards.forEach((card, i) => {
        card.style.animationDelay = `${(i % 12) * 0.03}s`;
        card.classList.add("fade-in");
    });
});
