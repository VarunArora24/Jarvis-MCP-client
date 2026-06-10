// --- Jarvis AI Desktop Assistant — Redesigned Controller & Arc Reactor Visualizer ---

// UI Core Elements Selection
const chatContainer = document.getElementById("chat-container");
const chatMessages = document.getElementById("chat-messages");
const commandForm = document.getElementById("command-form");
const commandInput = document.getElementById("command-input");
const sendBtn = document.getElementById("send-btn");
const welcomeScreen = document.getElementById("welcome-screen");
const typingIndicator = document.getElementById("typing-indicator");

// Sidebar Elements
const leftSidebar = document.getElementById("left-sidebar");
const rightSidebar = document.getElementById("right-sidebar");
const togglePanelsBtn = document.getElementById("toggle-panels-btn");
const refreshMemoryBtn = document.getElementById("refresh-memory-btn");
const clearChatBtn = document.getElementById("clear-chat-btn");
const toggleDebugBtn = document.getElementById("toggle-debug-btn");

// Control Toggles
const muteBtn = document.getElementById("mute-btn");
const muteLabel = document.getElementById("mute-label");
const voiceTalkBtn = document.getElementById("voice-talk-btn");
const voiceTalkLabel = document.getElementById("voice-talk-label");

// Status Badges
const headerStatusText = document.getElementById("header-status-text");
const statusBadge = document.getElementById("status-badge");
const agentStateBadge = document.getElementById("agent-state-badge");
const statusTitleText = document.getElementById("status-title-text");
const statusDescText = document.getElementById("status-desc-text");

// Diagnostics Elements
const diagOs = document.getElementById("diag-os");
const diagCpu = document.getElementById("diag-cpu");
const diagRam = document.getElementById("diag-ram");
const memoryFactsList = document.getElementById("memory-facts-list");

// Voice Mode Overlay Elements
const voiceOverlay = document.getElementById("voice-overlay");
const closeVoiceBtn = document.getElementById("close-voice-btn");
const voicePreviewText = document.getElementById("voice-preview-text");
const voiceStatusSub = document.getElementById("voice-status-sub");
const promptVoiceBtn = document.getElementById("prompt-voice-btn");
const promptVoicePulse = document.getElementById("prompt-voice-pulse");

// Tool Execution Elements
const liveToolContainer = document.getElementById("live-tool-container");
const confirmModal = document.getElementById("confirm-modal");
const confirmDescription = document.getElementById("confirm-description");
const allowBtn = document.getElementById("allow-btn");
const denyBtn = document.getElementById("deny-btn");

// Canvas voice reactors
const sidebarCanvas = document.getElementById("sidebar-logo-canvas");
const mainCanvas = document.getElementById("main-voice-canvas");
const overlayCanvas = document.getElementById("overlay-voice-canvas");

// Immersive Status Elements
const immersiveStatusLabel = document.getElementById("immersive-status-label");
const immersiveStatusSub = document.getElementById("immersive-status-sub");

// App State Variables
let isMuted = localStorage.getItem("jarvis_muted") === "true";
let isVoiceTalkActive = true; // Voice Loop active by default
let recognition = null;
let isRecognitionRunning = false;
let currentState = "SLEEP"; // States: SLEEP, LISTENING, THINKING, SPEAKING
let speakQueue = [];
let toolCallSeq = 0;
let sidebarsVisible = false;

// Web Audio API Elements
let audioContext = null;
let audioAnalyser = null;
let micSource = null;
let animFrameId = null;

// Spring physics solver for visual reactor scaling
let reactorSpring = {
    x: 1.0,      // current scale
    target: 0.9, // target scale
    v: 0.0,      // velocity
    k: 0.08,     // spring stiffness
    d: 0.74      // spring damping
};

// --- Debug Diagnostics Overlay ---
const DEBUG_PANEL_ID = "jarvis-debug-panel";
function ensureDebugPanel() {
    let panel = document.getElementById(DEBUG_PANEL_ID);
    if (!panel) {
        panel = document.createElement("div");
        panel.id = DEBUG_PANEL_ID;
        panel.style.cssText = [
            "position:fixed", "bottom:20px", "right:20px", "z-index:9999",
            "background:rgba(15,23,42,0.92)", "border:1px solid rgba(255,255,255,0.08)",
            "color:#00D4FF", "font-family:monospace", "font-size:10px",
            "padding:10px 14px", "border-radius:16px", "max-width:380px",
            "max-height:220px", "overflow-y:auto", "pointer-events:none",
            "backdrop-filter:blur(12px)", "box-shadow:0 10px 30px rgba(0,0,0,0.5)",
            localStorage.getItem("jarvis_debug") === "true" ? "display:block" : "display:none"
        ].join(";");

        // Mic meter display inside diagnostics box
        const meterRow = document.createElement("div");
        meterRow.id = "mic-meter-row";
        meterRow.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:6px;border-bottom:1px solid rgba(255,255,255,0.05);padding-bottom:6px;";
        meterRow.innerHTML = `
            <span style="color:#FF4FD8;white-space:nowrap">🎙️ MIC LEVEL:</span>
            <div id="mic-level-outer" style="flex:1;height:6px;background:rgba(255,255,255,0.05);border-radius:4px;overflow:hidden">
                <div id="mic-level-bar" style="height:100%;width:0%;background:linear-gradient(90deg, #6E5BFF, #00D4FF);border-radius:4px;transition:width 0.08s linear"></div>
            </div>
            <span id="mic-level-val" style="color:#A7B0C0;min-width:30px;text-align:right">0%</span>
        `;
        panel.appendChild(meterRow);
        document.body.appendChild(panel);
    }
    return panel;
}

function updateMicLevelBar(avgLevel) {
    const bar = document.getElementById("mic-level-bar");
    const val = document.getElementById("mic-level-val");
    if (bar && val) {
        const pct = Math.min(100, Math.round((avgLevel / 120) * 100));
        bar.style.width = pct + "%";
        val.textContent = pct + "%";
    }
}

function dbgLog(msg, level = "info") {
    const colors = { info: "#A7B0C0", warn: "#FBBF24", error: "#F87171", ok: "#34D399" };
    const ts = new Date().toLocaleTimeString("en-IN", { hour12: false });
    const line = `[${ts}] ${msg}`;
    
    if (level === "error") console.error(line);
    else if (level === "warn") console.warn(line);
    else console.log(line);
    
    const panel = ensureDebugPanel();
    const el = document.createElement("div");
    el.className = "py-0.5 leading-relaxed font-mono";
    el.style.color = colors[level] || colors.info;
    el.textContent = line;
    panel.appendChild(el);
    
    while (panel.children.length > 18) panel.removeChild(panel.children[1]); // Keep last 18 log rows
    panel.scrollTop = panel.scrollHeight;
}

// Synchronize Toggles on startup
updateMuteUI();
updateVoiceTalkUI();

