// Current active tab state
let currentTab = 'youtube';
let appConfig = {};

// Switch navigation tabs
function switchTab(tabId) {
    currentTab = tabId;
    const tabs = ['youtube', 'facebook', 'ai_studio', 'tasks', 'logs', 'cloud'];
    
    tabs.forEach(t => {
        const contentEl = document.getElementById(`tab-content-${t}`);
        const btnEl = document.getElementById(`tab-btn-${t}`);
        
        if (contentEl) {
            if (t === tabId) {
                contentEl.classList.remove('hidden');
            } else {
                contentEl.classList.add('hidden');
            }
        }
        
        if (btnEl) {
            btnEl.classList.remove('active-tab-yt', 'active-tab-fb', 'active-tab-default', 'text-white');
            btnEl.classList.add('text-slate-400', 'border-transparent');
            
            if (t === tabId) {
                btnEl.classList.remove('text-slate-400', 'border-transparent');
                if (t === 'youtube') btnEl.classList.add('active-tab-yt');
                else if (t === 'facebook') btnEl.classList.add('active-tab-fb');
                else btnEl.classList.add('active-tab-default');
            }
        }
    });

    if (tabId === 'tasks') loadTasks();
    if (tabId === 'logs') loadLogs();
}

// Toast Notifications
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    const toastMsg = document.getElementById('toast-message');
    const toastIcon = document.getElementById('toast-icon');

    toastMsg.innerText = message;
    toast.className = 'fixed bottom-5 right-5 z-50 px-4 py-3 rounded-lg shadow-xl text-xs font-medium text-white flex items-center space-x-2 transition-all duration-300 transform opacity-100 pointer-events-auto';

    if (type === 'success') {
        toast.classList.add('bg-emerald-600');
        toastIcon.className = 'fa-solid fa-circle-check';
    } else if (type === 'error') {
        toast.classList.add('bg-rose-600');
        toastIcon.className = 'fa-solid fa-circle-xmark';
    } else {
        toast.classList.add('bg-indigo-600');
        toastIcon.className = 'fa-solid fa-circle-info';
    }

    setTimeout(() => {
        toast.classList.remove('opacity-100');
        toast.classList.add('opacity-0', 'pointer-events-none');
    }, 3500);
}

// Load Application Config from Backend
async function loadConfig() {
    try {
        const res = await fetch('/api/config');
        appConfig = await res.json();

        // YouTube Settings
        const yt = appConfig.youtube || {};
        document.getElementById('yt_enable_toggle').checked = yt.enabled ?? true;
        document.getElementById('yt_access_token').value = yt.destination?.access_token || '';
        document.getElementById('yt_refresh_token').value = yt.destination?.refresh_token || '';
        
        const ytRules = yt.bypass_rules || {};
        document.getElementById('yt_filter_remove_logo').checked = ytRules.remove_logo ?? true;
        document.getElementById('yt_filter_hflip').checked = ytRules.hflip ?? false;
        document.getElementById('yt_filter_pitch').checked = ytRules.pitch_shift ?? true;
        document.getElementById('yt_filter_color').checked = ytRules.color_boost ?? true;
        document.getElementById('yt_filter_speed').value = ytRules.speed || 1.03;
        document.getElementById('yt_speed_label').innerText = (ytRules.speed || 1.03) + 'x';
        document.getElementById('yt_filter_crop').value = ytRules.crop_percent || 3;
        document.getElementById('yt_crop_label').innerText = (ytRules.crop_percent || 3) + '%';
        renderSourceList('youtube', yt.sources || []);

        // Facebook Settings
        const fb = appConfig.facebook || {};
        document.getElementById('fb_enable_toggle').checked = fb.enabled ?? true;
        document.getElementById('fb_page_id').value = fb.destination?.page_id || '';
        document.getElementById('fb_access_token').value = fb.destination?.access_token || '';
        document.getElementById('fb_post_as_reel').checked = fb.destination?.post_as_reel ?? false;
        
        const fbRules = fb.bypass_rules || {};
        document.getElementById('fb_filter_remove_logo').checked = fbRules.remove_logo ?? true;
        document.getElementById('fb_filter_hflip').checked = fbRules.hflip ?? false;
        document.getElementById('fb_filter_pitch').checked = fbRules.pitch_shift ?? true;
        document.getElementById('fb_hashtags').value = fb.metadata_rules?.title_suffix || '#reviewphim #xuhuong';
        renderSourceList('facebook', fb.sources || []);

        // AI Settings
        const gen = appConfig.general || {};
        document.getElementById('cfg_gemini_key').value = gen.gemini_api_key || '';
        document.getElementById('cfg_openai_key').value = gen.openai_api_key || '';

    } catch (err) {
        console.error('Error loading config:', err);
    }
}

