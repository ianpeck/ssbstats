(() => {
    const chat = window.SSBChat.create({
        messagesEl: document.getElementById("chatMessages"),
        inputEl: document.getElementById("chatInput"),
        buttonEl: document.getElementById("chatSendBtn"),
        storageKey: "ssbChatPage",
        maxTableRows: 20,
        showQuery: true,
    });

    document.getElementById("chatSuggestions").addEventListener("click", event => {
        const chip = event.target.closest("[data-question]");
        if (chip) chat.ask(chip.dataset.question);
    });
})();
