document.addEventListener('alpine:init', () => {
    Alpine.data('dashboard', () => ({
        isLoading: true,
        error: null,
        data: {},
        growthChartInstance: null,
        activeChartMetric: 'subscribers',
        
        init() {
            this.fetchData();
            // डार्क मोड में बदलाव को सुनें ताकि चार्ट फिर से रेंडर हो सके
            // Note: This requires the themeManager to dispatch an event
            window.addEventListener('theme-changed', () => {
                setTimeout(() => this.renderGrowthChart(), 50);
            });
        },

        fetchData(isRefresh = false) {
            this.isLoading = true;
            this.error = null;
            
            // Note: We use the direct URL path here because url_for() doesn't work in .js files
            fetch('/api/dashboard/main-data')
            .then(async (res) => {
                if (!res.ok) return Promise.reject(await res.json());
                return res.json();
            })
            .then(mainData => {
                this.data = mainData;
                this.$nextTick(() => {
                    this.renderGrowthChart();
                });
            }).catch(err => {
                this.error = err.error || 'Failed to load dashboard data.';
            }).finally(() => {
                this.isLoading = false;
            });
        },

        updateChart(metric) {
            this.activeChartMetric = metric;
            this.renderGrowthChart();
        },

        isNewVideo(uploadDateStr) {
            if (!uploadDateStr) return false;
            const uploadDate = new Date(uploadDateStr);
            const sixHoursAgo = new Date(Date.now() - 6 * 60 * 60 * 1000);
            return uploadDate > sixHoursAgo;
        },

        renderGrowthChart() {
            if (this.growthChartInstance) {
                this.growthChartInstance.destroy();
            }
            const ctx = this.$refs.growthChart;
            if (!ctx || !this.data.growth_chart || !this.data.growth_chart.labels) {
                return;
            }
            
            const isDarkMode = document.documentElement.classList.contains('dark');
            const textColor = isDarkMode ? '#a1a1aa' : '#6b7280';
            const gridColor = isDarkMode ? '#3f3f46' : '#e5e7eb';

            const isSubs = this.activeChartMetric === 'subscribers';
            const chartData = isSubs ? this.data.growth_chart.subscribers : this.data.growth_chart.views;
            const primaryColor = isSubs ? '#7e22ce' : '#22c55e';
            const backgroundColor = isSubs ? 'rgba(126, 34, 206, 0.2)' : 'rgba(34, 197, 94, 0.2)';
            
            const maxDataValue = Math.max(...chartData);
            const yAxisMax = maxDataValue > 5 ? maxDataValue + Math.ceil(maxDataValue * 0.2) : 10;

            this.growthChartInstance = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: this.data.growth_chart.labels,
                    datasets: [{
                        label: isSubs ? 'Subscribers' : 'Views',
                        data: chartData,
                        borderColor: primaryColor,
                        backgroundColor: backgroundColor,
                        borderWidth: 2, pointRadius: 0, pointHoverRadius: 5, fill: true, tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: { 
                        y: { 
                            beginAtZero: true, max: yAxisMax,
                            ticks: { color: textColor, precision: 0 },
                            grid: { color: gridColor }
                        },
                        x: {
                            ticks: { color: textColor },
                            grid: { display: false }
                        }
                    },
                    plugins: { 
                        legend: { display: false },
                        tooltip: { mode: 'index', intersect: false }
                    },
                    interaction: { intersect: false, mode: 'index' }
                }
            });
        }
    }));
});