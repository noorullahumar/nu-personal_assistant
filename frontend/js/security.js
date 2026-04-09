// Security utilities - Fixes XSS and input validation
function sanitizeInput(text) {
    if (!text) return '';
    return text.replace(/[<>]/g, '').trim().slice(0, 500);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function validateEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}