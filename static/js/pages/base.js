(() => {
    let floatHistory = JSON.parse(sessionStorage.getItem("floatHistory") || "[]");
    let floatMessages = JSON.parse(sessionStorage.getItem("floatMessages") || "[]");
    let floatOpen = sessionStorage.getItem("floatOpen") === "true";

    function saveSession() {
        sessionStorage.setItem("floatHistory", JSON.stringify(floatHistory));
        sessionStorage.setItem("floatMessages", JSON.stringify(floatMessages));
        sessionStorage.setItem("floatOpen", floatOpen);
    }

    function restoreMessages() {
        if (!floatMessages.length) return;
        const msgs = document.getElementById("floatChatMessages");
        msgs.innerHTML = "";
        floatMessages.forEach(message => {
            const wrap = document.createElement("div");
            wrap.className = `chat-message chat-message-${message.role}`;
            const bubble = document.createElement("div");
            bubble.className = "chat-bubble";
            bubble.innerHTML = message.html;
            wrap.appendChild(bubble);
            msgs.appendChild(wrap);
        });
        msgs.scrollTop = msgs.scrollHeight;
    }

    function toggleFloatChat() {
        floatOpen = !floatOpen;
        document.getElementById("floatChatPanel").style.display = floatOpen ? "flex" : "none";
        if (floatOpen) {
            document.getElementById("floatChatInput").focus();
            document.getElementById("floatChatMessages").scrollTop = 999999;
        }
        saveSession();
    }

    function floatAppend(role, html, persist = false, ephemeral = false) {
        const msgs = document.getElementById("floatChatMessages");
        const wrap = document.createElement("div");
        wrap.className = `chat-message chat-message-${role}`;
        const bubble = document.createElement("div");
        bubble.className = "chat-bubble";
        bubble.innerHTML = html;
        wrap.appendChild(bubble);
        msgs.appendChild(wrap);
        msgs.scrollTop = msgs.scrollHeight;
        if (!ephemeral) {
            floatMessages.push({ role, html });
        }
        return wrap;
    }

    function floatEsc(str) {
        return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    function floatTable(rows) {
        if (!rows || !rows.length) return "";
        const priority = ["fighter_name", "wins", "win_streak", "longest_streak", "losses", "losing_streak", "win_percentage", "win_pct"];
        const rawCols = Object.keys(rows[0]);
        const cols = [
            ...rawCols.filter(col => priority.includes(col.toLowerCase())).sort((a, b) => {
                const ai = priority.indexOf(a.toLowerCase());
                const bi = priority.indexOf(b.toLowerCase());
                return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
            }),
            ...rawCols.filter(col => !priority.includes(col.toLowerCase())),
        ];
        const maxRows = 10;
        let html = '<div class="chat-table-wrap"><table class="chat-table"><thead><tr>';
        cols.forEach(col => {
            html += `<th>${floatEsc(col)}</th>`;
        });
        html += "</tr></thead><tbody>";
        rows.slice(0, maxRows).forEach(row => {
            html += "<tr>";
            cols.forEach(col => {
                html += `<td>${floatEsc(row[col] ?? "")}</td>`;
            });
            html += "</tr>";
        });
        if (rows.length > maxRows) {
            html += `<tr><td colspan="${cols.length}" style="text-align:center;opacity:0.6">…${rows.length - maxRows} more</td></tr>`;
        }
        html += "</tbody></table></div>";
        return html;
    }

    function floatSend() {
        const inp = document.getElementById("floatChatInput");
        const question = inp.value.trim();
        if (!question) return;
        inp.value = "";
        inp.disabled = true;

        floatAppend("user", floatEsc(question));
        const thinking = floatAppend("ai", '<span class="chat-thinking">Thinking…</span>', false, true);

        fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question, history: floatHistory }),
        })
            .then(r => r.json())
            .then(data => {
                thinking.remove();
                if (data.error) {
                    floatAppend("ai", `⚠️ ${floatEsc(data.error)}`);
                } else {
                    floatHistory.push({ question, sql: data.sql || "", rows: (data.rows || []).slice(0, 15) });
                    if (floatHistory.length > 3) floatHistory.shift();

                    let html = floatEsc(data.answer || "No answer returned.")
                        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
                        .replace(/\*(.+?)\*/g, "<em>$1</em>")
                        .replace(/\n/g, "<br>");
                    if (data.rows && data.rows.length > 1) html += floatTable(data.rows);
                    floatAppend("ai", html, true);
                }
                saveSession();
            })
            .catch(() => {
                thinking.remove();
                floatAppend("ai", "⚠️ Could not reach server.");
            })
            .finally(() => {
                inp.disabled = false;
                inp.focus();
            });
    }

    document.addEventListener("DOMContentLoaded", () => {
        restoreMessages();
        if (floatOpen) {
            document.getElementById("floatChatPanel").style.display = "flex";
        }

        document.getElementById("floatChatInput").addEventListener("keydown", event => {
            if (event.key === "Enter") floatSend();
        });

        if (window.lucide) {
            lucide.createIcons();
        }
    });

    window.toggleFloatChat = toggleFloatChat;
    window.floatSend = floatSend;
})();