// Render source list for YouTube or Facebook
function renderSourceList(platform, sources) {
    const listEl = document.getElementById(platform === 'youtube' ? 'yt-source-list' : 'fb-source-list');
    if (!listEl) return;

    if (!sources || sources.length === 0) {
        listEl.innerHTML = `
            <div class="text-center py-8 text-slate-500 text-xs">
                <i class="fa-solid fa-folder-open text-2xl mb-1.5 text-slate-600"></i>
                <p>Chưa có kênh nguồn nào. Hãy bấm "Thêm Kênh" ở trên.</p>
            </div>
        `;
        return;
    }

    listEl.innerHTML = sources.map(s => `
        <div class="flex items-center justify-between p-3 bg-slate-800/60 rounded-xl border border-slate-700/50 hover:border-slate-600 transition">
            <div class="flex items-center space-x-3 overflow-hidden">
                <div class="w-8 h-8 rounded-lg ${platform === 'youtube' ? 'bg-red-950/60 text-red-400 border border-red-500/30' : 'bg-blue-950/60 text-blue-400 border border-blue-500/30'} flex items-center justify-center text-sm flex-shrink-0">
                    <i class="${platform === 'youtube' ? 'fa-brands fa-youtube' : 'fa-brands fa-facebook-f'}"></i>
                </div>
                <div class="truncate">
                    <h5 class="text-xs font-semibold text-white truncate">${s.name || s.id}</h5>
                    <p class="text-[11px] text-slate-400 font-mono truncate">${s.id}</p>
                </div>
            </div>
            <div class="flex items-center space-x-2 flex-shrink-0">
                <input type="checkbox" ${s.enabled ? 'checked' : ''} onchange="toggleSource('${platform}', '${s.id}', this.checked)" class="w-4 h-4 rounded accent-indigo-600 cursor-pointer">
                <button onclick="deleteSource('${platform}', '${s.id}')" class="text-slate-500 hover:text-rose-400 text-xs p-1.5 transition">
                    <i class="fa-solid fa-trash-can"></i>
                </button>
            </div>
        </div>
    `).join('');
}

// Modal management
function openAddSourceModal(platform) {
    document.getElementById('modal-platform').value = platform;
    document.getElementById('modal-title').innerText = platform === 'youtube' ? 'Thêm Kênh YouTube Nguồn' : 'Thêm Nguồn Facebook Video';
    document.getElementById('modal-name').value = '';
    document.getElementById('modal-url').value = '';
    document.getElementById('add-source-modal').classList.remove('hidden');
}

function closeAddSourceModal() {
    document.getElementById('add-source-modal').classList.add('hidden');
}

async function submitAddSource() {
    const platform = document.getElementById('modal-platform').value;
    const name = document.getElementById('modal-name').value.trim();
    const url = document.getElementById('modal-url').value.trim();

    if (!url) {
        showToast('Vui lòng nhập Channel ID hoặc link nguồn', 'error');
        return;
    }

    try {
        const res = await fetch('/api/sources/add', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ platform, name, url_or_id: url })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message, 'success');
            closeAddSourceModal();
            loadConfig();
        } else {
            showToast(data.detail || 'Có lỗi xảy ra', 'error');
        }
    } catch (e) {
        showToast('Lỗi kết nối máy chủ', 'error');
    }
}

async function toggleSource(platform, sourceId, enabled) {
    await fetch('/api/sources/toggle', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ platform, source_id: sourceId, enabled })
    });
}

async function deleteSource(platform, sourceId) {
    if (!confirm('Bạn có chắc muốn xóa kênh nguồn này khỏi danh sách theo dõi?')) return;
    try {
        const res = await fetch('/api/sources/delete', {
            method: 'DELETE',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ platform, source_id: sourceId })
        });
        if (res.ok) {
            showToast('Đã xóa kênh nguồn thành công', 'success');
            loadConfig();
        }
    } catch (e) {
        showToast('Lỗi khi xóa nguồn', 'error');
    }
}

