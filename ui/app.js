
class ConfigUI {
    constructor() {
        this.config = {};
        this.schema = [];
        this.categorized = {};
        this.currentTab = 'dashboard';
        this.mainServerRunning = false;
        this.agentStatus = null;
        this.webhookListening = false;
        this.webhookUrl = '';
        this.pollingIntervals = {};
        this.allCalls = [];
        this.filteredCalls = [];
        this.currentPage = 1;
        this.itemsPerPage = 20;
        this.agentType = 'bundled';

        this.liveTranscriptPollInterval = null;
        this.liveTranscriptAutoCloseTimer = null;
        this.liveTranscriptLastIndex = 0;
        this.liveTranscriptCallId = null;
        this.init();
    }

    async init() {

        this.setupLoginDialog();


        const authenticated = await this.checkAuthOnInit();
        if (!authenticated) {

            this.showLoginModal();
            return;
        }


        this.hideLoginModal();

        this.setupNavigation();
        await this.loadConfig();
        await this.loadSections();
        this.setupFormHandlers();
        this.startPolling();
        this.setupModalClose();

        this.switchTab('dashboard');


        this.startTokenRefreshTimer();


        this.loadAgentType();
    }

    setupNavigation() {
        const tabButtons = document.querySelectorAll('.tab-button');
        tabButtons.forEach(button => {
            button.addEventListener('click', () => {
                const tab = button.dataset.tab;
                this.switchTab(tab);
            });
        });
    }