// --- 1. UI State Management ---
function setUIState(state) {
    currentState = state;
    dbgLog(`State Transition -> ${state}`, "info");

    // Header Status Text
    if (headerStatusText) {
        headerStatusText.innerText = `JARVIS: ${state}`;
    }

    // Top status badge styles
    if (statusBadge) {
        statusBadge.className = `px-3 py-1 rounded-full border text-[10px] font-semibold tracking-wider font-mono flex items-center gap-1.5 uppercase transition-all duration-300`;
        const dot = statusBadge.querySelector('span') || document.createElement('span');
        dot.className = "w-1.5 h-1.5 rounded-full";
        if (state === "SLEEP") {
            statusBadge.classList.add('bg-white/5', 'border-white/10', 'text-textMuted');
            dot.className = "w-1.5 h-1.5 rounded-full bg-white/40";
        } else if (state === "LISTENING") {
            statusBadge.classList.add('bg-accentStart/10', 'border-accentStart/25', 'text-accentEnd');
            dot.className = "w-1.5 h-1.5 rounded-full bg-accentEnd animate-pulse";
        } else if (state === "THINKING") {
            statusBadge.classList.add('bg-accentEnd/10', 'border-accentEnd/20', 'text-accentStart');
            dot.className = "w-1.5 h-1.5 rounded-full bg-accentStart animate-ping";
        } else if (state === "SPEAKING") {
            statusBadge.classList.add('bg-accentSecondary/10', 'border-accentSecondary/20', 'text-accentSecondary');
            dot.className = "w-1.5 h-1.5 rounded-full bg-accentSecondary animate-pulse";
        }
        if (!statusBadge.contains(dot)) statusBadge.prepend(dot);
        const label = statusBadge.querySelector('span:last-child');
        if (label) label.innerText = state;
    }

    // Right panel state badge
    if (agentStateBadge) {
        agentStateBadge.innerText = state;
        agentStateBadge.className = "px-2.5 py-0.5 rounded-full text-[9px] font-mono font-bold tracking-widest border uppercase transition-all duration-300";
        if (state === "SLEEP") {
            agentStateBadge.classList.add('bg-white/5', 'text-white/60', 'border-white/10');
        } else if (state === "LISTENING") {
            agentStateBadge.classList.add('bg-accentEnd/10', 'text-accentEnd', 'border-accentEnd/20');
        } else if (state === "THINKING") {
            agentStateBadge.classList.add('bg-accentStart/10', 'text-accentStart', 'border-accentStart/25');
        } else if (state === "SPEAKING") {
            agentStateBadge.classList.add('bg-accentSecondary/10', 'text-accentSecondary', 'border-accentSecondary/20');
        }
    }

    // Dynamic right card description
    if (statusTitleText && statusDescText) {
        if (state === "SLEEP") {
            statusTitleText.innerText = "System Idle";
            statusDescText.innerText = "Jarvis is in standby mode. Type a message or click the voice buttons to communicate.";
        } else if (state === "LISTENING") {
            statusTitleText.innerText = "Active Capture";
            statusDescText.innerText = "Microphone transcription is running. Say your command clearly for hands-free processing.";
        } else if (state === "THINKING") {
            statusTitleText.innerText = "Reasoning Engine";
            statusDescText.innerText = "Analyzing query intent, looking up persistent memory, and executing whitelisted workspace tools.";
        } else if (state === "SPEAKING") {
            statusTitleText.innerText = "Speech Synthesis";
            statusDescText.innerText = "Streaming synthesized voice output corresponding to the completed response.";
        }
    }

    // Spring physics target scale adjustments for reactor orb
    if (state === "SLEEP") {
        reactorSpring.target = 0.9;
    } else if (state === "LISTENING") {
        reactorSpring.target = 1.15; // Orb expands slightly
    } else if (state === "THINKING") {
        reactorSpring.target = 1.05;
    } else if (state === "SPEAKING") {
        reactorSpring.target = 1.1;
    }

    // Update immersive status text
    if (immersiveStatusLabel && immersiveStatusSub) {
        if (state === "SLEEP") {
            immersiveStatusLabel.innerText = "Sleeping";
            immersiveStatusSub.innerText = "TAP ORB TO COMMUNICATE";
        } else if (state === "LISTENING") {
            immersiveStatusLabel.innerText = "Listening...";
            immersiveStatusSub.innerText = "Microphone Active";
        } else if (state === "THINKING") {
            immersiveStatusLabel.innerText = "Thinking...";
            immersiveStatusSub.innerText = "Processing request";
        } else if (state === "SPEAKING") {
            immersiveStatusLabel.innerText = "Speaking...";
            immersiveStatusSub.innerText = "Streaming response";
        }
    }

    // Voice Overlay screen control
    if (voiceOverlay) {
        if ((state === "LISTENING" || state === "SPEAKING") && isVoiceTalkActive) {
            voiceOverlay.classList.remove("opacity-0", "pointer-events-none", "scale-105");
            voiceOverlay.classList.add("opacity-100", "pointer-events-auto", "scale-100");
            if (voiceStatusSub) {
                voiceStatusSub.innerText = state === "LISTENING" ? "Listening" : "Speaking";
            }
        } else {
            voiceOverlay.classList.remove("opacity-100", "pointer-events-auto", "scale-100");
            voiceOverlay.classList.add("opacity-0", "pointer-events-none", "scale-105");
        }
    }

    // Typing animation display
    if (typingIndicator) {
        if (state === "THINKING") {
            typingIndicator.classList.remove("hidden");
            chatMessages.scrollTop = chatMessages.scrollHeight;
        } else {
            typingIndicator.classList.add("hidden");
        }
    }
}

// --- 2. High-Performance Canvas-based Arc Reactor Status Visualizer ---

function resizeCanvases() {
    const dpr = window.devicePixelRatio || 1;
    [
        { canvas: sidebarCanvas, size: 36 },
        { canvas: mainCanvas, size: 320 }, // Placed above chat feed (320px diameter)
        { canvas: overlayCanvas, size: 320 }
    ].forEach(({ canvas, size }) => {
        if (!canvas) return;
        canvas.width = size * dpr;
        canvas.height = size * dpr;
        canvas.style.width = size + "px";
        canvas.style.height = size + "px";
        const ctx = canvas.getContext("2d");
        ctx.setTransform(1, 0, 0, 1, 0, 0); // reset scale
        ctx.scale(dpr, dpr);
    });
}

