// static/js/competitors.js

document.addEventListener('alpine:init', () => {
    Alpine.data('competitorPage', () => ({
        showConfirmModal: false,
        competitorToDelete: null,
        competitors: JSON.parse(document.getElementById('competitors-data').textContent),
        query: '',
        suggestions: [],
        loading: false,
        showSuggestions: false,
        activeIndex: -1,
        selectedChannelTitle: '',
        
        // --- यहाँ बदलाव किया गया है ---
        limit: COMPETITOR_LIMIT, // पहले यहाँ {{ competitor_limit }} था, जो गलत है
        // --- बदलाव खत्म ---

        get currentCount() { return this.competitors.length; },
        get limitReached() { return this.limit !== -1 && this.currentCount >= this.limit; },

        init() {
            // ... बाकी का init() फंक्शन वैसा ही रहेगा ...
            const flash = document.querySelector('.flash-warning');
            if (flash) {
                const channelId = flash.dataset.channelId;
                if (channelId) {
                    this.$nextTick(() => {
                        const card = document.getElementById(`competitor-card-${channelId}`);
                        if (card) {
                            card.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            card.classList.add('highlight-card');
                            setTimeout(() => card.classList.remove('highlight-card'), 2500);
                        }
                    });
                }
            }
            this.$watch('query', (newValue) => {
                if (newValue !== this.selectedChannelTitle) {
                    this.$refs.hiddenIdInput.value = '';
                    this.selectedChannelTitle = '';
                }
            });
            this.$el.addEventListener('confirm-delete', (event) => this.confirmDelete(event.detail));
            this.$el.addEventListener('move-competitor', (event) => this.moveCompetitor(event.detail.id, event.detail.direction));
            this.$el.addEventListener('go-to-analysis', (event) => this.goToDeepAnalysis(event.detail.data, event.detail.competitor));
        },
        fetchSuggestions() {
            if (this.query.length < 3) { this.suggestions = []; this.showSuggestions = false; return; }
            this.loading = true; this.showSuggestions = true;
            fetch(`/api/search-channels?q=${this.query}`)
                .then(res => res.json()).then(data => { this.suggestions = data; this.activeIndex = -1; })
                .finally(() => this.loading = false);
        },
        selectSuggestion(channel) {
            this.query = channel.title;
            this.selectedChannelTitle = channel.title;
            this.$refs.hiddenIdInput.value = channel.channel_id;
            this.showSuggestions = false; this.activeIndex = -1;
        },
        handleKeydown(event) {
            if (!this.showSuggestions || this.suggestions.length === 0) return;
            if (event.key === 'ArrowDown') { event.preventDefault(); this.activeIndex = (this.activeIndex + 1) % this.suggestions.length; } 
            else if (event.key === 'ArrowUp') { event.preventDefault(); this.activeIndex = (this.activeIndex - 1 + this.suggestions.length) % this.suggestions.length; } 
            else if (event.key === 'Enter') { event.preventDefault(); if (this.activeIndex !== -1) { this.selectSuggestion(this.suggestions[this.activeIndex]); } }
        },
        confirmDelete(competitorId) { this.competitorToDelete = competitorId; this.showConfirmModal = true; },
        proceedWithDelete() { if (this.competitorToDelete) { document.getElementById(`delete-form-${this.competitorToDelete}`).submit(); } this.showConfirmModal = false; },
        moveCompetitor(id, direction) {
            const index = this.competitors.findIndex(c => c.id === id);
            if (index === -1) return;
            const otherIndex = direction === 'up' ? index - 1 : index + 1;
            if (otherIndex < 0 || otherIndex >= this.competitors.length) return;
            [this.competitors[index], this.competitors[otherIndex]] = [this.competitors[otherIndex], this.competitors[index]];
            const csrfToken = document.querySelector('form#add-competitor-form input[name=csrf_token]').value;
            fetch(`/competitors/move/${id}/${direction}`, {
                method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }
            }).then(res => res.json()).then(data => {
                if (!data.success) {
                    [this.competitors[index], this.competitors[otherIndex]] = [this.competitors[otherIndex], this.competitors[index]];
                    alert('Could not update position. Please refresh.');
                }
            });
        },
        goToDeepAnalysis(cardData, competitor) {
            sessionStorage.setItem('deepAnalysisPreload', JSON.stringify(cardData));
            window.location.href = `/deep-analysis/${competitor.channel_id_youtube}`;
        }
    }));

    Alpine.data('competitorCard', (competitor) => ({
        // ... competitorCard का कोड वैसा ही रहेगा ...
        isLoading: true, isRefreshing: false, isRefreshed: false, error: null, data: null,
        activeSort: 'date',
        video_sets: null,

        init() { this.fetchData(); },
        fetchData() {
            this.isLoading = true;
            fetch(`/api/competitor/${competitor.id}/data`)
                .then(res => res.json())
                .then(apiData => {
                    if (apiData.error) { this.error = apiData.error; } 
                    else { this.data = apiData; this.processVideoSets(); }
                })
                .catch(() => this.error = 'Failed to load data.')
                .finally(() => this.isLoading = false);
        },
        refreshData() {
            this.isRefreshing = true; this.isRefreshed = false;
            const csrfToken = document.querySelector('form#add-competitor-form input[name=csrf_token]').value;
            fetch(`/api/competitor/${competitor.id}/refresh`, { method: 'POST', headers: { 'X-CSRFToken': csrfToken } })
                .then(res => res.json())
                .then(apiData => {
                    if (apiData.error) { this.error = apiData.error; } 
                    else { this.data = apiData; this.processVideoSets(); this.isRefreshed = true; }
                })
                .catch(() => this.error = 'Failed to refresh data.')
                .finally(() => this.isRefreshing = false);
        },
        processVideoSets() {
            const videosByDate = this.data.recent_videos_data.videos || [];
            const videosByViews = this.data.most_viewed_videos_data.videos || [];
            
            const allVideosDict = {};
            [...videosByDate, ...videosByViews].forEach(v => { if (v && v.id) allVideosDict[v.id] = v; });

            const processedVideos = Object.values(allVideosDict).map(video => {
                if (video && video.upload_date) {
                    const uploadDate = new Date(video.upload_date);
                    const daysSinceUpload = (new Date() - uploadDate) / (1000 * 3600 * 24);
                    video.views_per_day = daysSinceUpload > 0 ? (video.view_count / daysSinceUpload) : video.view_count;
                } else if (video) { video.views_per_day = 0; }
                return video;
            }).filter(Boolean);

            this.video_sets = {
                date: [...processedVideos].sort((a, b) => new Date(b.upload_date) - new Date(a.upload_date)).slice(0, 5),
                viewCount: [...processedVideos].sort((a, b) => b.view_count - a.view_count).slice(0, 5),
                views_per_day: [...processedVideos].sort((a, b) => (b.views_per_day || 0) - (a.views_per_day || 0)).slice(0, 5),
                most_comments: [...processedVideos].sort((a, b) => b.comment_count - a.comment_count).slice(0, 5)
            };
        }
    }));
});

function formatRelativeTimeAlpine(isoDate) {
    if (!isoDate) return '';
    const dt = new Date(isoDate); const now = new Date(); const diff = (now.getTime() - dt.getTime()) / 1000;
    if (diff < 60) return 'just now'; const minutes = Math.floor(diff / 60); if (minutes < 60) return `${minutes} minute${minutes > 1 ? 's' : ''} ago`; const hours = Math.floor(minutes / 60); if (hours < 24) return `${hours} hour${hours > 1 ? 's' : ''} ago`; const days = Math.floor(hours / 24); if (days < 30) return `${days} day${days > 1 ? 's' : ''} ago`; const months = Math.floor(days / 30); if (months < 12) return `${months} month${months > 1 ? 's' : ''} ago`; const years = Math.floor(months / 12); return `${years} year${years > 1 ? 's' : ''} ago`;
}