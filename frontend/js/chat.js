// ========== CONFIGURATION ==========
const API_BASE_URL = 'http://127.0.0.1:8000';

// Check authentication on load
let token = localStorage.getItem('token');

if (!token) {
    window.location.href = 'login.html';
}

let currentUser = null;
let currentConversation = null;
let conversations = [];
let touchStartX = 0;
let touchEndX = 0;

const ASSISTANT_AVATAR_URL = "/frontend/images/noorullahumar_profile.png";

// ========== SIDEBAR TOGGLE ==========
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('closed');
}

// ========== SWIPE TO DELETE ==========
function addSwipeToDelete() {
    const conversationItems = document.querySelectorAll('.conversation-item');
    conversationItems.forEach(item => {
        item.removeEventListener('touchstart', swipeStart);
        item.removeEventListener('touchend', swipeEnd);
        item.addEventListener('touchstart', swipeStart);
        item.addEventListener('touchend', swipeEnd);
    });
}

function swipeStart(e) {
    touchStartX = e.changedTouches[0].screenX;
}

function swipeEnd(e) {
    touchEndX = e.changedTouches[0].screenX;
    const diff = touchEndX - touchStartX;
    if (diff < -50) {
        const deleteBtn = this.querySelector('.delete-conv-btn');
        if (deleteBtn) deleteBtn.click();
    }
}

// ========== INITIALIZATION ==========
document.addEventListener('DOMContentLoaded', async () => {
    console.log('DOM loaded, token exists:', !!token);
    await verifyToken();
    setupEventListeners();
});

function setupEventListeners() {
    const input = document.getElementById('user-input');
    if (input) input.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(); });
}

// ========== AUTHENTICATION ==========
async function verifyToken() {
    try {
        console.log('Verifying token...');
        const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
            currentUser = await response.json();
            console.log('User verified:', currentUser.email);
            showChatInterface();
            await loadConversations();
        } else {
            console.log('Token invalid, redirecting to login');
            logout();
        }
    } catch (error) {
        console.error('Token verification error:', error);
        logout();
    }
}

function logout() {
    localStorage.removeItem('token');
    window.location.href = 'login.html';
}

function showChatInterface() {
    document.getElementById('sidebar-name').textContent = currentUser?.username || currentUser?.email || 'User';
    document.getElementById('sidebar-email').textContent = currentUser?.email || '';
    document.getElementById('sidebar-avatar').textContent = (currentUser?.username?.[0] || currentUser?.email?.[0] || 'U').toUpperCase();
}

// ========== CONVERSATION MANAGEMENT (FIXED - NO DUPLICATE) ==========
let isLoadingConversations = false;
let loadCounter = 0;

