let isListening = false;

// Version for confirmation
console.log("JARVIS UI v2.0 — PREMIUM HUD REDESIGN");

/* ══════════════════════════════════════════════════════
   PARTICLE SYSTEM
   ══════════════════════════════════════════════════════ */
(function initParticles() {
    const canvas = document.getElementById('particles');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let particles = [];
    const PARTICLE_COUNT = 80;

    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }
    window.addEventListener('resize', resize);
    resize();

    class Particle {
        constructor() { this.reset(); }
        reset() {
            this.x = Math.random() * canvas.width;
            this.y = Math.random() * canvas.height;
            this.size = Math.random() * 1.8 + 0.3;
            this.speedX = (Math.random() - 0.5) * 0.15;
            this.speedY = (Math.random() - 0.5) * 0.15;
            this.opacity = Math.random() * 0.5 + 0.1;
            this.pulse = Math.random() * Math.PI * 2;
            this.pulseSpeed = Math.random() * 0.015 + 0.005;
            // Some particles are cyan, most are white
            this.isCyan = Math.random() < 0.2;
        }
        update() {
            this.x += this.speedX;
            this.y += this.speedY;
            this.pulse += this.pulseSpeed;
            if (this.x < 0 || this.x > canvas.width) this.speedX *= -1;
            if (this.y < 0 || this.y > canvas.height) this.speedY *= -1;
        }
        draw() {
            const a = this.opacity * (0.5 + 0.5 * Math.sin(this.pulse));
            if (this.isCyan) {
                ctx.fillStyle = `rgba(0, 229, 255, ${a})`;
            } else {
                ctx.fillStyle = `rgba(255, 255, 255, ${a * 0.7})`;
            }
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    for (let i = 0; i < PARTICLE_COUNT; i++) particles.push(new Particle());

    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        particles.forEach(p => { p.update(); p.draw(); });

        // Draw connecting lines between close particles
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 100) {
                    ctx.beginPath();
                    ctx.strokeStyle = `rgba(0, 229, 255, ${0.03 * (1 - dist / 100)})`;
                    ctx.lineWidth = 0.5;
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.stroke();
                }
            }
        }

        requestAnimationFrame(animate);
    }
    animate();
})();

/* ══════════════════════════════════════════════════════
   CORE FUNCTIONS
   ══════════════════════════════════════════════════════ */
async function toggleMic() {
    const btn = document.getElementById('toggle-mic');
    const status = document.getElementById('mic-status');

    if (!isListening) {
        await eel.start_listening()();
        isListening = true;
        btn.innerHTML = `<span class="icon"><svg viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg></span> ОСТАНОВИТЬ`;
        btn.classList.add('active');
        status.innerText = "MIC: LISTENING";
        addLog("Microphone activated.");
    } else {
        await eel.stop_listening()();
        isListening = false;
        btn.innerHTML = `<span class="icon"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/><path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg></span> РЕЖИМ ОЖИДАНИЯ`;
        btn.classList.remove('active');
        status.innerText = "MIC: OFF";
        addLog("Microphone deactivated.");
    }
}

function addLog(text) {
    const container = document.getElementById('log-list');
    if (!container) {
        console.log("[LOG]", text);
        return;
    }

    // Efficiency: If the new log is a percentage, replace the previous percentage log
    if (text.includes('%') && container.lastElementChild && container.lastElementChild.innerText.includes('%')) {
        const timeStr = new Date().toLocaleTimeString('ru-RU', { hour12: false });
        container.lastElementChild.innerHTML = `<span class="log-time">[${timeStr}]</span> ${text}`;
        return;
    }

    const entry = document.createElement('div');
    entry.className = 'log-entry';
    const timeStr = new Date().toLocaleTimeString('ru-RU', { hour12: false });

    entry.innerHTML = `<span class="log-time">[${timeStr}]</span> ${text}`;
    container.appendChild(entry);
    container.scrollTop = container.scrollHeight;

    // Auto-remove old logs
    if (container.children.length > 50) container.removeChild(container.firstChild);
}

function showResponse(text) {
    try {
        const overlay = document.getElementById('response-overlay');
        const msg = document.getElementById('response-text');
        if (msg) msg.innerText = text;
        if (overlay) overlay.classList.add('visible');
        setTimeout(() => { if (overlay) overlay.classList.remove('visible'); }, 10000);

        // Persistent chat history
        addChatMessage("JARVIS", text);
    } catch (e) { console.error(e); }
}

