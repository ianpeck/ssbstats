(() => {
    document.addEventListener("DOMContentLoaded", () => {
        if (window.lucide) lucide.createIcons();

        const panel = document.getElementById("floatChatPanel");
        if (!panel) return;
        const input = document.getElementById("floatChatInput");
        const messages = document.getElementById("floatChatMessages");

        window.SSBChat.create({
            messagesEl: messages,
            inputEl: input,
            buttonEl: document.getElementById("floatChatSend"),
            storageKey: "ssbFloatChat",
            maxTableRows: 10,
        });

        const setOpen = open => {
            panel.hidden = !open;
            document.getElementById("floatChatWrap").classList.toggle("is-open", open);
            try { sessionStorage.setItem("ssbFloatChat:open", open ? "1" : "0"); } catch (e) { /* ignore */ }
            if (open) {
                messages.scrollTop = messages.scrollHeight;
                input.focus();
            }
        };
        let initialOpen = false;
        try { initialOpen = sessionStorage.getItem("ssbFloatChat:open") === "1"; } catch (e) { /* ignore */ }
        setOpen(initialOpen);

        document.getElementById("floatChatToggle").addEventListener("click", () => setOpen(panel.hidden));
        document.getElementById("floatChatClose").addEventListener("click", () => setOpen(false));
    });
})();