async function loadConversations() {
    loadCounter++;
    console.log(`🔄 loadConversations called ${loadCounter} times`);

    if (isLoadingConversations) {
        console.log('Already loading conversations, skipping...');
        return;
    }

    isLoadingConversations = true;

    try {
        console.log('Loading conversations for user:', currentUser?.email);
        const response = await fetch(`${API_BASE_URL}/api/conversations/`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        console.log('Conversations API response status:', response.status);

        if (response.ok) {
            const data = await response.json();
            console.log('Raw conversations data from server:', data);

            conversations = [];
            for (const item of data) {
                if (typeof item !== 'object' || item === null) {
                    console.warn('Skipping non-object item:', item);
                    continue;
                }

                if (item.error) {
                    console.warn('Skipping error item:', item.error);
                    continue;
                }

                if (!item.conversation_id) {
                    console.warn('Skipping item without conversation_id:', item);
                    continue;
                }

                conversations.push({
                    conversation_id: item.conversation_id,
                    title: item.title || 'Conversation',
                    preview: item.preview || 'No messages',
                    updated_at: item.updated_at
                });
            }

            console.log('Mapped conversations count:', conversations.length);
            renderConversations();

            if (conversations.length > 0 && !currentConversation) {
                console.log('Loading first conversation:', conversations[0].conversation_id);
                await loadConversation(conversations[0].conversation_id);
            } else if (conversations.length === 0) {
                console.log('No valid conversations found, creating one...');
                await createNewConversation();
            }
        } else if (response.status === 401) {
            console.log('Unauthorized, redirecting to login');
            logout();
        } else {
            console.error('Failed to load conversations:', response.status);
        }
    } catch (error) {
        console.error('Error loading conversations:', error);
        conversations = [];
        renderConversations();
    } finally {
        isLoadingConversations = false;
    }
}

function renderConversations() {
    const container = document.getElementById('conversations-list');
    if (!container) return;

    if (!conversations || conversations.length === 0) {
        container.innerHTML = '<div class="loading"><i class="fas fa-comments"></i> No conversations yet. Click "New Chat" to start!</div>';
        return;
    }

    container.innerHTML = conversations.map(conv => `
                <div class="conversation-item ${currentConversation?.conversation_id === conv.conversation_id ? 'active' : ''}">
                    <div class="conversation-preview" onclick="loadConversation('${conv.conversation_id}')">
                        <i class="fas fa-message"></i> ${escapeHtml(conv.preview || 'New Conversation')}
                    </div>
                    <button class="delete-conv-btn" onclick="deleteConversation(event, '${conv.conversation_id}')" title="Delete conversation">
                        <i class="fas fa-trash-alt"></i>
                    </button>
                </div>
            `).join('');
    addSwipeToDelete();
}

async function deleteConversation(event, conversationId) {
    if (event) event.stopPropagation();
    if (!confirm('Delete this conversation?')) return;

    try {
        const response = await fetch(`${API_BASE_URL}/api/conversations/${conversationId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
        });
        if (response.ok) {
            conversations = conversations.filter(c => c.conversation_id !== conversationId);
            if (currentConversation?.conversation_id === conversationId) {
                currentConversation = null;
                document.getElementById('chat-window').innerHTML = '<div class="loading"><i class="fas fa-comments"></i> Conversation deleted. Start a new chat!</div>';
            }
            renderConversations();
            showToast('Conversation deleted', 'success');

            if (conversations.length === 0) {
                setTimeout(() => createNewConversation(), 500);
            }
        }
    } catch (error) {
        showToast('Error deleting conversation', 'error');
    }
}

async function loadConversation(conversationId) {
    if (!conversationId) {
        console.error('No conversation ID provided');
        return;
    }

    console.log('Loading conversation:', conversationId);

    const conversation = conversations.find(c => c.conversation_id === conversationId);
    if (!conversation) {
        console.error('Conversation not found:', conversationId);
        return;
    }

    currentConversation = conversation;
    renderConversations();

    try {
        const response = await fetch(`${API_BASE_URL}/api/conversations/${conversationId}/messages`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
            const messages = await response.json();
            console.log('Loaded', messages.length, 'messages');
            renderMessages(messages);
        } else {
            console.error('Failed to load messages:', response.status);
            document.getElementById('chat-window').innerHTML = '<div class="loading">Failed to load messages</div>';
        }
    } catch (error) {
        console.error('Error loading messages:', error);
    }
}

// ========== CREATE NEW CONVERSATION ==========
async function createNewConversation() {
    try {
        console.log('Creating new conversation...');

        const response = await fetch(`${API_BASE_URL}/api/conversations/create`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        console.log('Create conversation response status:', response.status);

        if (response.ok) {
            const data = await response.json();
            console.log('Conversation created:', data);

            const newConversation = {
                conversation_id: data.conversation_id,
                title: data.title || 'New Conversation',
                preview: 'New conversation'
            };

            conversations.unshift(newConversation);
            currentConversation = newConversation;
            renderConversations();

            const chatWindow = document.getElementById('chat-window');
            if (chatWindow) {
                chatWindow.innerHTML = '<div class="loading"><i class="fas fa-plus-circle"></i> New conversation started. Start typing your message!</div>';
            }

            const input = document.getElementById('user-input');
            if (input) input.focus();

            showToast('New conversation created!', 'success');
            return true;
        } else {
            console.error('Failed to create conversation:', response.status);
            showToast('Failed to create conversation', 'error');
            return false;
        }
    } catch (error) {
        console.error('Error creating conversation:', error);
        showToast('Error creating conversation', 'error');
        return false;
    }
}

// ========== MESSAGE RENDERING ==========
function renderMessages(messages) {
    const chatWindow = document.getElementById('chat-window');
    if (!chatWindow) return;

    chatWindow.innerHTML = '';

    if (!messages || messages.length === 0) {
        chatWindow.innerHTML = '<div class="loading"><i class="fas fa-comments"></i> No messages yet. Start chatting!</div>';
        return;
    }

    messages.forEach(msg => {
        if (msg.role === 'user') {
            addUserMessageToUI(msg.content, false);
        } else {
            addAssistantMessageToUI(msg.content, false);
        }
    });

    scrollToBottom();
}

function addUserMessageToUI(content, save = true) {
    const chatWindow = document.getElementById('chat-window');
    if (!chatWindow) return;

    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper user-message-wrapper';

    const contentWrapper = document.createElement('div');
    contentWrapper.className = 'message-content-wrapper';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.textContent = content;

    const time = document.createElement('div');
    time.className = 'message-time';
    time.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    contentWrapper.appendChild(bubble);
    contentWrapper.appendChild(time);

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar default';
    avatar.textContent = (currentUser?.username?.[0] || currentUser?.email?.[0] || 'U').toUpperCase();

    wrapper.appendChild(avatar);
    wrapper.appendChild(contentWrapper);
    chatWindow.appendChild(wrapper);
    scrollToBottom();
}

function addAssistantMessageToUI(content, save = true) {
    const chatWindow = document.getElementById('chat-window');
    if (!chatWindow) return;

    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper assistant-message-wrapper';

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.innerHTML = `<img src="${ASSISTANT_AVATAR_URL}" alt="NU AI">`;

    const contentWrapper = document.createElement('div');
    contentWrapper.className = 'message-content-wrapper';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.textContent = content;

    const time = document.createElement('div');
    time.className = 'message-time';
    time.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    contentWrapper.appendChild(bubble);
    contentWrapper.appendChild(time);

    wrapper.appendChild(avatar);
    wrapper.appendChild(contentWrapper);
    chatWindow.appendChild(wrapper);
    scrollToBottom();
}

function showTypingIndicator() {
    const chatWindow = document.getElementById('chat-window');
    if (!chatWindow) return;

    const typingWrapper = document.createElement('div');
    typingWrapper.className = 'typing-indicator-wrapper';
    typingWrapper.id = 'typing-indicator';

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.innerHTML = `<img src="${ASSISTANT_AVATAR_URL}" alt="NU AI">`;

    const bubbleWrapper = document.createElement('div');
    bubbleWrapper.className = 'message-content-wrapper';

    const bubble = document.createElement('div');
    bubble.className = 'typing-indicator-bubble';
    bubble.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>';

    bubbleWrapper.appendChild(bubble);
    typingWrapper.appendChild(avatar);
    typingWrapper.appendChild(bubbleWrapper);
    chatWindow.appendChild(typingWrapper);
    scrollToBottom();
}

function removeTypingIndicator() {
    const indicator = document.getElementById('typing-indicator');
    if (indicator) indicator.remove();
}

// ========== SEND MESSAGE ==========
async function sendMessage() {
    const input = document.getElementById('user-input');
    const message = input.value.trim();
    if (!message) return;

    if (!currentConversation) {
        const created = await createNewConversation();
        if (!created) {
            showToast('Failed to create conversation', 'error');
            return;
        }
        setTimeout(() => sendMessage(), 300);
        return;
    }

    const chatWindow = document.getElementById('chat-window');
    if (chatWindow.children.length === 1 && chatWindow.children[0]?.classList.contains('loading')) {
        chatWindow.innerHTML = '';
    }

    addUserMessageToUI(message, false);
    input.value = '';
    showTypingIndicator();

    try {
        const response = await fetch(`${API_BASE_URL}/api/chat`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                query: message,
                conversation_id: currentConversation.conversation_id
            })
        });

        removeTypingIndicator();

        if (response.status === 401) {
            logout();
            return;
        }

        if (response.ok) {
            const data = await response.json();
            addAssistantMessageToUI(data.reply, false);
            updateSingleConversationPreview(currentConversation.conversation_id, message);
        } else {
            addAssistantMessageToUI('Error: Failed to get response', false);
        }
    } catch (error) {
        removeTypingIndicator();
        addAssistantMessageToUI(`Error: ${error.message}`, false);
    }

    scrollToBottom();
}

function updateSingleConversationPreview(conversationId, firstMessage) {
    const conversation = conversations.find(c => c.conversation_id === conversationId);
    if (conversation) {
        const previewText = firstMessage.length > 50 ? firstMessage.substring(0, 47) + '...' : firstMessage;
        conversation.preview = previewText;
        renderConversations();
    }
}

function scrollToBottom() {
    const chatWindow = document.getElementById('chat-window');
    if (chatWindow) chatWindow.scrollTop = chatWindow.scrollHeight;
}

function handleKeyPress(event) {
    if (event.key === 'Enter') sendMessage();
}

// ========== UTILITY FUNCTIONS ==========
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showToast(message, type = 'info') {
    const existingToast = document.querySelector('.toast');
    if (existingToast) existingToast.remove();

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `<i class="fas ${type === 'success' ? 'fa-check-circle' : type === 'error' ? 'fa-exclamation-circle' : 'fa-info-circle'}"></i> ${message}`;
    toast.style.backgroundColor = type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6';
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

function toggleDropdown() {
    const dropdown = document.getElementById('dropdown-menu');
    dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
}

document.addEventListener('click', function (event) {
    const dropdown = document.getElementById('dropdown-menu');
    const userInfo = document.querySelector('.user-info');
    if (dropdown && userInfo && !userInfo.contains(event.target)) {
        dropdown.style.display = 'none';
    }
});

function openChangePasswordModal() {
    document.getElementById('password-modal').style.display = 'flex';
    toggleDropdown();
    document.getElementById('current-password').value = '';
    document.getElementById('new-password').value = '';
    document.getElementById('confirm-new-password').value = '';
    const messageDiv = document.getElementById('password-modal-message');
    messageDiv.style.display = 'none';
    messageDiv.textContent = '';
}

function closePasswordModal() {
    document.getElementById('password-modal').style.display = 'none';
}

async function handleChangePassword(event) {
    event.preventDefault();
    const currentPassword = document.getElementById('current-password').value;
    const newPassword = document.getElementById('new-password').value;
    const confirmPassword = document.getElementById('confirm-new-password').value;
    const messageDiv = document.getElementById('password-modal-message');

    if (newPassword !== confirmPassword) {
        messageDiv.className = 'error-message';
        messageDiv.textContent = 'Passwords do not match';
        messageDiv.style.display = 'block';
        return;
    }

    if (newPassword.length < 6) {
        messageDiv.className = 'error-message';
        messageDiv.textContent = 'Password must be at least 6 characters';
        messageDiv.style.display = 'block';
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/api/auth/change-password`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
        });

        const data = await response.json();
        if (response.ok) {
            messageDiv.className = 'success-message';
            messageDiv.textContent = 'Password changed successfully!';
            messageDiv.style.display = 'block';
            setTimeout(() => closePasswordModal(), 2000);
        } else {
            messageDiv.className = 'error-message';
            messageDiv.textContent = data.detail || 'Failed to change password';
            messageDiv.style.display = 'block';
        }
    } catch (error) {
        messageDiv.className = 'error-message';
        messageDiv.textContent = 'Connection error';
        messageDiv.style.display = 'block';
    }
}

// Global exports
window.toggleSidebar = toggleSidebar;
window.toggleDropdown = toggleDropdown;
window.openChangePasswordModal = openChangePasswordModal;
window.closePasswordModal = closePasswordModal;
window.handleChangePassword = handleChangePassword;
window.createNewConversation = createNewConversation;
window.sendMessage = sendMessage;
window.deleteConversation = deleteConversation;
window.loadConversation = loadConversation;
window.handleKeyPress = handleKeyPress;
window.logout = logout;
