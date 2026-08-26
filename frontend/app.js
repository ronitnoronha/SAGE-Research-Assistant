// app.js - FRONTEND CONTROLLER FOR SAGE RESEARCH ASSISTANT
document.addEventListener("DOMContentLoaded", () => {
    // API State
    let apiBaseUrl = localStorage.getItem("sage_api_url") || "http://localhost:8000";

    // DOM Elements
    const systemStatus = document.getElementById("system-status");
    const documentList = document.getElementById("document-list");
    const pdfFileInput = document.getElementById("pdf-file-input");
    const uploadStatus = document.getElementById("upload-status");
    const chatMessages = document.getElementById("chat-messages");
    const welcomeScreen = document.getElementById("welcome-screen");
    const chatForm = document.getElementById("chat-form");
    const userInput = document.getElementById("user-input");
    const btnClearChat = document.getElementById("btn-clear-chat");
    const btnApiConfig = document.getElementById("btn-api-config");
    const configModal = document.getElementById("config-modal");
    const apiUrlInput = document.getElementById("api-url-input");
    const btnModalSave = document.getElementById("btn-modal-save");
    const btnModalCancel = document.getElementById("btn-modal-cancel");

    // Initialize
    checkApiHealth();
    fetchDocuments();

    // Check API Health
    async function checkApiHealth() {
        try {
            const res = await fetch(`${apiBaseUrl}/health`);
            if (res.ok) {
                const data = await res.json();
                systemStatus.innerHTML = `
                    <span class="status-dot success"></span>
                    <span class="status-text">Connected: Supabase Vector</span>
                `;
            } else {
                throw new Error("API Offline");
            }
        } catch (err) {
            systemStatus.innerHTML = `
                <span class="status-dot warning"></span>
                <span class="status-text">API Disconnected</span>
            `;
        }
    }

    // Fetch Indexed Documents
    async function fetchDocuments() {
        try {
            const res = await fetch(`${apiBaseUrl}/documents`);
            if (res.ok) {
                const data = await res.json();
                renderDocumentList(data.documents || []);
            }
        } catch (err) {
            console.warn("Could not fetch documents:", err);
        }
    }

    function renderDocumentList(docs) {
        if (!docs || docs.length === 0) {
            documentList.innerHTML = `<div class="empty-docs">No documents indexed yet.</div>`;
            return;
        }

        documentList.innerHTML = docs.map(doc => `
            <div class="doc-item">
                <i class="fa-solid fa-file-pdf"></i>
                <div style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                    <strong>${doc.source}</strong><br>
                    <span style="font-size:0.7rem; color:var(--text-muted);">${doc.chunk_count} vector chunks</span>
                </div>
            </div>
        `).join("");
    }

    // PDF Upload Handler
    pdfFileInput.addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        uploadStatus.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Indexing into Supabase...`;
        
        const formData = new FormData();
        formData.append("file", file);

        try {
            const res = await fetch(`${apiBaseUrl}/upload`, {
                method: "POST",
                body: formData
            });

            if (res.ok) {
                const result = await res.json();
                uploadStatus.innerHTML = `<span style="color:#10b981;">✅ Indexed ${result.chunks_inserted} chunks!</span>`;
                fetchDocuments();
            } else {
                const errData = await res.json();
                uploadStatus.innerHTML = `<span style="color:#ef4444;">❌ ${errData.detail || "Upload failed"}</span>`;
            }
        } catch (err) {
            uploadStatus.innerHTML = `<span style="color:#ef4444;">❌ Network error</span>`;
        }

        setTimeout(() => { uploadStatus.innerHTML = ""; }, 5000);
    });

    // Chat Form Submit
    chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const question = userInput.value.trim();
        if (!question) return;

        sendQuestion(question);
        userInput.value = "";
    });

    async function sendQuestion(question) {
        if (welcomeScreen) {
            welcomeScreen.style.display = "none";
        }

        // Add User Message
        appendMessage("user", question);

        // Add Bot Loading State
        const loadingId = appendMessage("bot", `<i class="fa-solid fa-spinner fa-spin"></i> Searching Supabase Vector DB...`);

        try {
            const res = await fetch(`${apiBaseUrl}/query`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ question })
            });

            if (res.ok) {
                const data = await res.json();
                updateMessage(loadingId, data.answer, data.sources);
            } else {
                updateMessage(loadingId, "⚠️ Error processing request from server.");
            }
        } catch (err) {
            updateMessage(loadingId, "⚠️ Could not connect to SAGE API server. Please verify endpoint configuration.");
        }
    }

    function appendMessage(role, content) {
        const msgId = "msg-" + Date.now();
        const isUser = role === "user";
        
        const row = document.createElement("div");
        row.className = `message-row ${role}`;
        row.id = msgId;

        row.innerHTML = `
            <div class="avatar ${role}">
                <i class="fa-solid ${isUser ? 'fa-user' : 'fa-brain'}"></i>
            </div>
            <div class="message-bubble">${content}</div>
        `;

        chatMessages.appendChild(row);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return msgId;
    }

    function updateMessage(msgId, answerText, sources) {
        const row = document.getElementById(msgId);
        if (!row) return;

        const bubble = row.querySelector(".message-bubble");
        
        let formattedText = answerText
            .replace(/\n\n/g, "<br><br>")
            .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
            .replace(/\*(.*?)\*/g, "<em>$1</em>");

        let sourcesHtml = "";
        if (sources && sources.length > 0) {
            sourcesHtml = `
                <div class="sources-box">
                    <div class="sources-header">
                        <i class="fa-solid fa-book-bookmark"></i> Evidence Sources (${sources.length})
                    </div>
                    ${sources.map(src => `
                        <div class="source-tag">
                            📄 <strong>${src.source}</strong> (Page ${src.page})
                        </div>
                    `).join("")}
                </div>
            `;
        }

        bubble.innerHTML = formattedText + sourcesHtml;
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // Quick Sample Questions
    document.getElementById("sample-q1")?.addEventListener("click", () => sendQuestion("What is the recommended first-line treatment for Type 2 Diabetes?"));
    document.getElementById("sample-q2")?.addEventListener("click", () => sendQuestion("What are the HbA1c diagnostic thresholds for diabetes?"));
    document.getElementById("sample-q3")?.addEventListener("click", () => sendQuestion("Summarize key risk factors mentioned in uploaded papers."));

    // Clear Chat
    btnClearChat.addEventListener("click", () => {
        chatMessages.innerHTML = "";
        if (welcomeScreen) {
            welcomeScreen.style.display = "block";
            chatMessages.appendChild(welcomeScreen);
        }
    });

    // API Config Modal Actions
    btnApiConfig.addEventListener("click", () => {
        apiUrlInput.value = apiBaseUrl;
        configModal.classList.add("active");
    });

    btnModalCancel.addEventListener("click", () => configModal.classList.remove("active"));
    
    btnModalSave.addEventListener("click", () => {
        const newUrl = apiUrlInput.value.trim();
        if (newUrl) {
            apiBaseUrl = newUrl;
            localStorage.setItem("sage_api_url", newUrl);
            checkApiHealth();
            fetchDocuments();
        }
        configModal.classList.remove("active");
    });
});
