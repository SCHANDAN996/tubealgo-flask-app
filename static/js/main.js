// tubealgo/static/js/main.js
/**
 * TubeAlgo - Global JavaScript
 * Handles CSRF protection, dark mode, and common utilities
 */

// ============================================
// CSRF Protection (CRITICAL)
// ============================================

/**
 * Setup CSRF token for all fetch requests
 * Automatically adds X-CSRFToken header to POST/PUT/PATCH/DELETE requests
 */
(function setupCSRFProtection() {
    const originalFetch = window.fetch;
    
    window.fetch = function(url, options = {}) {
        // Only add CSRF token for write operations
        const method = (options.method || 'GET').toUpperCase();
        const needsCSRF = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method);
        
        if (needsCSRF) {
            // Get CSRF token from multiple sources
            const csrfToken = window.CSRF_TOKEN || 
                             document.querySelector('meta[name="csrf-token"]')?.content ||
                             document.querySelector('input[name="csrf_token"]')?.value;
            
            if (csrfToken) {
                // Ensure headers object exists
                options.headers = options.headers || {};
                
                // Add CSRF token to headers
                if (options.headers instanceof Headers) {
                    options.headers.append('X-CSRFToken', csrfToken);
                } else if (typeof options.headers === 'object') {
                    options.headers['X-CSRFToken'] = csrfToken;
                }
                
                console.debug(`✅ CSRF token added to ${method} request: ${url}`);
            } else {
                console.warn(`⚠️ CSRF token not found for ${method} request: ${url}`);
            }
        }
        
        return originalFetch(url, options);
    };
    
    console.log('✅ CSRF protection enabled globally');
})();

/**
 * jQuery AJAX CSRF setup (if jQuery is available)
 */
if (typeof $ !== 'undefined' && $.ajaxSetup) {
    $.ajaxSetup({
        beforeSend: function(xhr, settings) {
            // Only for write operations
            if (!/^(GET|HEAD|OPTIONS|TRACE)$/i.test(settings.type)) {
                const csrfToken = window.CSRF_TOKEN || 
                                 $('meta[name="csrf-token"]').attr('content');
                
                if (csrfToken) {
                    xhr.setRequestHeader('X-CSRFToken', csrfToken);
                    console.debug('✅ CSRF token added to jQuery AJAX request');
                }
            }
        }
    });
    
    console.log('✅ jQuery AJAX CSRF protection enabled');
}

// ============================================
// Dark Mode
// ============================================

/**
 * Dark mode toggle
 */
function initDarkMode() {
    const darkModeToggle = document.getElementById('darkModeToggle');
    
    if (darkModeToggle) {
        darkModeToggle.addEventListener('click', () => {
            const isDark = localStorage.getItem('darkMode') === 'true';
            localStorage.setItem('darkMode', !isDark);
            document.documentElement.classList.toggle('dark');
        });
    }
}

// Initialize on DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDarkMode);
} else {
    initDarkMode();
}

// ============================================
// Utility Functions
// ============================================

/**
 * Format number with commas
 */
function formatNumber(num) {
    if (num === null || num === undefined) return '0';
    return parseInt(num).toLocaleString();
}

/**
 * Format duration from seconds to HH:MM:SS
 */
function formatDuration(seconds) {
    if (!seconds) return '0:00';
    
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hours > 0) {
        return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    } else {
        return `${minutes}:${String(secs).padStart(2, '0')}`;
    }
}

/**
 * Format time ago
 */
