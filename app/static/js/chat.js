/**
 * Legal AI Assistant — Chat Frontend Logic
 * Handles multi-session management, message sending/receiving, and UI interactions.
 */

// =================================================================
// State
// =================================================================
let sessions = loadSessions();
let currentSessionId = loadLastActiveSession();
let isProcessing = false;
let chatHistory = [];

// =================================================================
// DOM References
// =================================================================
const messagesContainer = document.getElementById('messagesContainer');
const messagesList = document.getElementById('messagesList');
const welcomeScreen = document.getElementById('welcomeScreen');
const chatInput = document.getElementById('chatInput');
const sendBtn = document.getElementById('sendBtn');
const newChatBtn = document.getElementById('newChatBtn');
const menuToggle = document.getElementById('menuToggle');
const sidebar = document.getElementById('sidebar');
const chatHistoryList = document.getElementById('chatHistoryList');

// =================================================================
// Initialization
// =================================================================
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    
    if (!currentSessionId) {
        startNewChat(false); // Don't wipe UI yet, just generate ID
    } else {
        loadSession(currentSessionId);
    }
    
    renderSidebar();
    chatInput.focus();
});

function setupEventListeners() {
    sendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    chatInput.addEventListener('input', () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
        sendBtn.disabled = !chatInput.value.trim();
    });
    newChatBtn.addEventListener('click', () => startNewChat(true));
    menuToggle.addEventListener('click', toggleSidebar);
}

// =================================================================
// Multi-Session Management
// =================================================================
function generateSessionId() {
    return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}

function loadSessions() {
    try {
        const saved = localStorage.getItem('legal_ai_sessions');
        return saved ? JSON.parse(saved) : [];
    } catch (e) {
        return [];
    }
}

function saveSessions() {
    localStorage.setItem('legal_ai_sessions', JSON.stringify(sessions));
}

function loadLastActiveSession() {
    return localStorage.getItem('legal_ai_last_session_id');
}

function setLastActiveSession(id) {
    if (id) {
        localStorage.setItem('legal_ai_last_session_id', id);
    } else {
        localStorage.removeItem('legal_ai_last_session_id');
    }
}

function loadSessionHistory(id) {
    try {
        const saved = localStorage.getItem(`legal_ai_messages_${id}`);
        return saved ? JSON.parse(saved) : [];
    } catch (e) {
        return [];
    }
}

function saveCurrentSessionHistory() {
    if (currentSessionId) {
        localStorage.setItem(`legal_ai_messages_${currentSessionId}`, JSON.stringify(chatHistory));
    }
}

function startNewChat(clearUI = true) {
    currentSessionId = generateSessionId();
    setLastActiveSession(currentSessionId);
    chatHistory = [];
    
    if (clearUI) {
        messagesList.innerHTML = '';
        if (welcomeScreen) welcomeScreen.classList.remove('hidden');
        chatInput.value = '';
        chatInput.style.height = 'auto';
        sendBtn.disabled = true;
        chatInput.focus();
    }
    
    renderSidebar();
    
    // Close mobile sidebar if open
    sidebar.classList.remove('open');
    const backdrop = document.querySelector('.sidebar-backdrop');
    if (backdrop) backdrop.classList.remove('visible');
}

function loadSession(id) {
    currentSessionId = id;
    setLastActiveSession(id);
    chatHistory = loadSessionHistory(id);
    
    // Clear UI
    messagesList.innerHTML = '';
    
    if (chatHistory.length > 0) {
        if (welcomeScreen) welcomeScreen.classList.add('hidden');
        chatHistory.forEach(msg => renderMessageToDOM(msg.role, msg.content));
    } else {
        if (welcomeScreen) welcomeScreen.classList.remove('hidden');
    }
    
    renderSidebar();
    
    // Close mobile sidebar if open
    sidebar.classList.remove('open');
    const backdrop = document.querySelector('.sidebar-backdrop');
    if (backdrop) backdrop.classList.remove('visible');
}

function deleteSession(id, event) {
    event.stopPropagation(); // Prevent loading the session when clicking delete
    
    // Remove from array
    sessions = sessions.filter(s => s.id !== id);
    saveSessions();
    
    // Remove messages from storage
    localStorage.removeItem(`legal_ai_messages_${id}`);
    
    // If it was the active session, start a new one
    if (currentSessionId === id) {
        startNewChat(true);
    } else {
        renderSidebar();
    }
}

