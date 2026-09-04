/**
 * MasterWriter 前端应用 v2
 * 现代简洁 UI + Agent Pipeline + 模板上传 + 外部查重
 */

const API_BASE = '';

const app = {
    state: {
        currentTab: 'dashboard',
        currentPaper: null,
        papers: [],
        templates: [],
        skills: [],
        library: [],
        lastResult: '',
        pendingTemplate: null
    },

    init() {
        this.loadTemplates();
        this.loadPapers();
        this.loadSkills();
        this.loadLibrary();
        this.checkHealth();
        this.setupUploadZone();
    },

    // === API ===
    async api(url, options = {}) {
        const res = await fetch(`${API_BASE}${url}`, {
            headers: { 'Content-Type': 'application/json' },
            ...options
        });
        return res.json();
    },

    async checkHealth() {
        try {
            const data = await this.api('/api/health');
            const el = document.getElementById('model-status');
            if (data.status === 'ok') {
                const def = (data.models || []).find(m => m.default);
                const modelInfo = def ? `<div class="text-xs text-gray-500 pl-5">默认模型: ${def.name}/${def.model} ${def.ready ? '' : '(未配置)'}</div>` : '';
                el.innerHTML = `
                    <div class="status-row mb-2">
                        <span class="status-dot"></span>
                        <span>服务运行正常</span>
                    </div>
                    <div class="text-xs text-gray-500 pl-5">模板 ${data.templates} 个 · Skill ${data.skills} 个</div>
                    ${modelInfo}
                `;
                this.loadConfiguredModels();
            }
        } catch (e) {
            document.getElementById('model-status').innerHTML = `
                <div class="status-row mb-2">
                    <span class="status-dot" style="background:#ef4444"></span>
                    <span>服务未连接</span>
                </div>
            `;
        }
    },

    async loadConfiguredModels() {
        try {
            const listRes = await this.api('/api/config/models');
            const def = (listRes.data || []).find(m => m.default);
            const sel = document.getElementById('setting-provider');
            if (def && sel) sel.value = def.name;
            await this.loadProviderConfig(sel ? sel.value : 'mock');
        } catch (e) {}
    },

    async loadProviderConfig(provider) {
        if (provider === 'mock') {
            document.getElementById('setting-apikey').value = '';
            document.getElementById('setting-model').value = '';
            document.getElementById('setting-baseurl').value = '';
            this.onProviderChange();
            return;
        }
        try {
            const res = await this.api(`/api/config/models/${provider}`);
            if (res.success && res.data) {
                document.getElementById('setting-apikey').value = res.data.api_key || '';
                document.getElementById('setting-model').value = res.data.model || '';
                document.getElementById('setting-baseurl').value =
                    res.data.base_url || this.defaultBaseUrl(provider);
            } else {
                document.getElementById('setting-apikey').value = '';
                document.getElementById('setting-model').value = this.defaultModelFor(provider);
                document.getElementById('setting-baseurl').value = this.defaultBaseUrl(provider);
            }
        } catch (e) {}
        this.onProviderChange();
    },

    onProviderChange() {
        const provider = document.getElementById('setting-provider').value;
        const baseUrlWrap = document.getElementById('setting-baseurl-wrap');
        if (provider === 'custom') {
            baseUrlWrap.style.display = '';
        } else if (provider === 'mock') {
            baseUrlWrap.style.display = 'none';
            document.getElementById('setting-apikey').value = '';
            document.getElementById('setting-model').value = 'mock-local';
        } else {
            baseUrlWrap.style.display = '';
            document.getElementById('setting-baseurl').value = this.defaultBaseUrl(provider);
        }
    },

    defaultBaseUrl(provider) {
        return {
            openai: 'https://api.openai.com/v1',
            zhipu: 'https://open.bigmodel.cn/api/paas/v4',
            deepseek: 'https://api.deepseek.com/v1',
            ollama: 'http://localhost:11434',
            custom: ''
        }[provider] || '';
    },

    async testConnection() {
        const provider = document.getElementById('setting-provider').value;
        const apiKey = document.getElementById('setting-apikey').value.trim();
        const model = document.getElementById('setting-model').value.trim();
        const baseUrl = document.getElementById('setting-baseurl').value.trim();
        const btn = document.getElementById('test-conn-btn');
        const result = document.getElementById('test-conn-result');

        if (provider === 'mock') {
            result.innerHTML = '<span class="text-green-600"><i class="fas fa-check"></i> 模拟模式无需测试</span>';
            return;
        }
        if (provider !== 'ollama' && (!apiKey || !model)) {
            result.innerHTML = '<span class="text-red-600">请先填写 API Key 和模型名</span>';
            return;
        }

        btn.innerHTML = '<div class="spinner" style="width:14px;height:14px"></div> 测试中...';
        btn.disabled = true;
        result.innerHTML = '';
        try {
            const res = await this.api('/api/config/models/test', {
                method: 'POST',
                body: JSON.stringify({ provider, api_key: apiKey, model, base_url: baseUrl })
            });
            if (res.success && res.data) {
                const d = res.data;
                result.innerHTML = d.ok
                    ? `<span class="text-green-600"><i class="fas fa-check-circle"></i> ${d.message}</span>`
                    : `<span class="text-red-600"><i class="fas fa-times-circle"></i> ${d.message}</span>`;
            } else {
                result.innerHTML = `<span class="text-red-600">${res.message || '测试失败'}</span>`;
            }
        } catch (e) {
            result.innerHTML = `<span class="text-red-600">请求失败: ${e.message}</span>`;
        } finally {
            btn.innerHTML = '<i class="fas fa-plug"></i> 测试连接';
            btn.disabled = false;
        }
    },

    // === Tab ===
    switchTab(tab) {
        this.state.currentTab = tab;
        document.querySelectorAll('.nav-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tab);
        });
        document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
        document.getElementById(`tab-${tab}`).classList.remove('hidden');
        if (tab === 'papers') this.loadPapers();
        if (tab === 'library') this.loadLibrary();
        if (tab === 'writing') this.renderWritingWorkspace();
    },

    // === Modal ===
    showModal(id) {
        const el = document.getElementById(id);
        el.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    },
    closeModal(id) {
        const el = document.getElementById(id);
        el.classList.add('hidden');
        document.body.style.overflow = '';
    },

    // === Toast ===
    showToast(message, type = 'info') {
        const toast = document.getElementById('toast');
        const msgEl = document.getElementById('toast-message');
        msgEl.textContent = message;
        toast.className = `toast toast-${type} show`;
        setTimeout(() => toast.classList.remove('show'), 3000);
    },

    // === Templates ===
    async loadTemplates() {
        const res = await this.api('/api/templates');
        this.state.templates = res.data || [];
        const select = document.getElementById('new-paper-template');
        if (select) {
            const existing = Array.from(select.options).map(o => o.value);
            this.state.templates.forEach(t => {
                if (!existing.includes(t.id)) {
                    const opt = document.createElement('option');
                    opt.value = t.id;
                    opt.textContent = t.name;
                    select.appendChild(opt);
                }
            });
        }
    },

    setupUploadZone() {
        const zone = document.getElementById('upload-zone');
        const input = document.getElementById('template-file-input');
        if (!zone || !input) return;

        zone.addEventListener('click', () => input.click());
        zone.addEventListener('dragover', (e) => {
            e.preventDefault();
            zone.classList.add('dragover');
        });
        zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
        zone.addEventListener('drop', (e) => {
            e.preventDefault();
            zone.classList.remove('dragover');
            if (e.dataTransfer.files.length) this.handleTemplateFile(e.dataTransfer.files[0]);
        });
        input.addEventListener('change', (e) => {
            if (e.target.files.length) this.handleTemplateFile(e.target.files[0]);
        });
    },

    async handleTemplateFile(file) {
        if (!file.name.endsWith('.docx')) {
            this.showToast('仅支持 .docx 格式', 'error');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        try {
            this.showToast('正在解析模板...');
            const res = await fetch(`${API_BASE}/api/templates/upload`, {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            if (data.success) {
                this.state.pendingTemplate = data.data;
                const preview = document.getElementById('upload-preview');
                preview.classList.remove('hidden');
                const cfg = data.data;
                preview.innerHTML = `
                    <div class="font-medium mb-2">解析成功：${cfg.name}</div>
                    <div class="grid grid-cols-2 gap-2 text-xs">
                        <div>页面：${cfg.page.width}×${cfg.page.height} cm</div>
                        <div>页边距：${cfg.page.margin_top}/${cfg.page.margin_left} cm</div>
                        <div>正文字体：${cfg.fonts.chinese} ${cfg.fonts.size}pt</div>
                        <div>行距：${cfg.paragraph.line_spacing} 倍</div>
                        <div>一级标题：${cfg.headings['1'].font} ${cfg.headings['1'].size}pt</div>
                        <div>二级标题：${cfg.headings['2'].font} ${cfg.headings['2'].size}pt</div>
                    </div>
                `;
            } else {
                this.showToast(data.message || '解析失败', 'error');
            }
        } catch (e) {
            this.showToast('上传失败: ' + e.message, 'error');
        }
    },

    async confirmUploadTemplate() {
        if (!this.state.pendingTemplate) {
            this.showToast('请先上传模板文件', 'error');
            return;
        }
        this.closeModal('modal-upload-template');
        this.showToast('模板已保存');
        await this.loadTemplates();
        this.state.pendingTemplate = null;
    },

    // === 模板管理 ===
    async showTemplateManage() {
        this.showModal('modal-template-manage');
        const container = document.getElementById('template-manage-list');
        container.innerHTML = '<div class="text-center py-4 text-gray-400">加载中...</div>';
        try {
            const res = await this.api('/api/templates/manage/list');
            const rows = res.data || [];
            if (!rows.length) {
                container.innerHTML = '<div class="text-center py-6 text-gray-400">暂无模板</div>';
                return;
            }
            container.innerHTML = rows.map(t => `
                <div class="flex justify-between items-center border border-gray-200 rounded-lg p-3">
                    <div>
                        <div class="flex items-center gap-2">
                            <span class="font-medium text-gray-900">${this.escapeHtml(t.name)}</span>
                            <span class="tag" style="background:${t.is_builtin ? '#e0e7ff' : '#fef3c7'};color:${t.is_builtin ? '#3730a3' : '#92400e'}">
                                ${t.is_builtin ? '内置' : '自定义'}
                            </span>
                        </div>
                        <div class="text-xs text-gray-500 mt-1">${this.escapeHtml(t.description || '')} <span class="text-gray-300">(${t.id})</span></div>
                    </div>
                    <button onclick="app.deleteTemplate('${t.id}', '${this.escapeHtml(t.name)}')" class="btn btn-sm btn-icon" ${t.is_builtin ? 'disabled' : ''} style="background:${t.is_builtin ? 'transparent' : '#fee2e2'};color:${t.is_builtin ? '#d1d5db' : '#dc2626'}" title="${t.is_builtin ? '内置模板不可删除' : '删除'}">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            `).join('');
        } catch (e) {
            container.innerHTML = `<div class="text-center py-4 text-red-500">加载失败: ${this.escapeHtml(e.message)}</div>`;
        }
    },

    async deleteTemplate(id, name) {
        if (!confirm(`确定删除模板「${name}」吗？`)) return;
        try {
            const res = await this.api(`/api/templates/${id}`, { method: 'DELETE' });
            if (res.success) {
                this.showToast('模板已删除');
                await this.loadTemplates();
                this.showTemplateManage();
            } else {
                this.showToast(res.message || '删除失败', 'error');
            }
        } catch (e) {
            this.showToast('删除失败: ' + e.message, 'error');
        }
    },

    // === Papers ===
    async loadPapers() {
        const res = await this.api('/api/papers');
        this.state.papers = res.data || [];
        this.renderPapersList();
    },

    renderPapersList() {
        const container = document.getElementById('papers-list');
        if (!this.state.papers.length) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon"><i class="fas fa-inbox"></i></div>
                    <p>暂无论文，点击右上角新建</p>
                </div>
            `;
            return;
        }
        container.innerHTML = this.state.papers.map(p => {
            const t = this.state.templates.find(x => x.id === p.template_id) || { name: p.template_id };
            return `
                <div class="list-item" onclick="app.selectPaper('${p.id}')">
                    <div>
                        <div class="list-item-title">${p.title || '未命名论文'}</div>
                        <div class="list-item-meta">
                            <span class="tag">${t.name}</span>
                            <span>${new Date(p.updated_at).toLocaleDateString()}</span>
                        </div>
                    </div>
                    <div class="flex gap-2">
                        <button onclick="event.stopPropagation(); app.selectPaper('${p.id}')" class="btn btn-sm btn-secondary btn-icon" title="编辑">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button onclick="event.stopPropagation(); app.deletePaper('${p.id}')" class="btn btn-sm btn-icon" style="background:#fee2e2;color:#dc2626" title="删除">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    },

    createNewPaper() {
        document.getElementById('new-paper-title').value = '';
        this.showModal('modal-new-paper');
    },

    async confirmCreatePaper() {
        const title = document.getElementById('new-paper-title').value.trim();
        const templateId = document.getElementById('new-paper-template').value;
        if (!title) {
            this.showToast('请输入论文题目', 'error');
            return;
        }
        const res = await this.api('/api/papers', {
            method: 'POST',
            body: JSON.stringify({ title, template_id: templateId })
        });
        if (res.success) {
            this.closeModal('modal-new-paper');
            this.showToast('论文创建成功');
            await this.loadPapers();
            await this.selectPaper(res.data.id);
        } else {
            this.showToast(res.message || '创建失败', 'error');
        }
    },

    async selectPaper(paperId) {
        const res = await this.api(`/api/papers/${paperId}`);
        if (res.success) {
            this.state.currentPaper = res.data;
            this.switchTab('writing');
        }
    },

    async deletePaper(paperId) {
        if (!confirm('确定删除这篇论文吗？')) return;
        await this.api(`/api/papers/${paperId}`, { method: 'DELETE' });
        this.showToast('已删除');
        this.loadPapers();
        if (this.state.currentPaper?.id === paperId) {
            this.state.currentPaper = null;
            this.switchTab('papers');
        }
    },

    // === Writing Workspace ===
    renderWritingWorkspace() {
        const container = document.getElementById('writing-workspace');
        const paper = this.state.currentPaper;
        if (!paper) {
            container.innerHTML = `
                <div class="card">
                    <div class="card-body text-center py-12">
                        <div class="empty-state-icon"><i class="fas fa-pen-fancy"></i></div>
                        <h3 class="text-lg font-semibold text-gray-700 mb-2">选择一篇论文开始写作</h3>
                        <p class="text-gray-500 mb-4">在"我的论文"中选择，或点击下方按钮创建新论文</p>
                        <button onclick="app.switchTab('papers')" class="btn btn-primary btn-sm">去选择论文</button>
                    </div>
                </div>
            `;
            return;
        }

        const templateName = this.state.templates.find(t => t.id === paper.template_id)?.name || paper.template_id;

        container.innerHTML = `
            <div class="space-y-4">
                <!-- 论文头部 -->
                <div class="card">
                    <div class="card-body">
                        <div class="flex flex-col md:flex-row md:justify-between md:items-start gap-4">
                            <div>
                                <h2 class="text-xl font-bold text-gray-900">${paper.title || '未命名论文'}</h2>
                                <div class="mt-2 flex flex-wrap gap-2">
                                    <span class="tag">${templateName}</span>
                                    <span class="tag">${paper.sections?.length || 0} 个章节</span>
                                </div>
                            </div>
                            <div class="flex gap-2">
                                <button onclick="app.exportPaper('docx')" class="btn btn-success btn-sm">
                                    <i class="fas fa-file-word"></i> Word
                                </button>
                                <button onclick="app.exportPaper('markdown')" class="btn btn-secondary btn-sm">
                                    <i class="fas fa-file-code"></i> Markdown
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 工具栏 -->
                <div class="card">
                    <div class="card-body">
                        <h3 class="text-sm font-semibold text-gray-700 mb-3">写作工具</h3>
                        <div class="tool-grid">
                            <button onclick="app.runSkill('paper_outline')" class="tool-btn">
                                <i class="fas fa-sitemap text-blue-600"></i>
                                <span>生成大纲</span>
                            </button>
                            <button onclick="app.runSkill('introduction')" class="tool-btn">
                                <i class="fas fa-play text-green-600"></i>
                                <span>引言</span>
                            </button>
                            <button onclick="app.runSkill('body_writing')" class="tool-btn">
                                <i class="fas fa-paragraph text-purple-600"></i>
                                <span>正文</span>
                            </button>
                            <button onclick="app.runSkill('conclusion')" class="tool-btn">
                                <i class="fas fa-flag-checkered text-orange-600"></i>
                                <span>结论</span>
                            </button>
                            <button onclick="app.runSkill('abstract')" class="tool-btn">
                                <i class="fas fa-compress text-pink-600"></i>
                                <span>摘要</span>
                            </button>
                            <button onclick="app.runSkill('references')" class="tool-btn">
                                <i class="fas fa-book-open text-indigo-600"></i>
                                <span>参考文献</span>
                            </button>
                            <button onclick="app.runPipeline('full_paper')" class="tool-btn" style="border-color:#bfdbfe;background:#eff6ff">
                                <i class="fas fa-magic text-blue-600"></i>
                                <span>一键成文</span>
                            </button>
                            <button onclick="app.runSkill('polish')" class="tool-btn">
                                <i class="fas fa-magic text-yellow-600"></i>
                                <span>润色</span>
                            </button>
                            <button onclick="app.runSkill('reduce_similarity')" class="tool-btn">
                                <i class="fas fa-compress-arrows-alt text-red-600"></i>
                                <span>降重</span>
                            </button>
                            <button onclick="app.runPipeline('polish_paper')" class="tool-btn" style="border-color:#fef3c7;background:#fffbeb">
                                <i class="fas fa-wand-magic text-amber-600"></i>
                                <span>一键润色全文</span>
                            </button>
                        </div>
                    </div>
                </div>

                <!-- 编辑器 -->
                <div class="editor-layout">
                    <div class="outline-panel">
                        <div class="flex justify-between items-center mb-3">
                            <h3 class="font-semibold text-gray-700">大纲</h3>
                            <div class="flex gap-1">
                                <button onclick="app.runSkill('paper_outline')" class="text-xs text-blue-600 hover:text-blue-800" title="重新生成">
                                    <i class="fas fa-sync-alt"></i>
                                </button>
                                <button onclick="app.toggleOutlineEdit()" class="text-xs text-gray-500 hover:text-gray-700" title="编辑大纲" id="outline-edit-btn">
                                    <i class="fas fa-pen"></i>
                                </button>
                            </div>
                        </div>
                        <div id="outline-tree" class="text-sm text-gray-600">
                            ${this.renderOutlineTree(paper.outline)}
                        </div>
                        <div id="outline-editor" class="hidden"></div>
                    </div>
                    <div class="editor-panel">
                        <div class="editor-toolbar">
                            <button onclick="app.addSection()" class="btn btn-primary btn-sm">
                                <i class="fas fa-plus"></i> 章节
                            </button>
                            <button onclick="app.saveAllSections()" class="btn btn-secondary btn-sm">
                                <i class="fas fa-save"></i> 保存
                            </button>
                        </div>
                        <div class="editor-content">
                            <div id="sections-list" class="space-y-4 p-4">
                                ${this.renderSections(paper.sections || [])}
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 生成结果 -->
                <div class="card">
                    <div class="card-body">
                        <div class="flex justify-between items-center mb-3">
                            <h3 class="font-semibold text-gray-700">AI 生成结果</h3>
                            <div class="flex gap-2">
                                <button onclick="app.copyResult()" class="btn btn-secondary btn-sm">复制</button>
                                <button onclick="app.insertToSection()" class="btn btn-primary btn-sm">插入章节</button>
                            </div>
                        </div>
                        <div id="generation-result" class="result-box">点击上方工具开始写作...</div>
                    </div>
                </div>
            </div>
        `;
    },

    renderOutlineTree(outline) {
        if (!outline || !outline.sections) {
            return '<div class="text-gray-400 italic">暂无大纲，点击生成</div>';
        }
        const renderNode = (node, level) => {
            const indent = level * 0.75;
            const size = level === 1 ? 'font-medium text-gray-800' : 'text-gray-600';
            let html = `<div style="margin-left:${indent}rem;margin-bottom:0.5rem" class="${size}">${node.title}</div>`;
            if (node.children) {
                html += node.children.map(c => renderNode(c, level + 1)).join('');
            }
            return html;
        };
        return outline.sections.map(s => renderNode(s, 0)).join('');
    },

    renderSections(sections) {
        if (!sections.length) {
            return '<div class="empty-state py-8"><p>暂无章节，点击上方"章节"按钮添加</p></div>';
        }
        return sections.map((s, i) => `
            <div class="border border-gray-200 rounded-lg p-3 hover:border-blue-300 transition" data-section-id="${s.id}">
                <div class="flex justify-between items-center mb-2">
                    <input type="text" value="${this.escapeHtml(s.title || '')}" 
                        onchange="app.updateSection('${s.id}', 'title', this.value)"
                        class="font-medium text-gray-900 bg-transparent border-none focus:outline-none focus:ring-0 w-full" 
                        placeholder="章节标题">
                    <div class="flex gap-1 ml-2 items-center">
                        ${s.type !== 'abstract' && s.type !== 'references' ? `
                        <button onclick="app.toggleSectionPreview('${s.id}', this)" class="text-gray-400 hover:text-blue-600 text-xs" title="预览">
                            <i class="fas fa-eye"></i>
                        </button>` : ''}
                        <button onclick="app.moveSection('${s.id}', -1)" class="text-gray-400 hover:text-gray-600" ${i === 0 ? 'disabled' : ''}><i class="fas fa-chevron-up"></i></button>
                        <button onclick="app.moveSection('${s.id}', 1)" class="text-gray-400 hover:text-gray-600" ${i === sections.length - 1 ? 'disabled' : ''}><i class="fas fa-chevron-down"></i></button>
                        <button onclick="app.deleteSection('${s.id}')" class="text-red-400 hover:text-red-600"><i class="fas fa-times"></i></button>
                    </div>
                </div>
                <textarea id="sec-text-${s.id}"
                    onchange="app.updateSection('${s.id}', 'content', this.value)"
                    class="w-full text-sm text-gray-700 border border-gray-200 rounded-lg p-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent" 
                    rows="5" placeholder="章节内容...">${this.escapeHtml(s.content || '')}</textarea>
                <div id="sec-preview-${s.id}" class="hidden border border-gray-200 rounded-lg p-3 text-sm text-gray-700 prose-view"></div>
            </div>
        `).join('');
    },

    toggleSectionPreview(id, btn) {
        const textEl = document.getElementById(`sec-text-${id}`);
        const prevEl = document.getElementById(`sec-preview-${id}`);
        const isPreview = prevEl.classList.contains('hidden');
        if (isPreview) {
            prevEl.innerHTML = this.mdToHtml(textEl.value);
            prevEl.classList.remove('hidden');
            textEl.classList.add('hidden');
            btn.innerHTML = '<i class="fas fa-pen"></i>';
        } else {
            prevEl.classList.add('hidden');
            textEl.classList.remove('hidden');
            btn.innerHTML = '<i class="fas fa-eye"></i>';
        }
    },

    mdToHtml(md) {
        if (!md) return '<span class="text-gray-400">（空内容）</span>';
        const esc = (t) => {
            const div = document.createElement('div');
            div.textContent = t;
            return div.innerHTML;
        };
        const lines = md.split('\n');
        let html = '';
        let inList = false;
        const closeList = () => { if (inList) { html += '</ul>'; inList = false; } };
        for (let raw of lines) {
            const line = raw.trim();
            if (!line) { closeList(); continue; }
            // 标题
            const h = line.match(/^(#{1,4})\s+(.+)/);
            if (h) {
                closeList();
                const lv = h[1].length;
                const cls = lv === 1 ? 'text-lg font-bold' : lv === 2 ? 'text-base font-bold' : 'text-sm font-semibold';
                html += `<div class="${cls} mt-2">${esc(h[2])}</div>`;
                continue;
            }
            // 列表
            if (/^[-*]\s+/.test(line)) {
                if (!inList) { html += '<ul class="list-disc ml-5">'; inList = true; }
                html += `<li>${esc(line.replace(/^[-*]\s+/, ''))}</li>`;
                continue;
            }
            closeList();
            // 加粗/斜体
            let t = esc(line);
            t = t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\*(.+?)\*/g, '<em>$1</em>');
            html += `<p class="mb-2 leading-relaxed">${t}</p>`;
        }
        closeList();
        return html;
    },

    toggleOutlineEdit() {
        const tree = document.getElementById('outline-tree');
        const editor = document.getElementById('outline-editor');
        const paper = this.state.currentPaper;
        if (!paper || !paper.outline) return;
        if (editor.classList.contains('hidden')) {
            // 进入编辑模式
            const renderNodeEdit = (node, level) => {
                const cls = level === 0 ? ['w-full font-medium', 'text-gray-800'] : ['w-full ml-' + (level * 4), 'text-gray-600'];
                let html = `<div class="flex items-center gap-1 mb-1">`;
                html += `<span class="text-gray-400 text-xs">${'　'.repeat(level)}${node.level || level + 1}.</span>`;
                html += `<input class="outline-title-input flex-1 border border-gray-200 rounded px-2 py-1 text-sm" value="${this.escapeHtml(node.title || '')}" data-path="${this.outlinePath(node)}">`;
                html += `</div>`;
                if (node.children) html += node.children.map(c => renderNodeEdit(c, level + 1)).join('');
                return html;
            };
            const list = paper.outline.sections || [];
            editor.innerHTML = list.map(n => renderNodeEdit(n, 0)).join('') +
                '<div class="mt-3 flex gap-2"><button onclick="app.saveOutlineEdit()" class="btn btn-primary btn-sm">保存大纲</button>' +
                '<button onclick="app.cancelOutlineEdit()" class="btn btn-secondary btn-sm">取消</button></div>';
            editor.classList.remove('hidden');
            tree.classList.add('hidden');
        }
    },

    outlinePath(node) {
        // 生成节点路径标识（用标题关联）
        return node.title;
    },

    async saveOutlineEdit() {
        const paper = this.state.currentPaper;
        const titleMap = {};
        document.querySelectorAll('.outline-title-input').forEach(inp => {
            titleMap[inp.dataset.path] = inp.value.trim();
        });
        // 更新大纲对象中的标题
        const updateTitles = (nodes) => {
            nodes.forEach(n => {
                if (titleMap[n.title] !== undefined) {
                    n.title = titleMap[n.title];
                }
                if (n.children) updateTitles(n.children);
            });
        };
        updateTitles(paper.outline.sections || []);
        // 保存
        const res = await this.api(`/api/papers/${paper.id}`, {
            method: 'PUT',
            body: JSON.stringify({ outline: paper.outline })
        });
        if (res.success) {
            this.showToast('大纲已保存');
            await this.selectPaper(paper.id);
        } else {
            this.showToast('保存失败', 'error');
        }
    },

    cancelOutlineEdit() {
        const tree = document.getElementById('outline-tree');
        const editor = document.getElementById('outline-editor');
        editor.classList.add('hidden');
        tree.classList.remove('hidden');
    },

    async addSection() {
        if (!this.state.currentPaper) return;
        const res = await this.api('/api/sections', {
            method: 'POST',
            body: JSON.stringify({
                paper_id: this.state.currentPaper.id,
                type: 'body',
                title: '新章节',
                content: '',
                order: (this.state.currentPaper.sections || []).length
            })
        });
        if (res.success) {
            await this.selectPaper(this.state.currentPaper.id);
            this.showToast('章节已添加');
        }
    },

    async updateSection(id, field, value) {
        await this.api(`/api/sections/${id}`, {
            method: 'PUT',
            body: JSON.stringify({ [field]: value })
        });
    },

    async saveAllSections() {
        this.showToast('保存成功');
        await this.selectPaper(this.state.currentPaper.id);
    },

    async deleteSection(id) {
        await this.api(`/api/sections/${id}`, { method: 'DELETE' });
        await this.selectPaper(this.state.currentPaper.id);
    },

    async moveSection(id, direction) {
        // 简化实现：服务端暂不提供重排，通过顺序更新
        await this.selectPaper(this.state.currentPaper.id);
    },

    // === Skills ===
    async loadSkills() {
        const res = await this.api('/api/skills');
        this.state.skills = res.data || [];
    },

    async runSkill(skillId) {
        if (!this.state.currentPaper) {
            this.showToast('请先选择一篇论文', 'error');
            return;
        }
        const inputs = this.buildSkillInputs(skillId);
        if (inputs === null) return;
        await this.streamExecute(`/api/skills/${skillId}/execute`, {
            paper_id: this.state.currentPaper.id,
            inputs,
            stream: true
        });
    },

    async runPipeline(pipelineName) {
        if (!this.state.currentPaper) {
            this.showToast('请先选择一篇论文', 'error');
            return;
        }
        await this.streamExecute(`/api/agent/pipeline/${pipelineName}`, {
            paper_id: this.state.currentPaper.id,
            inputs: {},
            stream: true
        });
    },

    buildSkillInputs(skillId) {
        const paper = this.state.currentPaper;
        const inputs = {};
        if (skillId === 'paper_outline') {
            inputs.topic = paper.title;
            inputs.paper_type = paper.template_id;
            inputs.word_count = 10000;
        } else if (skillId === 'introduction' || skillId === 'conclusion') {
            inputs.topic = paper.title;
        } else if (skillId === 'body_writing') {
            const title = prompt('请输入当前章节标题：', '第一章 绪论');
            if (!title) return null;
            inputs.section_title = title;
            inputs.word_count = 2000;
        } else if (skillId === 'abstract') {
            inputs.full_text = (paper.sections || []).map(s => s.content).join('\n\n');
        } else if (skillId === 'references') {
            inputs.topic = paper.title;
            inputs.full_text = (paper.sections || []).map(s => s.content).join('\n\n');
            inputs.count = 10;
        } else if (skillId === 'polish' || skillId === 'reduce_similarity') {
            const text = prompt('请输入要处理的文本：');
            if (!text) return null;
            inputs.text = text;
        }
        return inputs;
    },

    async streamExecute(url, body) {
        const resultEl = document.getElementById('generation-result');
        this._genController = new AbortController();
        let fullText = '';

        resultEl.innerHTML = `
            <div class="flex items-center text-blue-600 gap-3">
                <div class="spinner"></div>
                <span>正在生成...</span>
                <button onclick="app.pauseGeneration()" class="btn btn-secondary btn-sm" style="background:#fff7ed;color:#c2410c;border:1px solid #fdba74">
                    <i class="fas fa-pause"></i> 暂停
                </button>
            </div>`;

        try {
            const response = await fetch(`${API_BASE}${url}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
                signal: this._genController.signal
            });
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            resultEl.innerHTML = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const text = decoder.decode(value);
                const lines = text.split('\n');
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = line.slice(6);
                        if (data === '[DONE]') continue;
                        try {
                            const parsed = JSON.parse(data);
                            if (parsed.chunk) {
                                fullText += parsed.chunk;
                                resultEl.innerHTML = this.escapeHtml(fullText);
                                resultEl.scrollTop = resultEl.scrollHeight;
                            }
                        } catch (e) {}
                    }
                }
            }
            this._genController = null;
            this.state.lastResult = fullText;
            this.showToast('生成完成');
            setTimeout(() => this.selectPaper(this.state.currentPaper.id), 500);
        } catch (e) {
            this._genController = null;
            if (e.name === 'AbortError') {
                // 用户暂停：保存已生成的部分内容
                this.state.lastResult = fullText;
                if (fullText && fullText.trim()) {
                    resultEl.innerHTML = this.escapeHtml(fullText) +
                        '<div class="mt-3 text-green-600"><i class="fas fa-check-circle"></i> 已暂停，正在保存已生成内容...</div>';
                    await this.savePausedContent(fullText);
                } else {
                    resultEl.innerHTML = '<span class="text-gray-500">已暂停（暂无内容可保存）</span>';
                }
            } else {
                resultEl.innerHTML = `<span style="color:var(--danger)">生成失败: ${e.message}</span>`;
            }
        }
    },

    async pauseGeneration() {
        if (this._genController) {
            this._genController.abort();
        }
    },

    async savePausedContent(text) {
        const paper = this.state.currentPaper;
        if (!paper) {
            this.showToast('未找到论文', 'error');
            return;
        }
        try {
            const now = new Date();
            const ts = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
            const res = await this.api('/api/sections', {
                method: 'POST',
                body: JSON.stringify({
                    paper_id: paper.id,
                    type: 'body',
                    title: 'AI 生成内容（暂停于 ' + ts + '）',
                    content: text,
                    order: (paper.sections || []).length
                })
            });
            if (res.success) {
                this.showToast('已保存，可导出 Word 查看（新增了一个章节）');
                await this.selectPaper(paper.id);
            } else {
                this.showToast('保存失败: ' + (res.message || ''), 'error');
            }
        } catch (err) {
            this.showToast('保存失败: ' + err.message, 'error');
        }
    },

    // === Plagiarism ===
    async checkPlagiarism(mode) {
        const text = document.getElementById('plagiarism-text').value.trim();
        if (!text) {
            this.showToast('请输入待查重文本', 'error');
            return;
        }

        if (mode === 'external') {
            this.showToast('第三方查重需要配置 API Key', 'info');
            return;
        }

        const threshold = parseFloat(document.getElementById('plagiarism-threshold').value);
        const resultEl = document.getElementById('plagiarism-result');
        resultEl.classList.remove('hidden');
        resultEl.innerHTML = '<div class="flex items-center text-purple-600 gap-2"><div class="spinner" style="border-color:rgba(139,92,246,0.3);border-top-color:var(--purple)"></div>正在查重...</div>';

        try {
            const res = await this.api('/api/plagiarism/check', {
                method: 'POST',
                body: JSON.stringify({ text, threshold })
            });
            if (res.success) {
                this.renderPlagiarismResult(res.data);
            } else {
                resultEl.innerHTML = `<div style="color:var(--danger)">查重失败: ${res.message}</div>`;
            }
        } catch (e) {
            resultEl.innerHTML = `<div style="color:var(--danger)">请求失败: ${e.message}</div>`;
        }
    },

    renderPlagiarismResult(data) {
        const resultEl = document.getElementById('plagiarism-result');
        const pct = (data.overall_similarity * 100).toFixed(1);
        const colorClass = data.overall_similarity > 0.3 ? 'similarity-high' : (data.overall_similarity > 0.1 ? 'similarity-medium' : 'similarity-low');

        let matchesHtml = '';
        if (data.matches && data.matches.length > 0) {
            matchesHtml = data.matches.map(m => `
                <div class="match-item">
                    <div class="match-source">
                        <span class="font-semibold text-red-700">${m.source_title}</span>
                        <span class="text-red-600 font-medium">${(m.similarity * 100).toFixed(1)}%</span>
                    </div>
                    <div class="match-text">${this.escapeHtml(m.matched_text)}</div>
                </div>
            `).join('');
        } else {
            matchesHtml = `<div class="text-center py-6 text-green-600"><i class="fas fa-check-circle text-2xl mb-2 block"></i>未发现明显重复内容</div>`;
        }

        resultEl.innerHTML = `
            <div class="flex items-center justify-between border-b border-gray-100 pb-4 mb-4">
                <div>
                    <div class="text-sm text-gray-500">总体相似度</div>
                    <div class="similarity-score ${colorClass}">${pct}%</div>
                </div>
                <div class="text-right text-sm text-gray-500">
                    <div>检查字数</div>
                    <div class="font-medium text-gray-900">${data.checked_length} 字</div>
                </div>
            </div>
            <div>${matchesHtml}</div>
        `;
    },

    // === Library ===
    async loadLibrary() {
        const res = await this.api('/api/plagiarism/library');
        this.state.library = res.data || [];
        this.renderLibraryList();
    },

    renderLibraryList() {
        const container = document.getElementById('library-list');
        if (!this.state.library.length) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon"><i class="fas fa-book"></i></div>
                    <p>暂无文档，点击右上角添加</p>
                </div>
            `;
            return;
        }
        container.innerHTML = this.state.library.map(doc => `
            <div class="list-item">
                <div>
                    <div class="list-item-title">${doc.title || '未命名'}</div>
                    <div class="list-item-meta">${new Date(doc.added_at).toLocaleDateString()}</div>
                </div>
                <button onclick="app.deleteLibraryDoc('${doc.id}')" class="btn btn-sm btn-icon" style="background:#fee2e2;color:#dc2626">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `).join('');
    },

    showAddLibraryModal() {
        document.getElementById('library-title').value = '';
        document.getElementById('library-content').value = '';
        this.showModal('modal-add-library');
    },

    async confirmAddLibrary() {
        const title = document.getElementById('library-title').value.trim();
        const content = document.getElementById('library-content').value.trim();
        if (!title || !content) {
            this.showToast('请填写标题和内容', 'error');
            return;
        }
        const res = await this.api('/api/plagiarism/library', {
            method: 'POST',
            body: JSON.stringify({ title, content })
        });
        if (res.success) {
            this.closeModal('modal-add-library');
            this.showToast('添加成功');
            this.loadLibrary();
        } else {
            this.showToast(res.message || '添加失败', 'error');
        }
    },

    async deleteLibraryDoc(id) {
        if (!confirm('确定删除此文档？')) return;
        await this.api(`/api/plagiarism/library/${id}`, { method: 'DELETE' });
        this.showToast('已删除');
        this.loadLibrary();
    },

    // === Export ===
    async exportPaper(format) {
        if (!this.state.currentPaper) {
            this.showToast('请先选择论文', 'error');
            return;
        }
        try {
            const res = await fetch(`${API_BASE}/api/export/${format}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ paper_id: this.state.currentPaper.id })
            });
            if (!res.ok) {
                const err = await res.json();
                this.showToast(err.message || '导出失败', 'error');
                return;
            }
            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const filename = res.headers.get('content-disposition')?.match(/filename="(.+)"/)?.[1] || `论文.${format}`;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            this.showToast('导出成功');
        } catch (e) {
            this.showToast('导出失败: ' + e.message, 'error');
        }
    },

    // === Utils ===
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    copyResult() {
        const text = document.getElementById('generation-result').innerText;
        navigator.clipboard.writeText(text).then(() => this.showToast('已复制'));
    },

    insertToSection() {
        const text = this.state.lastResult;
        if (!text || !this.state.currentPaper) {
            this.showToast('没有可插入的内容', 'error');
            return;
        }
        const sections = this.state.currentPaper.sections || [];
        if (!sections.length) {
            this.showToast('请先添加章节', 'error');
            return;
        }
        const last = sections[sections.length - 1];
        const newContent = last.content ? last.content + '\n\n' + text : text;
        this.updateSection(last.id, 'content', newContent);
        this.showToast('已插入到最后章节');
        setTimeout(() => this.selectPaper(this.state.currentPaper.id), 300);
    },

    // === Settings & Help ===
    showSettings() {
        this.showModal('modal-settings');
        this.loadConfiguredModels();
    },
    async saveSettings() {
        const provider = document.getElementById('setting-provider').value;
        const apiKey = document.getElementById('setting-apikey').value.trim();
        const model = document.getElementById('setting-model').value.trim();
        const baseUrl = document.getElementById('setting-baseurl').value.trim();

        let payload;
        if (provider === 'ollama') {
            payload = { provider: 'ollama', api_key: '', model: model || 'qwen2.5', base_url: baseUrl || 'http://localhost:11434' };
        } else if (provider === 'mock') {
            payload = { provider: 'mock', api_key: '', model: 'mock-local' };
        } else if (provider === 'custom') {
            if (!apiKey || !model || !baseUrl) {
                this.showToast('自定义供应商需填写 API Key、模型名和接口地址', 'error');
                return;
            }
            payload = { provider: 'custom', api_key: apiKey, model, base_url: baseUrl };
        } else {
            payload = {
                provider,
                api_key: apiKey,
                model: model || this.defaultModelFor(provider),
                base_url: baseUrl || this.defaultBaseUrl(provider)
            };
        }

        const res = await this.api('/api/config/models', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        if (res.success) {
            this.closeModal('modal-settings');
            this.showToast('模型配置已保存');
            this.checkHealth();
        } else {
            this.showToast(res.message || '保存失败', 'error');
        }
    },
    defaultModelFor(provider) {
        return {
            openai: 'gpt-4o-mini',
            zhipu: 'glm-4-flash',
            deepseek: 'deepseek-chat',
            custom: '（填写你的模型名）'
        }[provider] || 'gpt-4o-mini';
    },
    showHelp() {
        alert(`MasterWriter 使用帮助：\n\n1. 配置 AI 模型（设置中填写 API Key）\n2. 新建论文或上传 Word 模板\n3. 使用"生成大纲"规划论文结构\n4. 分步生成各章节内容\n5. 使用"一键成文"自动完成全文\n6. 查重：本地库免费查重，或配置第三方 API\n7. 导出 Word / Markdown`);
    }
};

document.addEventListener('DOMContentLoaded', () => app.init());