// Map degrees (0-360) to circular FFT visualizer values
function getWaveValue(deg, fftData, avgLevel, time, scaleRadius) {
    if (currentState === "LISTENING" || currentState === "SPEAKING") {
        if (fftData && fftData.length > 0) {
            // Symmetrical frequency indexing (0-180 mirrored to 180-360)
            let halfIndex = deg % 180;
            if (deg > 180) halfIndex = 180 - halfIndex;
            
            let idx = Math.floor((halfIndex / 180) * fftData.length * 0.55); // Use first 55% of frequency bands
            let fftVal = fftData[idx] / 255;
            
            let baseAmp = 3.5 + fftVal * (scaleRadius * 0.32);
            let harmonicOffset = Math.sin(deg * 9 * Math.PI / 180) * baseAmp * 0.22;
            let primaryWave = Math.sin(deg * 3.5 * Math.PI / 180 - time * 5) * baseAmp * 0.78;
            return primaryWave + harmonicOffset;
        }
    } else if (currentState === "THINKING") {
        // Active energy ripples
        return Math.sin(deg * 6 * Math.PI / 180 + time * 7.5) * (scaleRadius * 0.08) + 
               Math.cos(deg * 11 * Math.PI / 180 - time * 3.8) * (scaleRadius * 0.025);
    }
    // Idle breathing waves
    return Math.sin(deg * 4.5 * Math.PI / 180 + time * 1.6) * (scaleRadius * 0.04) + 
           Math.cos(deg * 8 * Math.PI / 180 - time * 0.8) * (scaleRadius * 0.015);
}

