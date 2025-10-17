// static/js/ai_generator.js

function aiGeneratorPage() {
    return {
        // --- State Variables ---
        isLoading: false,
        loadingMessage: '',
        topic: PAGE_DATA.initialTopic || '',
        step: 'initial', // 'initial', 'titles', 'description'
        results: { titles: [], tags: { main_keywords: [], secondary_keywords: [], broad_tags: [] } }, // Correctly initialized
        selectedTitleData: null,
        generatedDescription: '',
        csrfToken: '',

        init() {
            // Flask-WTF forms automatically add a CSRF token input. We can find it.
            const csrfInput = document.querySelector('input[name="csrf_token"]');
            if (csrfInput) {
                this.csrfToken = csrfInput.value;
            }
        },

        // --- Methods ---
        async generateTitlesAndTags() {
            if (!this.topic.trim()) {
                alert('Please enter a topic for your video.');
                return;
            }
            this.isLoading = true;
            this.loadingMessage = 'Generating Titles & Tags...';

            try {
                const response = await fetch(PAGE_DATA.urls.generate, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.csrfToken 
                    },
                    body: JSON.stringify({ topic: this.topic })
                });

                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.error || 'Failed to generate content.');
                }
                
                this.results = data;
                this.step = 'titles';

            } catch (error) {
                alert('Error: ' + error.message);
                this.step = 'initial';
            } finally {
                this.isLoading = false;
            }
        },

        selectTitleAndProceed(titleData) {
            this.selectedTitleData = titleData;
            this.generatedDescription = ''; // Reset previous description
            this.step = 'description';
        },

        async generateDescription() {
            if (!this.selectedTitleData || !this.selectedTitleData.title) {
                alert('Please select a title first.');
                return;
            }
            this.isLoading = true;
            this.loadingMessage = 'Generating Description...';

            try {
                const response = await fetch(PAGE_DATA.urls.generateDescription, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.csrfToken
                    },
                    body: JSON.stringify({
                        topic: this.topic,
                        title: this.selectedTitleData.title
                    })
                });
                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.error || 'Failed to generate description.');
                }
                this.generatedDescription = data.description;

            } catch (error) {
                alert('Error: ' + error.message);
            } finally {
                this.isLoading = false;
            }
        },

        copyToClipboard(text, buttonEl) {
            if (!text) return;
            navigator.clipboard.writeText(text).then(() => {
                const originalText = buttonEl.textContent;
                buttonEl.textContent = 'Copied!';
                setTimeout(() => {
                    buttonEl.textContent = originalText;
                }, 2000);
            });
        },

        copyTags(tags, buttonEl) {
            if (!tags || tags.length === 0) return;
            this.copyToClipboard(tags.join(', '), buttonEl);
        },

        copyAllTags(buttonEl) {
            if (!this.results || !this.results.tags) return;
            const allTags = [
                ...(this.results.tags.main_keywords || []),
                ...(this.results.tags.secondary_keywords || []),
                ...(this.results.tags.broad_tags || [])
            ];
            this.copyToClipboard(allTags.join(', '), buttonEl);
        }
    }
}

document.addEventListener('alpine:init', () => {
    // Register the aiGeneratorPage component with Alpine
    Alpine.data('aiGeneratorPage', aiGeneratorPage);
});
