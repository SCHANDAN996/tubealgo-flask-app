// static/js/competitors.js

/**
 * Helper function to format ISO date strings into relative time (e.g., "5 days ago").
 */
function formatRelativeTimeAlpine(isoDate) {
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
 * Helper function to abbreviate large numbers.
 */
function abbreviateNumber(value) {
    const num = Number(value);
    if (num >= 1e6) {
        return (num / 1e6).toFixed(1) + 'M';
    }
    if (num >= 1e3) {
        return (num / 1e3).toFixed(1) + 'K';
    }
    return num.toLocaleString();
}


/**
 * Main Alpine.js data object for the competitors page.
 */
function competitorPage() {
    return {
        showConfirmModal: false,
        competitorToDelete: null,
        competitors: [],
        query: '',
        suggestions: [],
        loading: false,
        showSuggestions: false,
        activeIndex: -1,
        selectedChannelTitle: '',
        isAdding: false,
        limit: -1,
        formError: '', // Property for form error messages

        // AI Idea Generator State
        showIdeaModal: false,
        isGeneratingIdeas: false,
        ideaSourceTitle: '',
        generatedIdeas: [],

        init() {
            this.competitors = JSON.parse(document.getElementById('competitors-data').textContent);
            this.limit = COMPETITOR_LIMIT;

            this.$watch('query', (newValue) => {
                this.formError = ''; // Clear error on new input
                if (newValue !== this.selectedChannelTitle) {
                    if (this.$refs.hiddenIdInput) this.$refs.hiddenIdInput.value = '';
                    this.selectedChannelTitle = '';
                }
            });
            
            this.$el.addEventListener('confirm-delete', (event) => this.confirmDelete(event.detail));
            this.$el.addEventListener('move-competitor', (event) => this.moveCompetitor(event.detail.id, event.detail.direction));
            this.$el.addEventListener('go-to-analysis', (event) => this.goToDeepAnalysis(event.detail.data, event.detail.competitor));
            this.$el.addEventListener('generate-ideas-from', (event) => this.handleGenerateIdeas(event.detail));
        },

        get currentCount() { return this.competitors.length; },
        get limitReached() { return this.limit !== -1 && this.currentCount >= this.limit; },

        async handleAddCompetitor() {
            this.formError = ''; // Clear previous errors

            // Check if a valid channel ID has been selected.
            if (!this.$refs.hiddenIdInput.value) {
                // If there's only one suggestion and the text matches, auto-select it.
                if (this.suggestions.length === 1 && this.query.toLowerCase() === this.suggestions[0].title.toLowerCase()) {
                    this.selectSuggestion(this.suggestions[0]);
                    // A small delay to let Alpine update the hidden input's value before re-submitting.
                    setTimeout(() => this.handleAddCompetitor(), 100);
                } else {
                    this.formError = 'Please type and select a channel from the suggestion list.';
                }
                return; // Stop the submission if no valid ID is set.
            }

            if (this.isAdding) return;
            this.isAdding = true;

            const form = this.$refs.addCompetitorForm;
            const payload = {
                channel_url: this.query,
                channel_id_hidden: this.$refs.hiddenIdInput.value
            };
            
            try {
                const response = await fetch(form.action, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': form.querySelector('input[name=csrf_token]').value
                    },
                    body: JSON.stringify(payload)
                });
                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.error || 'An unknown error occurred.');
                }
                if (data.success && data.competitor) {
                    this.competitors.unshift(data.competitor);
                    this.query = '';
                    if (this.$refs.hiddenIdInput) this.$refs.hiddenIdInput.value = '';
                    this.suggestions = [];
                }
            } catch (error) {
                console.error('Error adding competitor:', error.message);
                alert('Error: ' + error.message);
            } finally {
                this.isAdding = false;
            }
        },

        fetchSuggestions() {
            if (this.query.length < 2) { this.suggestions = []; this.showSuggestions = false; return; }
            this.loading = true;
            this.showSuggestions = true;
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
            else if (event.key === 'Enter') {
                event.preventDefault(); 
                if (this.activeIndex !== -1) { 
                    this.selectSuggestion(this.suggestions[this.activeIndex]);
                } else {
                    // If user just types and hits enter, trigger form submission logic
                    this.handleAddCompetitor();
                }
            }
        },
        confirmDelete(competitorId) { this.competitorToDelete = competitorId; this.showConfirmModal = true; },
        proceedWithDelete() { 
            if (this.competitorToDelete) {
                document.getElementById(`delete-form-${this.competitorToDelete}`).submit(); 
            }
            this.showConfirmModal = false; 
        },
        moveCompetitor(id, direction) {
            const index = this.competitors.findIndex(c => c.id === id);
            if (index === -1) return;
            const otherIndex = direction === 'up' ? index - 1 : index + 1;
            if (otherIndex < 0 || otherIndex >= this.competitors.length) return;
            [this.competitors[index], this.competitors[otherIndex]] = [this.competitors[otherIndex], this.competitors[index]];
            const csrfToken = document.querySelector('form[id="add-competitor-form"] input[name=csrf_token]').value;
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
        },
        handleGenerateIdeas(title) {
            this.ideaSourceTitle = title;
            this.isGeneratingIdeas = true;
            this.generatedIdeas = [];
            this.showIdeaModal = true;

            setTimeout(() => {
                this.generatedIdeas = [
                    { title: `✅ Your UNIQUE Take on: ${title}`, description: 'This is a fresh angle for your audience.' },
                    { title: `🔥 The ULTIMATE Guide to ${title}`, description: 'A comprehensive version that can outrank the original.' },
                    { title: `🤯 We Tried "${title}" And THIS Happened!`, description: 'A reaction or challenge style video for high engagement.' }
                ];
                this.isGeneratingIdeas = false;
            }, 2000);
        },
        addIdeaToPlanner(idea) {
            alert(`"${idea.title}" has been added to your Content Planner! (Backend logic needed)`);
            this.showIdeaModal = false;
        }
    }
}

