const chatInput = document.getElementById("chatInput");
const chatButton = document.getElementById("chatSendBtn");
const chatMessages = document.getElementById("chatMessages");
const chatHistory = [];

function appendMessage(role, html) {
    const wrap = document.createElement("div");
    wrap.className = `chat-message chat-message-${role}`;
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";
    bubble.innerHTML = html;
    wrap.appendChild(bubble);
    chatMessages.appendChild(wrap);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return wrap;
}

function escHtml(str) {
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function buildTable(rows) {
    if (!rows || !rows.length) return "";
    const priority = ["fighter_name", "wins", "win_streak", "longest_streak", "losses", "losing_streak", "win_percentage", "win_pct"];
    const rawCols = Object.keys(rows[0]);
    const cols = [
        ...rawCols.filter(c => priority.includes(c.toLowerCase())).sort((a, b) => {
            const ai = priority.indexOf(a.toLowerCase());
            const bi = priority.indexOf(b.toLowerCase());
            return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
        }),
        ...rawCols.filter(c => !priority.includes(c.toLowerCase())),
    ];
    const maxRows = 20;
    let html = '<div class="chat-table-wrap"><table class="chat-table"><thead><tr>';
    cols.forEach(col => {
        html += `<th>${escHtml(col)}</th>`;
    });
    html += "</tr></thead><tbody>";
    rows.slice(0, maxRows).forEach(row => {
        html += "<tr>";
        cols.forEach(col => {
            html += `<td>${escHtml(row[col] ?? "")}</td>`;
        });
        html += "</tr>";
    });
    if (rows.length > maxRows) {
        html += `<tr><td colspan="${cols.length}" style="text-align:center;opacity:0.6">…and ${rows.length - maxRows} more rows</td></tr>`;
    }
    html += "</tbody></table></div>";
    return html;
}

function sendQuestion() {
    const question = chatInput.value.trim();
    if (!question) return;
    chatInput.value = "";
    chatButton.disabled = true;

    appendMessage("user", question);
    const thinking = appendMessage("ai", '<span class="chat-thinking">Thinking…</span>');

    fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, history: chatHistory }),
    })
        .then(r => r.json())
        .then(data => {
            thinking.remove();
            if (data.error) {
                appendMessage("ai", `⚠️ ${data.error}`);
            } else {
                chatHistory.push({ question, sql: data.sql || "", rows: (data.rows || []).slice(0, 15) });
                if (chatHistory.length > 3) chatHistory.shift();

                let html = escHtml(data.answer || "No answer returned.");
                if (data.rows && data.rows.length > 1) html += buildTable(data.rows);
                if (data.sql) {
                    html += `<details class="chat-sql-details"><summary>View query</summary><code class="chat-sql">${escHtml(data.sql)}</code></details>`;
                }
                appendMessage("ai", html);
            }
        })
        .catch(() => {
            thinking.remove();
            appendMessage("ai", "⚠️ Could not reach the server. Try again.");
        })
        .finally(() => {
            chatButton.disabled = false;
        });
}

chatInput.addEventListener("keydown", event => {
    if (event.key === "Enter") sendQuestion();
});

window.sendQuestion = sendQuestion;
