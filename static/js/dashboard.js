// static/js/dashboard.js

function dashboard() {
    return {
        isLoading: true,
        error: null,
        data: {
            kpis: { subscribers: 0, views: 0, videos: 0, subscribers_change: 0, views_change: 0 },
            growth_chart: { labels: [], subscribers: [], views: [] },
            ai_assistant: [],
            trending_videos: [],
            goal: null
        },
        chart: null,
        activeChartMetric: 'subscribers',

        // --- State for Goal Modal ---
        showGoalModal: false,
        goalError: '',
        newGoal: {
            type: 'subscribers',
            target: null,
            date: ''
        },
        
        csrfToken: null, 

        init() {
            const csrfMeta = document.querySelector('meta[name="csrf-token"]');
            if (csrfMeta) {
                this.csrfToken = csrfMeta.getAttribute('content');
            }
            this.fetchData();
        },

        fetchData() {
            // Add a cache-busting query parameter to ensure fresh data
            fetch(`/api/dashboard/main-data?t=${new Date().getTime()}`)
                .then(res => {
                    if (!res.ok) {
                        return res.json().then(err => { throw new Error(err.error || 'Could not load dashboard data.') });
                    }
                    return res.json();
                })
                .then(apiData => {
                    this.data = apiData;
                    this.error = null;
                    this.$nextTick(() => this.renderChart());
                })
                .catch(err => {
                    this.error = err.message;
                    console.error("Dashboard fetch error:", err);
                })
                .finally(() => {
                    this.isLoading = false;
                });
        },
        
        renderChart() {
            if (this.chart) { this.chart.destroy(); }
            if (!this.$refs.growthChart || !this.data.growth_chart || !this.data.growth_chart.labels) { return; }
            
            // === FIX: Get computed CSS variable and format it correctly for the canvas API ===
            const rootStyles = getComputedStyle(document.documentElement);
            const primaryColorHSL = rootStyles.getPropertyValue('--primary').trim();
            // The value is "262 84% 54%", but canvas needs "262, 84%, 54%"
            const primaryColorCommaSeparated = primaryColorHSL.replace(/ /g, ',');

            const ctx = this.$refs.growthChart.getContext('2d');
            const gradient = ctx.createLinearGradient(0, 0, 0, 250);
            gradient.addColorStop(0, `hsla(${primaryColorCommaSeparated}, 0.5)`);
            gradient.addColorStop(1, `hsla(${primaryColorCommaSeparated}, 0)`);

            const theme = localStorage.getItem('theme') || 'light';
            const gridColor = theme === 'dark' ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)';
            const labelColor = theme === 'dark' ? '#cbd5e1' : '#475569';

            this.chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: this.data.growth_chart.labels,
                    datasets: [{
                        label: this.activeChartMetric.charAt(0).toUpperCase() + this.activeChartMetric.slice(1),
                        data: this.data.growth_chart[this.activeChartMetric],
                        borderColor: `hsl(${primaryColorCommaSeparated})`,
                        backgroundColor: gradient,
                        borderWidth: 2,
                        pointBackgroundColor: `hsl(${primaryColorCommaSeparated})`,
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    scales: {
                        y: { beginAtZero: false, grid: { color: gridColor }, ticks: { color: labelColor } },
                        x: { grid: { display: false }, ticks: { color: labelColor } }
                    },
                    plugins: { 
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: 'hsl(var(--card))',
                            titleColor: 'hsl(var(--foreground))',
                            bodyColor: 'hsl(var(--foreground))',
                            borderColor: 'hsl(var(--border))',
                            borderWidth: 1,
                        }
                    }
                }
            });
        },

        updateChart(metric) {
            this.activeChartMetric = metric;
            this.renderChart();
        },
        
        formatChange(value) {
            const sign = value > 0 ? '+' : '';
            return sign + Number(value).toLocaleString();
        },

        getIconForSuggestion(type) {
            switch(type) {
                case 'topic': return 'fa-solid fa-lightbulb text-yellow-500';
                case 'performance': return 'fa-solid fa-arrow-trend-up text-green-500';
                case 'consistency': return 'fa-solid fa-calendar-days text-blue-500';
                default: return 'fa-solid fa-star text-primary';
            }
        },

        openGoalModal() {
            this.goalError = '';
            this.newGoal = { type: 'subscribers', target: null, date: '' };
            this.showGoalModal = true;
        },

        async saveGoal() {
            this.goalError = '';
            if (!this.newGoal.target || this.newGoal.target <= 0) {
                this.goalError = 'Please enter a valid target value.';
                return;
            }

            try {
                const headers = { 'Content-Type': 'application/json' };
                if (this.csrfToken) {
                    headers['X-CSRFToken'] = this.csrfToken;
                }

                const response = await fetch('/api/goals/', {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify({
                        goal_type: this.newGoal.type,
                        target_value: this.newGoal.target,
                        target_date: this.newGoal.date || null
                    })
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.error || 'Failed to save goal.');
                }

                this.showGoalModal = false;
                this.fetchData(); // Refresh dashboard to show the new goal

            } catch (error) {
                this.goalError = error.message;
            }
        }
    }
}