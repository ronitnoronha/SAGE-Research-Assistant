// app.js - FRONTEND CONTROLLER FOR SAGE RESEARCH ASSISTANT WITH SUPABASE AUTH
document.addEventListener("DOMContentLoaded", () => {
    // Configurable Backend API Endpoint
    let apiBaseUrl = localStorage.getItem("sage_api_url") ||
        (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
            ? "http://localhost:8000"
            : "https://sage-research-assistant.onrender.com");

    // Supabase Auth Client
    const SUPABASE_URL = "https://vvpstsihxzoselrunhwy.supabase.co";
    const SUPABASE_ANON_KEY = "sb_publishable_cD59VHq9A5zr5-yBmisaAA_dFZUXYBe";

    let supabaseClient = null;
    if (window.supabase) {
        supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
    }

    // User Session State
    let currentUserSession = null;

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

    // Auth Elements
    const authHeaderContainer = document.getElementById("auth-header-container");
    const btnOpenAuth = document.getElementById("btn-open-auth");
    const authModal = document.getElementById("auth-modal");
    const tabLogin = document.getElementById("tab-login");
    const tabSignup = document.getElementById("tab-signup");
    const authForm = document.getElementById("auth-form");
    const authModalTitle = document.getElementById("auth-modal-title");
    const authModalSubtitle = document.getElementById("auth-modal-subtitle");
    const authEmailInput = document.getElementById("auth-email");
    const authPasswordInput = document.getElementById("auth-password");
    const btnAuthSubmit = document.getElementById("btn-auth-submit");
    const btnAuthCancel = document.getElementById("btn-auth-cancel");
    const authAlert = document.getElementById("auth-alert");

    // Settings Modal Elements
    const btnSettings = document.getElementById("btn-settings");
    const settingsModal = document.getElementById("settings-modal");
    const settingsForm = document.getElementById("settings-form");
    const backendUrlInput = document.getElementById("backend-url-input");
    const btnSettingsCancel = document.getElementById("btn-settings-cancel");

    if (backendUrlInput) {
        backendUrlInput.value = apiBaseUrl;
    }

    btnSettings?.addEventListener("click", () => {
        if (backendUrlInput) backendUrlInput.value = apiBaseUrl;
        settingsModal?.classList.add("active");
    });

    btnSettingsCancel?.addEventListener("click", () => {
        settingsModal?.classList.remove("active");
    });

    settingsForm?.addEventListener("submit", (e) => {
        e.preventDefault();
        const newUrl = backendUrlInput.value.trim().replace(/\/+$/, "");
        if (newUrl) {
            apiBaseUrl = newUrl;
            localStorage.setItem("sage_api_url", apiBaseUrl);
            settingsModal?.classList.remove("active");
            systemStatus.innerHTML = `
                <span class="status-dot warning"></span>
                <span class="status-text">Connecting to ${apiBaseUrl}...</span>
            `;
            checkApiHealth();
            fetchDocuments();
        }
    });

    let isSignUpMode = false;

    const escapeHtml = (str) => String(str ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const mainContent = document.querySelector(".main-content");
    const setThinking = (on) => window.SageSpace?.setThinking(on);

    // Mobile library drawer
    const sidebar = document.getElementById("sidebar");
    const closeSidebar = () => sidebar?.classList.remove("open");
    document.getElementById("btn-sidebar-open")?.addEventListener("click", () => sidebar?.classList.add("open"));
    document.getElementById("btn-sidebar-close")?.addEventListener("click", closeSidebar);
    document.getElementById("sidebar-scrim")?.addEventListener("click", closeSidebar);

    // Drag & drop upload onto the dropzone
    const dropzone = document.getElementById("dropzone");
    ["dragenter", "dragover"].forEach(ev => dropzone?.addEventListener(ev, (e) => {
        e.preventDefault();
        dropzone.classList.add("dragging");
    }));
    ["dragleave", "drop"].forEach(ev => dropzone?.addEventListener(ev, (e) => {
        e.preventDefault();
        dropzone.classList.remove("dragging");
    }));
    dropzone?.addEventListener("drop", (e) => {
        const file = e.dataTransfer?.files?.[0];
        if (file) uploadFile(file);
    });

    // Initialize (the library loads once the auth session is known)
    checkApiHealth();
    initAuthSession();

    // Initialize Auth Session
    async function initAuthSession() {
        if (!supabaseClient) { fetchDocuments(); return; }

        try {
            const { data: { session } } = await supabaseClient.auth.getSession();
            updateAuthUI(session);

            supabaseClient.auth.onAuthStateChange((_event, session) => {
                updateAuthUI(session);
            });
        } catch (err) {
            console.warn("Auth initialization error:", err);
        }
    }

    function updateAuthUI(session) {
        const previousToken = currentUserSession?.access_token;
        currentUserSession = session;
        if (session?.access_token !== previousToken || !session) fetchDocuments();
        if (session && session.user) {
            const email = session.user.email;
            authHeaderContainer.innerHTML = `
                <div class="user-badge" title="${escapeHtml(email)}">
                    <span class="avatar-dot">${escapeHtml(email.charAt(0))}</span>
                    <span>${escapeHtml(email)}</span>
                    <button id="btn-signout" class="icon-btn" title="Sign out" aria-label="Sign out">
                        <i class="fa-solid fa-right-from-bracket"></i>
                    </button>
                </div>
            `;
            document.getElementById("btn-signout")?.addEventListener("click", async () => {
                await supabaseClient?.auth.signOut();
            });
        } else {
            authHeaderContainer.innerHTML = `
                <button class="btn btn-primary btn-sm" id="btn-open-auth">Sign in</button>
            `;
            document.getElementById("btn-open-auth")?.addEventListener("click", openAuthModal);
        }
    }

    function openAuthModal() {
        showAuthAlert("", "");
        authModal.classList.add("active");
    }

    function closeAuthModal() {
        authModal.classList.remove("active");
    }

    // Auth Tabs Switcher
    tabLogin?.addEventListener("click", () => {
        isSignUpMode = false;
        tabLogin.classList.add("active");
        tabSignup.classList.remove("active");
        authModalTitle.innerText = "Welcome back";
        authModalSubtitle.innerText = "Sign in to upload and search your documents.";
        btnAuthSubmit.innerText = "Sign in";
        showAuthAlert("", "");
    });

    tabSignup?.addEventListener("click", () => {
        isSignUpMode = true;
        tabSignup.classList.add("active");
        tabLogin.classList.remove("active");
        authModalTitle.innerText = "Create an account";
        authModalSubtitle.innerText = "Register with your email to start using SAGE.";
        btnAuthSubmit.innerText = "Create account";
        showAuthAlert("", "");
    });

    btnAuthCancel?.addEventListener("click", closeAuthModal);
    btnOpenAuth?.addEventListener("click", openAuthModal);

    // Auth Form Submit (Sign In / Sign Up)
    authForm?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const email = authEmailInput.value.trim();
        const password = authPasswordInput.value.trim();

        if (!email || !password) {
            showAuthAlert("Please fill in email and password.", "error");
            return;
        }

        btnAuthSubmit.disabled = true;
        btnAuthSubmit.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Working...`;

        try {
            if (isSignUpMode) {
                const { data, error } = await supabaseClient.auth.signUp({ email, password });
                if (error) throw error;

                if (data?.session) {
                    showAuthAlert("Account created successfully! You are logged in.", "success");
                    setTimeout(closeAuthModal, 1500);
                } else {
                    showAuthAlert("Account created! Check your email to confirm registration.", "success");
                }
            } else {
                const { data, error } = await supabaseClient.auth.signInWithPassword({ email, password });
                if (error) throw error;

                showAuthAlert("Signed in successfully!", "success");
                setTimeout(closeAuthModal, 1000);
            }
        } catch (err) {
            showAuthAlert(err.message || "Authentication failed", "error");
        } finally {
            btnAuthSubmit.disabled = false;
            btnAuthSubmit.innerText = isSignUpMode ? "Create account" : "Sign in";
        }
    });

    function showAuthAlert(msg, type) {
        if (!msg) {
            authAlert.style.display = "none";
            return;
        }
        authAlert.className = `auth-alert ${type}`;
        authAlert.innerText = msg;
        authAlert.style.display = "block";
    }

    // Check API Health
    async function checkApiHealth() {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 8000);
            const res = await fetch(`${apiBaseUrl}/health`, { signal: controller.signal });
            clearTimeout(timeoutId);

            if (res.ok) {
                systemStatus.innerHTML = `
                    <span class="status-dot success"></span>
                    <span class="status-text">Connected to vector database</span>
                `;
            } else {
                throw new Error("API Offline");
            }
        } catch (err) {
            systemStatus.innerHTML = `
                <span class="status-dot warning"></span>
                <span class="status-text">Backend offline. Check settings.</span>
            `;
        }
    }

    // Fetch Indexed Documents
    async function fetchDocuments() {
        if (!currentUserSession?.access_token) {
            renderDocumentList(null);
            return;
        }
        try {
            const headers = {};
            if (currentUserSession?.access_token) {
                headers["Authorization"] = `Bearer ${currentUserSession.access_token}`;
            }
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 8000);
            const res = await fetch(`${apiBaseUrl}/documents`, { headers, signal: controller.signal });
            clearTimeout(timeoutId);

            if (res.ok) {
                const data = await res.json();
                renderDocumentList(data.documents || []);
            }
        } catch (err) {
            console.warn("Could not fetch documents:", err);
        }
    }

    function renderDocumentList(docs) {
        const docCount = document.getElementById("doc-count");
        if (docCount) docCount.textContent = docs && docs.length ? `${docs.length} files` : "";
        if (!docs) {
            documentList.innerHTML = `<div class="empty-docs">Sign in to see your library.</div>`;
            return;
        }
        if (docs.length === 0) {
            documentList.innerHTML = `<div class="empty-docs">No documents yet. Upload a PDF to get started.</div>`;
            return;
        }

        documentList.innerHTML = docs.map(doc => `
            <div class="doc-item" title="${escapeHtml(doc.source)}">
                <span class="doc-icon">PDF</span>
                <div class="doc-meta">
                    <strong>${escapeHtml(doc.source)}</strong>
                    <span>${escapeHtml(doc.chunk_count)} chunks indexed</span>
                </div>
            </div>
        `).join("");
    }

    // Conversational Multi-Turn Memory State
    let conversationHistory = [];

    // PDF Upload Handler
    pdfFileInput.addEventListener("change", (e) => {
        const file = e.target.files[0];
        if (file) uploadFile(file);
        pdfFileInput.value = "";
    });

    async function uploadFile(file) {
        if (!currentUserSession) {
            openAuthModal();
            showAuthAlert("Sign in to upload documents.", "error");
            return;
        }
        if (!file.name.toLowerCase().endsWith(".pdf")) {
            uploadStatus.innerHTML = `<span class="err">Only PDF files are supported.</span>`;
            setTimeout(() => { uploadStatus.innerHTML = ""; }, 6000);
            return;
        }
        sidebar?.classList.add("open");
        uploadStatus.innerHTML = `<span class="busy"><i class="fa-solid fa-spinner fa-spin"></i> Indexing ${escapeHtml(file.name)}...</span>`;
        const formData = new FormData();
        formData.append("file", file);

        const headers = {};
        if (currentUserSession?.access_token) {
            headers["Authorization"] = `Bearer ${currentUserSession.access_token}`;
        }

        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 60000);
            const res = await fetch(`${apiBaseUrl}/upload`, {
                method: "POST",
                headers,
                body: formData,
                signal: controller.signal
            });
            clearTimeout(timeoutId);

            if (res.ok) {
                const result = await res.json();
                uploadStatus.innerHTML = `<span class="ok"><i class="fa-solid fa-check"></i> Indexed ${escapeHtml(result.chunks_inserted)} chunks from ${escapeHtml(file.name)}</span>`;
                fetchDocuments();
            } else {
                const errData = await res.json();
                uploadStatus.innerHTML = `<span class="err">${escapeHtml(errData.detail || "Upload failed. Try again.")}</span>`;
            }
        } catch (err) {
            uploadStatus.innerHTML = `<span class="err">Can't reach the backend. It may be waking up, so try again in a minute.</span>`;
        }

        setTimeout(() => { uploadStatus.innerHTML = ""; }, 8000);
    }

    // Chat Form Submit
    chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const question = userInput.value.trim();
        if (!question) return;

        sendQuestion(question);
        userInput.value = "";
    });

    async function sendQuestion(question) {
        if (!currentUserSession) {
            openAuthModal();
            showAuthAlert("Sign in to ask questions about your documents.", "error");
            return;
        }
        if (welcomeScreen) {
            welcomeScreen.style.display = "none";
        }
        mainContent?.classList.add("chatting");
        setThinking(true);

        // Add User Message to UI and History
        appendMessage("user", escapeHtml(question));
        conversationHistory.push({ role: "user", content: question });

        // Add Bot Loading State
        const loadingId = appendMessage("bot", `<span class="thinking"><span class="dots"><i></i><i></i><i></i></span> Searching your documents...</span>`);

        const headers = { "Content-Type": "application/json" };
        if (currentUserSession?.access_token) {
            headers["Authorization"] = `Bearer ${currentUserSession.access_token}`;
        }

        try {
            const res = await fetch(`${apiBaseUrl}/query`, {
                method: "POST",
                headers,
                body: JSON.stringify({
                    question,
                    chat_history: conversationHistory.slice(-6)
                })
            });

            if (res.ok) {
                const data = await res.json();
                if (data.mode === "error") {
                    console.error("SAGE backend error:", data.answer);
                    updateMessage(loadingId, null, null, null, "Something went wrong while answering. Try again, or rephrase the question.");
                } else {
                    conversationHistory.push({ role: "assistant", content: data.answer });
                    updateMessage(loadingId, data.answer, data.sources, data.tools_used);
                }
            } else if (res.status === 401) {
                updateMessage(loadingId, null, null, null, "Your session has expired. Please sign in again.");
                openAuthModal();
            } else {
                updateMessage(loadingId, null, null, null, "The server couldn't process that request. Try again in a moment.");
            }
        } catch (err) {
            updateMessage(loadingId, null, null, null, "Can't reach the backend. It may be waking up, so try again in a minute.");
        } finally {
            setThinking(false);
        }
    }

    let messageCounter = 0;
    function appendMessage(role, content) {
        const msgId = "msg-" + (++messageCounter);
        const isUser = role === "user";

        const row = document.createElement("div");
        row.className = `message-row ${role}`;
        row.id = msgId;

        row.innerHTML = `
            <div class="avatar ${role}">
                <i class="fa-solid ${isUser ? 'fa-user' : 'fa-feather-pointed'}"></i>
            </div>
            <div class="message-bubble">${content}</div>
        `;

        chatMessages.appendChild(row);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return msgId;
    }

    function updateMessage(msgId, answerText, sources, toolsUsed, errorText) {
        const row = document.getElementById(msgId);
        if (!row) return;

        const bubble = row.querySelector(".message-bubble");
        if (errorText) {
            bubble.innerHTML = `<p class="error-note">${escapeHtml(errorText)}</p>`;
            chatMessages.scrollTop = chatMessages.scrollHeight;
            return;
        }
        let formattedText = "";
        if (typeof marked !== "undefined" && marked.parse && window.DOMPurify) {
            // Answers can echo text from uploaded PDFs, so strip scripts, event handlers and iframes
            formattedText = DOMPurify.sanitize(marked.parse(answerText));
        } else {
            formattedText = escapeHtml(answerText)
                .replace(/\n\n/g, "<br><br>")
                .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
        }

        let toolsHtml = "";
        if (toolsUsed && toolsUsed.length > 0) {
            const toolBadges = toolsUsed.map(t => `<span class="tool-badge">${escapeHtml(t)}</span>`).join("");
            toolsHtml = `<div class="tools-execution-box">${toolBadges}</div>`;
        }

        let sourcesHtml = "";
        if (sources && sources.length > 0) {
            // Group citations by file: "insulin.pdf · p. 2, 3, 6"
            const byFile = new Map();
            sources.forEach(src => {
                const pages = byFile.get(src.source) || new Set();
                pages.add(src.page);
                byFile.set(src.source, pages);
            });
            sourcesHtml = `
                <div class="sources-box">
                    <div class="sources-header mono">Sources · ${sources.length}</div>
                    <div class="source-list">
                        ${[...byFile].map(([file, pages]) => `
                            <span class="source-tag" title="${escapeHtml(file)}">
                                <i class="fa-solid fa-file-pdf"></i>
                                <strong>${escapeHtml(file)}</strong>
                                <span>p. ${[...pages].sort((a, b) => a - b).map(escapeHtml).join(", ")}</span>
                            </span>
                        `).join("")}
                    </div>
                </div>
            `;
        }

        bubble.innerHTML = toolsHtml + formattedText + sourcesHtml;
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // Quick Sample Questions
    document.getElementById("sample-q1")?.addEventListener("click", () => sendQuestion("Summarize the primary objectives and key findings in the documents."));
    document.getElementById("sample-q2")?.addEventListener("click", () => sendQuestion("What are the specific metrics, dates, and numbers mentioned?"));
    document.getElementById("sample-q3")?.addEventListener("click", () => sendQuestion("Compare the main conclusions and insights across the uploaded files."));

    // Clear Chat
    btnClearChat.addEventListener("click", () => {
        chatMessages.innerHTML = "";
        conversationHistory = [];
        mainContent?.classList.remove("chatting");
        if (welcomeScreen) {
            welcomeScreen.style.display = "block";
            chatMessages.appendChild(welcomeScreen);
        }
    });
});