eel.expose(add_chat_message);
function add_chat_message(sender, text) {
    try { addChatMessage(sender, text); } catch (e) { console.error(e); }
}

function addChatMessage(sender, text) {
    const history = document.getElementById('chat-history');
    if (history) {
        const entry = document.createElement('div');
        entry.className = `chat-bubble ${sender.toLowerCase() === 'jarvis' ? 'ai' : 'user'}`;
        const name = sender === 'YOU' ? 'ВЫ' : 'JARVIS';
        entry.innerHTML = `<span class="chat-name">${name}</span>: ${text}`;
        history.appendChild(entry);
        history.scrollTop = history.scrollHeight;
    }
}

eel.expose(add_log);
function add_log(text) {
    try { addLog(text); } catch (e) { console.error(e); }
}

eel.expose(set_speaking);
function set_speaking(val) {
    try {
        const core = document.querySelector('.hud-core');
        const ring5 = document.querySelector('.ring-5');
        const glow = document.querySelector('.core-glow');
        if (val) {
            if (core) {
                core.style.boxShadow = "0 0 40px #fff, 0 0 80px var(--hud-primary), 0 0 120px var(--hud-primary)";
                core.style.transform = "scale(1.35)";
            }
            if (ring5) {
                ring5.style.borderColor = "#fff";
                ring5.style.boxShadow = "0 0 30px rgba(0, 229, 255, 0.4)";
            }
            if (glow) glow.style.transform = "scale(1.6)";
        } else {
            if (core) {
                core.style.boxShadow = "";
                core.style.transform = "scale(1)";
            }
            if (ring5) {
                ring5.style.borderColor = "";
                ring5.style.boxShadow = "";
            }
            if (glow) glow.style.transform = "";
        }
    } catch (e) { console.error(e); }
}

eel.expose(show_response);
function show_response(text) {
    try { showResponse(text); } catch (e) { console.error(e); }
}

function switchTab(tabId, el) {
    try {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        el.classList.add('active');

        document.querySelectorAll('.tab-content').forEach(c => c.classList.add('hidden'));
        const target = document.getElementById(`tab-${tabId}`);
        if (target) target.classList.remove('hidden');

        // NO LOGGING FOR TAB SWITCH
    } catch (e) { console.error(e); }
}

async function updateSettings() {
    try {
        const settings = {
            use_qwen_cli: document.getElementById('check-qwen-cli').checked,
            use_online_ai: document.getElementById('check-online-ai').checked,
            yandex_api_key: document.getElementById('yandex-api-key') ? document.getElementById('yandex-api-key').value.trim() : '',
            yandex_folder_id: document.getElementById('yandex-folder-id') ? document.getElementById('yandex-folder-id').value.trim() : '',
            use_qwen_llm: document.getElementById('check-qwen-llm').checked,
            local_llm_path: document.getElementById('local-llm-path') ? document.getElementById('local-llm-path').value.trim() : '',
            local_llm_gpu_layers: document.getElementById('local-llm-gpu-layers') ? parseInt(document.getElementById('local-llm-gpu-layers').value || '-1', 10) : -1,
            use_qwen_tts: document.getElementById('check-qwen').checked,
            use_cosyvoice_tts: document.getElementById('check-cosyvoice').checked,
            cosyvoice_mode: document.getElementById('cosyvoice-mode') ? document.getElementById('cosyvoice-mode').value : 'local',
            cosyvoice_api_url: document.getElementById('cosyvoice-api-url') ? document.getElementById('cosyvoice-api-url').value.trim() : 'http://127.0.0.1:9880',
            cosyvoice_model: document.getElementById('cosyvoice-model') ? document.getElementById('cosyvoice-model').value.trim() : 'FunAudioLLM/CosyVoice-300M-Instruct',
            cosyvoice_reference_path: document.getElementById('cosyvoice-reference-path') ? document.getElementById('cosyvoice-reference-path').value.trim() : '',
            use_movie_sounds: document.getElementById('check-movie').checked,
            use_vosk: document.getElementById('check-vosk') ? document.getElementById('check-vosk').checked : false,
            confirm_dangerous: document.getElementById('check-confirm') ? document.getElementById('check-confirm').checked : true,
            memory_max_turns: document.getElementById('memory-turns') ? parseInt(document.getElementById('memory-turns').value || '6', 10) : 6,
            power_saving_enabled: document.getElementById('check-power-saving') ? document.getElementById('check-power-saving').checked : false,
            performance_mode: document.getElementById('performance-mode') ? document.getElementById('performance-mode').value : 'balanced',
            smart_home_api_url: document.getElementById('smart-home-api-url') ? document.getElementById('smart-home-api-url').value : '',
            smart_home_access_token: document.getElementById('smart-home-access-token') ? document.getElementById('smart-home-access-token').value : ''
        };
        await eel.update_settings(settings)();
        addLog("Settings updated.");
    } catch (e) { console.error(e); }
}