// Save Platform Config (YouTube / Facebook)
async function savePlatformConfig(platform) {
    if (!appConfig[platform]) appConfig[platform] = {};
    
    if (platform === 'youtube') {
        appConfig.youtube.destination = {
            ...appConfig.youtube.destination,
            access_token: document.getElementById('yt_access_token').value.trim(),
            refresh_token: document.getElementById('yt_refresh_token').value.trim()
        };
        appConfig.youtube.bypass_rules = {
            ...appConfig.youtube.bypass_rules,
            remove_logo: document.getElementById('yt_filter_remove_logo').checked,
            hflip: document.getElementById('yt_filter_hflip').checked,
            pitch_shift: document.getElementById('yt_filter_pitch').checked,
            color_boost: document.getElementById('yt_filter_color').checked,
            speed: parseFloat(document.getElementById('yt_filter_speed').value),
            crop_percent: parseInt(document.getElementById('yt_filter_crop').value),
            target_resolution: "720p"
        };
    } else if (platform === 'facebook') {
        appConfig.facebook.destination = {
            page_id: document.getElementById('fb_page_id').value.trim(),
            access_token: document.getElementById('fb_access_token').value.trim(),
            post_as_reel: document.getElementById('fb_post_as_reel').checked
        };
        appConfig.facebook.bypass_rules = {
            ...appConfig.facebook.bypass_rules,
            remove_logo: document.getElementById('fb_filter_remove_logo').checked,
            hflip: document.getElementById('fb_filter_hflip').checked,
            pitch_shift: document.getElementById('fb_filter_pitch').checked,
            color_boost: true,
            speed: 1.04,
            crop_percent: 4,
            target_resolution: "720p"
        };
        if (!appConfig.facebook.metadata_rules) appConfig.facebook.metadata_rules = {};
        appConfig.facebook.metadata_rules.title_suffix = ' ' + document.getElementById('fb_hashtags').value.trim();
    }

    try {
        const res = await fetch('/api/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(appConfig)
        });
        if (res.ok) {
            showToast(`Đã lưu cấu hình ${platform.toUpperCase()} thành công!`, 'success');
        }
    } catch (e) {
        showToast('Không thể lưu cấu hình', 'error');
    }
}

// Save General & AI Config
async function saveGeneralConfig() {
    if (!appConfig.general) appConfig.general = {};
    appConfig.general.gemini_api_key = document.getElementById('cfg_gemini_key').value.trim();
    appConfig.general.openai_api_key = document.getElementById('cfg_openai_key').value.trim();

    try {
        const res = await fetch('/api/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(appConfig)
        });
        if (res.ok) {
            showToast('Đã lưu cấu hình AI thành công!', 'success');
        }
    } catch (e) {
        showToast('Không thể lưu cấu hình', 'error');
    }
}

// Trigger Manual Reup 1 Video
async function triggerManualReup(platform) {
    const inputEl = document.getElementById(platform === 'youtube' ? 'yt_manual_url' : 'fb_manual_url');
    const url = inputEl.value.trim();
    if (!url) {
        showToast('Vui lòng dán link video cần reup', 'error');
        return;
    }

    try {
        const res = await fetch('/api/tasks/trigger', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ platform, url })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message, 'success');
            inputEl.value = '';
            switchTab('tasks');
            loadTasks();
        } else {
            showToast(data.detail || 'Không thể tạo task', 'error');
        }
    } catch (e) {
        showToast('Lỗi khi gửi yêu cầu', 'error');
    }
}

