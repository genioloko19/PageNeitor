/**
 * API client module for Pageneitor v3.0.
 * Handles links, profiles, categories, gamification with decay, and local Ollama AI.
 */

const API = {
  baseUrl: window.location.origin.includes('http') ? window.location.origin : 'http://127.0.0.1:5241',

  async getLinks(params = {}) {
    const searchParams = new URLSearchParams();
    if (params.profile_id) searchParams.append('profile_id', params.profile_id);
    if (params.category_id) searchParams.append('category_id', params.category_id);
    if (params.query) searchParams.append('q', params.query);
    if (params.favorite) searchParams.append('favorite', 'true');
    if (params.unread) searchParams.append('unread', 'true');
    if (params.archived) searchParams.append('archived', 'true');
    if (params.root_domain) searchParams.append('root_domain', params.root_domain);

    const res = await fetch(`${this.baseUrl}/api/links?${searchParams.toString()}`);
    return await res.json();
  },

  async getLink(id) {
    const res = await fetch(`${this.baseUrl}/api/links/${id}`);
    return await res.json();
  },

  async createLink(linkData) {
    const res = await fetch(`${this.baseUrl}/api/links`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(linkData)
    });
    return await res.json();
  },

  async updateLink(id, updateData) {
    const res = await fetch(`${this.baseUrl}/api/links/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updateData)
    });
    return await res.json();
  },

  async deleteLink(id) {
    const res = await fetch(`${this.baseUrl}/api/links/${id}`, {
      method: 'DELETE'
    });
    return await res.json();
  },

  async openInBrowser(id) {
    const res = await fetch(`${this.baseUrl}/api/links/${id}/open`, {
      method: 'POST'
    });
    return await res.json();
  },

  async scrapeUrl(url) {
    const res = await fetch(`${this.baseUrl}/api/scrape`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });
    return await res.json();
  },

  // Profiles CRUD
  async getProfiles() {
    const res = await fetch(`${this.baseUrl}/api/profiles`);
    return await res.json();
  },

  async createProfile(data) {
    const res = await fetch(`${this.baseUrl}/api/profiles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    return await res.json();
  },

  async updateProfile(id, data) {
    const res = await fetch(`${this.baseUrl}/api/profiles/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    return await res.json();
  },

  async deleteProfile(id) {
    const res = await fetch(`${this.baseUrl}/api/profiles/${id}`, {
      method: 'DELETE'
    });
    return await res.json();
  },

  // Categories CRUD
  async getCategories() {
    const res = await fetch(`${this.baseUrl}/api/categories`);
    return await res.json();
  },

  async createCategory(data) {
    const res = await fetch(`${this.baseUrl}/api/categories`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    return await res.json();
  },

  async updateCategory(id, data) {
    const res = await fetch(`${this.baseUrl}/api/categories/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    return await res.json();
  },

  async deleteCategory(id) {
    const res = await fetch(`${this.baseUrl}/api/categories/${id}`, {
      method: 'DELETE'
    });
    return await res.json();
  },

  async getStats() {
    const res = await fetch(`${this.baseUrl}/api/stats`);
    return await res.json();
  },

  async getGamification() {
    const res = await fetch(`${this.baseUrl}/api/gamification`);
    return await res.json();
  },

  async getAnalytics() {
    const res = await fetch(`${this.baseUrl}/api/analytics`);
    return await res.json();
  },

  async batchImport(text, profile_id, category_id) {
    const res = await fetch(`${this.baseUrl}/api/batch-import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, profile_id, category_id })
    });
    return await res.json();
  },

  // Ollama AI Local Endpoints
  async getOllamaStatus() {
    const res = await fetch(`${this.baseUrl}/api/ollama/status`);
    return await res.json();
  },

  async startOllama() {
    const res = await fetch(`${this.baseUrl}/api/ollama/start`, {
      method: 'POST'
    });
    return await res.json();
  },

  async configOllama(host, model) {
    const res = await fetch(`${this.baseUrl}/api/ollama/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ host, model })
    });
    return await res.json();
  },

  async getCyclicTip(context = {}) {
    const res = await fetch(`${this.baseUrl}/api/ollama/cyclic-tip`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(context)
    });
    return await res.json();
  },

  // ==========================================
  // Credentials Vault (Multi-Account per Link)
  // ==========================================
  async getCredentials(linkId) {
    const res = await fetch(`${this.baseUrl}/api/links/${linkId}/credentials`);
    return await res.json();
  },

  async addCredential(linkId, credData) {
    const res = await fetch(`${this.baseUrl}/api/links/${linkId}/credentials`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(credData)
    });
    return await res.json();
  },

  async updateCredential(linkId, credId, credData) {
    const res = await fetch(`${this.baseUrl}/api/links/${linkId}/credentials/${credId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(credData)
    });
    return await res.json();
  },

  async deleteCredential(linkId, credId) {
    const res = await fetch(`${this.baseUrl}/api/links/${linkId}/credentials/${credId}`, {
      method: 'DELETE'
    });
    return await res.json();
  },

  // ==========================================
  // Sub-Links / Child Tabs per Link
  // ==========================================
  async getSublinks(linkId) {
    const res = await fetch(`${this.baseUrl}/api/links/${linkId}/sublinks`);
    return await res.json();
  },

  async addSublink(linkId, subData) {
    const res = await fetch(`${this.baseUrl}/api/links/${linkId}/sublinks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(subData)
    });
    return await res.json();
  },

  async batchAddSublinks(linkId, text) {
    const res = await fetch(`${this.baseUrl}/api/links/${linkId}/sublinks/batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    return await res.json();
  },

  async toggleSublinkRead(linkId, subId) {
    const res = await fetch(`${this.baseUrl}/api/links/${linkId}/sublinks/${subId}/toggle-read`, {
      method: 'PUT'
    });
    return await res.json();
  },

  async openSublink(linkId, subId) {
    const res = await fetch(`${this.baseUrl}/api/links/${linkId}/sublinks/${subId}/open`, {
      method: 'POST'
    });
    return await res.json();
  },

  async openAllSublinks(linkId) {
    const res = await fetch(`${this.baseUrl}/api/links/${linkId}/sublinks/open-all`, {
      method: 'POST'
    });
    return await res.json();
  },

  async deleteSublink(linkId, subId) {
    const res = await fetch(`${this.baseUrl}/api/links/${linkId}/sublinks/${subId}`, {
      method: 'DELETE'
    });
    return await res.json();
  },

  // ==========================================
  // Zero-Loss Database & Backup Engine
  // ==========================================
  getExportDbUrl() {
    return `${this.baseUrl}/api/backup/export-db`;
  },

  getExportJsonUrl() {
    return `${this.baseUrl}/api/backup/export-json`;
  },

  async importJsonData(payload, mode = 'merge') {
    const res = await fetch(`${this.baseUrl}/api/backup/import-json`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode, backup_data: payload })
    });
    return await res.json();
  },

  async createBackup() {
    const res = await fetch(`${this.baseUrl}/api/backup/create`, { method: 'POST' });
    return await res.json();
  },

  async getDbInfo() {
    const res = await fetch(`${this.baseUrl}/api/db/info`);
    return await res.json();
  },

  async importDbFile(formData) {
    const res = await fetch(`${this.baseUrl}/api/backup/import-db`, {
      method: 'POST',
      body: formData
    });
    return await res.json();
  },

  async listAutoBackups() {
    const res = await fetch(`${this.baseUrl}/api/backup/list-auto`);
    return await res.json();
  },

  async restoreAutoBackup(filename) {
    const res = await fetch(`${this.baseUrl}/api/backup/restore-auto`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename })
    });
    return await res.json();
  },

  // ==========================================
  // Persistent Floating Assistant
  // ==========================================
  async getChatSessions() {
    const res = await fetch(`${this.baseUrl}/api/chat/sessions`);
    return await res.json();
  },

  async getChatSession(sessionId) {
    const res = await fetch(`${this.baseUrl}/api/chat/sessions/${sessionId}`);
    return await res.json();
  },

  async sendChatMessage(message, sessionId = null) {
    const res = await fetch(`${this.baseUrl}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, session_id: sessionId })
    });
    return await res.json();
  },

  async renameChatSession(sessionId, title) {
    const res = await fetch(`${this.baseUrl}/api/chat/sessions/${sessionId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title })
    });
    return await res.json();
  },

  async deleteChatSession(sessionId) {
    const res = await fetch(`${this.baseUrl}/api/chat/sessions/${sessionId}`, {
      method: 'DELETE'
    });
    return await res.json();
  },

  // ==========================================
  // Domain grouping, LLM suggestions & undo
  // ==========================================
  async getDomainDashboard() {
    const res = await fetch(`${this.baseUrl}/api/domains/dashboard`);
    return await res.json();
  },

  async getDomainGroups() {
    const res = await fetch(`${this.baseUrl}/api/domains/groups`);
    return await res.json();
  },

  async getDomainSuggestions(status = 'pending', unreadOnly = false) {
    const params = new URLSearchParams({ status });
    if (unreadOnly) params.append('unread', 'true');
    const res = await fetch(`${this.baseUrl}/api/domains/suggestions?${params.toString()}`);
    return await res.json();
  },

  async getDomainSuggestion(id) {
    const res = await fetch(`${this.baseUrl}/api/domains/suggestions/${id}`);
    return await res.json();
  },

  async applyDomainSuggestion(id) {
    const res = await fetch(`${this.baseUrl}/api/domains/suggestions/${id}/apply`, { method: 'POST' });
    return await res.json();
  },

  async dismissDomainSuggestion(id) {
    const res = await fetch(`${this.baseUrl}/api/domains/suggestions/${id}/dismiss`, { method: 'POST' });
    return await res.json();
  },

  async markDomainSuggestionsRead(ids = null) {
    const res = await fetch(`${this.baseUrl}/api/domains/suggestions/read`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids })
    });
    return await res.json();
  },

  async getDomainSettings() {
    const res = await fetch(`${this.baseUrl}/api/domains/settings`);
    return await res.json();
  },

  async saveDomainSettings(data) {
    const res = await fetch(`${this.baseUrl}/api/domains/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    return await res.json();
  },

  async scanDomains() {
    const res = await fetch(`${this.baseUrl}/api/domains/scan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ use_llm: true })
    });
    return await res.json();
  },

  async mergeDomain(rootDomain, mainLinkId, linkIds, reason = 'manual') {
    const res = await fetch(`${this.baseUrl}/api/domains/merge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        root_domain: rootDomain,
        main_link_id: mainLinkId,
        link_ids: linkIds,
        reason
      })
    });
    return await res.json();
  },

  async undoDomainAction() {
    const res = await fetch(`${this.baseUrl}/api/domains/undo`, { method: 'POST' });
    return await res.json();
  },

  async getDomainActions() {
    const res = await fetch(`${this.baseUrl}/api/domains/actions`);
    return await res.json();
  },

  async openAllDomain(rootDomain) {
    const res = await fetch(`${this.baseUrl}/api/domains/open-all`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ root_domain: rootDomain })
    });
    return await res.json();
  },

  async getDomainDetail(rootDomain) {
    const res = await fetch(`${this.baseUrl}/api/domains/detail?root_domain=${encodeURIComponent(rootDomain)}`);
    return await res.json();
  },

  // ==========================================
  // Link insertion assistant
  // ==========================================
  async previewLinks(text, useLlm = true) {
    const res = await fetch(`${this.baseUrl}/api/links/assistant/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, use_llm: useLlm })
    });
    return await res.json();
  },

  async commitAssistantLinks(items, acceptNewCategories = true, acceptNewProfiles = true, skipDuplicates = true) {
    const res = await fetch(`${this.baseUrl}/api/links/assistant/commit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        items,
        accept_new_categories: acceptNewCategories,
        accept_new_profiles: acceptNewProfiles,
        skip_duplicates: skipDuplicates
      })
    });
    return await res.json();
  },

  // ==========================================
  // Analytics, telemetry & LLM data processing
  // ==========================================
  async trackEvent(eventType, action = '', metadata = {}, entityType = '', entityId = '') {
    try {
      await fetch(`${this.baseUrl}/api/telemetry/event`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_type: eventType,
          action,
          metadata,
          entity_type: entityType,
          entity_id: entityId
        })
      });
    } catch (err) {}
  },

  async getAnalyticsOverview(force = false) {
    const res = await fetch(`${this.baseUrl}/api/analytics/overview${force ? '?force=true' : ''}`);
    return await res.json();
  },

  async getAnalyticsInsights(force = false) {
    const res = await fetch(`${this.baseUrl}/api/analytics/insights`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force })
    });
    return await res.json();
  },

  async getAnalyticsEvents(limit = 100) {
    const res = await fetch(`${this.baseUrl}/api/analytics/events?limit=${limit}`);
    return await res.json();
  },

  async getWordCloud(force = false) {
    const res = await fetch(`${this.baseUrl}/api/wordcloud${force ? '?force=true' : ''}`);
    return await res.json();
  }
};