eel.expose(set_energy);
function set_energy(val) {
    try {
        const core = document.querySelector('.hud-core');
        const glow = document.querySelector('.core-glow');
        const ring5 = document.querySelector('.ring-5');

        // Intensified scaling
        const scaleCore = 1.0 + (val * 0.8); // 80% growth
        const scaleGlow = 1.0 + (val * 1.5); // 150% growth

        if (core) core.style.transform = `scale(${scaleCore})`;
        if (glow) {
            glow.style.transform = `scale(${scaleGlow})`;
            glow.style.opacity = 0.4 + (val * 0.6);
        }
        if (ring5) {
            ring5.style.borderWidth = (2 + val * 15) + "px";
            ring5.style.boxShadow = `0 0 ${20 + val * 60}px rgba(0, 229, 255, ${0.15 + val * 0.3})`;
        }
    } catch (e) { console.error(e); }
}

function openFileSelector() {
    document.getElementById('file-selector').click();
}

function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
        document.getElementById('new-cmd-action').value = file.path;
    }
}

async function addNewCommand() {
    try {
        const key = document.getElementById('new-cmd-key').value;
        const action = document.getElementById('new-cmd-action').value;
        if (!key || !action) return;

        const success = await eel.add_custom_command(key, action)();
        if (success) {
            const container = document.getElementById('cmd-container');
            const item = document.createElement('div');
            item.className = 'cmd-item';
            item.innerHTML = `<span>${key}</span> — ${action}`;
            if (container) container.appendChild(item);

            document.getElementById('new-cmd-key').value = '';
            document.getElementById('new-cmd-action').value = '';
            document.getElementById('file-selector').value = '';
            addLog(`Command added: ${key}`);
        }
    } catch (e) { console.error(e); }
}

async function editCommand() {
    try {
        const key = document.getElementById('new-cmd-key').value;
        const action = document.getElementById('new-cmd-action').value;
        if (!key || !action) return;

        const success = await eel.add_custom_command(key, action)();
        if (success) {
            const container = document.getElementById('cmd-container');
            let updated = false;
            if (container) {
                const items = container.getElementsByClassName('cmd-item');
                for (let item of items) {
                    const span = item.querySelector('span');
                    if (span && span.textContent.toLowerCase() === key.toLowerCase()) {
                        item.innerHTML = `<span>${key}</span> — ${action}`;
                        updated = true;
                        break;
                    }
                }
                if (!updated) {
                    const item = document.createElement('div');
                    item.className = 'cmd-item';
                    item.innerHTML = `<span>${key}</span> — ${action}`;
                    container.appendChild(item);
                }
            }
            addLog(`Command updated: ${key}`);
        }
    } catch (e) { console.error(e); }
}

async function toggleAutostart() {
    try {
        const enabled = document.getElementById('check-autostart').checked;
        const success = await eel.set_autostart(enabled)();
        if (success) addLog(`Autostart: ${enabled ? 'ON' : 'OFF'}`);
    } catch (e) { console.error(e); }
}

