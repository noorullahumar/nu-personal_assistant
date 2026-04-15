// frontend/js/config.js
const CONFIG = {
    API_URL: window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
        ? 'http://127.0.0.1:8000'
        : 'http://nu-ai-env.eba-ijpiuack.eu-north-1.elasticbeanstalk.com/', 
    DEBUG: window.location.hostname === 'localhost',
    SESSION_DURATION: 30 * 60 * 1000, // 30 minutes
    RATE_LIMIT_DELAY: 2000 // 2 seconds between submissions
};

// Make config available globally
window.CONFIG = CONFIG;

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { CONFIG };
}
