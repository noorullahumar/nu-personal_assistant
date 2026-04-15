// ========== CONFIGURATION ==========
const API_BASE_URL = 'http://127.0.0.1:8000';

// Profile Image Configuration
const MY_PROFILE_IMAGE = "/frontend/images/noorullahumar_profile.png";

// // Wait for DOM to be fully loaded
document.addEventListener('DOMContentLoaded', function () {
    console.log('DOM loaded, initializing...');

    // Set profile image
    const heroImage = document.getElementById('profileImage');
    if (heroImage) {
        heroImage.src = MY_PROFILE_IMAGE;
        heroImage.alt = "Profile Photo";
    }

    // Start terminal animation
    startTerminalAnimation();

    // Check auth status (non-blocking)
    setTimeout(() => {
        checkAuthStatus();
    }, 100);
});

// Terminal Animation
function startTerminalAnimation() {
    const terminalTexts = [
        "> Initializing NU AI...",
        "> Loading RAG pipeline...",
        "> Vector database connected...",
        "> Ready to assist!"
    ];

    let textIndex = 0;
    let charIndex = 0;
    const terminalElement = document.getElementById('terminalText');

    if (!terminalElement) return;

    function typeTerminalText() {
        if (textIndex < terminalTexts.length) {
            if (charIndex < terminalTexts[textIndex].length) {
                terminalElement.innerHTML += terminalTexts[textIndex].charAt(charIndex);
                charIndex++;
                setTimeout(typeTerminalText, 50);
            } else {
                textIndex++;
                charIndex = 0;
                if (textIndex < terminalTexts.length) {
                    terminalElement.innerHTML += '<br>';
                    setTimeout(typeTerminalText, 500);
                }
            }
        }
    }

    setTimeout(typeTerminalText, 500);
}

// ========== AUTHENTICATION FUNCTIONS ==========
async function checkAuthStatus() {
    const token = localStorage.getItem('token');
    const adminToken = localStorage.getItem('adminToken');

    if (token) {
        try {
            console.log('Verifying user token...');
            const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (response.ok) {
                const user = await response.json();
                console.log('User verified:', user.email);
                showLoggedInUser(user);
                return;
            } else {
                console.log('Token invalid, removing');
                localStorage.removeItem('token');
            }
        } catch (error) {
            console.error('Token verification failed:', error);
            localStorage.removeItem('token');
        }
    }

    if (adminToken) {
        try {
            console.log('Verifying admin token...');
            const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
                headers: { 'Authorization': `Bearer ${adminToken}` }
            });
            if (response.ok) {
                const user = await response.json();
                if (user.role === 'admin') {
                    console.log('Admin verified:', user.email);
                    showLoggedInUser(user);
                    return;
                }
            } else {
                console.log('Admin token invalid, removing');
                localStorage.removeItem('adminToken');
            }
        } catch (error) {
            console.error('Admin token verification failed:', error);
            localStorage.removeItem('adminToken');
        }
    }

    console.log('No valid token found, showing logged out state');
    showLoggedOutUser();
}

function showLoggedInUser(user) {
    const navButtons = document.getElementById('navButtons');
    const userMenu = document.getElementById('userMenu');
    if (navButtons) navButtons.style.display = 'none';
    if (userMenu) userMenu.style.display = 'block';

    const userName = document.getElementById('userName');
    const userEmail = document.getElementById('userEmail');
    if (userName) userName.textContent = user.username || user.email;
    if (userEmail) userEmail.textContent = user.email;

    const avatar = document.getElementById('userAvatar');
    if (avatar) {
        avatar.textContent = (user.username?.[0] || user.email?.[0] || 'U').toUpperCase();
    }
}

function showLoggedOutUser() {
    const navButtons = document.getElementById('navButtons');
    const userMenu = document.getElementById('userMenu');
    if (navButtons) navButtons.style.display = 'flex';
    if (userMenu) userMenu.style.display = 'none';
}

function goToChat() {
    const token = localStorage.getItem('token');
    const adminToken = localStorage.getItem('adminToken');

    if (adminToken) {
        window.location.href = 'admin.html';
    } else if (token) {
        window.location.href = 'chat.html';
    } else {
        window.location.href = 'login.html';
    }
}

async function logout() {
    try {
        const token = localStorage.getItem('token');
        const adminToken = localStorage.getItem('adminToken');
        const activeToken = token || adminToken;

        if (activeToken) {
            await fetch(`${API_BASE_URL}/api/auth/logout`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${activeToken}` }
            });
        }
    } catch (error) {
        console.error('Logout error:', error);
    } finally {
        localStorage.removeItem('token');
        localStorage.removeItem('adminToken');
        localStorage.removeItem('user');
        window.location.href = 'index.html';
    }
}

// ========== CONTACT FORM HANDLER ==========
async function handleContactSubmit(event) {
    event.preventDefault();

    const name = document.getElementById('contactName').value.trim();
    const email = document.getElementById('contactEmail').value.trim();
    const subject = document.getElementById('contactSubject').value.trim();
    const message = document.getElementById('contactMessage').value.trim();
    const successDiv = document.getElementById('contactSuccess');
    const submitBtn = event.target.querySelector('.submit-btn');
    const originalText = submitBtn.textContent;

    // Client-side validation
    if (name.length < 2) {
        alert('Please enter your full name');
        return;
    }

    if (!email.includes('@') || !email.includes('.')) {
        alert('Please enter a valid email address');
        return;
    }

    if (subject.length < 1) {
        alert('Please enter a subject');
        return;
    }

    if (message.length < 10) {
        alert('Please enter a message (at least 10 characters)');
        return;
    }

    // Show loading state
    submitBtn.disabled = true;
    submitBtn.textContent = 'Sending...';
    successDiv.style.display = 'none';

    try {
        const token = localStorage.getItem('token') || localStorage.getItem('adminToken');

        const headers = {
            'Content-Type': 'application/json'
        };

        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch(`${API_BASE_URL}/api/contact/submit`, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({
                name: name,
                email: email,
                subject: subject,
                message: message
            })
        });

        const data = await response.json();

        if (response.ok) {
            successDiv.style.display = 'block';
            document.getElementById('contactForm').reset();

            setTimeout(() => {
                successDiv.style.display = 'none';
            }, 5000);
        } else {
            alert(data.detail || 'Failed to send message. Please try again.');
        }

    } catch (error) {
        console.error('Contact form error:', error);
        alert('Connection error. Please try again later.');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = originalText;
    }

    return false;
}

// ========== SMOOTH SCROLL ==========
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        const href = this.getAttribute('href');
        if (href && href !== '#') {
            e.preventDefault();
            const target = document.querySelector(href);
            if (target) {
                target.scrollIntoView({ behavior: 'smooth' });
            }
        }
    });
});

// ========== EXPOSE GLOBAL FUNCTIONS ==========
window.goToChat = goToChat;
window.logout = logout;
window.handleContactSubmit = handleContactSubmit;