function drawVoiceOrb(canvas, ctx, avgLevel, time, scale, fftData) {
    if (!canvas || !ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const w = canvas.width / dpr;
    const h = canvas.height / dpr;
    ctx.clearRect(0, 0, w, h);

    const cx = w / 2;
    const cy = h / 2;
    
    // Core radius is scaled dynamically via spring physics
    const baseR = Math.min(cx, cy) * 0.85; // slightly reduced from 0.88 to ensure brackets fit within bounds
    const r = baseR * scale;

    const isMini = w < 60; // Mini logo checks

    if (isMini) {
        // Simplified mini voice orb for sidebar logo
        ctx.save();
        ctx.beginPath();
        ctx.arc(cx, cy, r * 0.2, 0, 2 * Math.PI);
        ctx.fillStyle = '#0B0F19';
        ctx.fill();
        ctx.strokeStyle = '#00E5FF';
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.restore();

        // Layer 3: Segmented blocks (fewer for mini)
        ctx.save();
        ctx.strokeStyle = '#00E5FF';
        ctx.lineWidth = 2;
        ctx.lineCap = 'butt';
        let blockRotation = time * 0.3;
        const blocksCount = 6;
        const blockAngle = (2 * Math.PI) / blocksCount;
        for (let i = 0; i < blocksCount; i++) {
            let start = i * blockAngle + blockRotation;
            let end = start + blockAngle - 0.2;
            ctx.beginPath();
            ctx.arc(cx, cy, r * 0.4, start, end);
            ctx.stroke();
        }
        ctx.restore();

        // Layer 4: Spectrum ribbon (drawn as a single thin line)
        ctx.save();
        ctx.strokeStyle = '#6E5BFF';
        ctx.lineWidth = 1;
        ctx.beginPath();
        for (let i = 0; i <= 360; i += 15) {
            let rad = (i * Math.PI) / 180;
            let waveVal = getWaveValue(i, fftData, avgLevel, time, r);
            let dist = r * 0.65 + waveVal * 0.4;
            let x = cx + Math.cos(rad) * dist;
            let y = cy + Math.sin(rad) * dist;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.stroke();
        ctx.restore();

        // Layer 5: Outer energy ring
        ctx.save();
        ctx.strokeStyle = '#FF4DFF';
        ctx.lineWidth = 0.8;
        ctx.beginPath();
        ctx.arc(cx, cy, r * 0.85, 0, 2 * Math.PI);
        ctx.stroke();
        ctx.restore();
        
        return;
    }

    // ==========================================
    // LAYER 1: Glowing Central Core
    // ==========================================
    const coreR = r * 0.18;
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, coreR, 0, 2 * Math.PI);
    ctx.fillStyle = '#0B0F19';
    ctx.fill();
    ctx.strokeStyle = '#00E5FF';
    ctx.lineWidth = 2;
    ctx.shadowColor = '#00E5FF';
    ctx.shadowBlur = 8;
    ctx.stroke();
    ctx.restore();

    // Crosshairs
    ctx.save();
    ctx.strokeStyle = 'rgba(0, 229, 255, 0.4)';
    ctx.lineWidth = 0.8;
    ctx.beginPath();
    ctx.arc(cx, cy, 1.5, 0, 2 * Math.PI);
    ctx.fillStyle = '#00E5FF';
    ctx.fill();
    ctx.moveTo(cx - coreR * 0.5, cy); ctx.lineTo(cx + coreR * 0.5, cy);
    ctx.moveTo(cx, cy - coreR * 0.5); ctx.lineTo(cx, cy + coreR * 0.5);
    ctx.stroke();
    ctx.restore();

    // ==========================================
    // LAYER 2: Concentric Mechanical Rings
    // ==========================================
    ctx.save();
    // Thick circular mechanical ring around core
    ctx.strokeStyle = 'rgba(0, 229, 255, 0.25)';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(cx, cy, r * 0.23, 0, 2 * Math.PI);
    ctx.stroke();

    // Thin mechanical inner ring
    ctx.strokeStyle = 'rgba(0, 229, 255, 0.1)';
    ctx.lineWidth = 0.8;
    ctx.beginPath();
    ctx.arc(cx, cy, r * 0.26, 0, 2 * Math.PI);
    ctx.arc(cx, cy, r * 0.38, 0, 2 * Math.PI);
    ctx.stroke();
    ctx.restore();

    // ==========================================
    // LAYER 3: Segmented Cyan Blocks (Arc Reactor)
    // ==========================================
    ctx.save();
    ctx.strokeStyle = '#00E5FF';
    ctx.lineWidth = r * 0.06;
    ctx.lineCap = 'butt';
    ctx.shadowColor = '#00E5FF';
    ctx.shadowBlur = 18;
    
    let blockRotation = time * 0.2;
    if (currentState === "THINKING") blockRotation = -time * 0.5;
    else if (currentState === "SPEAKING") blockRotation = time * 0.35;
    
    const blocksCount = 12;
    const blockAngle = (2 * Math.PI) / blocksCount;
    const gapAngle = 0.09;
    
    for (let i = 0; i < blocksCount; i++) {
        let start = i * blockAngle + blockRotation;
        let end = start + blockAngle - gapAngle;
        ctx.beginPath();
        ctx.arc(cx, cy, r * 0.32, start, end);
        ctx.stroke();
    }
    ctx.restore();

    // ==========================================
    // LAYER 4: Continuous Circular Audio Spectrum Ribbon
    // ==========================================
    ctx.save();
    let waveGrad = ctx.createLinearGradient(cx - r * 0.8, cy, cx + r * 0.8, cy);
    waveGrad.addColorStop(0, '#FF4DFF');
    waveGrad.addColorStop(0.5, '#6E5BFF');
    waveGrad.addColorStop(1, '#00E5FF');

    ctx.beginPath();
    // Trace outer boundary
    const step = 2;
    for (let i = 0; i <= 360; i += step) {
        let rad = (i * Math.PI) / 180;
        let waveVal = getWaveValue(i, fftData, avgLevel, time, r);
        let dist = r * 0.68 + waveVal * 1.5;
        let x = cx + Math.cos(rad) * dist;
        let y = cy + Math.sin(rad) * dist;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    // Trace inner boundary in reverse
    for (let i = 360; i >= 0; i -= step) {
        let rad = (i * Math.PI) / 180;
        let waveVal = getWaveValue(i, fftData, avgLevel, time, r);
        let dist = r * 0.62 - waveVal * 0.8;
        let x = cx + Math.cos(rad) * dist;
        let y = cy + Math.sin(rad) * dist;
        ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.fillStyle = waveGrad;
    ctx.fill();
    ctx.restore();

    // ==========================================
    // LAYER 5: Neon Outer Energy Ring
    // ==========================================
    ctx.save();
    // Magenta outer ring
    ctx.strokeStyle = '#FF4DFF';
    ctx.lineWidth = 1.2;
    ctx.shadowColor = '#FF4DFF';
    ctx.shadowBlur = 6;
    ctx.beginPath();
    ctx.arc(cx, cy, r * 0.84, 0, 2 * Math.PI);
    ctx.stroke();

    // Ticking dashed cyan ring
    ctx.strokeStyle = '#00E5FF';
    ctx.lineWidth = 1.5;
    ctx.shadowColor = '#00E5FF';
    ctx.shadowBlur = 8;
    ctx.setLineDash([4, 12]);
    ctx.beginPath();
    ctx.arc(cx, cy, r * 0.88, time * 0.05, time * 0.05 + 2 * Math.PI);
    ctx.stroke();
    ctx.restore();

    // Quadrant brackets
    ctx.save();
    ctx.strokeStyle = '#00E5FF';
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    ctx.shadowColor = '#00E5FF';
    ctx.shadowBlur = 12;
    
    let bracketRotation = time * 0.08;
    const bracketWidth = 25 * Math.PI / 180;
    const bracketGaps = [0, Math.PI / 2, Math.PI, 3 * Math.PI / 2];
    
    bracketGaps.forEach(baseAngle => {
        let start = baseAngle + bracketRotation - bracketWidth / 2;
        let end = baseAngle + bracketRotation + bracketWidth / 2;
        ctx.beginPath();
        ctx.arc(cx, cy, r * 0.94, start, end);
        ctx.stroke();
    });
    ctx.restore();
}

// Visualizer continuous 60FPS animation loop
function animLoop() {
    animFrameId = requestAnimationFrame(animLoop);

    let fftData = null;
    let avgLevel = 0;
    const time = Date.now() * 0.001;

    // Spring physics update
    let force = (reactorSpring.target - reactorSpring.x) * reactorSpring.k;
    reactorSpring.v = (reactorSpring.v + force) * reactorSpring.d;
    reactorSpring.x += reactorSpring.v;

    // Collect real mic streams or simulate states output
    if (audioAnalyser) {
        fftData = new Uint8Array(audioAnalyser.frequencyBinCount);
        audioAnalyser.getByteFrequencyData(fftData);
        
        let sum = 0;
        for (let i = 0; i < fftData.length; i++) sum += fftData[i];
        avgLevel = sum / fftData.length;
        updateMicLevelBar(avgLevel);
    } else if (currentState === "SPEAKING") {
        // Simulate animated amplitude output
        fftData = new Uint8Array(64);
        for (let i = 0; i < fftData.length; i++) {
            fftData[i] = 40 + Math.random() * 190 * Math.abs(Math.sin(Date.now() * 0.016 + i * 0.12));
        }
        let sum = 0;
        for (let i = 0; i < fftData.length; i++) sum += fftData[i];
        avgLevel = sum / fftData.length;
        updateMicLevelBar(avgLevel);
    } else if (currentState === "LISTENING") {
        // Low amplitude listening noise
        fftData = new Uint8Array(64);
        for (let i = 0; i < fftData.length; i++) {
            fftData[i] = 10 + Math.random() * 45 * Math.abs(Math.sin(Date.now() * 0.007 + i * 0.16));
        }
        let sum = 0;
        for (let i = 0; i < fftData.length; i++) sum += fftData[i];
        avgLevel = sum / fftData.length;
        updateMicLevelBar(avgLevel);
    }

    // Draw standard logo canvases
    if (sidebarCanvas) {
        drawVoiceOrb(sidebarCanvas, sidebarCanvas.getContext("2d"), avgLevel, time, reactorSpring.x, fftData);
    }
    if (mainCanvas) {
        drawVoiceOrb(mainCanvas, mainCanvas.getContext("2d"), avgLevel, time, reactorSpring.x, fftData);
    }
    if (overlayCanvas) {
        drawVoiceOrb(overlayCanvas, overlayCanvas.getContext("2d"), avgLevel, time, reactorSpring.x, fftData);
    }
}

// Request mic streams and load analyser
function startMicAnalyser() {
    if (audioAnalyser) return;
    dbgLog("Initializing mic analyzer...", "info");
    
    navigator.mediaDevices.getUserMedia({ audio: true, video: false })
        .then(stream => {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
            audioAnalyser = audioContext.createAnalyser();
            audioAnalyser.fftSize = 256;
            
            micSource = audioContext.createMediaStreamSource(stream);
            micSource.connect(audioAnalyser);
            
            if (audioContext.state === "suspended") {
                audioContext.resume();
            }
            dbgLog("Microphone input successfully connected.", "ok");
            
            // Connect and size canvases
            resizeCanvases();
            if (!animFrameId) animLoop();
        })
        .catch(err => {
            dbgLog("Mic connection failed: " + err.message, "error");
        });
}

// --- 3. Speech Recognition (STT Dictation & Loop) ---
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = false; // Trigger immediate execution on natural pause
    recognition.interimResults = true;
    recognition.lang = "en-US";
    
    recognition.onstart = () => {
        isRecognitionRunning = true;
        dbgLog("Voice recognition engine started.", "ok");
        setUIState("LISTENING");
        window.speechSynthesis.cancel(); // Stop active speaking if user talks back
    };
    
    recognition.onresult = (event) => {
        const transcript = Array.from(event.results)
            .map(res => res[0])
            .map(res => res.transcript)
            .join("");
        
        const isFinal = event.results[event.results.length - 1].isFinal;
        dbgLog(`STT Capture: "${transcript}" (${isFinal ? "Final" : "Interim"})`, "info");
        
        if (voicePreviewText) {
            voicePreviewText.innerText = transcript || "Listening...";
        }
        if (commandInput) {
            commandInput.value = transcript;
        }
    };
    
    recognition.onerror = (e) => {
        dbgLog(`STT Exception: ${e.error}`, "error");
        if (e.error === "not-allowed") {
            dbgLog("Mic access blocked. Allow permissions in the container.", "error");
            isVoiceTalkActive = false;
            updateVoiceTalkUI();
            setUIState("SLEEP");
        } else if (e.error === "no-speech") {
            dbgLog("Silence detected in recognition loop.", "warn");
        }
    };
    
    recognition.onend = () => {
        isRecognitionRunning = false;
        const query = commandInput.value.trim();
        dbgLog("Speech ended.", "info");
        
        if (query) {
            submitCommand(query);
            if (commandInput) commandInput.value = "";
        } else {
            restartListeningLoop();
        }
    };
}

// --- 4. Python-Based STT callbacks (WebView2 local fallback overrides) ---
window.onPySTTStatus = (status) => {
    dbgLog(`Python STT Status Event: ${status}`, "info");
    if (status === "listening") {
        setUIState("LISTENING");
        if (voicePreviewText) voicePreviewText.innerText = "Listening...";
    } else if (status === "processing") {
        setUIState("THINKING");
        if (voicePreviewText) voicePreviewText.innerText = "Processing voice...";
    } else if (status === "timeout") {
        dbgLog("Python voice capture timed out.", "warn");
        isRecognitionRunning = false;
        restartListeningLoop();
    }
};

window.onPySTTResult = (text) => {
    dbgLog(`Python STT Result text: "${text}"`, "ok");
    isRecognitionRunning = false;
    if (voicePreviewText) voicePreviewText.innerText = text;
    if (text) {
        submitCommand(text);
    } else {
        restartListeningLoop();
    }
};

window.onPySTTError = (err) => {
    dbgLog(`Python STT Error details: ${err}`, "error");
    isRecognitionRunning = false;
    setUIState("SLEEP");
    restartListeningLoop();
};

function startListening() {
    if (isRecognitionRunning) return;

    // Use Python pywebview local STT recorder (bypasses browser authorization sandbox bugs)
    if (window.pywebview && window.pywebview.api && window.pywebview.api.start_voice_capture) {
        dbgLog("Invoking local OS voice recorder (Python)", "ok");
        isRecognitionRunning = true;
        setUIState("LISTENING");
        if (voicePreviewText) voicePreviewText.innerText = "Activating microphone...";
        window.pywebview.api.start_voice_capture();
        return;
    }

    // Fallback standard browser speech synthesis
    if (!recognition) {
        dbgLog("SpeechRecognition engine not supported in container.", "error");
        return;
    }

    try {
        if (audioContext && audioContext.state === "suspended") {
            audioContext.resume();
        }
        recognition.start();
    } catch (ex) {
        dbgLog(`STT engine launch error: ${ex.message}`, "error");
    }
}

function stopListening() {
    if (!isRecognitionRunning) return;
    dbgLog("Cancelling microphone listening.", "info");
    try {
        if (recognition) recognition.stop();
    } catch (e) {}
}

function restartListeningLoop() {
    if (isVoiceTalkActive && currentState !== "THINKING" && currentState !== "SPEAKING") {
        setTimeout(() => {
            if (isVoiceTalkActive && currentState !== "THINKING" && currentState !== "SPEAKING") {
                startListening();
            }
        }, 800);
    } else if (!isVoiceTalkActive && currentState !== "THINKING" && currentState !== "SPEAKING") {
        setUIState("SLEEP");
    }
}

// --- 5. Speech Synthesis (TTS Voice output engine) ---
function speak(text) {
    if (isMuted) {
        onSpeakComplete();
        return;
    }

    window.speechSynthesis.cancel();
    
    // Scrub markdown elements and syntax from synthesized audio
    const cleanText = text
        .replace(/```[\s\S]*?```/g, "[Task complete]")
        .replace(/`([^`]+)`/g, "$1")
        .replace(/\*\*([^*]+)\*\*/g, "$1")
        .replace(/\*([^*]+)\*/g, "$1")
        .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
        .replace(/[-*#]/g, "")
        .trim();

    if (!cleanText) {
        onSpeakComplete();
        return;
    }

    const sentences = cleanText.split(/\. |\n+/);
    let index = 0;
    
    setUIState("SPEAKING");
    if (voicePreviewText) voicePreviewText.innerText = cleanText;

    fontSelected = false;

    function speakSentence() {
        if (index >= sentences.length || isMuted || !isVoiceTalkActive) {
            onSpeakComplete();
            return;
        }

        const sentence = sentences[index].trim();
        index++;

        if (!sentence) {
            speakSentence();
            return;
        }

        const utterance = new SpeechSynthesisUtterance(sentence);
        const voices = window.speechSynthesis.getVoices();

        // Target Microsoft Online Natural guy voices
        const idealVoice = voices.find(v => v.lang.startsWith("en") && v.name.includes("Online") && v.name.includes("Natural") && (v.name.includes("Guy") || v.name.includes("Ryan") || v.name.includes("Andrew")))
            || voices.find(v => v.lang.startsWith("en") && (v.name.includes("Guy") || v.name.toLowerCase().includes("male")))
            || voices.find(v => v.lang.startsWith("en") && v.name.includes("David"))
            || voices.find(v => v.lang.startsWith("en") && v.name.includes("Google") && !v.name.includes("Female"))
            || voices.find(v => v.lang.startsWith("en"));

        if (idealVoice) utterance.voice = idealVoice;
        utterance.rate = 1.05;
        utterance.pitch = 0.96;

        utterance.onend = () => speakSentence();
        utterance.onerror = () => speakSentence();

        window.speechSynthesis.speak(utterance);
    }

    speakSentence();
}

function onSpeakComplete() {
    if (isVoiceTalkActive) {
        setUIState("LISTENING");
        startListening();
    } else {
        setUIState("SLEEP");
    }
}

// --- 6. Event Listeners & UI Inputs Binding ---

// Click visual voice reactors to toggle voice dictation/speech synthesis
function handleReactorClick() {
    if (!audioAnalyser) {
        startMicAnalyser();
    }

    if (currentState === "SLEEP" || currentState === "LISTENING") {
        if (isVoiceTalkActive) {
            if (isRecognitionRunning) {
                stopListening();
                isRecognitionRunning = false;
                setUIState("SLEEP");
            } else {
                setUIState("LISTENING");
                startListening();
            }
        } else {
            isVoiceTalkActive = true;
            updateVoiceTalkUI();
            startListening();
        }
    } else if (currentState === "SPEAKING") {
        window.speechSynthesis.cancel();
        onSpeakComplete();
    }
}

[sidebarCanvas, mainCanvas, overlayCanvas].forEach(canvas => {
    if (canvas) {
        canvas.addEventListener("click", handleReactorClick);
    }
});

// Voice Buttons Toggles
voiceTalkBtn.addEventListener("click", () => {
    isVoiceTalkActive = !isVoiceTalkActive;
    localStorage.setItem("jarvis_voice_talk", isVoiceTalkActive);
    updateVoiceTalkUI();
    
    if (isVoiceTalkActive) {
        startMicAnalyser();
        startListening();
    } else {
        stopListening();
        isRecognitionRunning = false;
        window.speechSynthesis.cancel();
        setUIState("SLEEP");
    }
});

muteBtn.addEventListener("click", () => {
    isMuted = !isMuted;
    localStorage.setItem("jarvis_muted", isMuted);
    updateMuteUI();
    if (isMuted) {
        window.speechSynthesis.cancel();
        if (currentState === "SPEAKING") {
            onSpeakComplete();
        }
    }
});

// Floating buttons inside Prompt bar
promptVoiceBtn.addEventListener("click", () => {
    isVoiceTalkActive = !isVoiceTalkActive;
    updateVoiceTalkUI();
    if (isVoiceTalkActive) {
        startMicAnalyser();
        startListening();
    } else {
        stopListening();
        isRecognitionRunning = false;
        window.speechSynthesis.cancel();
        setUIState("SLEEP");
    }
});

// Close Voice overlay window back to standard layout
if (closeVoiceBtn) {
    closeVoiceBtn.addEventListener("click", () => {
        isVoiceTalkActive = false;
        updateVoiceTalkUI();
        stopListening();
        isRecognitionRunning = false;
        window.speechSynthesis.cancel();
        setUIState("SLEEP");
    });
}

// Quick Starter Prompt Clickers
document.querySelectorAll(".quick-prompt-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        const textElement = btn.querySelector("span:first-child");
        if (textElement) {
            let command = textElement.innerText;
            if (command === "Show System Diagnostics") command = "Show system diagnostics";
            else if (command === "Recent Memory Log") command = "Show recent memory facts";
            else if (command === "Open Web Browser") command = "Open Brave browser and search Google";
            else if (command === "Find Local Scripts") command = "Search for local Python scripts";
            submitCommand(command);
        }
    });
});

// Clear conversational history
if (clearChatBtn) {
    clearChatBtn.addEventListener("click", () => {
        chatMessages.innerHTML = "";
        welcomeScreen.classList.remove("hidden");
        dbgLog("Chat timeline cleared.", "info");
    });
}

// Diagnostics refresh button
if (refreshMemoryBtn) {
    refreshMemoryBtn.addEventListener("click", () => {
        reloadMemoryFacts();
        reloadDiagnostics();
        dbgLog("Requested memory database refresh.", "ok");
    });
}

// Diagnostics debug panel visibility
if (toggleDebugBtn) {
    toggleDebugBtn.addEventListener("click", () => {
        const panel = ensureDebugPanel();
        const shown = panel.style.display === "block";
        panel.style.display = shown ? "none" : "block";
        localStorage.setItem("jarvis_debug", !shown);
    });
}

// Layout Sidebars Expand Toggle
function toggleZenMode() {
    sidebarsVisible = !sidebarsVisible;
    const mainEl = document.querySelector("main");
    if (sidebarsVisible) {
        leftSidebar.classList.remove("w-0", "p-0", "opacity-0", "overflow-hidden");
        leftSidebar.classList.add("w-80", "p-6", "opacity-100");
        rightSidebar.classList.remove("w-0", "p-0", "opacity-0", "overflow-hidden");
        rightSidebar.classList.add("w-80", "p-6", "opacity-100");
        if (mainEl) mainEl.classList.remove("immersive-mode");
    } else {
        leftSidebar.classList.remove("w-80", "p-6", "opacity-100");
        leftSidebar.classList.add("w-0", "p-0", "opacity-0", "overflow-hidden");
        rightSidebar.classList.remove("w-80", "p-6", "opacity-100");
        rightSidebar.classList.add("w-0", "p-0", "opacity-0", "overflow-hidden");
        if (mainEl) mainEl.classList.add("immersive-mode");
    }
    resizeCanvases();
    dbgLog(`Zen Mode toggled: Sidebars visible = ${sidebarsVisible}`, "info");
}

if (togglePanelsBtn) {
    togglePanelsBtn.addEventListener("click", toggleZenMode);
}

// Global Hotkeys Escape
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
        e.preventDefault();
        toggleZenMode();
    }
});

// --- 7. Diagnostics Render Updates ---
function reloadDiagnostics() {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.get_system_diagnostics) {
        window.pywebview.api.get_system_diagnostics().then(info => renderDiagnostics(info));
    } else {
        fetch("/api/diagnostics")
            .then(res => res.json())
            .then(info => renderDiagnostics(info))
            .catch(err => console.log("Diag fetch deferred:", err));
    }
}

let currentUsername = "User";

function renderDiagnostics(info) {
    if (!info) return;
    if (diagOs) diagOs.innerText = info.os ? info.os.toUpperCase() : "WINDOWS";
    if (diagCpu) diagCpu.innerText = info.logical_processors ? `${info.logical_processors} CORES` : "N/A";
    if (diagRam) diagRam.innerText = info.total_ram_gb ? `${Math.round(info.total_ram_gb)} GB` : "N/A";
    
    if (info.username) {
        currentUsername = info.username;
        const welcomeTitle = document.getElementById("welcome-title");
        if (welcomeTitle) {
            welcomeTitle.innerText = `Hello, ${info.username.charAt(0).toUpperCase() + info.username.slice(1)}`;
        }
    }
}

function reloadMemoryFacts() {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.get_learned_facts) {
        window.pywebview.api.get_learned_facts().then(facts => renderMemoryFacts(facts));
    } else {
        fetch("/api/facts")
            .then(res => res.json())
            .then(facts => renderMemoryFacts(facts))
            .catch(err => console.log("Facts fetch deferred:", err));
    }
}

function renderMemoryFacts(facts) {
    if (!memoryFactsList) return;
    memoryFactsList.innerHTML = "";
    
    if (facts && facts.length > 0) {
        facts.forEach(fact => {
            const item = document.createElement("div");
            item.className = "p-3 rounded-2xl bg-white/[0.02] border border-white/5 text-[11px] font-mono text-textMuted flex items-start gap-2 hover:border-white/10 transition-colors leading-relaxed";
            item.innerHTML = `
                <span class="w-1.5 h-1.5 rounded-full bg-accentStart mt-1.5 shrink-0"></span>
                <span>${fact}</span>
            `;
            memoryFactsList.appendChild(item);
        });
    } else {
        memoryFactsList.innerHTML = `
            <div class="text-white/20 italic text-center py-6 font-mono text-[11.5px] flex flex-col gap-1 items-center">
                <i data-lucide="info" class="w-4 h-4 opacity-40"></i>
                <span>No facts stored yet.</span>
            </div>
        `;
        lucide.createIcons();
    }
}

// --- 8. Conversational Messages & HTML Renderers ---

function appendTerminalLog(role, text) {
    if (welcomeScreen) welcomeScreen.classList.add("hidden");

    const bubbleId = `msg-bubble-${Date.now()}`;
    const bubble = document.createElement("div");
    bubble.id = bubbleId;
    bubble.className = `flex gap-4 items-start w-full max-w-3xl mx-auto message-bubble ${role === "user" ? "justify-end" : "justify-start"}`;

    const isUser = role === "user";
    
    // Avatar
    const avatarHtml = isUser ? `
        <div class="w-8 h-8 rounded-full bg-gradient-to-tr from-accentStart to-accentEnd flex items-center justify-center shrink-0 shadow-md">
            <i data-lucide="user" class="w-4 h-4 text-white"></i>
        </div>
    ` : `
        <div class="w-8 h-8 rounded-full bg-white/5 border border-white/10 flex items-center justify-center shrink-0">
            <i data-lucide="bot" class="w-4 h-4 text-accentEnd animate-pulse"></i>
        </div>
    `;

    // Bubble Text Body
    const bubbleBody = `
        <div class="flex flex-col gap-1 max-w-[80%] ${isUser ? "items-end" : "items-start"}">
            <span class="text-[9px] font-mono font-bold tracking-wider text-textMuted uppercase">${isUser ? currentUsername.toUpperCase() : "JARVIS"}</span>
            <div class="glass-panel px-5 py-3.5 rounded-[22px] shadow-sm leading-relaxed text-sm text-white/90 markdown-body ${isUser ? "rounded-tr-none bg-accentStart/10 border-accentStart/20" : "rounded-tl-none bg-white/[0.02]"}">
                ${parseMarkdown(text)}
            </div>
        </div>
    `;

    if (isUser) {
        bubble.innerHTML = bubbleBody + avatarHtml;
    } else {
        bubble.innerHTML = avatarHtml + bubbleBody;
    }

    chatMessages.appendChild(bubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    // Re-bind SVG Icons dynamically
    lucide.createIcons();
}

// Markdown Parser
function parseMarkdown(text) {
    let html = text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        // Code blocks
        .replace(/```([a-zA-Z0-9]*)\n([\s\S]*?)```/g, function(match, lang, code) {
            return `<pre><code class="language-${lang}">${code.trim()}</code></pre>`;
        })
        // Inline code
        .replace(/`([^`\n]+)`/g, '<code>$1</code>')
        // Bold
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        // Italic
        .replace(/\*([^*]+)\*/g, '<em>$1</em>')
        // Linebreaks
        .replace(/\n/g, "<br>");
    return html;
}

// --- 9. Tool Execution UI Card Renderers ---

window.onAgentEvent = function(event) {
    if (event.type === "tool_call") {
        setUIState("THINKING");
        toolCallSeq++;
        
        // Hide welcome on tool logs
        if (welcomeScreen) welcomeScreen.classList.add("hidden");

        // 1. Create center conversation card for the tool execution
        const toolCard = document.createElement("div");
        toolCard.id = `tool-card-${toolCallSeq}`;
        toolCard.className = "w-full max-w-3xl mx-auto glass-panel border-accentEnd/20 rounded-[20px] p-4 flex flex-col gap-3 status-glow-running transition-all duration-300 message-bubble";
        toolCard.innerHTML = `
            <div class="flex items-center justify-between text-xs">
                <div class="flex items-center gap-2">
                    <i data-lucide="play-circle" class="w-4 h-4 text-accentEnd animate-pulse"></i>
                    <span class="font-mono font-bold tracking-wide uppercase">Executing Tool</span>
                </div>
                <span class="px-2 py-0.5 rounded-full font-mono text-[9px] bg-accentEnd/10 text-accentEnd border border-accentEnd/25 flex items-center gap-1.5 uppercase">
                    <span class="w-1.2 h-1.2 rounded-full bg-accentEnd animate-ping"></span>
                    ${event.name}
                </span>
            </div>
            <div class="text-[11px] font-mono text-textMuted bg-black/20 border border-white/5 rounded-xl p-3 max-h-24 overflow-y-auto">
                <span class="text-white/40">arguments:</span> ${JSON.stringify(event.arguments)}
            </div>
            <div class="tool-result-box text-xs hidden flex-col gap-1.5 border-t border-white/5 pt-3">
                <span class="font-semibold text-textMuted font-mono text-[10px]">OUTPUT:</span>
                <div class="tool-output-content text-[11px] font-mono text-white/75 bg-black/40 border border-white/5 rounded-xl p-3 max-h-40 overflow-y-auto break-all">
                </div>
            </div>
        `;
        chatMessages.appendChild(toolCard);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        // 2. Append quick sidebar row inside Activity Feed
        const sidebarRow = document.createElement("div");
        sidebarRow.id = `right-tool-row-${toolCallSeq}`;
        sidebarRow.className = "p-3 rounded-2xl bg-white/[0.02] border border-white/5 text-[11px] font-mono text-textMuted flex flex-col gap-1.5 hover:border-white/10 transition-colors";
        sidebarRow.innerHTML = `
            <div class="flex items-center justify-between">
                <span class="text-white truncate">${event.name}</span>
                <span class="text-[8px] bg-accentEnd/15 text-accentEnd border border-accentEnd/20 px-1.5 rounded uppercase">running</span>
            </div>
            <span class="text-[9px] text-white/30 truncate">Active execution logs</span>
        `;
        // Clear placeholder logs
        const placeholder = liveToolContainer.querySelector(".italic");
        if (placeholder) placeholder.remove();
        liveToolContainer.prepend(sidebarRow);
        
        lucide.createIcons();
    } else if (event.type === "tool_result") {
        const card = document.getElementById(`tool-card-${toolCallSeq}`);
        if (card) {
            card.classList.remove("status-glow-running", "border-accentEnd/20");
            card.classList.add("status-glow-success", "border-emerald-500/20");
            
            const statusIndicator = card.querySelector(".flex .flex-wrap") || card.querySelector(".flex.items-center.justify-between");
            if (statusIndicator) {
                const badge = statusIndicator.querySelector("span:last-child");
                if (badge) {
                    badge.className = "px-2 py-0.5 rounded-full font-mono text-[9px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/25 uppercase";
                    badge.innerHTML = "Success";
                }
            }
            const icon = card.querySelector("[data-lucide='play-circle']");
            if (icon) {
                icon.outerHTML = '<i data-lucide="check-circle-2" class="w-4 h-4 text-emerald-400"></i>';
            }

            const resultBox = card.querySelector(".tool-result-box");
            const outputBox = card.querySelector(".tool-output-content");
            if (resultBox && outputBox) {
                resultBox.classList.remove("hidden");
                resultBox.classList.add("flex");
                
                let resultText = typeof event.result === "string" ? event.result : JSON.stringify(event.result);
                if (resultText.length > 500) {
                    resultText = resultText.substring(0, 500) + "\n\n... (Output truncated)";
                }
                outputBox.innerText = resultText;
            }
        }

        const row = document.getElementById(`right-tool-row-${toolCallSeq}`);
        if (row) {
            const badge = row.querySelector("span:last-child");
            if (badge) {
                badge.className = "text-[8px] bg-emerald-500/15 text-emerald-400 border border-emerald-500/20 px-1.5 rounded uppercase";
                badge.innerText = "done";
            }
        }
        
        lucide.createIcons();
    }
};

window.onAgentComplete = function(responseText) {
    appendTerminalLog("jarvis", responseText);
    speak(responseText);
};

window.onAgentError = function(errorMsg) {
    appendTerminalLog("system", `Critical system execution failure: ${errorMsg}`);
    onSpeakComplete();
};

// --- 10. Security Overlay Confirmation Dialog ---
window.showConfirmationModal = function(description) {
    setUIState("THINKING");
    confirmDescription.innerText = description;
    
    confirmModal.classList.remove("opacity-0", "pointer-events-none");
    confirmModal.classList.add("opacity-100", "pointer-events-auto");
    const innerCard = confirmModal.querySelector('.glass-panel');
    if (innerCard) {
        innerCard.classList.remove("scale-95");
        innerCard.classList.add("scale-100");
    }

    allowBtn.onclick = () => {
        confirmModal.classList.add("opacity-0", "pointer-events-none");
        confirmModal.classList.remove("opacity-100", "pointer-events-auto");
        if (innerCard) {
            innerCard.classList.add("scale-95");
            innerCard.classList.remove("scale-100");
        }
        window.pywebview.api.set_confirmation_response(true);
    };

    denyBtn.onclick = () => {
        confirmModal.classList.add("opacity-0", "pointer-events-none");
        confirmModal.classList.remove("opacity-100", "pointer-events-auto");
        if (innerCard) {
            innerCard.classList.add("scale-95");
            innerCard.classList.remove("scale-100");
        }
        window.pywebview.api.set_confirmation_response(false);
        onSpeakComplete();
    };
};

// --- 11. Core Command Submissions & HTTP Polling ---

function submitCommand(query) {
    if (!query) return;

    dbgLog(`Submitting natural language command: "${query}"`, "info");
    appendTerminalLog("user", query);
    setUIState("THINKING");

    if (window.pywebview && window.pywebview.api && window.pywebview.api.execute_command) {
        dbgLog("Dispatching query via PyWebView desktop bridge.", "info");
        window.pywebview.api.execute_command(query);
    } else {
        dbgLog("Dispatching query to async Local HTTP job queue.", "info");
        fetch("/api/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ command: query })
        })
        .then(res => {
            if (!res.ok) throw new Error("HTTP connection code: " + res.status);
            return res.json();
        })
        .then(data => {
            if (data.job_id) {
                dbgLog(`Job registered: ${data.job_id.slice(0, 8)}. Initializing output polling...`, "ok");
                pollForResult(data.job_id, 0);
            } else if (data.response) {
                window.onAgentComplete(data.response);
            } else {
                throw new Error("Invalid response format received from queue.");
            }
        })
        .catch(err => {
            dbgLog("Server connection lost: " + err.message, "error");
            window.onAgentError("Connection failed: " + err.message);
        });
    }
}

function pollForResult(jobId, elapsedSec) {
    const MAX_POLL_LIMIT = 300;
    if (elapsedSec > MAX_POLL_LIMIT) {
        dbgLog("Model execution timed out.", "error");
        window.onAgentError("Command reasoning took too long. Check local runner logs.");
        return;
    }

    fetch(`/api/result?id=${jobId}`)
        .then(res => res.json())
        .then(data => {
            if (data.status === "pending") {
                setTimeout(() => pollForResult(jobId, elapsedSec + 2.5), 2500);
            } else if (data.status === "done") {
                dbgLog(`Reasoning completed in ${elapsedSec}s. Output: ${data.response ? data.response.length : 0} chars.`, "ok");
                window.onAgentComplete(data.response);
            } else if (data.status === "error") {
                window.onAgentError(data.response);
            } else {
                setTimeout(() => pollForResult(jobId, elapsedSec + 2.5), 2500);
            }
        })
        .catch(err => {
            dbgLog(`Polling retrying due to network wobble: ${err.message}`, "warn");
            setTimeout(() => pollForResult(jobId, elapsedSec + 2.5), 2500);
        });
}

// Form Submission Event
commandForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const query = commandInput.value.trim();
    if (query) {
        submitCommand(query);
        commandInput.value = "";
    }
});

