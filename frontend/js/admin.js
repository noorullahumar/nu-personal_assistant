// ========== CONFIGURATION ==========
// API Configuration
const API_BASE_URL = 'http://nu-ai-env.eba-ijpiuack.eu-north-1.elasticbeanstalk.com/0';

// Session and token management
let token = localStorage.getItem('adminToken') || sessionStorage.getItem('adminToken');
let adminUser = null;
let temp2FAToken = null;
let pending2FAUserId = null;

// Contact messages variables
let currentFilter = 'all';
let currentMessages = [];

// Rate limiting for login
let lastSubmitTime = 0;
const SUBMIT_DELAY = 2000;

// Session timeout
let sessionTimeout;
const SESSION_DURATION = 30 * 60 * 1000; // 30 minutes

// ========== SESSION TIMEOUT FUNCTIONS ==========
function resetSessionTimeout() {
    clearTimeout(sessionTimeout);
    sessionTimeout = setTimeout(() => {
        if (token && adminUser) {
            alert('Session expired. Please login again.');
            logout();
        }
    }, SESSION_DURATION);
}

function startSessionMonitoring() {
    ['click', 'keypress', 'mousemove', 'scroll'].forEach(event => {
        document.addEventListener(event, resetSessionTimeout);
    });
    resetSessionTimeout();
}

// ========== SECURITY UTILITIES ==========
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function sanitizeInput(text) {
    if (!text) return '';
    return text.replace(/[<>]/g, '').trim().slice(0, 500);
}

// ========== DOM ELEMENTS ==========
document.addEventListener('DOMContentLoaded', function() {
    console.log('Admin.js loaded, token exists:', !!token);
    if (token) {
        verifyAdminToken();
    }
    startSessionMonitoring();
});

