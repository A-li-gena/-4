// Main JavaScript functionality

// Utility functions
function formatDate(dateStr) {
    return new Date(dateStr).toLocaleString('ru-RU');
}

function formatCurrency(amount) {
    return new Intl.NumberFormat('ru-RU', {
        style: 'currency',
        currency: 'RUB',
        minimumFractionDigits: 0
    }).format(amount);
}

// API client
class ApiClient {
    constructor() {
        this.baseURL = '/api';
    }

    async request(url, options = {}) {
        const response = await fetch(this.baseURL + url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return response.json();
    }

    async get(url, params = {}) {
        const searchParams = new URLSearchParams(params);
        const urlWithParams = searchParams.toString() ? `${url}?${searchParams}` : url;
        return this.request(urlWithParams);
    }

    async post(url, data) {
        return this.request(url, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }
}

const api = new ApiClient();

// Modal functionality
function showModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    }
}

function hideModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = '';
    }
}

// Loading states
function showLoading(element) {
    element.innerHTML = '<div class="spinner"></div>';
}

// Error handling
function showError(message, container = document.body) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error';
    errorDiv.textContent = message;
    
    if (container === document.body) {
        container.insertAdjacentElement('afterbegin', errorDiv);
    } else {
        container.innerHTML = '';
        container.appendChild(errorDiv);
    }
    
    setTimeout(() => errorDiv.remove(), 5000);
}

// Success messages
function showSuccess(message) {
    const successDiv = document.createElement('div');
    successDiv.className = 'alert alert-success';
    successDiv.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: #10b981;
        color: white;
        padding: 12px 24px;
        border-radius: 6px;
        z-index: 1001;
    `;
    successDiv.textContent = message;
    
    document.body.appendChild(successDiv);
    setTimeout(() => successDiv.remove(), 3000);
}

// Page-specific functionality
document.addEventListener('DOMContentLoaded', function() {
    console.log('Workers System загружен');
    
    // Обработка кнопок фильтрации
    const filterButtons = document.querySelectorAll('.filter-button');
    filterButtons.forEach(button => {
        button.addEventListener('click', function() {
            filterButtons.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
        });
    });
    
    // Модальные окна
    const modalTriggers = document.querySelectorAll('[data-modal]');
    const modals = document.querySelectorAll('.modal-overlay');
    
    modalTriggers.forEach(trigger => {
        trigger.addEventListener('click', function(e) {
            e.preventDefault();
            const modalId = this.getAttribute('data-modal');
            const modal = document.getElementById(modalId);
            if (modal) {
                modal.style.display = 'flex';
            }
        });
    });
    
    // Закрытие модальных окон
    modals.forEach(modal => {
        modal.addEventListener('click', function(e) {
            if (e.target === this) {
                this.style.display = 'none';
            }
        });
    });
    
    // Автообновление статистики (каждые 30 секунд)
    if (document.querySelector('.stats-grid')) {
        setInterval(function() {
            fetch('/api/stats/summary')
                .then(response => response.json())
                .then(data => {
                    updateStats(data);
                })
                .catch(error => {
                    console.error('Ошибка обновления статистики:', error);
                });
        }, 30000);
    }
    
    function updateStats(stats) {
        const statCards = document.querySelectorAll('.stat-card-value');
        if (statCards.length >= 4) {
            statCards[0].textContent = stats.total_tasks || 0;
            statCards[1].textContent = formatCurrency(stats.total_revenue || 0);
            statCards[2].textContent = stats.total_users || 0;
            statCards[3].textContent = stats.workers_count || 0;
        }
    }
    
    // Telegram WebApp интеграция
    if (window.Telegram && window.Telegram.WebApp) {
        const webapp = window.Telegram.WebApp;
        webapp.ready();
        webapp.expand();
        
        if (webapp.colorScheme === 'dark') {
            document.body.classList.add('dark-theme');
        }
    }
});