// UI Toggles Helpers
function updateMuteUI() {
    if (!muteBtn) return;
    if (isMuted) {
        muteBtn.classList.remove("bg-white/[0.02]");
        muteBtn.classList.add("bg-red-500/10", "border-red-500/20", "text-red-400");
        muteLabel.innerText = "VOICE OUTPUT: MUTED";
        const icon = document.getElementById("mute-icon");
        if (icon) icon.setAttribute("data-lucide", "volume-x");
    } else {
        muteBtn.classList.remove("bg-red-500/10", "border-red-500/20", "text-red-400");
        muteBtn.classList.add("bg-white/[0.02]");
        muteLabel.innerText = "VOICE OUTPUT: ACTIVE";
        const icon = document.getElementById("mute-icon");
        if (icon) icon.setAttribute("data-lucide", "volume-2");
    }
    lucide.createIcons();
}

function updateVoiceTalkUI() {
    if (!voiceTalkBtn || !promptVoiceBtn) return;
    if (isVoiceTalkActive) {
        voiceTalkBtn.classList.remove("bg-white/[0.02]");
        voiceTalkBtn.classList.add("bg-accentStart/15", "border-accentStart/35", "text-accentEnd");
        voiceTalkLabel.innerText = "VOICE LOOP: ACTIVE";
        promptVoiceBtn.classList.add("text-accentSecondary");
        if (promptVoicePulse) promptVoicePulse.classList.remove("hidden");
    } else {
        voiceTalkBtn.classList.remove("bg-accentStart/15", "border-accentStart/35", "text-accentEnd");
        voiceTalkBtn.classList.add("bg-white/[0.02]", "border-white/5", "text-textMuted");
        voiceTalkLabel.innerText = "VOICE LOOP: OFF";
        promptVoiceBtn.classList.remove("text-accentSecondary");
        if (promptVoicePulse) promptVoicePulse.classList.add("hidden");
    }
    lucide.createIcons();
}

// Dom Loaded Main Boot Routine
document.addEventListener("DOMContentLoaded", () => {
    dbgLog("=== REDESIGNED JARVIS BOOTED ===", "ok");
    
    // Resolve Lucide icons on boot
    lucide.createIcons();

    // Canvas size initialization
    resizeCanvases();
    window.addEventListener("resize", resizeCanvases);

    // Initial system load
    setTimeout(() => {
        reloadDiagnostics();
        reloadMemoryFacts();
        
        // Connect mic stream
        startMicAnalyser();
        
        if (isVoiceTalkActive) {
            setUIState("SLEEP");
        }
    }, 1200);
});

// Update voices list callback
window.speechSynthesis.onvoiceschanged = () => {
    console.log("TTS voice list updated.");
};
