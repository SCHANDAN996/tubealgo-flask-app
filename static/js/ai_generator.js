// static/js/ai_generator.js

function aiGeneratorPage() {
    return {
        step: 'initial', // 'initial', 'titles', 'description'
        topic: PAGE_DATA.initialTopic,
        results: null,
        selectedTitle: '',
        isLoading: false,
        loadingMessage: '',
        generatedDescription: '',

        async generateTitlesAndTags() {
            if (!this.topic.trim()) { alert("Please enter a topic."); return; }
            const cacheKey = `ai_copilot_titles_${this.topic.trim().toLowerCase()}`;
            const cachedResult = localStorage.getItem(cacheKey);
            if(cachedResult) {
                this.results = JSON.parse(cachedResult);
                this.step = 'titles';
                return;
            }

            this.isLoading = true;
            this.loadingMessage = 'Generating Titles & Tags...';
            try {
                const response = await fetch(PAGE_DATA.urls.generate, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ topic: this.topic })
                });
                if (!response.ok) throw new Error('Network response was not ok.');
                const data = await response.json();
                if (data.error) throw new Error(data.error);
                this.results = data;
                this.step = 'titles';
                localStorage.setItem(cacheKey, JSON.stringify(data));
            } catch (error) {
                alert('An error occurred: ' + error.message);
                this.results = null;
            } finally {
                this.isLoading = false;
            }
        },

        selectTitleAndProceed(titleData) {
            this.topic = titleData.title;
            this.selectedTitle = titleData.title;
            this.step = 'description';
            this.generatedDescription = ''; // Reset previous description
        },

        async generateDescription() {
            if (!this.selectedTitle) return;
            this.isLoading = true;
            this.loadingMessage = 'Generating Description...';
            try {
                const response = await fetch(PAGE_DATA.urls.generateDescription, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ topic: this.topic, title: this.selectedTitle })
                });
                if (!response.ok) throw new Error('Network response was not ok.');
                const data = await response.json();
                if (data.error) throw new Error(data.error.details || data.error);
                this.generatedDescription = data.description;
            } catch (error) {
                alert('An error occurred: ' + error.message);
            } finally {
                this.isLoading = false;
            }
        },

        copyTags(tags, btn) { this.copyToClipboard(tags.join(', '), btn); },
        
        copyAllTags(btn) {
            if (!this.results || !this.results.tags) return;
            const allTags = [
                ...(this.results.tags.main_keywords || []),
                ...(this.results.tags.secondary_keywords || []),
                ...(this.results.tags.broad_tags || [])
            ];
            this.copyToClipboard(allTags.join(', '), btn);
        },

        copyToClipboard(text, btn) {
            if (!text || text.trim() === '') return;
            navigator.clipboard.writeText(text.trim()).then(() => {
                const originalText = btn.innerHTML;
                btn.innerHTML = 'Copied!';
                setTimeout(() => { btn.innerHTML = originalText; }, 2000);
            });
        }
    }
}