    switchTab(tab) {

        document.querySelectorAll('.tab-button').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelector(`[data-tab="${tab}"]`).classList.add('active');


        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });
        document.getElementById(`${tab}-screen`).classList.add('active');

        this.currentTab = tab;


        if (tab === 'about') {
            this.loadAbout();
        } else if (tab === 'dashboard') {
            this.loadDashboard();
        } else if (tab === 'call-history') {
            this.loadCallHistory();
        } else if (tab === 'modules') {
            this.loadModules();
        }
    }

    async loadConfig() {
        try {
            const response = await fetch('/api/config');
            const data = await response.json();
            this.config = data.config;
            this.schema = data.schema;
            this.categorized = data.categorized;
            this.renderConfigForm();
        } catch (error) {
            this.showMessage('Failed to load configuration', 'error');
            console.error('Error loading config:', error);
        }
    }

    renderConfigForm() {
        const container = document.getElementById('config-screen');
        let html = '<form class="config-form" id="config-form">';


        html += `<div class="button-group" style="margin-bottom: 2rem;">
            <button type="button" class="btn btn-primary" onclick="configUI.saveConfig()">Save Configuration</button>
        </div>`;


        html += '<div class="config-categories-container">';


        for (const [category, fields] of Object.entries(this.categorized)) {
            html += `<div class="config-category">
                <h3>${category}</h3>`;

            fields.forEach(field => {
                const value = this.config[field.name] || field.default || '';
                html += this.renderField(field, value);


                if (field.name === 'GOOGLE_SHEET_ID') {
                    html += `<div class="config-field" style="margin-top: -10px; margin-bottom: 15px;">
                        <button type="button" class="btn btn-secondary btn-sm" onclick="configUI.openGoogleSheet()" style="width: 100%;">
                            📊 Open Google Sheet
                        </button>
                    </div>`;
                }
            });

            html += '</div>';
        }


        html += '</div>';
        html += '</form>';
        container.innerHTML = html;


        this.loadSelectFieldOptions();


        this.loadLocalIP();
    }

    async loadLocalIP() {
        try {
            const response = await fetch('/api/local-ip');
            const data = await response.json();


            const localIpField = document.getElementById('LOCAL_IP');
            if (localIpField && data.local_ip) {
                localIpField.value = data.local_ip;
            }
        } catch (error) {
            console.error('Error loading local IP:', error);
        }
    }

    async loadSelectFieldOptions() {


        const selectFields = document.querySelectorAll('select[data-field-type="select"][data-options-url]:not([data-options-url=""])');

        for (const select of selectFields) {
            const optionsUrl = select.getAttribute('data-options-url');
            const optionsKey = select.getAttribute('data-options-key');
            const optionsLabel = select.getAttribute('data-options-label') || 'name';
            const optionsValue = select.getAttribute('data-options-value') || 'name';
            const fieldName = select.id;
            const currentValue = this.config[fieldName] || '';

            if (!optionsUrl || !optionsKey) {
                continue;
            }

            try {
                const response = await fetch(optionsUrl);
                const data = await response.json();


                const options = data[optionsKey] || [];


                select.innerHTML = '';


                const defaultOption = document.createElement('option');
                defaultOption.value = '';
                defaultOption.textContent = 'Default (System Default)';
                if (currentValue === '' || currentValue === null) {
                    defaultOption.selected = true;
                }
                select.appendChild(defaultOption);


                options.forEach(option => {
                    const optionElement = document.createElement('option');
                    const label = option[optionsLabel] || option.name || String(option);
                    const optionValue = option[optionsValue] || option.name || String(option);
                    optionElement.value = optionValue;
                    optionElement.textContent = `${label} (${option.channels_in || 0} in, ${option.channels_out || 0} out)`;


                    if (currentValue === optionValue || currentValue === label) {
                        optionElement.selected = true;
                    }

                    select.appendChild(optionElement);
                });
            } catch (error) {
                console.error(`Error loading options for ${fieldName}:`, error);

                select.innerHTML = '<option value="">Error loading options</option>';
            }
        }
    }

    renderField(field, value) {
        let html = `<div class="config-field">
            <label for="${field.name}">${field.name}</label>`;

        if (field.readonly) {

            html += `<input type="text"
                id="${field.name}"
                name="${field.name}"
                value="${value}"
                readonly
                style="background-color: #f5f5f5; cursor: not-allowed;"
                placeholder="${field.default || ''}">`;
        } else if (field.type === 'boolean') {
            const checked = value === 'true' || value === '1' || value === 'yes' || (value === '' && field.default === 'true');
            html += `<select id="${field.name}" name="${field.name}">
                <option value="true" ${checked ? 'selected' : ''}>True</option>
                <option value="false" ${!checked ? 'selected' : ''}>False</option>
            </select>`;
        } else if (field.type === 'select') {

            if (field.options && Array.isArray(field.options) && field.options.length > 0) {

                html += `<select id="${field.name}" name="${field.name}" data-field-type="select">`;
                field.options.forEach(option => {
                    const optionValue = option.value || option;
                    const optionLabel = option.label || option.value || option;
                    const isSelected = (value === optionValue || (value === '' && optionValue === field.default)) ? 'selected' : '';
                    html += `<option value="${optionValue}" ${isSelected}>${optionLabel}</option>`;
                });
                html += `</select>`;
            } else {

                html += `<select id="${field.name}" name="${field.name}" data-field-type="select" data-options-url="${field.options_url || ''}" data-options-key="${field.options_key || ''}" data-options-label="${field.options_label || 'name'}" data-options-value="${field.options_value || 'name'}">
                    <option value="">Loading options...</option>
                </select>`;
            }
        } else if (field.type === 'integer' || field.type === 'float') {
            html += `<input type="number"
                id="${field.name}"
                name="${field.name}"
                value="${value}"
                ${field.validation?.min !== undefined ? `min="${field.validation.min}"` : ''}
                ${field.validation?.max !== undefined ? `max="${field.validation.max}"` : ''}
                step="${field.type === 'float' ? '0.1' : '1'}">`;
        } else if (field.name.includes('URL') || field.name.includes('PATH')) {
            html += `<input type="text"
                id="${field.name}"
                name="${field.name}"
                value="${value}"
                placeholder="${field.default || ''}">`;
        } else {
            html += `<input type="text"
                id="${field.name}"
                name="${field.name}"
                value="${value}"
                placeholder="${field.default || ''}">`;
        }

        html += `<div class="help-text">${field.description || ''}</div>`;
        html += `<div class="error-text" id="error-${field.name}" style="display: none;"></div>`;
        html += '</div>';

        return html;
    }

    async loadSections() {
        const sections = ['instructions', 'help', 'credits', 'dashboard', 'call-history'];
        for (const section of sections) {
            try {
                const response = await fetch(`/sections/${section}.html`);
                if (response.ok) {
                    const html = await response.text();
                    document.getElementById(`${section}-screen`).innerHTML = html;
                }
            } catch (error) {
                console.error(`Error loading ${section}:`, error);
            }
        }
    }

    async loadDashboard() {

        await this.updateDashboard();
        await this.checkWebhookStatus();
    }

    async loadCallHistory() {

        const transcriptModal = document.getElementById('transcript-modal');
        if (transcriptModal) {
            transcriptModal.style.display = 'none';
        }


        document.getElementById('call-history-loading').style.display = 'block';
        document.getElementById('call-history-empty').style.display = 'none';
        document.getElementById('call-history-content').style.display = 'none';

        try {

            const response = await fetch('/api/call-history?limit=10000');
            const data = await response.json();

            document.getElementById('call-history-loading').style.display = 'none';

            if (!data.calls || data.calls.length === 0) {
                document.getElementById('call-history-empty').style.display = 'block';
                this.allCalls = [];
                this.filteredCalls = [];
                return;
            }

            this.allCalls = data.calls;
            this.currentPage = 1;
            this.filterCallHistory();
        } catch (error) {
            console.error('Error loading call history:', error);
            document.getElementById('call-history-loading').style.display = 'none';
            document.getElementById('call-history-empty').style.display = 'block';
            document.getElementById('call-history-empty').innerHTML =
                '<p>Error loading call history. Please try again.</p>';
        }
    }

    filterCallHistory() {
        const searchTerm = (document.getElementById('call-history-search')?.value || '').toLowerCase();
        const dateFrom = document.getElementById('call-history-date-from')?.value || '';
        const dateTo = document.getElementById('call-history-date-to')?.value || '';

        this.filteredCalls = this.allCalls.filter(call => {

            if (searchTerm) {
                const searchableText = [
                    call.phone_number || '',
                    call.client_name || '',
                    call.client_code || '',
                    call.summary || ''
                ].join(' ').toLowerCase();

                if (!searchableText.includes(searchTerm)) {
                    return false;
                }
            }


            if (dateFrom || dateTo) {
                const callDate = new Date(call.start_time);
                const fromDate = dateFrom ? new Date(dateFrom) : null;
                const toDate = dateTo ? new Date(dateTo + 'T23:59:59') : null;

                if (fromDate && callDate < fromDate) {
                    return false;
                }
                if (toDate && callDate > toDate) {
                    return false;
                }
            }

            return true;
        });

        this.currentPage = 1;
        this.renderCallHistoryTable();
    }

    clearCallHistoryFilters() {
        document.getElementById('call-history-search').value = '';
        document.getElementById('call-history-date-from').value = '';
        document.getElementById('call-history-date-to').value = '';
        this.filterCallHistory();
    }

    previousCallHistoryPage() {
        if (this.currentPage > 1) {
            this.currentPage--;
            this.renderCallHistoryTable();
        }
    }

    nextCallHistoryPage() {
        const totalPages = Math.ceil(this.filteredCalls.length / this.itemsPerPage);
        if (this.currentPage < totalPages) {
            this.currentPage++;
            this.renderCallHistoryTable();
        }
    }

    renderCallHistoryTable() {
        const tbody = document.getElementById('call-history-table-body');
        tbody.innerHTML = '';


        const totalPages = Math.ceil(this.filteredCalls.length / this.itemsPerPage);
        const startIndex = (this.currentPage - 1) * this.itemsPerPage;
        const endIndex = startIndex + this.itemsPerPage;
        const pageCalls = this.filteredCalls.slice(startIndex, endIndex);


        document.getElementById('call-history-page').textContent = this.currentPage;
        document.getElementById('call-history-total-pages').textContent = totalPages || 1;
        document.getElementById('call-history-prev').disabled = this.currentPage <= 1;
        document.getElementById('call-history-next').disabled = this.currentPage >= totalPages;


        const countText = `Showing ${startIndex + 1}-${Math.min(endIndex, this.filteredCalls.length)} of ${this.filteredCalls.length} calls`;
        document.getElementById('call-history-count').textContent = countText;


        if (this.filteredCalls.length === 0) {
            document.getElementById('call-history-content').style.display = 'none';
            document.getElementById('call-history-empty').style.display = 'block';
            document.getElementById('call-history-empty').innerHTML =
                '<p>No calls match your filters.</p>';
            return;
        }

        document.getElementById('call-history-content').style.display = 'block';
        document.getElementById('call-history-empty').style.display = 'none';


        pageCalls.forEach(call => {
            const row = document.createElement('tr');


            const startDate = new Date(call.start_time);
            const dateStr = startDate.toLocaleDateString();
            const timeStr = startDate.toLocaleTimeString();


            const duration = call.duration || 0;
            const minutes = Math.floor(duration / 60);
            const seconds = Math.floor(duration % 60);
            const durationStr = `${minutes}m ${seconds}s`;


            const rating = call.rating || {numeric: 3, text: 'Neutral'};
            const ratingStr = `${rating.numeric}/5 - ${rating.text}`;

            row.innerHTML = `
                <td>${dateStr}<br><small>${timeStr}</small></td>
                <td>${this.escapeHtml(call.phone_number || '')}</td>
                <td>${this.escapeHtml(call.client_code || '')}</td>
                <td>${this.escapeHtml(call.client_name || '')}</td>
                <td>${durationStr}</td>
                <td class="summary-cell">${this.escapeHtml(call.summary || 'No summary')}</td>
                <td><span class="mood-badge mood-${(call.mood || 'neutral').toLowerCase()}">${this.escapeHtml(call.mood || 'neutral')}</span></td>
                <td>${ratingStr}</td>
                <td>
                    <button class="btn btn-sm btn-primary" onclick="configUI.viewTranscript('${call.call_id}')">
                        View Transcript
                    </button>
                </td>
            `;
            tbody.appendChild(row);
        });
    }

    async refreshCallHistory() {
        await this.loadCallHistory();

        if (this.currentTab === 'dashboard') {
            await this.updateStats();
        }
    }

    async viewTranscript(callId) {

        if (this.liveTranscriptPollInterval) {
            clearInterval(this.liveTranscriptPollInterval);
            this.liveTranscriptPollInterval = null;
        }

        const modal = document.getElementById('transcript-modal');
        const loading = document.getElementById('transcript-loading');
        const content = document.getElementById('transcript-content');

        if (!modal || !loading || !content) {
            console.error('Missing elements for transcript modal');
            return;
        }

        modal.style.display = 'block';
        loading.style.display = 'block';
        content.style.display = 'none';

        try {
            const response = await fetch(`/api/call-history/${callId}`);
            const callData = await response.json();


            document.getElementById('transcript-call-id').textContent = callData.call_id || '';

            const startDate = new Date(callData.start_time);
            document.getElementById('transcript-start-time').textContent =
                startDate.toLocaleString();

            const duration = callData.duration_seconds || 0;
            const minutes = Math.floor(duration / 60);
            const seconds = Math.floor(duration % 60);
            document.getElementById('transcript-duration').textContent =
                `${minutes}m ${seconds}s`;

            const client = callData.client || {};
            document.getElementById('transcript-client').textContent =
                `${client.name || ''} (${client.client_code || ''}) - ${client.phone_number || ''}`;

            document.getElementById('transcript-summary').textContent =
                callData.summary || 'No summary available';

            document.getElementById('transcript-mood').textContent =
                callData.mood || 'unknown';

            const rating = callData.rating || {numeric: 3, text: 'Neutral'};
            document.getElementById('transcript-rating').textContent =
                `${rating.numeric}/5 - ${rating.text}`;


            const conversationDiv = document.getElementById('transcript-conversation');
            conversationDiv.innerHTML = '';

            if (callData.transcriptions && callData.transcriptions.length > 0) {
                callData.transcriptions.forEach(trans => {
                    const transcriptEntry = document.createElement('div');
                    transcriptEntry.className = `transcript-entry transcript-${trans.speaker}`;

                    const timestamp = new Date(trans.timestamp);
                    const timeStr = timestamp.toLocaleTimeString();
                    const speakerLabel = trans.speaker === 'user' ? 'User' : 'Agent';

                    transcriptEntry.innerHTML = `
                        <div class="transcript-header">
                            <strong>${speakerLabel}</strong>
                            <span class="transcript-time">${timeStr}</span>
                        </div>
                        <div class="transcript-text">${this.escapeHtml(trans.text)}</div>
                    `;
                    conversationDiv.appendChild(transcriptEntry);
                });
            } else {
                conversationDiv.innerHTML = '<p class="no-transcript">No transcriptions available for this call.</p>';
            }

            loading.style.display = 'none';
            content.style.display = 'block';
        } catch (error) {
            console.error('Error loading transcript:', error);
            loading.innerHTML = '<p class="error">Error loading transcript. Please try again.</p>';
        }
    }

    closeTranscriptModal() {
        const modal = document.getElementById('transcript-modal');
        modal.style.display = 'none';


        if (this.liveTranscriptPollInterval) {
            clearInterval(this.liveTranscriptPollInterval);
            this.liveTranscriptPollInterval = null;
        }


        if (this.liveTranscriptAutoCloseTimer) {
            clearTimeout(this.liveTranscriptAutoCloseTimer);
            this.liveTranscriptAutoCloseTimer = null;
        }


        this.liveTranscriptLastIndex = 0;
        this.liveTranscriptCallId = null;
    }

    closeLiveTranscriptModal() {
        const modal = document.getElementById('live-transcript-modal');
        if (modal) {
            modal.style.display = 'none';
        }


        if (this.liveTranscriptPollInterval) {
            clearInterval(this.liveTranscriptPollInterval);
            this.liveTranscriptPollInterval = null;
        }


        if (this.liveTranscriptAutoCloseTimer) {
            clearTimeout(this.liveTranscriptAutoCloseTimer);
            this.liveTranscriptAutoCloseTimer = null;
        }


        this.liveTranscriptLastIndex = 0;
        this.liveTranscriptCallId = null;
    }


    async openLiveTranscriptDialogManually() {
        try {

            const response = await fetch('/api/live-transcript');
            const data = await response.json();

            if (data.active && data.call_id) {

                await this.openLiveTranscriptDialog(
                    data.phone_number || 'Unknown',
                    data.name || 'Unknown',
                    data.client_code || 'Unknown'
                );
            } else {

                this.showMessage('No active call to display transcript for', 'info');
            }
        } catch (error) {
            console.error('Error opening live transcript dialog:', error);
            this.showMessage('Failed to open live transcript dialog', 'error');
        }
    }


    async openLiveTranscriptDialog(phoneNumber, name, clientCode) {

        const modal = document.getElementById('live-transcript-modal');
        const titleEl = document.getElementById('live-transcript-title');
        const nameEl = document.getElementById('live-transcript-caller-name');
        const phoneEl = document.getElementById('live-transcript-caller-phone');
        const codeEl = document.getElementById('live-transcript-caller-code');
        const conversationDiv = document.getElementById('live-transcript-conversation-container');

        if (!modal || !titleEl || !nameEl || !phoneEl || !codeEl || !conversationDiv) {
            throw new Error(`Missing required elements for live transcript modal`);
        }


        modal.style.display = 'block';


        titleEl.textContent = `Live Call - ${name || 'Unknown'}`;


        nameEl.textContent = name || 'Unknown';
        phoneEl.textContent = phoneNumber || 'Unknown';
        codeEl.textContent = clientCode || 'Unknown';


        conversationDiv.innerHTML = '';


        this.liveTranscriptLastIndex = 0;
        this.liveTranscriptCallId = null;
        this.liveTranscriptExpectedCallId = null;


        const pollInterval = parseInt((this.config && this.config.LIVE_TRANSCRIPT_POLL_INTERVAL) || '2000', 10);


        this.liveTranscriptPollInterval = setInterval(() => {
            this.updateLiveTranscript();
        }, pollInterval);



        setTimeout(async () => {
            await this.updateLiveTranscript();
        }, 1000);
    }

    async updateLiveTranscript() {
        try {
            const response = await fetch('/api/live-transcript');
            const data = await response.json();


            const liveModal = document.getElementById('live-transcript-modal');
            if (liveModal && liveModal.style.display === 'none') {
                liveModal.style.display = 'block';
            }


            if (this.liveTranscriptExpectedCallId && data.call_id && data.call_id !== this.liveTranscriptExpectedCallId) {
                return;
            }


            if (data.call_id) {


                if (!this.liveTranscriptExpectedCallId) {
                    if (data.active && data.status === "in_progress") {
                        this.liveTranscriptExpectedCallId = data.call_id;
                    } else {
                        return;
                    }
                }
            }




            if ((data.status === "ended" || data.status === "completed") &&
                data.transcriptions && data.transcriptions.length > 0 &&
                data.call_id && this.liveTranscriptExpectedCallId &&
                data.call_id === this.liveTranscriptExpectedCallId) {


                this.closeLiveTranscriptModal();
                this.showMessage('Call ended. View call history to see the transcript.', 'info');
                return;
            }


            if ((data.status === "ended" || data.status === "completed") &&
                this.liveTranscriptExpectedCallId &&
                data.call_id !== this.liveTranscriptExpectedCallId) {
                return;
            }


            if (!data.transcriptions || data.transcriptions.length === 0) {
                return;
            }


            if (!this.liveTranscriptCallId && data.call_id) {
                this.liveTranscriptCallId = data.call_id;
            }


            const conversationDiv = document.getElementById('live-transcript-conversation-container');
            if (!conversationDiv) {
                return;
            }

            const newTranscriptions = data.transcriptions.slice(this.liveTranscriptLastIndex);

            newTranscriptions.forEach(trans => {
                const transcriptEntry = document.createElement('div');
                transcriptEntry.className = `transcript-entry transcript-${trans.speaker}`;

                const timestamp = new Date(trans.timestamp);
                const timeStr = timestamp.toLocaleTimeString();
                const speakerLabel = trans.speaker === 'user' ? 'User' : 'Agent';

                transcriptEntry.innerHTML = `
                    <div class="transcript-header">
                        <strong>${speakerLabel}</strong>
                        <span class="transcript-time">${timeStr}</span>
                    </div>
                    <div class="transcript-text">${this.escapeHtml(trans.text)}</div>
                `;
                conversationDiv.appendChild(transcriptEntry);
            });


            this.liveTranscriptLastIndex = data.transcriptions.length;


            conversationDiv.scrollTop = conversationDiv.scrollHeight;

        } catch (error) {
            console.error('Error updating live transcript:', error);
        }
    }

    async switchToCallHistoryView(callId) {


        this.viewTranscript(callId);
        return;

        try {

            const response = await fetch(`/api/call-history/${callId}`);
            const callData = await response.json();


            const client = callData.client || {};
            document.getElementById('transcript-title').textContent =
                `Call History - ${client.name || 'Unknown'}`;


            document.getElementById('transcript-call-id').textContent = callData.call_id || '';

            const startDate = new Date(callData.start_time);
            document.getElementById('transcript-start-time').textContent =
                startDate.toLocaleString();

            const duration = callData.duration_seconds || 0;
            const minutes = Math.floor(duration / 60);
            const seconds = Math.floor(duration % 60);
            document.getElementById('transcript-duration').textContent =
                `${minutes}m ${seconds}s`;

            document.getElementById('transcript-client').textContent =
                `${client.name || ''} (${client.client_code || ''}) - ${client.phone_number || ''}`;

            document.getElementById('transcript-summary').textContent =
                callData.summary || 'No summary available';

            document.getElementById('transcript-mood').textContent =
                callData.mood || 'unknown';

            const rating = callData.rating || {numeric: 3, text: 'Neutral'};
            document.getElementById('transcript-rating').textContent =
                `${rating.numeric}/5 - ${rating.text}`;


            const conversationDiv = document.getElementById('transcript-conversation');
            conversationDiv.innerHTML = '';

            if (callData.transcriptions && callData.transcriptions.length > 0) {
                callData.transcriptions.forEach(trans => {
                    const transcriptEntry = document.createElement('div');
                    transcriptEntry.className = `transcript-entry transcript-${trans.speaker}`;

                    const timestamp = new Date(trans.timestamp);
                    const timeStr = timestamp.toLocaleTimeString();
                    const speakerLabel = trans.speaker === 'user' ? 'User' : 'Agent';

                    transcriptEntry.innerHTML = `
                        <div class="transcript-header">
                            <strong>${speakerLabel}</strong>
                            <span class="transcript-time">${timeStr}</span>
                        </div>
                        <div class="transcript-text">${this.escapeHtml(trans.text)}</div>
                    `;
                    conversationDiv.appendChild(transcriptEntry);
                });
            } else {
                conversationDiv.innerHTML = '<p class="no-transcript">No transcriptions available for this call.</p>';
            }

            loading.style.display = 'none';
            historyView.style.display = 'block';


            this.startAutoCloseTimer();

        } catch (error) {
            console.error('Error loading call history:', error);
            loading.innerHTML = '<p class="error">Error loading call history. Please try again.</p>';
        }
    }

    startAutoCloseTimer() {

        if (this.liveTranscriptAutoCloseTimer) {
            clearTimeout(this.liveTranscriptAutoCloseTimer);
        }


        const autoCloseDelay = parseInt(this.config.LIVE_TRANSCRIPT_AUTO_CLOSE_DELAY || '5000', 10);


        this.liveTranscriptAutoCloseTimer = setTimeout(() => {
            this.closeTranscriptModal();
        }, autoCloseDelay);
    }


    setupModalClose() {
        const modal = document.getElementById('transcript-modal');
        if (modal) {
            window.onclick = (event) => {
                if (event.target === modal) {
                    this.closeTranscriptModal();
                }
            };
        }
    }

    async loadAbout() {
        try {
            const response = await fetch('/api/version');
            const version = await response.json();

            const html = `
                <div class="content-section">
                    <h2>About Voice Agent Server</h2>
                    <p>${version.description || 'Voice AI assistant server with LiveKit Agents'}</p>

                    <div class="version-info">
                        <div class="version-card">
                            <strong>Version</strong>
                            <span>${version.version || '1.0.0'}</span>
                        </div>
                        <div class="version-card">
                            <strong>Build Date</strong>
                            <span>${version.build_date || 'Unknown'}</span>
                        </div>
                        <div class="version-card">
                            <strong>Build Number</strong>
                            <span>${version.build_number || '0'}</span>
                        </div>
                        <div class="version-card">
                            <strong>Python Version</strong>
                            <span>${version.python_version || '3.9+'}</span>
                        </div>
                    </div>

                    <h2>Platforms</h2>
                    <p>Supported platforms: ${(version.platforms || []).join(', ')}</p>
                </div>
            `;

            document.getElementById('about-screen').innerHTML = html;
        } catch (error) {
            console.error('Error loading version:', error);
        }
    }

    setupFormHandlers() {

        document.addEventListener('input', (e) => {
            if (e.target.matches('#config-form input, #config-form select')) {
                this.validateField(e.target);
            }
        });
    }

    validateField(field) {
        const fieldName = field.name;
        const value = field.value;
        const schemaField = this.schema.find(f => f.name === fieldName);

        if (!schemaField) return;

        const errorElement = document.getElementById(`error-${fieldName}`);
        let error = '';


        if (schemaField.type === 'integer' && value && !Number.isInteger(Number(value))) {
            error = 'Must be an integer';
        } else if (schemaField.type === 'float' && value && isNaN(Number(value))) {
            error = 'Must be a number';
        } else if (schemaField.type === 'boolean' && value !== 'true' && value !== 'false') {
            error = 'Must be true or false';
        }


        if (schemaField.validation) {
            const numValue = Number(value);
            if (!isNaN(numValue)) {
                if (schemaField.validation.min !== undefined && numValue < schemaField.validation.min) {
                    error = `Must be at least ${schemaField.validation.min}`;
                }
                if (schemaField.validation.max !== undefined && numValue > schemaField.validation.max) {
                    error = `Must be at most ${schemaField.validation.max}`;
                }
            }
        }

        if (error) {
            errorElement.textContent = error;
            errorElement.style.display = 'block';
            field.style.borderColor = 'var(--error-color)';
        } else {
            errorElement.style.display = 'none';
            field.style.borderColor = '';
        }
    }

    getFormData() {
        const form = document.getElementById('config-form');
        if (!form) return {};

        const formData = new FormData(form);
        const config = {};

        for (const [key, value] of formData.entries()) {

            const field = this.schema?.find(f => f.name === key);
            if (field && field.readonly) {
                continue;
            }
            config[key] = value.trim();
        }

        return config;
    }

    getChangedFields(oldConfig, newConfig) {
        const changedFields = [];
        const allKeys = new Set([...Object.keys(oldConfig), ...Object.keys(newConfig)]);

        for (const key of allKeys) {
            const oldValue = (oldConfig[key] || '').toString().trim();
            const newValue = (newConfig[key] || '').toString().trim();

            if (oldValue !== newValue) {
                changedFields.push(key);
            }
        }

        return changedFields;
    }

    categorizeChangedFields(changedFields) {
        const serverFields = ['SERVER_HOST', 'SERVER_PORT', 'CORS_ORIGINS'];
        const agentFields = [
            'AGENT_PROJECT_ROOT', 'AGENT_ENTRYPOINT', 'AGENT_LOG_DIR',
            'AGENT_START_DELAY', 'AGENT_STOP_TIMEOUT', 'AGENT_STOP_POLL_INTERVAL',
            'AGENT_PROCESS_WAIT_TIMEOUT', 'DEFAULT_AGENT_USE_CASE', 'END_CALL_WEBHOOK',
            'AUDIO_INPUT_DEVICE_ID', 'AUDIO_OUTPUT_DEVICE_ID'
        ];
        const chromeFields = [
            'CHROME_DEBUG_PORT', 'CHROME_USER_DATA_DIR', 'CHROME_EXECUTABLE_PATH',
            'CHROME_AUTO_START', 'CHROME_CLEANUP_ON_EXIT', 'CHROME_REMOVE_USER_DATA',
            'LOGIN_URL', 'LOGIN_TYPE'
        ];

        const categorized = {
            server: [],
            agent: [],
            chrome: [],
            other: []
        };

        for (const field of changedFields) {
            if (serverFields.includes(field)) {
                categorized.server.push(field);
            } else if (agentFields.includes(field)) {
                categorized.agent.push(field);
            } else if (chromeFields.includes(field)) {
                categorized.chrome.push(field);
            } else {
                categorized.other.push(field);
            }
        }

        return categorized;
    }

    async checkAgentStatus() {
        try {
            const response = await fetch('/api/agent-status');
            const data = await response.json();
            return data.status === 'running';
        } catch (error) {
            console.error('Error checking agent status:', error);
            return false;
        }
    }

    async checkChromeStatus() {
        try {
            const response = await fetch('/chrome/status');
            const data = await response.json();
            return data.status === 'running';
        } catch (error) {
            console.error('Error checking Chrome status:', error);
            return false;
        }
    }

    async saveConfig() {
        const newConfig = this.getFormData();
        const oldConfig = this.config || {};


        const changedFields = this.getChangedFields(oldConfig, newConfig);


        if (changedFields.length === 0) {
            this.showMessage('No configuration changes detected.', 'info');
            return;
        }


        const categorized = this.categorizeChangedFields(changedFields);


        const needsServerRestart = categorized.server.length > 0;
        const needsAgentRestart = categorized.agent.length > 0;
        const needsChromeRestart = categorized.chrome.length > 0;

        let agentRunning = false;
        let chromeRunning = false;

        if (needsAgentRestart) {
            agentRunning = await this.checkAgentStatus();
        }

        if (needsChromeRestart) {
            chromeRunning = await this.checkChromeStatus();
        }


        const restartPrompts = [];
        const restartActions = [];

        if (needsServerRestart) {
            restartPrompts.push('Server configuration changed. Restart main server?');
            restartActions.push('server');
        }

        if (needsAgentRestart && agentRunning) {
            restartPrompts.push('Agent configuration changed. Restart agent?');
            restartActions.push('agent');
        }

        if (needsChromeRestart && chromeRunning) {
            restartPrompts.push('Browser configuration changed. Restart Chrome?');
            restartActions.push('chrome');
        }


        let shouldRestart = false;
        if (restartPrompts.length > 0) {
            const promptMessage = restartPrompts.join('\n\n') +
                '\n\nClick OK to save and restart, or Cancel to just save.';
            shouldRestart = confirm(promptMessage);
        }


        try {
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ config: newConfig }),
            });

            const data = await response.json();

            if (!data.success) {
                this.showMessage(`Error: ${data.errors?.join(', ') || 'Failed to save configuration'}`, 'error');
                return;
            }


            this.config = newConfig;


            if (shouldRestart && restartActions.length > 0) {
                const restartMessages = [];

                for (const action of restartActions) {
                    try {
                        if (action === 'server') {

                            const restartResponse = await fetch('/api/start-server', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                },
                                body: JSON.stringify({ config: newConfig }),
                            });
                            const restartData = await restartResponse.json();
                            if (restartData.success) {
                                restartMessages.push('Server restarted');
                            } else {
                                restartMessages.push('Server restart failed');
                            }
                        } else if (action === 'agent' && agentRunning) {

                            await fetch('/api/agent-stop', { method: 'POST' });
                            await new Promise(resolve => setTimeout(resolve, 1000));
                            restartMessages.push('Agent restarted (stop only - start manually if needed)');
                        } else if (action === 'chrome' && chromeRunning) {

                            await fetch('/chrome/stop', { method: 'POST' });
                            await new Promise(resolve => setTimeout(resolve, 500));

                            restartMessages.push('Chrome restarted');
                        }
                    } catch (error) {
                        console.error(`Error restarting ${action}:`, error);
                        restartMessages.push(`${action} restart failed`);
                    }
                }

                const message = restartMessages.length > 0
                    ? `Configuration saved. ${restartMessages.join(', ')}.`
                    : 'Configuration saved successfully!';
                this.showMessage(message, 'success');
            } else {

                const otherChanges = categorized.other.length;
                const message = otherChanges > 0
                    ? `Configuration saved successfully! (${otherChanges} field${otherChanges > 1 ? 's' : ''} updated)`
                    : 'Configuration saved successfully!';
                this.showMessage(message, 'success');
            }
        } catch (error) {
            this.showMessage('Failed to save configuration', 'error');
            console.error('Error saving config:', error);
        }
    }

    async closeApp() {

        const confirmed = confirm(
            'Are you sure you want to close the application?\n\n' +
            'This will stop all processes including:\n' +
            '- Agent processes\n' +
            '- API server\n' +
            '- Browser services\n' +
            '- Chrome instances\n\n' +
            'This action cannot be undone.'
        );

        if (!confirmed) {
            return;
        }


        const closeBtn = document.getElementById('close-app-btn');
        if (closeBtn) {
            closeBtn.disabled = true;
            closeBtn.textContent = 'Shutting down...';
        }

        try {

            const response = await fetch('/api/shutdown', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
            });

            const data = await response.json();

            if (data.success) {

                this.showMessage('Application is shutting down...', 'info');



                setTimeout(() => {

                    window.close();
                }, 1000);
            } else {
                this.showMessage('Failed to shutdown application', 'error');
                if (closeBtn) {
                    closeBtn.disabled = false;
                    closeBtn.textContent = 'Close App';
                }
            }
        } catch (error) {
            console.error('Error shutting down:', error);

            this.showMessage('Shutdown initiated. The application may close shortly.', 'info');


            setTimeout(() => {
                window.close();
            }, 2000);
        }
    }

    async restartServer() {
        const config = this.getFormData();


        try {
            const validateResponse = await fetch('/api/validate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ config }),
            });

            const validateData = await validateResponse.json();

            if (!validateData.valid) {
                this.showMessage(`Validation errors: ${validateData.errors.join(', ')}`, 'error');
                return;
            }
        } catch (error) {
            console.error('Error validating config:', error);
        }


        try {
            const response = await fetch('/api/start-server', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ config }),
            });

            const data = await response.json();

            if (data.success) {
                this.showMessage('Configuration saved and server reloaded successfully!', 'success');

                this.config = config;

                setTimeout(async () => {
                    await this.checkMainServerStatus();
                    if (this.mainServerRunning) {
                        this.switchTab('dashboard');
                    }
                }, 500);
            } else {
                this.showMessage(`Error: ${data.errors?.join(', ') || 'Failed to restart server'}`, 'error');
            }
        } catch (error) {
            this.showMessage('Failed to restart server', 'error');
            console.error('Error restarting server:', error);
        }
    }

    showMessage(message, type = 'info') {
        const messageEl = document.getElementById('message');
        if (!messageEl) {
            console.error('Message element not found');
            return;
        }

        messageEl.textContent = message;
        messageEl.className = `message ${type} show`;

        setTimeout(() => {
            messageEl.classList.remove('show');
        }, 5000);
    }


    startPolling() {

        this.pollingIntervals.mainServer = setInterval(() => {
            this.checkMainServerStatus();
        }, 5000);


        this.pollingIntervals.agentStatus = setInterval(() => {
            if (this.mainServerRunning) {
                this.updateAgentStatus();
            }
        }, 5000);


        this.pollingIntervals.webhookStatus = setInterval(() => {
            if (this.mainServerRunning) {
                this.checkWebhookStatus();
            }
        }, 5000);


        this.pollingIntervals.dashboardStats = setInterval(() => {
            if (this.mainServerRunning && this.currentTab === 'dashboard') {
                this.updateStats();
            }
        }, 10000);


        this.checkMainServerStatus();
    }

    stopPolling() {
        Object.values(this.pollingIntervals).forEach(interval => clearInterval(interval));
        this.pollingIntervals = {};
    }

    async checkMainServerStatus() {
        try {
            const response = await fetch('/api/main-server-status');
            const data = await response.json();
            this.mainServerRunning = data.running;
            this.updateServerStatusIndicator();


            if (this.mainServerRunning) {
                this.enableConfigForm();
            }
        } catch (error) {
            console.error('Error checking main server status:', error);
            this.mainServerRunning = false;
        }
    }

    updateServerStatusIndicator() {
        const indicator = document.getElementById('server-status-dot');
        const text = document.getElementById('server-status-text');

        if (indicator && text) {
            if (this.mainServerRunning) {
                indicator.className = 'status-dot status-online';
                text.textContent = 'Main Server Running';
            } else {
                indicator.className = 'status-dot status-offline';
                text.textContent = 'Main Server Stopped';
            }
        }
    }

    async updateAgentStatus() {
        try {
            const response = await fetch('/api/agent-status');
            const data = await response.json();
            this.agentStatus = data;
            this.updateAgentStatusDisplay();
        } catch (error) {
            console.error('Error updating agent status:', error);
            this.agentStatus = { status: 'unknown' };
        }
    }

    async checkWebhookStatus() {
        try {
            const response = await fetch('/api/webhook-status');
            const data = await response.json();
            this.webhookListening = data.listening || false;
            this.webhookUrl = data.webhook_url || '';
            this.updateWebhookStatusDisplay();
        } catch (error) {
            console.error('Error checking webhook status:', error);
            this.webhookListening = false;
            this.webhookUrl = '';
        }
    }

    updateWebhookStatusDisplay() {
        const button = document.getElementById('webhook-status-button');
        const dot = document.getElementById('webhook-status-dot');
        const text = document.getElementById('webhook-status-text');

        if (button && dot && text) {
            if (this.webhookListening) {
                dot.className = 'status-dot status-online';
                text.textContent = 'Listening for calls';
            } else {
                dot.className = 'status-dot status-offline';
                text.textContent = 'Listening for calls';
            }


            if (this.webhookUrl) {
                button.title = this.webhookUrl;
            } else {
                button.title = 'Webhook URL not available';
            }
        }
    }

    async toggleWebhook() {

        if (!this.webhookListening && this.agentType === 'online') {
            try {
                this.showMessage('Fetching online agent code...', 'info');
                await this.fetchAgentCode();
            } catch (error) {
                console.error('Error fetching agent code:', error);
                this.showMessage('Failed to fetch agent code, will use cached or bundled', 'warning');
            }
        }

        try {
            const response = await fetch('/api/webhook-toggle', {
                method: 'POST'
            });

            const data = await response.json();

            if (response.ok && data.success) {
                this.webhookListening = data.listening;
                this.updateWebhookStatusDisplay();
                this.showMessage(
                    `Webhook listening ${data.listening ? 'enabled' : 'disabled'}`,
                    'success'
                );
            } else {
                this.showMessage('Failed to toggle webhook status', 'error');
            }
        } catch (error) {
            console.error('Error toggling webhook:', error);
            this.showMessage('Failed to toggle webhook status', 'error');
        }
    }

    async loadAgentType() {
        try {
            const response = await fetch('/api/agent-type');
            const data = await response.json();

            if (response.ok && data.agent_type) {
                this.agentType = data.agent_type;
                const select = document.getElementById('agent-type-select');
                if (select) {
                    select.value = this.agentType;
                }
            }
        } catch (error) {
            console.error('Error loading agent type:', error);
        }
    }

    async setAgentType(type) {
        if (type !== 'bundled' && type !== 'online') {
            this.showMessage('Invalid agent type', 'error');
            return;
        }

        try {
            const response = await fetch('/api/agent-type', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ agent_type: type })
            });

            const data = await response.json();

            if (response.ok && data.success) {
                this.agentType = type;
                this.showMessage(`Agent type set to ${type}`, 'success');
            } else {
                this.showMessage('Failed to set agent type', 'error');

                const select = document.getElementById('agent-type-select');
                if (select) {
                    select.value = this.agentType;
                }
            }
        } catch (error) {
            console.error('Error setting agent type:', error);
            this.showMessage('Failed to set agent type', 'error');

            const select = document.getElementById('agent-type-select');
            if (select) {
                select.value = this.agentType;
            }
        }
    }

    async fetchAgentCode() {
        try {
            const response = await fetch('/api/fetch-agent-code', {
                method: 'POST'
            });

            const data = await response.json();

            if (response.ok && data.success) {
                this.showMessage('Agent code fetch initiated', 'success');
            } else {
                this.showMessage('Failed to initiate agent code fetch', 'error');
            }
        } catch (error) {
            console.error('Error fetching agent code:', error);
            throw error;
        }
    }

    async getAvailableAgents() {
        try {
            const response = await fetch('/api/available-agents');
            const data = await response.json();

            if (response.ok && data.agents) {
                return data.agents;
            }
            return [];
        } catch (error) {
            console.error('Error getting available agents:', error);
            return [];
        }
    }

    updateAgentStatusDisplay() {
        if (!this.agentStatus) return;

        const dot = document.getElementById('agent-status-dot');
        const text = document.getElementById('agent-status-text');
        const pid = document.getElementById('agent-pid');
        const uptime = document.getElementById('agent-uptime');
        const callStatus = document.getElementById('call-status');

        if (dot && text) {
            if (this.agentStatus.status === 'running') {
                dot.className = 'status-dot status-running';
                text.textContent = 'Running';
            } else {
                dot.className = 'status-dot status-stopped';
                text.textContent = 'Stopped';
            }
        }

        if (pid) pid.textContent = this.agentStatus.pid || '-';
        if (uptime) {
            const uptimeSec = this.agentStatus.uptime_seconds;
            if (uptimeSec) {
                const minutes = Math.floor(uptimeSec / 60);
                const seconds = Math.floor(uptimeSec % 60);
                uptime.textContent = `${minutes}m ${seconds}s`;
            } else {
                uptime.textContent = '-';
            }
        }
        if (callStatus) {

            callStatus.textContent = 'No active call';
        }
    }

    async updateDashboard() {
        await this.updateAgentStatus();
        await this.updateStats();
    }

    async updateStats() {
        try {

            const response = await fetch('/api/stats');
            const stats = await response.json();


            document.getElementById('total-calls').textContent = stats.total_calls || 0;


            const avgRatingEl = document.getElementById('average-rating');
            if (stats.average_rating) {
                avgRatingEl.textContent = `${stats.average_rating}/5`;
                avgRatingEl.title = `Based on ${stats.rating_count} rated calls`;
            } else {
                avgRatingEl.textContent = '-';
                avgRatingEl.title = 'No ratings available';
            }


            const uptimeEl = document.getElementById('agent-uptime-stat');
            if (stats.uptime) {
                uptimeEl.textContent = stats.uptime;
                uptimeEl.title = `Total call duration: ${stats.total_duration_seconds.toFixed(0)} seconds`;
            } else {
                uptimeEl.textContent = '-';
            }


            document.getElementById('active-calls').textContent = '0';

        } catch (error) {
            console.error('Error updating stats:', error);

            document.getElementById('total-calls').textContent = '0';
            document.getElementById('average-rating').textContent = '-';
            document.getElementById('agent-uptime-stat').textContent = '-';
        }
    }


    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }


    async startAgent() {

        const clientCode = prompt('Enter Client Code:');
        const phoneNumber = prompt('Enter Phone Number:');
        const name = prompt('Enter Name:');

        if (!clientCode || !phoneNumber || !name) {
            this.showMessage('All fields are required', 'error');
            return;
        }

        try {
            const response = await fetch('/api/agent-start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    client_code: clientCode,
                    phone_number: phoneNumber,
                    name: name
                })
            });

            const data = await response.json();
            if (response.ok) {
                this.showMessage('Agent started successfully', 'success');
                await this.updateAgentStatus();


                await this.openLiveTranscriptDialog(phoneNumber, name, clientCode);
            } else {
                this.showMessage(`Error: ${data.detail || 'Failed to start agent'}`, 'error');
            }
        } catch (error) {
            this.showMessage('Failed to start agent', 'error');
            console.error('Error starting agent:', error);
        }
    }


    async startTestAgent() {
        const clientCode = 'xxxx';
        const phoneNumber = 'xxxx';
        const name = 'xxxxx';
        try {
            const response = await fetch('/api/agent-start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    client_code: clientCode,
                    phone_number: phoneNumber,
                    name: name
                })
            });

            const data = await response.json();
            if (response.ok) {
                this.showMessage('Test Agent started successfully', 'success');
                await this.updateAgentStatus();


                await this.openLiveTranscriptDialog(phoneNumber, name, clientCode);
            } else {
                this.showMessage(`Error: ${data.detail || 'Failed to start test agent'}`, 'error');
            }
        } catch (error) {
            this.showMessage('Failed to start agent', 'error');
            console.error('Error starting agent:', error);
        }
    }

    async stopAgent() {
        if (!confirm('Are you sure you want to stop the agent?')) {
            return;
        }

        try {
            const response = await fetch('/api/agent-stop', {
                method: 'POST'
            });

            const data = await response.json();
            if (response.ok) {
                this.showMessage('Agent stopped successfully', 'success');
                await this.updateAgentStatus();
            } else {
                this.showMessage(`Error: ${data.detail || 'Failed to stop agent'}`, 'error');
            }
        } catch (error) {
            this.showMessage('Failed to stop agent', 'error');
            console.error('Error stopping agent:', error);
        }
    }

    async manualOvertake() {
        if (!confirm('Manual Overtake: Stop agent but keep call alive. Continue?')) {
            return;
        }

        try {
            const response = await fetch('/api/agent-overtake', {
                method: 'POST'
            });

            const data = await response.json();
            if (response.ok) {
                this.showMessage('Manual overtake executed', 'success');
                await this.updateAgentStatus();
            } else {
                this.showMessage(`Error: ${data.detail || 'Failed to execute overtake'}`, 'error');
            }
        } catch (error) {
            this.showMessage('Failed to execute manual overtake', 'error');
            console.error('Error in manual overtake:', error);
        }
    }

    async endCall() {
        if (!confirm('End call? This will stop the agent and end the call.')) {
            return;
        }


        await this.stopAgent();
        this.showMessage('Call ended', 'info');
    }


    disableConfigForm() {
        const form = document.getElementById('config-form');
        if (!form) return;


        const banner = document.createElement('div');
        banner.className = 'config-banner';
        banner.innerHTML = `
            <div class="banner-content">
                <strong>⚠️ Main server is running</strong>
                <p>Configuration changes require application restart. Click "Restart Application" to apply changes.</p>
                <button class="btn btn-warning" onclick="configUI.restartApplication()">Restart Application</button>
            </div>
        `;

        const existingBanner = form.querySelector('.config-banner');
        if (!existingBanner) {
            form.insertBefore(banner, form.firstChild);
        }
    }

    enableConfigForm() {
        const form = document.getElementById('config-form');
        if (!form) return;


        const banner = form.querySelector('.config-banner');
        if (banner) {
            banner.remove();
        }


        form.querySelectorAll('input, select, textarea, button').forEach(el => {
            el.disabled = false;
            el.classList.remove('disabled');
        });
    }

    restartApplication() {
        if (confirm('Restart application? This will stop the main server and allow you to reconfigure.')) {


            this.showMessage('Restart functionality coming soon. Please restart manually.', 'warning');
        }
    }


    async loadModules() {
        const modulesScreen = document.getElementById('modules-screen');
        if (!modulesScreen) return;

        try {
            const response = await fetch('/sections/modules.html');
            const html = await response.text();
            modulesScreen.innerHTML = html;


            await this.checkAuthStatus();
            await this.loadInstallerId();
            await this.loadAvailableFiles();
            await this.loadInstalledFiles();
        } catch (error) {
            console.error('Error loading modules:', error);
            modulesScreen.innerHTML = '<p>Error loading modules section</p>';
        }
    }

    async checkAuthStatus() {
        try {
            const response = await fetch('/api/auth/status');
            const data = await response.json();

            const authStatus = document.getElementById('auth-status');
            const authForm = document.getElementById('auth-form');
            const authLoggedIn = document.getElementById('auth-logged-in');
            const authUserId = document.getElementById('auth-user-id');

            if (data.authenticated) {
                if (authStatus) authStatus.style.display = 'none';
                if (authForm) authForm.style.display = 'none';
                if (authLoggedIn) authLoggedIn.style.display = 'block';
                if (authUserId) authUserId.textContent = data.user_id || 'Anonymous';
            } else {
                if (authStatus) {
                    authStatus.style.display = 'block';
                    authStatus.innerHTML = '<p>Not authenticated. Please sign in to download modules.</p>';
                }
                if (authForm) authForm.style.display = 'block';
                if (authLoggedIn) authLoggedIn.style.display = 'none';
            }
        } catch (error) {
            console.error('Error checking auth status:', error);
        }
    }

    async loginWithEmail() {
        const email = document.getElementById('auth-email')?.value;
        const password = document.getElementById('auth-password')?.value;

        if (!email || !password) {
            this.showMessage('Please enter email and password', 'error');
            return;
        }

        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password, anonymous: false })
            });

            const data = await response.json();
            if (response.ok && data.success) {
                this.showMessage('Signed in successfully', 'success');
                await this.checkAuthStatus();
                await this.loadAvailableFiles();
            } else {
                this.showMessage(data.detail || 'Login failed', 'error');
            }
        } catch (error) {
            this.showMessage('Login error: ' + error.message, 'error');
        }
    }


    async logout() {
        try {
            const response = await fetch('/api/auth/logout', {
                method: 'POST'
            });

            const data = await response.json();
            if (response.ok && data.success) {
                this.showMessage('Signed out successfully', 'success');
                this.showLoginModal();

                this.config = {};
                this.schema = [];
                this.categorized = {};
            }
        } catch (error) {
            this.showMessage('Logout error: ' + error.message, 'error');
        }
    }

    async loadInstallerId() {
        try {
            const response = await fetch('/api/installer-id');
            const data = await response.json();
            const installerIdEl = document.getElementById('installer-id');
            if (installerIdEl) {
                installerIdEl.textContent = data.installer_id || 'Not set';
            }
        } catch (error) {
            console.error('Error loading installer ID:', error);
        }
    }

    async loadAvailableFiles() {
        const filesList = document.getElementById('available-files-list');
        if (!filesList) return;

        try {
            filesList.innerHTML = '<p>Loading...</p>';
            const response = await fetch('/api/files/available');
            const data = await response.json();

            if (data.available_files && data.available_files.length > 0) {
                let html = '';
                data.available_files.forEach(file => {
                    const installed = this.isFileInstalled(file.name);
                    html += `
                        <div class="file-item">
                            <div class="file-info">
                                <div class="file-name">${file.name}</div>
                                <div class="file-meta">
                                    Version: ${file.version} |
                                    Size: ${this.formatBytes(file.size || 0)} |
                                    ${file.description || 'No description'}
                                    ${file.required ? ' | <strong>Required</strong>' : ''}
                                </div>
                            </div>
                            <div class="file-actions">
                                ${installed ?
                                    '<span class="badge">Installed</span>' :
                                    `<button class="btn btn-primary btn-sm" onclick="configUI.installFile('${file.name}')">Install</button>`
                                }
                            </div>
                        </div>
                    `;
                });
                filesList.innerHTML = html;
            } else {
                filesList.innerHTML = '<p>No available files found. Make sure Firebase is configured and you are authenticated.</p>';
            }
        } catch (error) {
            filesList.innerHTML = '<p>Error loading available files: ' + error.message + '</p>';
            console.error('Error loading available files:', error);
        }
    }

    async loadInstalledFiles() {
        const filesList = document.getElementById('installed-files-list');
        if (!filesList) return;

        try {
            filesList.innerHTML = '<p>Loading...</p>';
            const response = await fetch('/api/files/installed');
            const data = await response.json();

            if (data.files && Object.keys(data.files).length > 0) {
                let html = '';
                Object.entries(data.files).forEach(([fileName, fileInfo]) => {
                    html += `
                        <div class="file-item">
                            <div class="file-info">
                                <div class="file-name">${fileName}</div>
                                <div class="file-meta">
                                    Version: ${fileInfo.version || 'unknown'} |
                                    Installed: ${new Date(fileInfo.installed_date).toLocaleDateString()} |
                                    Source: ${fileInfo.source || 'unknown'}
                                </div>
                            </div>
                            <div class="file-actions">
                                <span class="badge">Installed</span>
                            </div>
                        </div>
                    `;
                });
                filesList.innerHTML = html;
            } else {
                filesList.innerHTML = '<p>No files installed yet.</p>';
            }
        } catch (error) {
            filesList.innerHTML = '<p>Error loading installed files: ' + error.message + '</p>';
            console.error('Error loading installed files:', error);
        }
    }

    async installFile(fileName) {
        const progressDiv = document.getElementById('install-progress');
        const progressList = document.getElementById('install-progress-list');

        if (progressDiv) progressDiv.style.display = 'block';
        if (progressList) {
            progressList.innerHTML = `<div class="progress-item pending">Installing ${fileName}...</div>`;
        }

        try {
            const response = await fetch('/api/files/install', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ files: [fileName] })
            });

            const data = await response.json();

            if (response.ok && data.success) {
                const result = data.results[0];
                if (result.success) {
                    if (progressList) {
                        progressList.innerHTML = `<div class="progress-item success">${fileName} installed successfully (v${result.version})</div>`;
                    }
                    this.showMessage(`${fileName} installed successfully`, 'success');
                    await this.loadAvailableFiles();
                    await this.loadInstalledFiles();
                } else {
                    if (progressList) {
                        progressList.innerHTML = `<div class="progress-item error">${fileName} installation failed: ${result.error || 'Unknown error'}</div>`;
                    }
                    this.showMessage(`Failed to install ${fileName}: ${result.error || 'Unknown error'}`, 'error');
                }
            } else {
                throw new Error(data.detail || 'Installation failed');
            }
        } catch (error) {
            if (progressList) {
                progressList.innerHTML = `<div class="progress-item error">Error: ${error.message}</div>`;
            }
            this.showMessage('Installation error: ' + error.message, 'error');
        }
    }

    isFileInstalled(fileName) {


        return false;
    }

    formatBytes(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
    }


    async checkAuthOnInit() {
        try {
            const response = await fetch('/api/auth/status');
            const data = await response.json();

            if (data.authenticated && data.token_valid) {

                const verifyResponse = await fetch('/api/auth/verify');
                const verifyData = await verifyResponse.json();

                if (verifyData.valid) {
                    return true;
                }
            }


            const verifyResponse = await fetch('/api/auth/verify');
            const verifyData = await verifyResponse.json();

            return verifyData.valid || false;
        } catch (error) {
            console.error('Auth check error:', error);
            return false;
        }
    }

    setupLoginDialog() {
        const dialog = document.getElementById('login-modal');
        if (!dialog) return;


        if (dialog.hasAttribute('open')) {
            dialog.removeAttribute('open');
        }
        dialog.close();


        const closeButton = dialog.querySelector('.login-dialog-close');
        if (closeButton) {
            closeButton.addEventListener('click', () => {
                this.hideLoginModal();
            });
        }


        dialog.addEventListener('cancel', (event) => {
            event.preventDefault();
        });


        dialog.addEventListener('close', () => {


        });
    }

    showLoginModal() {
        const dialog = document.getElementById('login-modal');
        if (dialog && dialog instanceof HTMLDialogElement) {
            dialog.showModal();
        }
    }

    hideLoginModal() {
        const dialog = document.getElementById('login-modal');
        if (dialog && dialog instanceof HTMLDialogElement) {
            dialog.close();
        }
    }

    async handleLogin(event) {
        event.preventDefault();

        const email = document.getElementById('login-email')?.value;
        const password = document.getElementById('login-password')?.value;
        const errorDiv = document.getElementById('login-error');

        if (!email || !password) {
            if (errorDiv) {
                errorDiv.textContent = 'Please enter both email and password';
                errorDiv.style.display = 'block';
            }
            return;
        }

        if (errorDiv) errorDiv.style.display = 'none';

        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });

            const data = await response.json();

            if (response.ok && data.success) {
                this.showMessage('Signed in successfully', 'success');
                this.hideLoginModal();

                await this.init();
            } else {
                const errorMsg = data.detail || 'Login failed. Please check your credentials.';
                if (errorDiv) {
                    errorDiv.textContent = errorMsg;
                    errorDiv.style.display = 'block';
                }
            }
        } catch (error) {
            if (errorDiv) {
                errorDiv.textContent = 'Login error: ' + error.message;
                errorDiv.style.display = 'block';
            }
        }
    }

    startTokenRefreshTimer() {

        setInterval(async () => {
            try {
                const response = await fetch('/api/auth/status');
                const data = await response.json();

                if (data.authenticated) {

                    const timeUntilExpiry = data.time_until_expiry;
                    if (timeUntilExpiry && timeUntilExpiry < 3600 && timeUntilExpiry > 0) {

                        await this.refreshToken();
                    } else if (timeUntilExpiry <= 0) {

                        this.showMessage('Session expired. Please sign in again.', 'error');
                        this.showLoginModal();
                    }
                }
            } catch (error) {
                console.error('Token refresh check error:', error);
            }
        }, 5 * 60 * 1000);
    }

    openGoogleSheet() {

        const sheetIdField = document.getElementById('GOOGLE_SHEET_ID');
        const sheetId = sheetIdField ? sheetIdField.value.trim() : '';


        const configSheetId = (this.config && this.config.GOOGLE_SHEET_ID) ? this.config.GOOGLE_SHEET_ID.trim() : '';
        const finalSheetId = sheetId || configSheetId;

        if (!finalSheetId) {
            this.showMessage('Please enter a Google Sheet ID first', 'error');
            return;
        }


        const sheetUrl = `https://docs.google.com/spreadsheets/d/${finalSheetId}/edit`;


        window.open(sheetUrl, '_blank');
    }

    async refreshToken() {
        try {
            const response = await fetch('/api/auth/refresh', {
                method: 'POST'
            });

            const data = await response.json();
            if (response.ok && data.success) {
                console.log('Token refreshed successfully');
            } else {

                this.showMessage('Session expired. Please sign in again.', 'error');
                this.showLoginModal();
            }
        } catch (error) {
            console.error('Token refresh error:', error);
            this.showMessage('Session expired. Please sign in again.', 'error');
            this.showLoginModal();
        }
    }
}


let configUI;
document.addEventListener('DOMContentLoaded', () => {
    configUI = new ConfigUI();
});