window.addEventListener('load', async () => {
    try {
        const status = await eel.get_status()();
        if (status.is_listening) {
            isListening = true;
            const btn = document.getElementById('toggle-mic');
            if (btn) {
                btn.classList.add('active');
                btn.innerHTML = `<span class="icon"><svg viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg></span> ОСТАНОВИТЬ`;
            }
            const mstat = document.getElementById('mic-status');
            if (mstat) mstat.innerText = "MIC: LISTENING";
        }



        const settings = await eel.get_settings()();
        if (document.getElementById('check-qwen-cli')) document.getElementById('check-qwen-cli').checked = settings.use_qwen_cli;
        if (document.getElementById('check-online-ai')) document.getElementById('check-online-ai').checked = settings.use_online_ai !== false;
        if (document.getElementById('yandex-api-key')) document.getElementById('yandex-api-key').value = settings.yandex_api_key || '';
        if (document.getElementById('yandex-folder-id')) document.getElementById('yandex-folder-id').value = settings.yandex_folder_id || '';
        if (document.getElementById('check-qwen-llm')) document.getElementById('check-qwen-llm').checked = settings.use_qwen_llm;
        if (document.getElementById('local-llm-path')) document.getElementById('local-llm-path').value = settings.local_llm_path || '';
        if (document.getElementById('local-llm-gpu-layers')) document.getElementById('local-llm-gpu-layers').value = settings.local_llm_gpu_layers !== undefined ? settings.local_llm_gpu_layers : -1;
        if (document.getElementById('check-qwen')) document.getElementById('check-qwen').checked = settings.use_qwen_tts;
        if (document.getElementById('check-cosyvoice')) document.getElementById('check-cosyvoice').checked = settings.use_cosyvoice_tts || false;
        if (document.getElementById('cosyvoice-mode')) document.getElementById('cosyvoice-mode').value = settings.cosyvoice_mode || 'local';
        if (document.getElementById('cosyvoice-api-url')) document.getElementById('cosyvoice-api-url').value = settings.cosyvoice_api_url || 'http://127.0.0.1:9880';
        if (document.getElementById('cosyvoice-model')) document.getElementById('cosyvoice-model').value = settings.cosyvoice_model || 'FunAudioLLM/CosyVoice-300M-Instruct';
        if (document.getElementById('cosyvoice-reference-path')) document.getElementById('cosyvoice-reference-path').value = settings.cosyvoice_reference_path || '';
        if (document.getElementById('check-movie')) document.getElementById('check-movie').checked = settings.use_movie_sounds;
        if (document.getElementById('check-autostart')) document.getElementById('check-autostart').checked = settings.autostart || false;
        if (document.getElementById('check-vosk')) document.getElementById('check-vosk').checked = settings.use_vosk || false;
        if (document.getElementById('check-confirm')) document.getElementById('check-confirm').checked = (settings.confirm_dangerous !== false);
        if (document.getElementById('memory-turns')) document.getElementById('memory-turns').value = settings.memory_max_turns || 6;
        if (document.getElementById('check-power-saving')) document.getElementById('check-power-saving').checked = settings.power_saving_enabled || false;
        if (document.getElementById('performance-mode')) document.getElementById('performance-mode').value = settings.performance_mode || 'balanced';
        if (document.getElementById('smart-home-api-url')) document.getElementById('smart-home-api-url').value = settings.smart_home_api_url || '';
        if (document.getElementById('smart-home-access-token')) document.getElementById('smart-home-access-token').value = settings.smart_home_access_token || '';

        // Load saved custom commands
        const cmds = await eel.get_commands()();
        const container = document.getElementById('cmd-container');
        if (container && cmds) {
            Array.from(container.querySelectorAll('.cmd-item'))
                .filter(el => !el.dataset || !el.dataset.builtin)
                .forEach(el => el.remove());

            Object.entries(cmds).forEach(([key, cfg]) => {
                const action = cfg && cfg.action ? cfg.action : '';
                const item = document.createElement('div');
                item.className = 'cmd-item';
                item.innerHTML = `<span>${key}</span> — ${action}`;
                container.appendChild(item);
            });
        }

        // Update AI status immediately
        const aiEl = document.getElementById('ai-status');
        if (aiEl && status.ai) aiEl.innerText = status.ai;

        addLog("Interface Ready.");
    } catch (e) { console.error(e); }

    // Periodic status updater — every 5 seconds
    setInterval(async () => {
        try {
            const st = await eel.get_status()();
            const aiEl = document.getElementById('ai-status');
            if (aiEl && st.ai) aiEl.innerText = st.ai;
        } catch (e) { /* silent */ }
    }, 5000);
});