// ========== LOGIN FUNCTIONS ==========
async function handleLogin(event) {
    event.preventDefault();
    
    // Rate limiting check
    const now = Date.now();
    if (now - lastSubmitTime < SUBMIT_DELAY) {
        const errorDiv = document.getElementById('login-error');
        errorDiv.textContent = 'Please wait before trying again';
        errorDiv.style.display = 'block';
        return;
    }
    lastSubmitTime = now;
    
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;
    const errorDiv = document.getElementById('login-error');

    const submitBtn = event.target.querySelector('button[type="submit"]');
    const originalText = submitBtn.textContent;
    submitBtn.textContent = 'Logging in...';
    submitBtn.disabled = true;
    
    errorDiv.style.display = 'none';
    errorDiv.textContent = '';

    try {
        console.log('Attempting admin login for:', email);
        
        const response = await fetch(`${API_BASE_URL}/api/admin/auth/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({ email, password })
        });

        console.log('Response status:', response.status);
        
        let data;
        try {
            const text = await response.text();
            data = text ? JSON.parse(text) : {};
            console.log('Response data:', data);
        } catch (e) {
            console.error('JSON parse error:', e);
            throw new Error('Server returned invalid response');
        }
        
        if (response.ok) {
            if (data.user && data.user.role === 'admin') {
                token = data.access_token;
                adminUser = data.user;
                localStorage.setItem('adminToken', token);
                sessionStorage.setItem('adminToken', token);
                
                console.log('Admin login successful:', adminUser.email);
                
                showDashboard();
                loadDashboard();
                loadDocuments();
                loadUsers();
                loadLogs();
                loadContactMessages();
            } else {
                errorDiv.style.display = 'block';
                errorDiv.textContent = 'Access denied. Admin only.';
                console.error('User is not admin:', data.user);
            }
        } else {
            errorDiv.style.display = 'block';
            errorDiv.textContent = data.detail || 'Login failed. Invalid credentials or not an admin account.';
            console.error('Login failed:', data);
        }
    } catch (error) {
        console.error('Login error:', error);
        errorDiv.style.display = 'block';
        if (error.message.includes('Failed to fetch')) {
            errorDiv.textContent = 'Cannot connect to backend. Make sure FastAPI is running on port 8000.';
        } else {
            errorDiv.textContent = error.message || 'Connection error';
        }
    } finally {
        submitBtn.textContent = originalText;
        submitBtn.disabled = false;
    }
}

async function verifyAdminToken() {
    try {
        console.log('Verifying admin token...');
        
        const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });
        
        console.log('Verify token response status:', response.status);
        
        if (response.ok) {
            const user = await response.json();
            console.log('User from token:', user);
            
            if (user.role === 'admin') {
                adminUser = user;
                showDashboard();
                loadDashboard();
                loadDocuments();
                loadUsers();
                loadLogs();
                loadContactMessages();
            } else {
                console.log('User is not admin, role:', user.role);
                logout();
            }
        } else {
            console.log('Token invalid, logging out');
            logout();
        }
    } catch (error) {
        console.error('Token verification failed:', error);
        logout();
    }
}

function showDashboard() {
    const loginPage = document.getElementById('login-page');
    const dashboard = document.getElementById('dashboard');
    
    if (loginPage) loginPage.style.display = 'none';
    if (dashboard) dashboard.style.display = 'flex';
    
    const adminEmailSpan = document.getElementById('admin-email');
    if (adminEmailSpan && adminUser) {
        adminEmailSpan.textContent = adminUser.email;
    }
}

function logout() {
    localStorage.removeItem('adminToken');
    sessionStorage.removeItem('adminToken');
    token = null;
    adminUser = null;
    
    const loginPage = document.getElementById('login-page');
    const dashboard = document.getElementById('dashboard');
    
    if (loginPage) loginPage.style.display = 'flex';
    if (dashboard) dashboard.style.display = 'none';
    
    const emailInput = document.getElementById('email');
    const passwordInput = document.getElementById('password');
    if (emailInput) emailInput.value = '';
    if (passwordInput) passwordInput.value = '';
}

// ========== DASHBOARD FUNCTIONS ==========
function switchSection(section) {
    const navItem = event?.target?.closest('.nav-item');
    if (navItem) {
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.remove('active');
        });
        navItem.classList.add('active');
    }
    
    document.querySelectorAll('.content-section').forEach(s => {
        s.classList.remove('active');
    });
    
    const targetSection = document.getElementById(`section-${section}`);
    if (targetSection) targetSection.classList.add('active');
    
    if (section === 'documents') {
        loadDocuments();
    } else if (section === 'users') {
        loadUsers();
    } else if (section === 'logs') {
        loadLogs();
    } else if (section === 'dashboard') {
        loadDashboard();
    } else if (section === 'contact') {
        loadContactMessages();
    }
}

async function loadDashboard() {
    if (!token) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/admin/stats`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            const stats = await response.json();
            const totalDocs = document.getElementById('total-documents');
            const totalChunks = document.getElementById('total-chunks');
            const totalUsers = document.getElementById('total-users');
            const totalConvs = document.getElementById('total-conversations');
            
            if (totalDocs) totalDocs.textContent = stats.total_documents || '0';
            if (totalChunks) totalChunks.textContent = stats.total_chunks || '0';
            if (totalUsers) totalUsers.textContent = stats.total_users || '0';
            if (totalConvs) totalConvs.textContent = stats.total_conversations || '0';
        }
        
        const logsResponse = await fetch(`${API_BASE_URL}/api/admin/logs?limit=10`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (logsResponse.ok) {
            const logs = await logsResponse.json();
            displayRecentLogs(logs);
        }
        
    } catch (error) {
        console.error('Dashboard error:', error);
        showToast('Failed to load dashboard', 'error');
    }
}

function displayRecentLogs(logs) {
    const container = document.getElementById('recent-logs');
    if (!container) return;
    
    if (!logs || logs.length === 0) {
        container.innerHTML = '<div class="loading">No recent activity</div>';
        return;
    }
    
    container.innerHTML = logs.map(log => `
        <div class="log-item">
            <div class="log-icon">📝</div>
            <div class="log-content">
                <div class="log-action">${escapeHtml(log.action || 'Unknown')}</div>
                <div class="log-details">${escapeHtml(JSON.stringify(log.details || {}))}</div>
                <div class="log-time">${log.timestamp ? new Date(log.timestamp).toLocaleString() : 'Unknown'} - by ${escapeHtml(log.username || 'System')}</div>
            </div>
        </div>
    `).join('');
}

// ========== DOCUMENT FUNCTIONS ==========
async function loadDocuments() {
    if (!token) return;
    
    const container = document.getElementById('documents-container');
    if (!container) return;
    
    container.innerHTML = '<div class="loading">Loading documents...</div>';
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/admin/documents`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            const docs = await response.json();
            displayDocuments(docs);
        } else {
            container.innerHTML = '<div class="loading">Failed to load documents</div>';
        }
    } catch (error) {
        console.error('Load documents error:', error);
        container.innerHTML = '<div class="loading">Error loading documents</div>';
    }
}

function displayDocuments(docs) {
    const container = document.getElementById('documents-container');
    if (!container) return;
    
    if (!docs || docs.length === 0) {
        container.innerHTML = '<div class="loading">No documents uploaded</div>';
        return;
    }
    
    container.innerHTML = docs.map(doc => `
        <div class="document-card">
            <div class="document-icon">📄</div>
            <div class="document-name">${escapeHtml(doc.filename || 'Unknown')}</div>
            <div class="document-meta">
                <div>Type: ${escapeHtml(doc.file_type || 'Unknown')}</div>
                <div>Size: ${doc.size ? (doc.size / 1024).toFixed(2) : '0'} KB</div>
                <div>Chunks: ${doc.chunk_count || 0}</div>
                <div>Uploaded: ${doc.upload_date ? new Date(doc.upload_date).toLocaleString() : 'Unknown'}</div>
                <div>Status: <span style="color: ${doc.status === 'active' ? '#10b981' : '#f59e0b'}">${escapeHtml(doc.status || 'Unknown')}</span></div>
            </div>
            <div class="document-actions">
                <button class="btn-delete" onclick="deleteDocument('${doc.document_id}')">Delete</button>
                <button class="btn-view" onclick="viewDocument('${doc.document_id}')">View</button>
            </div>
        </div>
    `).join('');
}

async function uploadFiles() {
    const fileInput = document.getElementById('file-upload');
    if (!fileInput || !fileInput.files.length) return;
    
    const files = fileInput.files;
    
    for (let file of files) {
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const response = await fetch(`${API_BASE_URL}/api/admin/documents/upload`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`
                },
                body: formData
            });
            
            if (response.ok) {
                showToast(`${file.name} uploaded successfully`, 'success');
            } else {
                const error = await response.json();
                showToast(`Failed to upload ${file.name}: ${error.detail || 'Unknown error'}`, 'error');
            }
        } catch (error) {
            console.error('Upload error:', error);
            showToast(`Error uploading ${file.name}`, 'error');
        }
    }
    
    fileInput.value = '';
    loadDocuments();
    loadDashboard();
}

