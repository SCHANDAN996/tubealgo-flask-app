// static/js/ai_generator.js (Deep Analysis Page Specific Script)

/**
 * Helper function to format ISO date strings into relative time (e.g., "5 days ago").
 * This is duplicated here because this script runs on a different page context than competitors.js
 */
function formatRelativeTime(isoDate) {
    if (!isoDate) return '';
    const dt = new Date(isoDate); 
    const now = new Date();
    const diff = (now.getTime() - dt.getTime()) / 1000;

    if (diff < 60) return 'just now';
    const minutes = Math.floor(diff / 60);
    if (minutes < 60) return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} hour${hours > 1 ? 's' : ''} ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days} day${days > 1 ? 's' : ''} ago`;
    const months = Math.floor(days / 30);
    if (months < 12) return `${months} month${months > 1 ? 's' : ''} ago`;
    const years = Math.floor(months / 12);
    return `${years} year${years > 1 ? 's' : ''} ago`;
}


/**
 * Alpine.js data object for the deep analysis page.
 */
function deepAnalysisPage() {
    return {
        activeTab: 'overview',
        channelData: {},
        avgDailyViews: 0, // This is removed from display but kept for initial data structure
        topTags: [],
        avgStats: { views: 0, likes: 0, comments: 0 },
        playlists: [],
        uploadLabels: [],
        uploadData: [],
        videos: [], // All videos for this channel
        videoSort: 'most_recent', // 'most_recent', 'most_viewed'
        videoFilter: 'all', // 'all', 'long', 'shorts'

        init() {
            // Load preloaded data from sessionStorage
            const preloadedData = JSON.parse(sessionStorage.getItem('deepAnalysisPreload') || '{}');
            
            if (Object.keys(preloadedData).length > 0) {
                this.channelData = preloadedData.details || {};
                this.avgStats = preloadedData.avg_stats || { views: 0, likes: 0, comments: 0 };
                this.topTags = preloadedData.top_tags || [];
                this.playlists = preloadedData.playlists || [];
                
                // Parse video data
                const recentVideos = preloadedData.recent_videos_data?.videos || [];
                const mostViewedVideos = preloadedData.most_viewed_videos_data?.videos || [];
                
                // Combine and deduplicate videos
                const allVideosMap = new Map();
                [...recentVideos, ...mostViewedVideos].forEach(video => {
                    if (video && video.id) {
                        // Add video_duration_seconds for filtering
                        if (video.duration) {
                            video.duration_seconds = this.parseDuration(video.duration);
                        } else {
                            video.duration_seconds = 0; // Default or unknown duration
                        }
                        allVideosMap.set(video.id, video);
                    }
                });
                this.videos = Array.from(allVideosMap.values());


                // Chart data
                this.uploadLabels = JSON.parse(preloadedData.upload_labels || '[]');
                this.uploadData = JSON.parse(preloadedData.upload_data || '[]');

                this.$nextTick(() => {
                    this.renderUploadChart();
                });
            } else {
                console.error("Deep analysis data not found in session storage. Redirecting or showing error.");
                // Optionally redirect or fetch data from server
            }
        },

        // Helper to parse ISO 8601 duration to seconds
        parseDuration(isoDuration) {
            const matches = isoDuration.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);
            if (!matches) return 0;
            const hours = parseInt(matches[1] || '0', 10);
            const minutes = parseInt(matches[2] || '0', 10);
            const seconds = parseInt(matches[3] || '0', 10);
            return (hours * 3600) + (minutes * 60) + seconds;
        },

        renderUploadChart() {
            const ctx = document.getElementById('uploadChart').getContext('2d');
            new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: this.uploadLabels,
                    datasets: [{
                        label: 'Videos Uploaded',
                        data: this.uploadData,
                        backgroundColor: 'rgba(153, 102, 255, 0.6)', // Purple color
                        borderColor: 'rgba(153, 102, 255, 1)',
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                color: 'hsl(var(--muted-foreground))'
                            },
                            grid: {
                                color: 'hsl(var(--border))'
                            }
                        },
                        x: {
                            ticks: {
                                color: 'hsl(var(--muted-foreground))'
                            },
                            grid: {
                                color: 'hsl(var(--border))'
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    return context.dataset.label + ': ' + context.parsed.y;
                                }
                            }
                        }
                    }
                }
            });
        },

        sortVideos(criteria) {
            this.videoSort = criteria;
        },

        filterVideos(type) {
            this.videoFilter = type;
        },

        get filteredAndSortedVideos() {
            let tempVideos = [...this.videos]; // Create a copy to sort/filter

            // Filter
            if (this.videoFilter === 'long') {
                tempVideos = tempVideos.filter(video => video.duration_seconds > 60); // Longer than 60 seconds
            } else if (this.videoFilter === 'shorts') {
                tempVideos = tempVideos.filter(video => video.duration_seconds <= 60); // 60 seconds or less
            }

            // Sort
            if (this.videoSort === 'most_recent') {
                tempVideos.sort((a, b) => new Date(b.upload_date) - new Date(a.upload_date));
            } else if (this.videoSort === 'most_viewed') {
                tempVideos.sort((a, b) => b.view_count - a.view_count);
            }
            // 'top_engagement' sort has been removed due to policy violations

            return tempVideos;
        }
    }
}

// Ensure Alpine.js initializes this data component
document.addEventListener('alpine:init', () => {
    Alpine.data('deepAnalysisPage', deepAnalysisPage);
});

// Expose formatRelativeTime to global scope for use in _video_card_alpine.html snippet
window.formatRelativeTime = formatRelativeTime;