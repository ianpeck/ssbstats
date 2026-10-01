// Shared chat client used by the /chat page and the floating "Ask AI" widget.
window.SSBChat = (() => {
    const MAX_HISTORY = 4;
    const PRIORITY_COLS = ["fighter_name", "name", "opponent", "wins", "losses", "win percentage", "win_pct", "win_streak", "longest_streak"];

    function esc(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function formatAnswer(text) {
        return esc(text)
            .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
            .replace(/(^|[\s(])\*(\S(?:.*?\S)?)\*(?=[\s).,!?]|$)/g, "$1<em>$2</em>")
            .replace(/\n/g, "<br>");
    }

    function prettyColumn(col) {
        return col.replace(/_/g, " ");
    }

    function buildTable(rows, maxRows) {
        if (!rows || rows.length < 2) return "";
        const rawCols = Object.keys(rows[0]);
        const rank = col => {
            const i = PRIORITY_COLS.indexOf(col.toLowerCase());
            return i === -1 ? 99 : i;
        };
        const cols = [...rawCols].sort((a, b) => rank(a) - rank(b));
        let html = '<div class="chat-table-wrap"><table class="chat-table"><thead><tr>';
        cols.forEach(col => { html += `<th>${esc(prettyColumn(col))}</th>`; });
        html += "</tr></thead><tbody>";
        rows.slice(0, maxRows).forEach(row => {
            html += "<tr>";
            cols.forEach(col => {
                const value = row[col];
                const shown = typeof value === "number" && Number.isInteger(value) ? value : (value ?? "");
                html += `<td>${esc(shown)}</td>`;
            });
            html += "</tr>";
        });
        if (rows.length > maxRows) {
            html += `<tr><td colspan="${cols.length}" class="chat-table-more">…and ${rows.length - maxRows} more</td></tr>`;
        }
        return html + "</tbody></table></div>";
    }

    function load(key, fallback) {
        try {
            const raw = sessionStorage.getItem(key);
            return raw ? JSON.parse(raw) : fallback;
        } catch (e) {
            return fallback;
        }
    }

    function save(key, value) {
        try {
            sessionStorage.setItem(key, JSON.stringify(value));
        } catch (e) {
            // Storage can be unavailable (private mode); chat still works without it.
        }
    }

    function create({ messagesEl, inputEl, buttonEl, storageKey, maxTableRows = 20, showQuery = false }) {
        let history = load(`${storageKey}:history`, []);
        const transcript = load(`${storageKey}:messages`, []);
        let busy = false;

        function append(role, html, persist = true) {
            const wrap = document.createElement("div");
            wrap.className = `chat-message chat-message-${role}`;
            const bubble = document.createElement("div");
            bubble.className = "chat-bubble";
            bubble.innerHTML = html;
            wrap.appendChild(bubble);
            messagesEl.appendChild(wrap);
            messagesEl.scrollTop = messagesEl.scrollHeight;
            if (persist) {
                transcript.push({ role, html });
                save(`${storageKey}:messages`, transcript.slice(-30));
            }
            return wrap;
        }

        function setBusy(value) {
            busy = value;
            inputEl.disabled = value;
            if (buttonEl) buttonEl.disabled = value;
            messagesEl.closest("[data-chat-root]")?.classList.toggle("is-busy", value);
        }

        async function ask(text) {
            const question = String(text ?? inputEl.value).trim();
            if (!question || busy) return;
            inputEl.value = "";
            setBusy(true);
            append("user", esc(question));
            const thinking = append("ai", '<span class="chat-thinking"><span></span><span></span><span></span></span>', false);

            try {
                const response = await fetch("/api/chat", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ question, history }),
                });
                const data = await response.json();
                thinking.remove();
                if (data.error) {
                    append("ai", `<span class="chat-error">${esc(data.error)}</span>`);
                    return;
                }
                const answer = data.answer || "No answer returned.";
                let html = formatAnswer(answer) + buildTable(data.rows, maxTableRows);
                if (showQuery && data.sql) {
                    html += `<details class="chat-sql-details"><summary>View query</summary><code class="chat-sql">${esc(data.sql)}</code></details>`;
                }
                append("ai", html);
                history = [...history, { question, answer }].slice(-MAX_HISTORY);
                save(`${storageKey}:history`, history);
            } catch (e) {
                thinking.remove();
                append("ai", '<span class="chat-error">Could not reach the server. Try again.</span>', false);
            } finally {
                setBusy(false);
                inputEl.focus();
            }
        }

        transcript.forEach(message => append(message.role, message.html, false));
        inputEl.addEventListener("keydown", event => {
            if (event.key === "Enter" && !event.isComposing) {
                event.preventDefault();
                ask();
            }
        });
        if (buttonEl) buttonEl.addEventListener("click", () => ask());

        return { ask };
    }

    return { create };
})();
