// static/js/planner.js

function contentPlanner() {
    return {
        plannerData: { idea: [], scripting: [], filming: [], editing: [], scheduled: [] },
        newIdeaTitle: '',
        plannerColumns: [
            { id: 'idea', title: '💡 Ideas' }, { id: 'scripting', title: '✍️ Scripting' },
            { id: 'filming', title: '🎬 Filming' }, { id: 'editing', title: '✂️ Editing' },
            { id: 'scheduled', title: '🗓️ Scheduled' }
        ],
        isEditModalOpen: false, 
        editingIdea: null, 
        editingIdeaStatus: null,
        
        init() {
            this.fetchIdeas();
        },
        
        fetchIdeas() {
            fetch(PAGE_DATA.urls.getIdeas)
                .then(res => res.json())
                .then(data => {
                    this.plannerData = data;
                    this.$nextTick(() => this.initSortable());
                });
        },

        addNewIdea() {
            if (this.newIdeaTitle.trim() === '') return;
            
            fetch(PAGE_DATA.urls.createIdea, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: this.newIdeaTitle })
            })
            .then(res => res.json())
            .then(newIdea => {
                this.plannerData.idea.push(newIdea);
                this.newIdeaTitle = '';
            });
        },

        deleteIdea(id, status) {
            if (!confirm('Are you sure you want to delete this idea?')) return;

            fetch(`${PAGE_DATA.urls.deleteIdeaBase}/${id}`, { method: 'DELETE' })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    const index = this.plannerData[status].findIndex(idea => idea.id === id);
                    if (index > -1) {
                        this.plannerData[status].splice(index, 1);
                    }
                }
            });
        },

        editIdea(idea, status) {
            this.editingIdea = { ...idea };
            this.editingIdeaStatus = status;
            this.isEditModalOpen = true;
        },

        saveIdea() {
            if (!this.editingIdea) return;

            fetch(`${PAGE_DATA.urls.updateIdeaBase}/${this.editingIdea.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: this.editingIdea.title })
            })
            .then(res => res.json())
            .then(updatedIdea => {
                const index = this.plannerData[this.editingIdeaStatus].findIndex(idea => idea.id === updatedIdea.id);
                if (index > -1) {
                    this.plannerData[this.editingIdeaStatus][index] = updatedIdea;
                }
                this.isEditModalOpen = false;
            });
        },
        
        initSortable() {
            this.$refs.plannerColumn.forEach(columnEl => {
                if (columnEl._sortable) columnEl._sortable.destroy();
                
                new Sortable(columnEl, {
                    group: 'planner', 
                    animation: 150, 
                    ghostClass: 'bg-primary/20',
                    onEnd: () => {
                        let payload = {};
                        this.plannerColumns.forEach(col => {
                            const container = this.$el.querySelector(`[data-status="${col.id}"]`);
                            payload[col.id] = Array.from(container.children).map(child => child.dataset.id);
                        });
                        
                        fetch(PAGE_DATA.urls.moveIdea, { 
                            method: 'POST', 
                            headers: { 'Content-Type': 'application/json' }, 
                            body: JSON.stringify(payload) 
                        });
                    }
                });
            });
        }
    }
}