// Scan All Sources Now
async function scanNow() {
    showToast('Đang quét tất cả các kênh YouTube và Facebook...', 'info');
    try {
        const res = await fetch('/api/scan', { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            const found = data.found || {};
            showToast(`Quét xong! Tìm thấy ${found.youtube || 0} video YouTube mới, ${found.facebook || 0} Facebook mới`, 'success');
            loadTasks();
        }
    } catch (e) {
        showToast('Lỗi khi quét nguồn', 'error');
    }
}

// Load Task Queue and History
async function loadTasks() {
    try {
        const res = await fetch('/api/tasks');
        const data = await res.json();
        const tasks = data.tasks || [];
        
        document.getElementById('queue-badge').innerText = data.queue_length || 0;
        const tbody = document.getElementById('task-table-body');
        
        if (tasks.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" class="py-8 text-center text-slate-500">
                        Chưa có video nào trong hàng đợi. Hãy dán link test ở Tab YouTube/Facebook hoặc bấm "Quét Ngay".
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = tasks.map(t => {
            const statusClass = `status-${t.status}`;
            const platIcon = t.platform === 'youtube' ? '<i class="fa-brands fa-youtube text-red-500 mr-1"></i>' : '<i class="fa-brands fa-facebook text-blue-500 mr-1"></i>';
            const thumbDisplay = t.thumbnail_url 
                ? `<a href="${t.thumbnail_url}" target="_blank"><img src="${t.thumbnail_url}" class="w-12 h-7 object-cover rounded border border-slate-700 hover:scale-110 transition"></a>` 
                : '<span class="text-slate-600">-</span>';

            return `
                <tr class="hover:bg-slate-800/40 transition">
                    <td class="py-3 px-4 font-mono text-[11px] text-slate-400 font-bold">${t.id}</td>
                    <td class="py-3 px-4 font-semibold uppercase text-[11px]">${platIcon} ${t.platform}</td>
                    <td class="py-3 px-4 max-w-xs">
                        <div class="truncate text-slate-200 font-medium" title="${t.new_title || t.original_title}">
                            ${t.new_title || t.original_title}
                        </div>
                        <div class="text-[10px] text-slate-500 truncate">${t.stage_info || ''}</div>
                    </td>
                    <td class="py-3 px-4">
                        <span class="status-pill ${statusClass}">${t.status}</span>
                    </td>
                    <td class="py-3 px-4 w-28">
                        <div class="w-full bg-slate-800 rounded-full h-1.5">
                            <div class="bg-indigo-500 h-1.5 rounded-full transition-all duration-500" style="width: ${t.progress || 0}%"></div>
                        </div>
                        <span class="text-[10px] text-slate-400 mt-0.5 block">${t.progress || 0}%</span>
                    </td>
                    <td class="py-3 px-4">${thumbDisplay}</td>
                    <td class="py-3 px-4 font-mono text-[11px] text-slate-400">${t.created_at}</td>
                </tr>
            `;
        }).join('');
    } catch (e) {
        console.error('Error loading tasks:', e);
    }
}

// Load Logs for Terminal View
async function loadLogs() {
    try {
        const res = await fetch('/api/logs');
        const data = await res.json();
        const logs = data.logs || [];
        const terminal = document.getElementById('log-terminal');

        terminal.innerHTML = logs.map(l => {
            let color = 'text-slate-300';
            if (l.level === 'SUCCESS') color = 'text-emerald-400 font-semibold';
            else if (l.level === 'ERROR') color = 'text-rose-400 font-semibold';
            else if (l.level === 'WARNING') color = 'text-amber-400';
            else if (l.category === 'FFMPEG') color = 'text-purple-400';
            else if (l.category === 'AI') color = 'text-sky-300';

            return `
                <div class="flex items-start space-x-2 leading-relaxed">
                    <span class="text-slate-500 select-none flex-shrink-0">[${l.timestamp}]</span>
                    <span class="px-1.5 py-0.2 rounded text-[10px] bg-slate-800 border border-slate-700 flex-shrink-0">${l.category}</span>
                    <span class="${color} break-all">${l.message}</span>
                </div>
            `;
        }).join('');

        if (document.getElementById('auto_scroll_logs').checked) {
            terminal.scrollTop = terminal.scrollHeight;
        }
    } catch (e) {
        console.error('Error loading logs:', e);
    }
}

// Render Thumbnail Preview on demand
async function renderThumbnailPreview() {
    const title = document.getElementById('preview_thumb_title').value.trim();
    if (!title) return;

    try {
        const res = await fetch('/api/preview/thumbnail', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ title, style: 'modern_yellow' })
        });
        const data = await res.json();
        if (res.ok && data.url) {
            const img = document.getElementById('thumb-preview-img');
            const placeholder = document.getElementById('thumb-preview-placeholder');
            img.src = data.url + '?t=' + new Date().getTime();
            img.classList.remove('hidden');
            placeholder.classList.add('hidden');
            showToast('Đã tạo ảnh bìa xem trước thành công!', 'success');
        }
    } catch (e) {
        showToast('Lỗi khi tạo ảnh bìa', 'error');
    }
}

// Polling Loop: refresh active state every 3.5 seconds
setInterval(() => {
    if (currentTab === 'tasks') loadTasks();
    if (currentTab === 'logs') loadLogs();
}, 3500);

// Initial bootstrap
window.addEventListener('DOMContentLoaded', () => {
    loadConfig();
    loadTasks();
    loadLogs();
});