function competitorCard(competitor) {
    return {
        isLoading: true,
        isRefreshing: false,
        isRefreshed: false,
        error: null,
        data: null,
        activeSort: 'date',
        video_sets: null,
        retryTimeout: null,

        init() {
            setTimeout(() => this.fetchData(10), 500);
        },

        fetchData(retriesLeft = 0) {
            if (this.retryTimeout) clearTimeout(this.retryTimeout);

            this.isLoading = true;
            fetch(`/api/competitor/${competitor.id}/data`)
                .then(res => res.json())
                .then(apiData => {
                    if ((apiData.error || !apiData.details) && retriesLeft > 0) {
                        console.log(`Data not ready for ${competitor.channel_title}, retrying in 5 seconds... (${retriesLeft} retries left)`);
                        this.retryTimeout = setTimeout(() => this.fetchData(retriesLeft - 1), 5000);
                    } else if (apiData.error) {
                        this.error = apiData.error;
                        this.isLoading = false;
                    } else {
                        this.data = apiData;
                        this.processVideoSets();
                        this.isLoading = false;
                        this.error = null;
                    }
                })
                .catch(() => {
                    if (retriesLeft > 0) {
                        console.log(`Network error for ${competitor.channel_title}, retrying in 5 seconds...`);
                        this.retryTimeout = setTimeout(() => this.fetchData(retriesLeft - 1), 5000);
                    } else {
                        this.error = 'Failed to load data after multiple attempts.';
                        this.isLoading = false;
                    }
                });
        },
        
        refreshData() {
            this.isRefreshing = true; 
            this.isRefreshed = false;
            const csrfToken = document.querySelector('form[id="add-competitor-form"] input[name=csrf_token]').value;
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
            const processedVideos = Object.values(allVideosDict).filter(Boolean);

            this.video_sets = {
                date: [...processedVideos].sort((a, b) => new Date(b.upload_date) - new Date(a.upload_date)).slice(0, 5),
                viewCount: [...processedVideos].sort((a, b) => b.view_count - a.view_count).slice(0, 5),
                most_comments: [...processedVideos].sort((a, b) => b.comment_count - a.comment_count).slice(0, 5)
            };
        }
    }
}

document.addEventListener('alpine:init', () => {
    Alpine.data('competitorPage', competitorPage);
    Alpine.data('competitorCard', competitorCard);
});