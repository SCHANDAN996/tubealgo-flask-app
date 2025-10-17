// static/js/planner.js

function contentPlanner() {
    return {
        // State for Planner Board
        plannerData: { idea: [], scripting: [], filming: [], editing: [], scheduled: [] },
        newIdeaTitle: '',
        ideaEntryMode: 'button', // 'button', 'manual'
        
        plannerColumns: [
            { id: 'idea', title: 'Ideas', icon: '💡' },
            { id: 'scripting', title: 'Scripting', icon: '✍️' },
            { id: 'filming', title: 'Filming', icon: '🎬' },
            { id: 'editing', title: 'Editing', icon: '✂️' },
            { id: 'scheduled', title: 'Scheduled', icon: '🗓️' }
        ],
        columnColors: {
            idea: 'border-purple-500',
            scripting: 'border-blue-500',
            filming: 'border-orange-500',
            editing: 'border-teal-500',
            scheduled: 'border-green-500'
        },
        
        // State for Modals & Editing
        isEditModalOpen: false,
        editingIdea: { id: null, title: '', display_title: '', notes: '' },
        editingIdeaStatus: null,
        editModalTab: 'write',
        editModalCopyText: 'Copy Script',

        // State for custom delete modal
        showDeleteConfirmModal: false,
        ideaToDelete: null,
        
        // State for AI Generator
        isGeneratorOpen: false,
        generatorStep: 'input', 
        isGeneratorLoading: false,
        generatorTopic: '',
        generatorDescription: '', 
        generatorLanguage: 'English',
        generatorVideoType: 'any', // <<< बदलाव यहाँ है: यह लाइन जोड़ी गई है
        generatedIdeas: [],
        currentIdeaIndex: 0,
        copyButtonText: 'Copy Script',

        // State for dynamic loading screen
        loadingStepMessage: '',
        loadingInterval: null,
        loadingSteps: [
            'Analyzing your topic...',
            'Brainstorming viral angles...',
            'Checking competitor trends...',
            'Structuring the script outline...',
            'Adding a touch of creativity...',
            'Finalizing the ideas...'
        ],
        
        csrfToken: '',

        // Main Initialization
        init() {
            this.csrfToken = document.querySelector('input[name="csrf_token"]').value;
            this.loadFromCache();
            this.fetchIdeas();
        },
        
        // Caching Logic
        loadFromCache() {
            const cachedData = localStorage.getItem('plannerData');
            if (cachedData) { this.plannerData = JSON.parse(cachedData); }
            this.$nextTick(() => this.initSortable());
        },

        saveToCache() {
            localStorage.setItem('plannerData', JSON.stringify(this.plannerData));
        },

        // API Calls for Planner Board
        fetchIdeas() {
            fetch(PAGE_DATA.urls.getIdeas)
                .then(res => res.json())
                .then(data => {
                    this.plannerData = data;
                    this.saveToCache();
                    this.$nextTick(() => this.initSortable());
                });
        },

        addNewIdea() {
            if (this.newIdeaTitle.trim() === '') return;
            const payload = { title: this.newIdeaTitle.trim(), notes: '' };
            this.newIdeaTitle = '';
            this.ideaEntryMode = 'button';
            
            fetch(PAGE_DATA.urls.createIdea, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': this.csrfToken },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(newIdea => {
                if (!this.plannerData.idea) this.plannerData.idea = [];
                this.plannerData.idea.push(newIdea);
                this.saveToCache();
            });
        },

        deleteIdea(id, status) {
            this.ideaToDelete = { id, status };
            this.showDeleteConfirmModal = true;
        },

        proceedWithDelete() {
            if (!this.ideaToDelete) return;
            const { id, status } = this.ideaToDelete;
            
            this.plannerData[status] = this.plannerData[status].filter(idea => idea.id !== id);
            this.saveBoardState();

            fetch(`${PAGE_DATA.urls.deleteIdeaBase}/${id}`, { 
                method: 'DELETE',
                headers: { 'X-CSRFToken': this.csrfToken }
            });
            
            this.showDeleteConfirmModal = false;
            this.ideaToDelete = null;
        },

        editIdea(idea, status) {
            this.editingIdea = { ...idea };
            this.editingIdeaStatus = status;
            this.editModalTab = 'write';
            this.isEditModalOpen = true;
        },

        saveIdea() {
            if (!this.editingIdea) return;
            const payload = { 
                title: this.editingIdea.title,
                display_title: this.editingIdea.display_title,
                notes: this.editingIdea.notes 
            };

            fetch(`${PAGE_DATA.urls.updateIdeaBase}/${this.editingIdea.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': this.csrfToken },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(updatedIdea => {
                const index = this.plannerData[this.editingIdeaStatus].findIndex(idea => idea.id === updatedIdea.id);
                if (index > -1) {
                    this.plannerData[this.editingIdeaStatus][index] = updatedIdea;
                    this.saveToCache();
                }
                this.isEditModalOpen = false;
            });
        },

        moveCard(idea, fromStatus, direction) {
            const statuses = this.plannerColumns.map(c => c.id);
            const fromIndex = statuses.indexOf(fromStatus);
            let toIndex = direction === 'next' ? fromIndex + 1 : fromIndex - 1;

            if (toIndex < 0 || toIndex >= statuses.length) return;
            const toStatus = statuses[toIndex];

            const cardIndex = this.plannerData[fromStatus].findIndex(i => i.id === idea.id);
            if (cardIndex > -1) {
                this.plannerData[fromStatus].splice(cardIndex, 1);
            }

            if (!this.plannerData[toStatus]) this.plannerData[toStatus] = [];
            this.plannerData[toStatus].push(idea);
            
            this.saveBoardState();
        },
        
        saveBoardState() {
            this.saveToCache();
            const backendPayload = {};
            this.plannerColumns.forEach(column => {
                if (this.plannerData[column.id]) {
                   backendPayload[column.id] = this.plannerData[column.id].map(idea => idea.id);
                }
            });
            
            fetch(PAGE_DATA.urls.moveIdea, { 
                method: 'POST', 
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': this.csrfToken }, 
                body: JSON.stringify(backendPayload) 
            });
        },

        copyEditScript() {
            const ideaToCopy = this.editingIdea;
            if (!ideaToCopy) return;
            const fullText = `# ${ideaToCopy.title}\n\n${ideaToCopy.notes || ''}`;
            navigator.clipboard.writeText(fullText).then(() => {
                this.editModalCopyText = 'Copied!';
                setTimeout(() => { this.editModalCopyText = 'Copy Script'; }, 2000);
            });
        },

        // AI Generator Functions
        openGeneratorModal() {
            this.generatorStep = 'input';
            this.isGeneratorOpen = true;
            this.generatedIdeas = [];
            this.currentIdeaIndex = 0;
            this.generatorTopic = '';
            this.generatorDescription = '';
        },

        fetchGeneratedIdeas(forceRefresh = false, newLanguage = null) {
            if (newLanguage) { this.generatorLanguage = newLanguage; }
            if (!this.generatorTopic.trim()) { alert('Please enter a topic.'); return; }
            
            const cacheKey = `ideas_${this.generatorVideoType}_${this.generatorLanguage}_${this.generatorTopic.toLowerCase().trim()}_${this.generatorDescription.toLowerCase().trim()}`;
            if (!forceRefresh) {
                const cachedIdeas = localStorage.getItem(cacheKey);
                if (cachedIdeas) {
                    this.generatedIdeas = JSON.parse(cachedIdeas);
                    this.currentIdeaIndex = 0;
                    this.generatorStep = 'results';
                    return;
                }
            }
            
            this.isGeneratorLoading = true;
            this.generatorStep = 'results';
            let stepIndex = 0;
            this.loadingStepMessage = this.loadingSteps[stepIndex];
            this.loadingInterval = setInterval(() => {
                stepIndex = (stepIndex + 1) % this.loadingSteps.length;
                this.loadingStepMessage = this.loadingSteps[stepIndex];
            }, 1800);

            fetch(PAGE_DATA.urls.generateIdeas, {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                },
                body: JSON.stringify({ 
                    topic: this.generatorTopic, 
                    language: this.generatorLanguage,
                    description: this.generatorDescription,
                    video_type: this.generatorVideoType
                })
            })
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    alert(`Error: ${data.error}`);
                    this.generatorStep = 'input';
                } else {
                    this.generatedIdeas = data.ideas;
                    this.currentIdeaIndex = 0;
                    localStorage.setItem(cacheKey, JSON.stringify(data.ideas));
                }
            })
            .catch(err => {
                alert('An unexpected error occurred.');
                this.generatorStep = 'input';
            })
            .finally(() => { 
                this.isGeneratorLoading = false; 
                clearInterval(this.loadingInterval);
                this.loadingInterval = null;
                this.loadingStepMessage = '';
            });
        },
        
        nextIdea() {
            if (this.currentIdeaIndex < this.generatedIdeas.length - 1) { this.currentIdeaIndex++; }
        },

        previousIdea() {
            if (this.currentIdeaIndex > 0) { this.currentIdeaIndex--; }
        },

        saveIdeaToPlanner() {
            const ideaToSave = this.generatedIdeas[this.currentIdeaIndex];
            if (!ideaToSave) return;
            const payload = { 
                title: ideaToSave.title, 
                notes: ideaToSave.outline 
            };
            
            fetch(PAGE_DATA.urls.createIdea, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': this.csrfToken },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(newIdea => {
                if (!this.plannerData.idea) this.plannerData.idea = [];
                this.plannerData.idea.push(newIdea);
                this.saveToCache();
                this.isGeneratorOpen = false;
            });
        },

        copyScript() {
            const ideaToCopy = this.generatedIdeas[this.currentIdeaIndex];
            if (!ideaToCopy) return;
            const fullText = `# ${ideaToCopy.title}\n\n${ideaToCopy.outline}`;
            navigator.clipboard.writeText(fullText).then(() => {
                this.copyButtonText = 'Copied!';
                setTimeout(() => { this.copyButtonText = 'Copy Script'; }, 2000);
            });
        },
        
        initSortable() {
            const columnElements = this.$el.querySelectorAll('[x-ref="plannerColumn"]');
            columnElements.forEach(columnEl => {
                if (columnEl._sortable) columnEl._sortable.destroy();
                new Sortable(columnEl, {
                    group: 'planner', 
                    animation: 150, 
                    ghostClass: 'bg-primary/20',
                    handle: '.drag-handle',
                    onEnd: (evt) => {
                        const allIdeas = Object.values(this.plannerData).flat().reduce((acc, idea) => {
                            if(idea) acc[idea.id] = idea;
                            return acc;
                        }, {});
                        const newData = { idea: [], scripting: [], filming: [], editing: [], scheduled: [] };
                        this.$el.querySelectorAll('[x-ref="plannerColumn"]').forEach(colEl => {
                            const status = colEl.dataset.status;
                            const ideaIds = Array.from(colEl.children).map(child => child.dataset.id);
                            newData[status] = ideaIds.map(id => allIdeas[id]).filter(Boolean);
                        });
                        this.plannerData = newData;
                        this.saveBoardState();
                    }
                });
            });
        }
    }
}