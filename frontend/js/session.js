// Session management - Fixes missing session timeout
let sessionTimeout;

function resetSessionTimeout() {
    clearTimeout(sessionTimeout);
    sessionTimeout = setTimeout(() => {
        alert('Session expired. Please login again.');
        logout();
    }, CONFIG.SESSION_DURATION);
}

// Monitor user activity
['click', 'keypress', 'mousemove', 'scroll'].forEach(event => {
    document.addEventListener(event, resetSessionTimeout);
});