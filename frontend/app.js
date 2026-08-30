// app.js - FRONTEND CONTROLLER FOR SAGE RESEARCH ASSISTANT WITH SUPABASE AUTH
document.addEventListener("DOMContentLoaded", () => {
    // Permanent Production Backend Endpoint
    const apiBaseUrl = "https://sage-research-assistant.onrender.com";

    // Supabase Auth Client
    const SUPABASE_URL = "https://vvpstsihxzoselrunhwy.supabase.co";
    const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ2cHN0c2loeHpvc2VscnVuaHd5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODc3NDUxNjcsImV4cCI6MjEwMzMyMTE2N30.6sPtn9Dpl0T8wwHGyf15LOVwa4iwSfFxKXqR_ddFXvo";
    
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

    let isSignUpMode = false;

    // Initialize
    checkApiHealth();
    fetchDocuments();
    initAuthSession();

    // Initialize Auth Session
    async function initAuthSession() {
        if (!supabaseClient) return;

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
        currentUserSession = session;
        if (session && session.user) {
            const email = session.user.email;
            authHeaderContainer.innerHTML = `
                <div class="user-badge" title="${email}">
                    <i class="fa-solid fa-user-check"></i>
                    <span>${email}</span>
                    <button id="btn-signout" class="icon-btn" style="width:22px; height:22px; font-size:0.75rem;" title="Sign Out">
                        <i class="fa-solid fa-right-from-bracket"></i>
                    </button>
                </div>
            `;
            document.getElementById("btn-signout")?.addEventListener("click", async () => {
                await supabaseClient?.auth.signOut();
            });
        } else {
            authHeaderContainer.innerHTML = `
                <button class="btn btn-primary btn-sm" id="btn-open-auth">
                    <i class="fa-solid fa-user-lock"></i> Sign In / Register
                </button>
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
        authModalTitle.innerHTML = `<i class="fa-solid fa-lock"></i> Welcome Back`;
        authModalSubtitle.innerText = "Sign in to access AI document search & PDF indexing";
        btnAuthSubmit.innerText = "Sign In";
        showAuthAlert("", "");
    });

    tabSignup?.addEventListener("click", () => {
        isSignUpMode = true;
        tabSignup.classList.add("active");
        tabLogin.classList.remove("active");
        authModalTitle.innerHTML = `<i class="fa-solid fa-user-plus"></i> Create Account`;
        authModalSubtitle.innerText = "Register your email to unlock SAGE AI capabilities";
        btnAuthSubmit.innerText = "Create Account";
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
        btnAuthSubmit.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Processing...`;

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
            btnAuthSubmit.innerText = isSignUpMode ? "Create Account" : "Sign In";
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
            const res = await fetch(`${apiBaseUrl}/health`);
            if (res.ok) {
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
            const headers = {};
            if (currentUserSession?.access_token) {
                headers["Authorization"] = `Bearer ${currentUserSession.access_token}`;
            }
            const res = await fetch(`${apiBaseUrl}/documents`, { headers });
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

    // Conversational Multi-Turn Memory State
    let conversationHistory = [];

    // PDF Upload Handler
    pdfFileInput.addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        uploadStatus.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Indexing into Supabase...`;
        
        const formData = new FormData();
        formData.append("file", file);

        const headers = {};
        if (currentUserSession?.access_token) {
            headers["Authorization"] = `Bearer ${currentUserSession.access_token}`;
        }

        try {
            const res = await fetch(`${apiBaseUrl}/upload`, {
                method: "POST",
                headers,
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

        // Add User Message to UI and History
        appendMessage("user", question);
        conversationHistory.push({ role: "user", content: question });

        // Add Bot Loading State
        const loadingId = appendMessage("bot", `<i class="fa-solid fa-brain fa-fade"></i> Analyzing documents with LangChain Agent...`);

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
                conversationHistory.push({ role: "assistant", content: data.answer });
                updateMessage(loadingId, data.answer, data.sources, data.tools_used);
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

    function updateMessage(msgId, answerText, sources, toolsUsed) {
        const row = document.getElementById(msgId);
        if (!row) return;

        const bubble = row.querySelector(".message-bubble");
        
        let formattedText = "";
        if (typeof marked !== "undefined" && marked.parse) {
            formattedText = marked.parse(answerText);
        } else {
            formattedText = answerText
                .replace(/\n\n/g, "<br><br>")
                .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
        }

        let toolsHtml = "";
        if (toolsUsed && toolsUsed.length > 0) {
            const toolBadges = toolsUsed.map(t => `<span class="tool-badge"><i class="fa-solid fa-microchip"></i> ${t}</span>`).join(" ");
            toolsHtml = `<div class="tools-execution-box">${toolBadges}</div>`;
        }

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
        if (welcomeScreen) {
            welcomeScreen.style.display = "block";
            chatMessages.appendChild(welcomeScreen);
        }
    });
});