function timeAgo(date) {
    if (!date) return '';
    
    const now = new Date();
    const then = new Date(date);
    const diffMs = now - then;
    const diffSeconds = Math.floor(diffMs / 1000);
    
    if (diffSeconds < 60) return 'just now';
    
    const diffMinutes = Math.floor(diffSeconds / 60);
    if (diffMinutes < 60) return `${diffMinutes}m ago`;
    
    const diffHours = Math.floor(diffMinutes / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays}d ago`;
    
    const options = { month: 'short', day: 'numeric' };
    if (now.getFullYear() !== then.getFullYear()) {
        options.year = 'numeric';
    }
    
    return then.toLocaleDateString('en-US', options);
}

/**
 * Copy text to clipboard
 */
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showNotification('Copied to clipboard!', 'success');
        return true;
    } catch (err) {
        console.error('Failed to copy:', err);
        showNotification('Failed to copy', 'error');
        return false;
    }
}

/**
 * Show notification
 */
function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `fixed top-4 right-4 z-50 bg-white dark:bg-gray-800 rounded-lg shadow-lg p-4 max-w-md border-l-4 transition-all duration-300`;
    
    // Add color based on type
    const colors = {
        success: 'border-green-500',
        error: 'border-red-500',
        warning: 'border-yellow-500',
        info: 'border-blue-500'
    };
    notification.classList.add(colors[type] || colors.info);
    
    // Add icon
    const icons = {
        success: '✓',
        error: '✕',
        warning: '⚠',
        info: 'ℹ'
    };
    
    notification.innerHTML = `
        <div class="flex items-start">
            <div class="flex-shrink-0 text-2xl mr-3">
                ${icons[type] || icons.info}
            </div>
            <div class="flex-1">
                <p class="text-sm font-medium text-gray-900 dark:text-gray-100">
                    ${message}
                </p>
            </div>
            <button onclick="this.parentElement.parentElement.remove()" 
                    class="ml-4 text-gray-400 hover:text-gray-500">
                ✕
            </button>
        </div>
    `;
    
    document.body.appendChild(notification);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => notification.remove(), 300);
    }, 5000);
}

/**
 * Debounce function
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Throttle function
 */
function throttle(func, limit) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

/**
 * Extract YouTube video ID from URL
 */
function extractVideoId(url) {
    const patterns = [
        /(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)/,
        /^([a-zA-Z0-9_-]{11})$/  // Direct video ID
    ];
    
    for (const pattern of patterns) {
        const match = url.match(pattern);
        if (match) return match[1];
    }
    
    return null;
}

/**
 * Extract YouTube channel ID from URL
 */
function extractChannelId(url) {
    const patterns = [
        /youtube\.com\/channel\/([^\/\?]+)/,
        /youtube\.com\/@([^\/\?]+)/,
        /youtube\.com\/c\/([^\/\?]+)/
    ];
    
    for (const pattern of patterns) {
        const match = url.match(pattern);
        if (match) return match[1];
    }
    
    return null;
}

/**
 * Validate email
 */
function validateEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

/**
 * Format file size
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

/**
 * Parse query string
 */
function getQueryParams() {
    const params = {};
    const queryString = window.location.search.substring(1);
    const queries = queryString.split('&');
    
    for (const query of queries) {
        const [key, value] = query.split('=');
        if (key) {
            params[decodeURIComponent(key)] = decodeURIComponent(value || '');
        }
    }
    
    return params;
}

/**
 * Update query string without reload
 */
function updateQueryString(params) {
    const url = new URL(window.location);
    
    for (const [key, value] of Object.entries(params)) {
        if (value === null || value === undefined || value === '') {
            url.searchParams.delete(key);
        } else {
            url.searchParams.set(key, value);
        }
    }
    
    window.history.pushState({}, '', url);
}

// ============================================
// API Helper Functions
// ============================================

/**
 * Make API request with proper error handling
 */
async function apiRequest(url, options = {}) {
    try {
        const response = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || error.message || `HTTP ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('API request failed:', error);
        throw error;
    }
}

/**
 * GET request
 */
async function apiGet(url) {
    return apiRequest(url, { method: 'GET' });
}

/**
 * POST request
 */
async function apiPost(url, data) {
    return apiRequest(url, {
        method: 'POST',
        body: JSON.stringify(data)
    });
}

/**
 * PUT request
 */
async function apiPut(url, data) {
    return apiRequest(url, {
        method: 'PUT',
        body: JSON.stringify(data)
    });
}

/**
 * DELETE request
 */
async function apiDelete(url) {
    return apiRequest(url, { method: 'DELETE' });
}

// ============================================
// Form Validation
// ============================================

/**
 * Validate form on submit
 */
function setupFormValidation() {
    const forms = document.querySelectorAll('form[data-validate]');
    
    forms.forEach(form => {
        form.addEventListener('submit', (e) => {
            const inputs = form.querySelectorAll('input[required], textarea[required], select[required]');
            let isValid = true;
            
            inputs.forEach(input => {
                if (!input.value.trim()) {
                    isValid = false;
                    input.classList.add('border-red-500');
                } else {
                    input.classList.remove('border-red-500');
                }
            });
            
            if (!isValid) {
                e.preventDefault();
                showNotification('Please fill in all required fields', 'error');
            }
        });
    });
}

// Setup on DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupFormValidation);
} else {
    setupFormValidation();
}

// ============================================
// Keyboard Shortcuts
// ============================================

document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd + K for search
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        const searchInput = document.querySelector('input[type="search"]');
        if (searchInput) searchInput.focus();
    }
    
    // Escape to close modals
    if (e.key === 'Escape') {
        const modals = document.querySelectorAll('[x-show]');
        // Trigger Alpine.js close (if using Alpine)
    }
});

// ============================================
// Export for use in other scripts
// ============================================

window.TubeAlgo = {
    formatNumber,
    formatDuration,
    timeAgo,
    copyToClipboard,
    showNotification,
    debounce,
    throttle,
    extractVideoId,
    extractChannelId,
    validateEmail,
    formatFileSize,
    getQueryParams,
    updateQueryString,
    apiGet,
    apiPost,
    apiPut,
    apiDelete
};

console.log('✅ TubeAlgo utilities loaded');