async function deleteDocument(documentId) {
    if (!confirm('Delete this document permanently?')) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/admin/documents/${documentId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            showToast('Document deleted', 'success');
            loadDocuments();
            loadDashboard();
        } else {
            const error = await response.json();
            showToast('Failed to delete document: ' + (error.detail || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Delete error:', error);
        showToast('Error deleting document', 'error');
    }
}

function viewDocument(documentId) {
    window.open(`${API_BASE_URL}/api/admin/documents/${documentId}/view`, '_blank');
}

async function searchDocuments(query) {
    if (!query || query.length < 3) {
        loadDocuments();
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/admin/documents/search?query=${encodeURIComponent(query)}`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            const results = await response.json();
            displayDocuments(results);
        }
    } catch (error) {
        console.error('Search error:', error);
    }
}

// ========== USER FUNCTIONS ==========
async function loadUsers() {
    if (!token) return;
    
    const container = document.getElementById('users-container');
    if (!container) return;
    
    container.innerHTML = '<div class="loading">Loading users...</div>';
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/admin/users`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            const users = await response.json();
            displayUsers(users);
        } else {
            container.innerHTML = '<div class="loading">Failed to load users</div>';
        }
    } catch (error) {
        console.error('Load users error:', error);
        container.innerHTML = '<div class="loading">Error loading users</div>';
    }
}

function displayUsers(users) {
    const container = document.getElementById('users-container');
    if (!container) return;
    
    if (!users || users.length === 0) {
        container.innerHTML = '<div class="loading">No users found</div>';
        return;
    }
    
    container.innerHTML = users.map(user => `
        <div class="log-item">
            <div class="log-icon">👤</div>
            <div class="log-content">
                <div class="log-action">${escapeHtml(user.username || 'Unknown')} (${escapeHtml(user.email || 'No email')})</div>
                <div class="log-details">Role: ${escapeHtml(user.role || 'user')} | Joined: ${user.created_at ? new Date(user.created_at).toLocaleDateString() : 'Unknown'}</div>
                <div class="log-time">Last login: ${user.last_login ? new Date(user.last_login).toLocaleString() : 'Never'}</div>
            </div>
            ${user.role !== 'admin' ? `
                <button class="btn-delete" onclick="deleteUser('${user.user_id}')" style="width: auto; padding: 5px 10px;">Delete</button>
            ` : ''}
        </div>
    `).join('');
}

async function deleteUser(userId) {
    if (!confirm('Delete this user? Their conversations will also be deleted.')) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/admin/users/${userId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            showToast('User deleted', 'success');
            loadUsers();
        } else {
            const error = await response.json();
            showToast('Failed to delete user: ' + (error.detail || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Delete user error:', error);
        showToast('Error deleting user', 'error');
    }
}

// ========== LOG FUNCTIONS ==========
async function loadLogs() {
    if (!token) return;
    
    const container = document.getElementById('logs-container');
    if (!container) return;
    
    container.innerHTML = '<div class="loading">Loading logs...</div>';
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/admin/logs?limit=100`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            const logs = await response.json();
            displayLogs(logs);
        } else {
            container.innerHTML = '<div class="loading">Failed to load logs</div>';
        }
    } catch (error) {
        console.error('Load logs error:', error);
        container.innerHTML = '<div class="loading">Error loading logs</div>';
    }
}

function displayLogs(logs) {
    const container = document.getElementById('logs-container');
    if (!container) return;
    
    if (!logs || logs.length === 0) {
        container.innerHTML = '<div class="loading">No logs available</div>';
        return;
    }
    
    container.innerHTML = logs.map(log => `
        <div class="log-item">
            <div class="log-icon">📝</div>
            <div class="log-content">
                <div class="log-action">${escapeHtml(log.action || 'Unknown')}</div>
                <div class="log-details">${escapeHtml(JSON.stringify(log.details || {}))}</div>
                <div class="log-time">${log.timestamp ? new Date(log.timestamp).toLocaleString() : 'Unknown'} - by ${escapeHtml(log.username || 'System')}</div>
            </div>
        </div>
    `).join('');
}

// ========== CONTACT MESSAGES FUNCTIONS ==========
async function loadContactMessages() {
    const container = document.getElementById('messages-container');
    if (!container) return;
    
    container.innerHTML = '<div class="loading">Loading messages...</div>';
    
    try {
        let url = `${API_BASE_URL}/api/contact/messages?limit=200`;
        if (currentFilter !== 'all') {
            url += `&status=${currentFilter}`;
        }
        
        const response = await fetch(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
            currentMessages = await response.json();
            displayMessages(currentMessages);
            updateContactStats();
        } else {
            container.innerHTML = '<div class="loading">Failed to load messages</div>';
        }
    } catch (error) {
        console.error('Load messages error:', error);
        container.innerHTML = '<div class="loading">Error loading messages</div>';
    }
}

function displayMessages(messages) {
    console.log('displayMessages called with:', messages);
    
    const container = document.getElementById('messages-container');
    if (!container) {
        console.error('Container not found!');
        return;
    }
    
    if (!messages || messages.length === 0) {
        console.log('No messages to display');
        container.innerHTML = '<div class="loading">No messages found</div>';
        return;
    }
    
    console.log('Rendering', messages.length, 'messages');
    
    const html = messages.map(msg => {
        console.log('Rendering message:', msg.message_id, msg.name);
        return `
        <div class="message-card ${msg.status}" data-message-id="${msg.message_id}">
            <div class="message-header">
                <div class="message-sender">
                    <strong>${escapeHtml(msg.name)}</strong>
                    <span class="message-email">(${escapeHtml(msg.email)})</span>
                </div>
                <div class="message-status status-${msg.status}">${msg.status.toUpperCase()}</div>
            </div>
            <div class="message-subject">
                <strong>Subject:</strong> ${escapeHtml(msg.subject)}
            </div>
            <div class="message-preview">
                ${escapeHtml(msg.message.substring(0, 150))}${msg.message.length > 150 ? '...' : ''}
            </div>
            <div class="message-meta">
                <span>📅 ${new Date(msg.submitted_at).toLocaleString()}</span>
                <span>🌐 IP: ${escapeHtml(msg.ip_address || 'Unknown')}</span>
            </div>
            <div class="message-actions" style="display: flex !important; gap: 10px; margin-top: 15px;">
                <button class="btn-view" onclick="viewFullMessage('${msg.message_id}')" style="flex:1; padding:8px; background:#3b82f6; color:white; border:none; border-radius:6px; cursor:pointer;">View</button>
                <button class="btn-reply" onclick="openReplyModal('${msg.message_id}')" style="flex:1; padding:8px; background:#10b981; color:white; border:none; border-radius:6px; cursor:pointer;">Reply</button>
                <button class="btn-delete" onclick="deleteMessage('${msg.message_id}')" style="flex:1; padding:8px; background:#ef4444; color:white; border:none; border-radius:6px; cursor:pointer;">Delete</button>
            </div>
        </div>
    `}).join('');
    
    console.log('HTML generated, length:', html.length);
    container.innerHTML = html;
    console.log('Container updated');
}

async function viewFullMessage(messageId) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/contact/messages/${messageId}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
            const message = await response.json();
            
            const modalContent = `
                <div style="max-width: 600px; background: #1e293b; border-radius: 16px; padding: 20px;">
                    <h3 style="color: #3b82f6;">Message from ${escapeHtml(message.name)}</h3>
                    <p><strong>Email:</strong> ${escapeHtml(message.email)}</p>
                    <p><strong>Subject:</strong> ${escapeHtml(message.subject)}</p>
                    <p><strong>Submitted:</strong> ${new Date(message.submitted_at).toLocaleString()}</p>
                    <hr style="margin: 15px 0; border-color: #334155;">
                    <p><strong>Message:</strong></p>
                    <p style="background: #2d3748; padding: 15px; border-radius: 8px; white-space: pre-wrap;">${escapeHtml(message.message)}</p>
                    <div style="margin-top: 20px; text-align: right;">
                        <button onclick="this.closest('.modal').remove()" class="btn-primary">Close</button>
                    </div>
                </div>
            `;
            
            const modal = document.createElement('div');
            modal.className = 'modal';
            modal.style.display = 'flex';
            modal.innerHTML = modalContent;
            document.body.appendChild(modal);
            
            loadContactMessages();
        }
    } catch (error) {
        console.error('View message error:', error);
        showToast('Failed to load message', 'error');
    }
}

let currentReplyMessageId = null;

function openReplyModal(messageId) {
    const message = currentMessages.find(m => m.message_id === messageId);
    if (!message) return;
    
    currentReplyMessageId = messageId;
    const replyName = document.getElementById('reply-name');
    const replyEmail = document.getElementById('reply-email');
    const replySubject = document.getElementById('reply-subject');
    const replyContent = document.getElementById('reply-content');
    
    if (replyName) replyName.textContent = message.name;
    if (replyEmail) replyEmail.textContent = message.email;
    if (replySubject) replySubject.textContent = message.subject;
    if (replyContent) replyContent.value = '';
    
    const replyModal = document.getElementById('reply-modal');
    if (replyModal) replyModal.style.display = 'flex';
}

function closeReplyModal() {
    const replyModal = document.getElementById('reply-modal');
    if (replyModal) replyModal.style.display = 'none';
    currentReplyMessageId = null;
}

async function sendReply() {
    const replyContent = document.getElementById('reply-content');
    if (!replyContent) return;
    
    const replyText = replyContent.value.trim();
    
    if (!replyText) {
        alert('Please enter a reply message');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/contact/messages/${currentReplyMessageId}/reply`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ reply: replyText })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            if (result.email_sent) {
                showToast('Reply sent and email delivered successfully!', 'success');
            } else {
                showToast('Reply saved but email delivery failed. Check email settings.', 'warning');
            }
            closeReplyModal();
            loadContactMessages(); // Reload to update status
        } else {
            showToast('Failed to send reply: ' + (result.detail || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Send reply error:', error);
        showToast('Error sending reply: ' + error.message, 'error');
    }
}

async function deleteMessage(messageId) {
    if (!confirm('Delete this message permanently?')) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/contact/messages/${messageId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
            showToast('Message deleted', 'success');
            loadContactMessages();
        } else {
            showToast('Failed to delete message', 'error');
        }
    } catch (error) {
        console.error('Delete error:', error);
        showToast('Error deleting message', 'error');
    }
}

function filterMessages(status) {
    currentFilter = status;
    
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    if (event && event.target) {
        event.target.classList.add('active');
    }
    
    loadContactMessages();
}

async function updateContactStats() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/contact/stats`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
            const stats = await response.json();
            const pendingSpan = document.getElementById('pending-count');
            const readSpan = document.getElementById('read-count');
            const repliedSpan = document.getElementById('replied-count');
            
            if (pendingSpan) pendingSpan.textContent = `Pending: ${stats.pending || 0}`;
            if (readSpan) readSpan.textContent = `Read: ${stats.read || 0}`;
            if (repliedSpan) repliedSpan.textContent = `Replied: ${stats.replied || 0}`;
        }
    } catch (error) {
        console.error('Stats error:', error);
    }
}

// ========== UTILITY FUNCTIONS ==========
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        padding: 12px 20px;
        border-radius: 8px;
        color: white;
        z-index: 1000;
        animation: slideIn 0.3s ease;
        background-color: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'};
    `;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// ========== EXPOSE GLOBAL FUNCTIONS ==========
window.handleLogin = handleLogin;
window.logout = logout;
window.switchSection = switchSection;
window.uploadFiles = uploadFiles;
window.searchDocuments = searchDocuments;
window.deleteDocument = deleteDocument;
window.viewDocument = viewDocument;
window.deleteUser = deleteUser;
window.loadContactMessages = loadContactMessages;
window.filterMessages = filterMessages;
window.viewFullMessage = viewFullMessage;
window.openReplyModal = openReplyModal;
window.closeReplyModal = closeReplyModal;
window.sendReply = sendReply;
window.deleteMessage = deleteMessage;
