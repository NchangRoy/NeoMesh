document.addEventListener('DOMContentLoaded', () => {
    // ===== Navigation =====
    const navItems = document.querySelectorAll('.nav-item');
    const viewSections = document.querySelectorAll('.view-section');

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            navItems.forEach(n => n.classList.remove('active'));
            item.classList.add('active');

            const targetId = item.getAttribute('data-target');
            viewSections.forEach(v => {
                if (v.id === targetId) {
                    v.classList.remove('hidden');
                    v.classList.add('active');
                } else {
                    v.classList.add('hidden');
                    v.classList.remove('active');
                }
            });

            if (targetId === 'shards-view') loadShards();
            if (targetId === 'databases-view') loadDatabases();
            if (targetId === 'nodes-view') loadNodes();
            if (targetId === 'relationships-view') loadRelationships();
        });
    });

    // ===== Modal Helper =====
    const setupModal = (btnId, modalId, formId, apiEndpoint, dataFormatter, onSuccess) => {
        const btn = document.getElementById(btnId);
        const modal = document.getElementById(modalId);
        const cancelBtn = modal.querySelector('.modal-cancel-btn');
        const form = document.getElementById(formId);

        if (btn) btn.addEventListener('click', () => modal.classList.remove('hidden'));
        if (cancelBtn) cancelBtn.addEventListener('click', () => modal.classList.add('hidden'));

        // Close modal on backdrop click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.classList.add('hidden');
        });

        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                const data = dataFormatter(form);
                try {
                    const res = await fetch(apiEndpoint, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(data)
                    });
                    if (res.ok) {
                        modal.classList.add('hidden');
                        form.reset();
                        if (onSuccess) onSuccess();
                    } else {
                        alert('Failed to save.');
                    }
                } catch (err) {
                    console.error(err);
                    alert('Error: ' + err);
                }
            });
        }
    };

    setupModal('add-shard-btn', 'add-shard-modal', 'shard-form', '/api/shards',
        (form) => ({
            name: form.querySelector('#shard-name').value,
            host: form.querySelector('#shard-host').value,
            port: parseInt(form.querySelector('#shard-port').value),
            user: form.querySelector('#shard-user').value,
            password: form.querySelector('#shard-password').value
        }),
        loadShards
    );

    setupModal('add-db-btn', 'add-db-modal', 'db-form', '/api/databases',
        (form) => ({
            db_name: form.querySelector('#db-name').value,
            shard_name: form.querySelector('#db-shard').value
        }),
        loadDatabases
    );

    setupModal('add-node-btn', 'add-node-modal', 'node-form', '/api/nodes',
        (form) => ({
            label: form.querySelector('#node-label').value,
            db_name: form.querySelector('#node-db').value
        }),
        loadNodes
    );

    setupModal('add-rel-btn', 'add-rel-modal', 'rel-form', '/api/relationships',
        (form) => ({
            type: form.querySelector('#rel-type').value,
            db_name: form.querySelector('#rel-db').value
        }),
        loadRelationships
    );

    // ===== Data Loaders =====
    async function loadShards() {
        const res = await fetch('/api/shards');
        const shards = await res.json();
        const grid = document.getElementById('shards-grid');
        if (shards.length === 0) {
            grid.innerHTML = '<div class="empty-state">No shards configured yet. Click "+ Add Shard" to get started.</div>';
            return;
        }
        grid.innerHTML = shards.map(s => `
            <div class="card">
                <div class="card-icon">
                    <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M12 5l7 7-7 7"></path></svg>
                </div>
                <h3>${s}</h3>
                <div class="card-detail">Physical Neo4j Instance</div>
                <div class="card-status"><span class="dot"></span> Active</div>
            </div>
        `).join('');
    }

    async function loadDatabases() {
        const res = await fetch('/api/databases');
        const dbs = await res.json();
        const grid = document.getElementById('databases-grid');
        const entries = Object.entries(dbs);
        if (entries.length === 0) {
            grid.innerHTML = '<div class="empty-state">No databases created yet.</div>';
            return;
        }
        grid.innerHTML = entries.map(([db, shard]) => `
            <div class="card">
                <div class="card-icon">
                    <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><ellipse cx="12" cy="5" rx="9" ry="3" stroke-width="2"></ellipse><path stroke-width="2" d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path><path stroke-width="2" d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path></svg>
                </div>
                <h3>${db}</h3>
                <div class="card-detail">
                    <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M12 5l7 7-7 7"></path></svg>
                    ${shard}
                </div>
                <div class="card-status"><span class="dot"></span> Online</div>
            </div>
        `).join('');
    }

    async function loadNodes() {
        const res = await fetch('/api/nodes');
        const nodes = await res.json();
        const list = document.getElementById('nodes-list');
        const entries = Object.entries(nodes);
        if (entries.length === 0) {
            list.innerHTML = '<div class="empty-state">No nodes found in metadata.</div>';
            return;
        }
        list.innerHTML = entries.map(([label, dbs]) => `
            <div class="list-item">
                <span class="item-name">${label}</span>
                <div class="badges">${dbs.map(db => `<span class="badge">${db}</span>`).join('')}</div>
            </div>
        `).join('');
    }

    async function loadRelationships() {
        const res = await fetch('/api/relationships');
        const rels = await res.json();
        const list = document.getElementById('relationships-list');
        const entries = Object.entries(rels);
        if (entries.length === 0) {
            list.innerHTML = '<div class="empty-state">No relationships found in metadata.</div>';
            return;
        }
        list.innerHTML = entries.map(([type, dbs]) => `
            <div class="list-item">
                <span class="item-name">${type}</span>
                <div class="badges">${dbs.map(db => `<span class="badge">${db}</span>`).join('')}</div>
            </div>
        `).join('');
    }

    // ===== Chat-style Query Terminal =====
    const executeBtn = document.getElementById('execute-btn');
    const cypherInput = document.getElementById('cypher-input');
    const chatMessages = document.getElementById('chat-messages');
    const chatWelcome = document.getElementById('chat-welcome');
    const clearChatBtn = document.getElementById('clear-chat-btn');

    // Auto-resize textarea
    cypherInput.addEventListener('input', () => {
        cypherInput.style.height = 'auto';
        cypherInput.style.height = Math.min(cypherInput.scrollHeight, 160) + 'px';
    });

    // Ctrl+Enter to execute
    cypherInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && e.ctrlKey) {
            e.preventDefault();
            executeBtn.click();
        }
    });

    // Clear chat history
    clearChatBtn.addEventListener('click', () => {
        chatMessages.innerHTML = `
            <div class="chat-welcome" id="chat-welcome">
                <span class="welcome-icon">⚡</span>
                <h2>Welcome to NeoMesh</h2>
                <p>Type a Cypher query below and press Execute or Ctrl+Enter to run it across your distributed Neo4j cluster.</p>
            </div>
        `;
    });

    function getTimestamp() {
        return new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function buildResultTable(results) {
        if (!results || results.length === 0) return '';
        const keys = Object.keys(results[0]);
        let html = '<div class="result-table-wrap"><table class="result-table"><thead><tr>';
        keys.forEach(k => { html += `<th>${escapeHtml(k)}</th>`; });
        html += '</tr></thead><tbody>';
        results.forEach(row => {
            html += '<tr>';
            keys.forEach(k => {
                const val = row[k];
                html += `<td>${escapeHtml(typeof val === 'object' ? JSON.stringify(val) : String(val))}</td>`;
            });
            html += '</tr>';
        });
        html += '</tbody></table></div>';
        return html;
    }

    function addQueryBubble(query) {
        // Hide welcome message on first query
        const welcome = document.getElementById('chat-welcome');
        if (welcome) welcome.remove();

        const exchange = document.createElement('div');
        exchange.className = 'chat-exchange';

        exchange.innerHTML = `
            <div class="chat-query">
                <div class="bubble"><code>${escapeHtml(query)}</code></div>
                <div class="bubble-meta">${getTimestamp()}</div>
            </div>
        `;

        chatMessages.appendChild(exchange);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return exchange;
    }

    function addResponseBubble(exchange, data, isError) {
        let responseHtml = '';

        if (isError) {
            responseHtml = `
                <div class="chat-response">
                    <div class="bubble error-bubble">
                        <div class="response-status"><span class="dot"></span> Error</div>
                        <div style="color: var(--error); font-size: 13px;">${escapeHtml(data.error || 'Unknown error')}</div>
                    </div>
                    <div class="bubble-meta">${getTimestamp()}</div>
                </div>
            `;
        } else {
            const rowCount = data.results ? data.results.length : 0;
            const tableHtml = buildResultTable(data.results);
            const infoText = rowCount > 0 ? `${rowCount} row${rowCount !== 1 ? 's' : ''} returned` : 'No rows returned';

            responseHtml = `
                <div class="chat-response">
                    <div class="bubble">
                        <div class="response-status"><span class="dot"></span> Success</div>
                        <div class="response-info">${infoText}</div>
                        ${tableHtml}
                    </div>
                    <div class="bubble-meta">${getTimestamp()}</div>
                </div>
            `;
        }

        exchange.insertAdjacentHTML('beforeend', responseHtml);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    executeBtn.addEventListener('click', async () => {
        const query = cypherInput.value.trim();
        if (!query) return;

        executeBtn.disabled = true;
        const exchange = addQueryBubble(query);
        cypherInput.value = '';
        cypherInput.style.height = 'auto';

        try {
            const res = await fetch('/api/query', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query })
            });
            const data = await res.json();

            if (res.ok && data.status === 'success') {
                addResponseBubble(exchange, data, false);
            } else {
                addResponseBubble(exchange, data, true);
            }
        } catch (err) {
            addResponseBubble(exchange, { error: `Network Error: ${err}` }, true);
        }

        executeBtn.disabled = false;
        cypherInput.focus();
    });
});