function renderSidebar() {
    if (!chatHistoryList) return;
    
    chatHistoryList.innerHTML = '';
    
    // Sort by updated_at descending
    const sorted = [...sessions].sort((a, b) => b.updated_at - a.updated_at);
    
    sorted.forEach(session => {
        const el = document.createElement('div');
        el.className = `history-item ${session.id === currentSessionId ? 'active' : ''}`;
        el.onclick = () => loadSession(session.id);
        
        const titleEl = document.createElement('div');
        titleEl.className = 'history-title';
        titleEl.textContent = session.title;
        
        const delBtn = document.createElement('button');
        delBtn.className = 'history-delete-btn';
        delBtn.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
        `;
        delBtn.onclick = (e) => deleteSession(session.id, e);
        
        el.appendChild(titleEl);
        el.appendChild(delBtn);
        chatHistoryList.appendChild(el);
    });
}

// =================================================================
// Message Sending
// =================================================================
async function sendMessage() {
    const message = chatInput.value.trim();
    if (!message || isProcessing) return;

    isProcessing = true;
    sendBtn.disabled = true;

    // Check if this is a brand new session being used for the first time
    if (chatHistory.length === 0) {
        const title = message.length > 25 ? message.substring(0, 25) + '...' : message;
        sessions.push({
            id: currentSessionId,
            title: title,
            updated_at: Date.now()
        });
        saveSessions();
        renderSidebar();
    } else {
        // Update timestamp for sorting
        const sessionIndex = sessions.findIndex(s => s.id === currentSessionId);
        if (sessionIndex !== -1) {
            sessions[sessionIndex].updated_at = Date.now();
            saveSessions();
            renderSidebar();
        }
    }

    if (welcomeScreen) welcomeScreen.classList.add('hidden');

    appendMessage('user', message);
    chatInput.value = '';
    chatInput.style.height = 'auto';

    const typingEl = showTypingIndicator();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message, session_id: currentSessionId }),
        });

        const data = await response.json();
        removeTypingIndicator(typingEl);

        if (data.response) {
            appendMessage('assistant', data.response);
        } else if (data.error) {
            appendMessage('assistant', 'An error occurred: ' + data.error);
        }
    } catch (error) {
        removeTypingIndicator(typingEl);
        appendMessage('assistant', 'Failed to connect to the server. Please ensure the backend is running and try again.');
        console.error('Chat error:', error);
    } finally {
        isProcessing = false;
        sendBtn.disabled = !chatInput.value.trim();
        chatInput.focus();
    }
}

function sendSuggestion(chipEl) {
    const text = chipEl.textContent.trim();
    chatInput.value = text;
    chatInput.dispatchEvent(new Event('input'));
    sendMessage();
}

// =================================================================
// Message Rendering
// =================================================================
function appendMessage(role, content) {
    chatHistory.push({ role, content });
    saveCurrentSessionHistory();
    renderMessageToDOM(role, content);
}

function renderMessageToDOM(role, content) {
    const messageEl = document.createElement('div');
    messageEl.className = `message ${role}`;

    const avatarLabel = role === 'user' ? 'You' : 'AI';
    const avatarEl = document.createElement('div');
    avatarEl.className = 'message-avatar';
    avatarEl.textContent = avatarLabel;

    const contentEl = document.createElement('div');
    contentEl.className = 'message-content';

    const textEl = document.createElement('div');
    textEl.className = 'message-text';

    if (role === 'assistant') {
        textEl.innerHTML = renderMarkdown(content);
    } else {
        textEl.textContent = content;
    }

    contentEl.appendChild(textEl);
    messageEl.appendChild(avatarEl);
    messageEl.appendChild(contentEl);
    messagesList.appendChild(messageEl);

    scrollToBottom();
}

function renderMarkdown(text) {
    if (typeof marked !== 'undefined') {
        marked.setOptions({ breaks: true, gfm: true, sanitize: false });
        return marked.parse(text);
    }
    return text.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\*(.*?)\*/g, '<em>$1</em>').replace(/`(.*?)`/g, '<code>$1</code>');
}

// =================================================================
// Typing Indicator
// =================================================================
function showTypingIndicator() {
    const el = document.createElement('div');
    el.className = 'typing-indicator';
    el.id = 'typingIndicator';
    el.innerHTML = `
        <div class="message-avatar" style="background: linear-gradient(135deg, var(--accent-blue), var(--accent-blue-light)); color: var(--text-inverse); box-shadow: 0 2px 8px rgba(0, 113, 227, 0.25);">AI</div>
        <div class="typing-dots">
            <span></span><span></span><span></span>
        </div>
        <span class="typing-label">Thinking...</span>
    `;
    messagesList.appendChild(el);
    scrollToBottom();
    return el;
}

function removeTypingIndicator(el) {
    if (el && el.parentNode) {
        el.parentNode.removeChild(el);
    }
}

// =================================================================
// Sidebar Toggle (Mobile)
// =================================================================
function toggleSidebar() {
    const isOpen = sidebar.classList.toggle('open');
    let backdrop = document.querySelector('.sidebar-backdrop');
    if (!backdrop) {
        backdrop = document.createElement('div');
        backdrop.className = 'sidebar-backdrop';
        backdrop.addEventListener('click', () => {
            sidebar.classList.remove('open');
            backdrop.classList.remove('visible');
        });
        document.body.appendChild(backdrop);
    }
    isOpen ? backdrop.classList.add('visible') : backdrop.classList.remove('visible');
}

function scrollToBottom() {
    requestAnimationFrame(() => {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    });
}
