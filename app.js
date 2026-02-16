/* Tarot42 Frontend (no build step)
 * - Uses getUserMedia for camera
 * - POST /scan with a JPEG snapshot
 * - Renders spread board (1-card, 3-card, Celtic Cross)
 * - POST /reading then /chat
 */
// Flow state controller - single source of truth
const FlowState = {
  mode: 'physical', // 'physical' | 'digital'
  step: 'modeSelect', // 'modeSelect' | 'acquire' | 'reading' | 'chat'
  
  setMode(newMode) {
    this.mode = newMode;
    this.updateUI();
  },
  
  setStep(newStep) {
    this.step = newStep;
    this.updateUI();
  },
  
  updateUI() {
    const cameraSection = $("cameraSection");
    const digitalWidget = $('digitalWidget');
    
    // Invariant: digital mode should never show camera
    if (this.mode === 'digital' && cameraSection && !cameraSection.classList.contains('hidden')) {
      console.error('🚨 INVARIANT VIOLATION: Digital mode but camera visible!');
      cameraSection.classList.add('hidden');
    }
    
    // Update UI based on mode and step
    if (this.mode === 'digital') {
      // Digital mode flow
      if (cameraSection) cameraSection.classList.add('hidden');
      if (digitalWidget) digitalWidget.classList.remove('hidden');
    } else {
      // Physical mode flow
      if (cameraSection) cameraSection.classList.remove('hidden');
      if (digitalWidget) digitalWidget.classList.add('hidden');
    }
  }
};

const $ = (id) => document.getElementById(id);

function getStyle() {
  return $("readerStyle") ? $("readerStyle").value : "seer";
}

function vibrate(ms) {
  try { if (navigator.vibrate) navigator.vibrate(ms); } catch (_) {}
}

// Debounce function to prevent rapid Enter key presses
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

const debouncedSendChat = debounce(sendChat, 300);

function generateReadingId() {
  return 'reading_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}

function setClarifyOverlay(on) {
  const el = document.getElementById("clarifyOverlay");
  if (!el) return;
  if (on) el.classList.add("on");
  else el.classList.remove("on");
}

const state = {
  deck: null,
  overlays: [],
  overlayById: {},
  overlayId: "WIND",
  assetByCardId: {},
  cardById: {},
  sessionId: null,
  readingId: null, // For digital readings
  currentReadingId: null, // UUID for chat memory
  spreadType: "one_card",
  slots: [],
  stream: null,
  isRunning: false,
  readingMode: "physical", // "physical" or "digital"
  clarifyTarget: null, // { slotIndex, cardId } or null
  currentVoice: "nova",
  isPlaying: false,
  audioQueue: [],
  micPhase: "idle", // idle | recording | transcribing
  autoSpeakChat: true, // Auto-speak chat replies
  currentReading: null, // Store current reading context for chat
  mediaRecorder: null,
  micStream: null,
  micChunks: [],
  micStartedAtMs: 0,
  micTimerInterval: null,
  audioCtx: null,
  analyser: null,
  silenceInterval: null,
  silenceMs: 0,
  autoSend: false,
  chatInflight: false, // Prevent duplicate sends
  hasChatted: false, // Track if chat has been used
  chatState: 'collapsed', // 'collapsed' | 'half' | 'expanded'
};

function spreadTemplate(type) {
  if (type === "one_card") {
    return [{ slot_index: 0, slot_label: "The Card", card_id: null, reversed: false, revealed: false }];
  }
  if (type === "three_card") {
    return [
      { slot_index: 0, slot_label: "Past", card_id: null, reversed: false, revealed: false },
      { slot_index: 1, slot_label: "Present", card_id: null, reversed: false, revealed: false },
      { slot_index: 2, slot_label: "Future", card_id: null, reversed: false, revealed: false },
    ];
  }
  // Celtic Cross (10)
  return [
    { slot_index: 0, slot_label: "Present", card_id: null, reversed: false, revealed: false },
    { slot_index: 1, slot_label: "Challenge", card_id: null, reversed: false, revealed: false },
    { slot_index: 2, slot_label: "Past", card_id: null, reversed: false, revealed: false },
    { slot_index: 3, slot_label: "Future", card_id: null, reversed: false, revealed: false },
    { slot_index: 4, slot_label: "Above", card_id: null, reversed: false, revealed: false },
    { slot_index: 5, slot_label: "Below", card_id: null, reversed: false, revealed: false },
    { slot_index: 6, slot_label: "Advice", card_id: null, reversed: false, revealed: false },
    { slot_index: 7, slot_label: "External", card_id: null, reversed: false, revealed: false },
    { slot_index: 8, slot_label: "Hopes/Fears", card_id: null, reversed: false, revealed: false },
    { slot_index: 9, slot_label: "Outcome", card_id: null, reversed: false, revealed: false },
  ];
}

function setStatus(msg) {
  $("status").textContent = msg;
}

function setLastScan(msg) {
  $("lastScan").textContent = msg;
}

function cardName(card_id) {
  if (!state.deck) return card_id;
  const c = state.cardById[card_id];
  if (!c) return card_id;
  const animal = c.animal || c.name || card_id;
  const title = c.title ? ` — ${c.title}` : "";
  return `${animal}${title}`;
}

function cardImgUrl(card_id) {
  const assetId = state.assetByCardId[card_id] || card_id;
  return `/deck-assets/cards/${assetId}.png`;
}

function cardMeaningText(card_id, reversed) {
  const c = state.cardById[card_id];
  if (!c) return "";
  return reversed ? (c.storm || c.reversed || "") : (c.clear || c.upright || "");
}

function renderOverlayInfo() {
  const el = $("overlayInfo");
  if (!el) return;
  const o = state.overlayById[state.overlayId];
  if (!o) {
    el.textContent = "";
    return;
  }
  const kw = (o.keywords || []).join(", ");
  const kwText = kw ? ` • ${kw}` : "";
  el.textContent = `${o.name}: ${o.effect || ""}${kwText}`;
}

function nextEmptySlotIndex() {
  return state.slots.findIndex(s => !s.card_id);
}

function renderBoard() {
  const board = $("board");
  board.innerHTML = "";

  const type = state.spreadType;

  if (type === "one_card" || type === "three_card") {
    const cols = type === "one_card" ? "grid-cols-1" : "grid-cols-3";
    const wrap = document.createElement("div");
    wrap.className = `grid ${cols} gap-3`;
    state.slots.forEach((s) => wrap.appendChild(renderSlotCard(s)));
    board.appendChild(wrap);
  } else {
    // Celtic Cross layout using CSS grid template areas
    const wrap = document.createElement("div");
    wrap.className = "grid gap-3";
    wrap.style.gridTemplateColumns = "repeat(6, minmax(0, 1fr))";
    wrap.style.gridTemplateRows = "repeat(4, minmax(0, 1fr))";
    wrap.style.alignItems = "stretch";

    const area = {
      0: "2 / 2 / 4 / 4", // present center (span 2x2)
      1: "2 / 2 / 4 / 4", // challenge overlays (we'll rotate)
      2: "2 / 1 / 3 / 2", // past
      3: "2 / 4 / 3 / 5", // future
      4: "1 / 2 / 2 / 4", // above
      5: "4 / 2 / 5 / 4", // below
      6: "4 / 4 / 5 / 5", // advice
      7: "1 / 5 / 2 / 6", // external
      8: "2 / 5 / 3 / 6", // hopes/fears
      9: "3 / 5 / 4 / 6", // outcome
    };

    state.slots.forEach((s) => {
      const el = renderSlotCard(s);
      el.style.gridArea = area[s.slot_index] || "auto";
      if (s.slot_index === 1) {
        el.style.transform = "rotate(90deg)";
        el.style.transformOrigin = "center";
      }
      wrap.appendChild(el);
    });

    board.appendChild(wrap);
  }

  $("btnUndo").disabled = state.slots.filter(s => s.card_id).length === 0;
  $("btnReading").disabled = state.slots.some(s => !s.card_id);
}

function renderSlotCard(slot) {
  const box = document.createElement("div");
  box.className = "glass-card bg-zinc-950/40 border border-zinc-700/50 rounded-2xl p-4 flex flex-col gap-3 min-h-[160px] relative overflow-hidden transition-all duration-300 hover:border-zinc-600 hover:shadow-xl hover:shadow-indigo-500/10";
  box.setAttribute("data-slot-index", slot.slot_index);

  // Add animated background gradient for filled cards
  if (slot.card_id) {
    const bgGradient = document.createElement("div");
    bgGradient.className = "absolute inset-0 bg-gradient-to-br from-indigo-500/5 via-purple-500/5 to-cyan-500/5 opacity-0 transition-opacity duration-500";
    bgGradient.style.opacity = "0.3";
    box.appendChild(bgGradient);
  }

  const top = document.createElement("div");
  top.className = "flex items-center justify-between gap-2 relative z-10";
  const label = document.createElement("div");
  label.className = "text-xs font-bold text-zinc-300 uppercase tracking-wider";
  label.textContent = `${slot.slot_label}`;
  const badge = document.createElement("div");
  badge.className = `text-[10px] px-2 py-1 rounded-full border font-bold transition-all duration-300 ${
    slot.reversed 
      ? "bg-red-500/20 border-red-500/50 text-red-300 shadow-red-500/25 shadow-sm" 
      : "bg-emerald-500/20 border-emerald-500/50 text-emerald-300 shadow-emerald-500/25 shadow-sm"
  }`;
  badge.textContent = slot.reversed ? "REVERSED" : "UPRIGHT";
  top.appendChild(label);
  top.appendChild(badge);

  const mid = document.createElement("div");
  mid.className = "flex-1 flex items-center justify-center relative z-10";

  if (slot.card_id) {
    const cardContainer = document.createElement("div");
    cardContainer.className = "relative group";
    
    const img = document.createElement("img");
    img.src = slot.revealed ? cardImgUrl(slot.card_id) : '/deck-assets/cards/back.png';
    img.alt = slot.card_id;
    img.className = "w-28 h-auto rounded-xl border-2 border-zinc-700/50 shadow-lg transition-all duration-300";
    if (slot.revealed && slot.reversed) {
      img.style.transform = "rotate(180deg)";
      img.classList.add("group-hover:rotate-[186deg]");
    } else if (slot.revealed) {
      img.classList.add("group-hover:rotate-[-6deg]");
    }
    
    // Add glow effect for cards
    const glow = document.createElement("div");
    glow.className = "absolute inset-0 rounded-xl bg-gradient-to-t from-indigo-500/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none";
    
    cardContainer.appendChild(glow);
    cardContainer.appendChild(img);
    mid.appendChild(cardContainer);
  } else {
    const empty = document.createElement("div");
    empty.className = "glass-soft border-2 border-dashed border-zinc-700/50 rounded-xl p-8 text-center transition-all duration-300 hover:border-zinc-600/50 hover:bg-zinc-800/30";
    empty.innerHTML = `
      <div class="text-zinc-500 text-sm font-medium">Empty Slot</div>
      <div class="text-zinc-600 text-xs mt-1">Click to add card</div>
    `;
    mid.appendChild(empty);
  }

  const name = document.createElement("div");
  name.className = "text-sm font-bold text-zinc-200 relative z-10";
  name.textContent = slot.card_id ? cardName(slot.card_id) : "—";

  const meaning = document.createElement("div");
  meaning.className = "text-xs text-zinc-400/90 leading-relaxed relative z-10 max-h-12 overflow-y-auto";
  meaning.textContent = slot.card_id ? (cardMeaningText(slot.card_id, slot.reversed) || "") : "";

  // Add clarify button if card is placed
  if (slot.card_id) {
    const clarifyBtn = document.createElement("button");
    clarifyBtn.className = "btn clarifyBtn glass-soft border border-zinc-700/50 hover:border-indigo-500/50 hover:bg-indigo-500/10 rounded-xl px-4 py-2 text-sm font-medium transition-all duration-300 hover:scale-105 relative z-10";
    clarifyBtn.innerHTML = `<span class="mr-1">🔍</span> Clarify`;
    clarifyBtn.setAttribute("data-slot-index", slot.slot_index);
    box.appendChild(clarifyBtn);
  }

  box.appendChild(top);
  box.appendChild(mid);
  box.appendChild(name);
  box.appendChild(meaning);

  // Enhanced click interactions
  box.addEventListener("click", (e) => {
    if (!slot.card_id) return;
    if (e.target.closest(".clarifyBtn")) return;
    
    // Add haptic feedback
    vibrate(50);
    
    // Toggle reversed with animation
    slot.reversed = !slot.reversed;
    
    // Add pulse effect
    box.style.transform = "scale(0.95)";
    setTimeout(() => {
      box.style.transform = "scale(1)";
      renderBoard();
    }, 100);
  });

  // Add hover sound effect (optional)
  box.addEventListener("mouseenter", () => {
    if (slot.card_id) {
      vibrate(10);
    }
  });

  return box;
}

async function loadDeck() {
  const r = await fetch("/deck42/cards");
  if (!r.ok) throw new Error("Failed to load deck42 cards");
  const j = await r.json();
  const cards = j.cards || [];
  state.deck = { cards };
  state.assetByCardId = {};
  state.cardById = {};
  cards.forEach((c, idx) => {
    const assetId = `t42_${String(idx + 1).padStart(2, "0")}`;
    state.assetByCardId[c.id] = assetId;
    state.cardById[c.id] = c;
  });
}

async function loadOverlays() {
  const r = await fetch("/deck42/overlays");
  if (!r.ok) throw new Error("Failed to load overlays");
  const j = await r.json();
  state.overlays = j.overlays || [];
  state.overlayById = {};
  state.overlays.forEach(o => { state.overlayById[o.id] = o; });
  if (!state.overlayById[state.overlayId] && state.overlays.length) {
    state.overlayId = state.overlays[0].id;
  }

  const sel = $("overlaySelect");
  if (sel) {
    sel.innerHTML = state.overlays.map(o => `<option value="${o.id}">Overlay: ${escapeHtml(o.name)}</option>`).join("");
    sel.value = state.overlayId;
    sel.addEventListener("change", () => {
      state.overlayId = sel.value;
      localStorage.setItem("tarot42_overlay", state.overlayId);
      renderOverlayInfo();
    });
  }
  renderOverlayInfo();
}

async function startCamera() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ 
      video: { 
        facingMode: 'environment',
        width: { ideal: 1280 },
        height: { ideal: 720 }
      } 
    });
    const video = $("video");
    video.srcObject = stream;
    state.stream = stream;
    state.isRunning = true;
    
    // Update camera status
    const statusEl = $("cameraStatus");
    if (statusEl) {
      statusEl.textContent = "📷 Ready";
      statusEl.classList.add("text-green-400");
      statusEl.classList.remove("text-zinc-500");
    }
    
    setStatus("📷 Camera ready - align card with guide");
  } catch (err) {
    console.error("Camera error:", err);
    setStatus("❌ Camera error: " + err.message);
    
    // Update camera status
    const statusEl = $("cameraStatus");
    if (statusEl) {
      statusEl.textContent = "❌ Error";
      statusEl.classList.add("text-red-400");
      statusEl.classList.remove("text-zinc-500");
    }
  }
}

function stopCamera() {
  if (state.stream) {
    state.stream.getTracks().forEach(track => track.stop());
    const video = $("video");
    video.srcObject = null;
    state.stream = null;
    state.isRunning = false;
    
    // Update camera status
    const statusEl = $("cameraStatus");
    if (statusEl) {
      statusEl.textContent = "Camera off";
      statusEl.classList.remove("text-green-400", "text-red-400");
      statusEl.classList.add("text-zinc-500");
    }
  }
}

async function scanOnce() {
  const video = $("video");
  const canvas = $("canvas");
  const w = video.videoWidth || 1280;
  const h = video.videoHeight || 720;

  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, 0, 0, w, h);

  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.90));
  if (!blob) throw new Error("Failed to capture image");

  // Add scanning animation
  setStatus("🔍 Scanning sigil...");
  const scanOverlay = document.createElement("div");
  scanOverlay.className = "fixed inset-0 bg-white/10 backdrop-blur-sm z-50 pointer-events-none";
  scanOverlay.innerHTML = `
    <div class="flex items-center justify-center h-full">
      <div class="text-center">
        <div class="inline-block animate-spin rounded-full h-12 w-12 border-4 border-indigo-500 border-t-transparent mb-4"></div>
        <div class="text-white font-medium">Analyzing sigil pattern...</div>
      </div>
    </div>
  `;
  document.body.appendChild(scanOverlay);

  try {
    const fd = new FormData();
    fd.append("image", blob, "frame.jpg");
    const r = await fetch("/scan", { method: "POST", body: fd });
    const j = await r.json();

    if (!j.ok) {
      setLastScan(`❌ No match (matches=${j.matches}, conf=${j.confidence.toFixed(2)})`);
      setStatus("No match — try again");
      return null;
    }

    const cardId = j.card_id;
    
    // Handle clarifier scan vs normal scan
    if (state.clarifyTarget !== null) {
      // This is a clarifier scan
      await handleClarifierScan(cardId, state.clarifyTarget.slotIndex);
    } else {
      // Normal scan - place card in first empty slot
      const i = state.slots.findIndex(s => !s.card_id);
      if (i === -1) {
        setStatus("⚠️ Spread is full — clear a slot first");
        return null;
      }
      placeCard(cardId, i, j.confidence);
    }

    setLastScan(`✅ ${cardId} • conf=${j.confidence.toFixed(2)} • matches=${j.matches}`);
    setStatus("🎯 Matched!");
    
    // Add success pulse effect
    if (!state.clarifyTarget) {
      const newlyAddedCard = document.querySelector(`[data-slot-index="${i}"]`);
      if (newlyAddedCard) {
        newlyAddedCard.classList.add("newly-added");
        setTimeout(() => newlyAddedCard.classList.remove("newly-added"), 1500);
      }
    }
    
    return cardId;
  } finally {
    // Remove scanning overlay
    document.body.removeChild(scanOverlay);
  }
}

function placeCard(card_id, slotIndex = null, confidence = 0) {
  if (slotIndex === null) {
    slotIndex = nextEmptySlotIndex();
  }
  if (slotIndex === -1) {
    setStatus("⚠️ Spread full");
    return;
  }
  state.slots[slotIndex].card_id = card_id;
  state.slots[slotIndex].reversed = false;
  state.slots[slotIndex].revealed = true;
  renderBoard();
  
  // Add haptic feedback based on confidence
  if (confidence > 0.8) {
    vibrate(100); // Strong vibration for high confidence
  } else if (confidence > 0.6) {
    vibrate(50);  // Medium vibration
  } else {
    vibrate(25);  // Light vibration for low confidence
  }
}

function undoLast() {
  for (let i = state.slots.length - 1; i >= 0; i--) {
    if (state.slots[i].card_id) {
      state.slots[i].card_id = null;
      state.slots[i].reversed = false;
      break;
    }
  }
  $("readingPanel").classList.add("hidden");
  renderBoard();
}

async function generateReading() {
  // Check if all slots are filled
  const emptySlots = state.slots.filter(s => !s.card_id);
  if (emptySlots.length > 0) {
    setStatus(`⚠️ Fill all slots first (${emptySlots.length} empty)`);
    return;
  }

  setStatus("🔮 Generating reading...");
  
  try {
    const payload = {
      spread_type: state.spreadType,
      style: getStyle(),
      question: null,
      overlay_id: state.overlayId,
      placements: state.slots.map(s => ({
        slot_index: s.slot_index,
        slot_label: s.slot_label,
        card_id: s.card_id,
        reversed: s.reversed
      }))
    };
    
    const r = await fetch("/reading", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    
    if (!r.ok) {
      const errorText = await r.text();
      throw new Error(`Reading failed: ${r.status} - ${errorText}`);
    }
    
    const j = await r.json();
    state.sessionId = j.session_id;
  
    // Store reading data for voice playback and chat context
    state.currentReading = j;
    state.readingContext = {
      overlay: state.overlayId,
      cards: state.slots.filter(s => s.card_id).map(s => ({
        id: s.card_id,
        reversed: s.reversed
      }))
    };

    // Set reading summary chip
    const firstCardSlot = state.slots.find(s => s.card_id);
    if (firstCardSlot) {
      const card = cardName(firstCardSlot.card_id);
      const reversed = firstCardSlot.reversed ? ' (Reversed)' : '';
      const mode = state.readingMode;
      const overlay = state.overlayById[state.overlayId]?.name || '';
      const gist = j.summary ? j.summary.split(' ').slice(0, 8).join(' ') + '...' : '';
      const chipText = `${card}${reversed} (${mode}) + ${overlay} → ${gist}`;
      $('readingSummaryChip').textContent = chipText;
      $('readingSummaryChip').classList.remove('hidden');
    }

    $("readingSummary").textContent = j.summary || "";
    const notes = $("readingNotes");
    notes.innerHTML = "";
    (j.card_notes || []).forEach(n => {
      const div = document.createElement("div");
      div.className = "glass-panel rounded-xl p-4 border border-zinc-700/50";
      div.innerHTML = `
        <div class="text-xs font-bold text-purple-400 uppercase tracking-wider mb-2">${n.slot_label}</div>
        <div class="text-base font-semibold text-zinc-100 mb-2">${cardName(n.card_id)}</div>
        <div class="text-sm text-zinc-200 leading-relaxed mb-2">${escapeHtml(n.note || "")}</div>
        <div class="text-xs text-zinc-500 font-mono">${n.card_id}</div>
      `;
      notes.appendChild(div);
    });

    // Display additional structured data if available
    if (j.theme || j.energy || j.synthesis) {
      const insightsContainer = $("readingInsights");
      const insightsContent = $("insightsContent");
      
      if (insightsContainer && insightsContent) {
        insightsContainer.style.display = "block";
        let insightsHtml = "";
        
        if (j.theme) {
          insightsHtml += `<div class="text-sm"><span class="text-xs font-semibold text-purple-400">Theme:</span> <span class="text-zinc-200">${escapeHtml(j.theme)}</span></div>`;
        }
        
        if (j.energy) {
          insightsHtml += `<div class="text-sm mt-2"><span class="text-xs font-semibold text-purple-400">Energy:</span> <span class="text-zinc-200">${escapeHtml(j.energy)}</span></div>`;
        }
        
        if (j.synthesis) {
          insightsHtml += `<div class="text-sm mt-2"><span class="text-xs font-semibold text-purple-400">Synthesis:</span> <span class="text-zinc-200">${escapeHtml(j.synthesis)}</span></div>`;
        }
        
        if (j.reflection_prompt) {
          insightsHtml += `<div class="text-sm mt-2"><span class="text-xs font-semibold text-purple-400">Reflection:</span> <span class="text-zinc-200">${escapeHtml(j.reflection_prompt)}</span></div>`;
        }
        
        insightsContent.innerHTML = insightsHtml;
        notes.appendChild(insightsContainer);
      }
    }

    $("chatLog").innerHTML = "";
    $("readingPanel").classList.remove("hidden");
    setStatus("✨ Reading ready");
    updateVoiceUI();
    updateStepRail('reading');
    setChatState('half');
  } catch (error) {
    console.error("Generate reading error:", error);
    setStatus(`❌ Error: ${error.message}`);
  }
}

function updateStepRail(step) {
  const steps = ['mode', 'acquire', 'reading', 'chat'];
  steps.forEach(s => {
    const el = $(`step${s.charAt(0).toUpperCase() + s.slice(1)}`);
    if (el) el.classList.remove('step-active');
  });
  const currentEl = $(`step${step.charAt(0).toUpperCase() + step.slice(1)}`);
  if (currentEl) currentEl.classList.add('step-active');
}

function setChatState(newState) {
  const panel = $('chatPanel');
  if (!panel) return;
  panel.classList.remove('collapsed', 'half', 'expanded', 'open');
  state.chatState = newState;
  if (window.innerWidth >= 1024) {
    // Desktop: right drawer
    if (newState !== 'collapsed') {
      panel.classList.add('open');
    }
  } else {
    // Mobile: bottom sheet
    panel.classList.add(newState);
  }
}

function appendChat(role, text) {
  const log = $("chatMessages");
  if (!log) return;
  const row = document.createElement("div");
  const base = "border border-zinc-800 rounded-xl p-3 text-sm relative";
  row.className = role === "user"
    ? `${base} bg-indigo-950/40`
    : `${base} bg-zinc-950/60`;
  
  // Add voice indicator for assistant messages
  const voiceIndicator = role === "assistant" ? `
    <div class="absolute top-2 right-2 text-xs text-purple-400 opacity-60 voice-indicator">
      🔊
    </div>
  ` : '';
  
  row.innerHTML = `
    ${voiceIndicator}
    <div class="text-xs text-zinc-400">${role}</div>
    <div class="mt-1 whitespace-pre-wrap">${escapeHtml(text)}</div>
  `;
  log.appendChild(row);

  // Auto-scroll logic
  const isAtBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 80; // 80px threshold
  if (isAtBottom || role === "user") { // Always scroll for user messages
    log.scrollTop = log.scrollHeight;
    $('jumpToLatest').classList.add('hidden');
  } else {
    $('jumpToLatest').classList.remove('hidden');
  }
}

async function sendChat() {
  const msg = $("chatInput").value.trim();
  if (!msg) return;
  if (!state.sessionId && !state.readingContext) return;
  
  // Prevent duplicate sends
  if (state.chatInflight) return;
  state.chatInflight = true;

  // Mark as chatted
  if (!state.hasChatted) {
    updateStepRail('chat');
    state.hasChatted = true;
  }

  $("chatInput").value = "";
  appendChat("user", msg);

  setStatus("🤔 Thinking...");
  
  try {
    let response;
    
    // Use new reading/ask endpoint if we have reading context
    if (state.readingContext && state.currentReadingId) {
      response = await fetch("/reading/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reading_id: state.currentReadingId,
          reading: state.readingContext,
          message: msg
        })
      });
    } else {
      // Fallback to old chat endpoint for backward compatibility
      response = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          session_id: state.sessionId, 
          message: msg, 
          style: getStyle() 
        })
      });
    }
    
    const j = await response.json();
    
    // Handle different response formats
    const reply = j.answer || j.reply || "";
    appendChat("assistant", reply);
    setStatus("✨ Ready");
    
    // Auto-speak the assistant's reply if enabled
    if (state.autoSpeakChat && reply.trim()) {
      try {
        await speakText(reply.trim());
      } catch (error) {
        console.error("Chat voice synthesis failed:", error);
        // Don't show error to user, just log it
      }
    }
    
    // Optionally display used cards for verification
    if (j.used_cards && j.used_cards.length > 0) {
      console.log("Used cards in response:", j.used_cards);
      // Could add UI element to show this if needed
    }
    
  } catch (error) {
    console.error("Chat error:", error);
    setStatus("❌ Chat failed");
    appendChat("assistant", "Sorry, I encountered an error processing your question. Please try again.");
  } finally {
    state.chatInflight = false;
  }
}

function setClarifyTarget(slotIndex) {
  state.clarifyTarget = { slotIndex };
  // Clear previous highlights
  document.querySelectorAll(".card--clarify-target").forEach(el => el.classList.remove("card--clarify-target"));

  const tile = document.querySelector(`[data-slot-index="${slotIndex}"]`);
  if (tile) tile.classList.add("card--clarify-target");

  setClarifyOverlay(true);
  vibrate(20);
}

function animateClarifier(el) {
  if (!el) return;
  el.classList.add("enter");
  vibrate(12);
  setTimeout(() => el.classList.remove("enter"), 400);
}

async function handleClarifierScan(clarifierCardId, originalSlotIndex) {
  // Call backend for clarifier reading
  const res = await fetch("/clarify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      original_card_id: state.slots[originalSlotIndex].card_id,
      original_position: state.slots[originalSlotIndex].slot_label,
      clarifier_card_id: clarifierCardId,
      spread: state.spreadType,
      session_id: state.sessionId
    })
  });

  if (!res.ok) {
    setStatus("Clarifier reading failed");
    return;
  }

  const data = await res.json();
  
  // Render clarifier card under original
  const originalTile = document.querySelector(`[data-slot-index="${originalSlotIndex}"]`);
  if (!originalTile) return;

  // Create clarifier element
  const clarifierEl = document.createElement("div");
  clarifierEl.className = "clarifier-card bg-zinc-900/60 border border-zinc-800 rounded-xl p-3 mt-2";
  clarifierEl.innerHTML = `
    <div class="text-xs text-zinc-400 mb-1">Clarifier</div>
    <div class="flex items-center gap-2">
      <img src="${cardImgUrl(clarifierCardId)}" alt="${clarifierCardId}" class="w-16 h-auto rounded-lg border border-zinc-800" />
      <div>
        <div class="text-sm font-medium">${cardName(clarifierCardId)}</div>
        <div class="text-xs text-zinc-400 mt-1">${data.interpretation || "Processing..."}</div>
      </div>
    </div>
  `;

  // Add connector
  const connector = document.createElement("div");
  connector.className = "clarifier-connector";

  // Insert after original tile
  originalTile.parentNode.insertBefore(connector, originalTile.nextSibling);
  originalTile.parentNode.insertBefore(clarifierEl, connector.nextSibling);

  // Animate in
  animateClarifier(clarifierEl);

  // Clear overlay and highlights
  setClarifyOverlay(false);
  document.querySelectorAll(".card--clarify-target").forEach(el => el.classList.remove("card--clarify-target"));
  state.clarifyTarget = null;

  setStatus("Clarifier added");
}

async function newReading() {
  $("readingPanel").classList.add("hidden");
  state.sessionId = null;
  state.readingId = null;
  state.currentReadingId = generateReadingId();
  state.readingMode = $("modeSelect").value;
  state.spreadType = $("spreadSelect").value;
  state.slots = spreadTemplate(state.spreadType);
  renderBoard();
  
  // Clear chat history for new reading
  const chatLog = $("chatLog");
  if (chatLog) chatLog.innerHTML = "";
  
  // Reset chat flag
  state.hasChatted = false;
  
  // Use FlowState for mode switching
  FlowState.setMode(state.readingMode);
  FlowState.setStep('acquire');
  
  // Trigger digital shuffle if in digital mode
  if (state.readingMode === "digital") {
    await performDigitalShuffle();
  }
  
  updateStepRail('acquire');
  setChatState('collapsed');
}

function showDigitalShuffleButton() {
  const widget = $('digitalWidget');
  if (widget) {
    widget.classList.remove('hidden');
  }
}

function hideDigitalShuffleButton() {
  const widget = $('digitalWidget');
  if (widget) {
    widget.classList.add('hidden');
  }
}

async function performDigitalShuffle() {
  try {
    setStatus("Starting digital reading...");
    
    // Start reading
    const startResponse = await fetch("/reading/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: "digital",
        spread_id: state.spreadType
      })
    });
    
    if (!startResponse.ok) throw new Error("Failed to start reading");
    const startData = await startResponse.json();
    state.readingId = startData.reading_id;
    
    setStatus("Shuffling and drawing cards...");
    
    // Draw cards
    const count = state.slots.length;
    const slots = state.slots.map(s => s.slot_label);
    
    const drawResponse = await fetch("/reading/draw", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reading_id: state.readingId,
        count: count,
        allow_reversed: true,
        slots: slots
      })
    });
    
    if (!drawResponse.ok) throw new Error("Failed to draw cards");
    const drawData = await drawResponse.json();
    
    // Update slots with drawn cards
    drawData.positions.forEach((pos, index) => {
      if (state.slots[index]) {
        state.slots[index].card_id = pos.card_id;
        state.slots[index].reversed = pos.reversed;
      }
    });
    
    // Store reading context for chat
    state.readingContext = {
      overlay: state.overlayId,
      cards: state.slots.filter(s => s.card_id).map(s => ({
        id: s.card_id,
        reversed: s.reversed
      }))
    };
    
    renderBoard();
    setStatus("Cards drawn successfully");
    
    // Auto-generate reading after a short delay
    setTimeout(() => generateReading(), 1000);
    
  } catch (error) {
    console.error("Digital shuffle error:", error);
    setStatus("Error: " + error.message);
  }
}

// Voice synthesis functions
async function synthesizeSpeech(text, voice = null) {
  try {
    const selectedVoice = voice || state.currentVoice;
    const response = await fetch("/voice/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice: selectedVoice })
    });
    
    if (!response.ok) {
      throw new Error(`Voice synthesis failed: ${response.statusText}`);
    }
    
    const data = await response.json();
    return data.audio_base64;
  } catch (error) {
    console.error("Voice synthesis error:", error);
    return null;
  }
}

function playAudioFromBase64(base64Audio) {
  return new Promise((resolve, reject) => {
    try {
      // Convert base64 to binary
      const binaryString = atob(base64Audio);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      
      // Create blob and play
      const blob = new Blob([bytes], { type: "audio/mp3" });
      const audioUrl = URL.createObjectURL(blob);
      const audio = new Audio(audioUrl);
      
      audio.onended = () => {
        URL.revokeObjectURL(audioUrl);
        state.isPlaying = false;
        resolve();
      };
      
      audio.onerror = () => {
        URL.revokeObjectURL(audioUrl);
        state.isPlaying = false;
        reject(new Error("Audio playback failed"));
      };
      
      state.isPlaying = true;
      audio.play().catch(reject);
    } catch (error) {
      reject(error);
    }
  });
}

async function speakText(text, voice = null) {
  if (!text || state.isPlaying) return;
  
  // Show voice indicator on most recent assistant message
  const indicators = document.querySelectorAll(".voice-indicator");
  const latestIndicator = indicators[indicators.length - 1];
  if (latestIndicator) {
    latestIndicator.style.opacity = "1";
    latestIndicator.textContent = "🔊 Speaking...";
  }
  
  try {
    const base64Audio = await synthesizeSpeech(text, voice);
    if (base64Audio) {
      await playAudioFromBase64(base64Audio);
    }
  } finally {
    // Hide voice indicator when done
    if (latestIndicator) {
      latestIndicator.style.opacity = "0.6";
      latestIndicator.textContent = "🔊";
    }
  }
}

async function speakReading(readingData) {
  if (!readingData) return;
  
  // Build comprehensive reading text
  let fullText = "";
  
  if (readingData.summary) {
    fullText += `Summary: ${readingData.summary}\n\n`;
  }
  
  if (readingData.theme) {
    fullText += `Theme: ${readingData.theme}\n\n`;
  }
  
  if (readingData.energy) {
    fullText += `Energy: ${readingData.energy}\n\n`;
  }
  
  if (readingData.card_notes && readingData.card_notes.length > 0) {
    fullText += "Card insights:\n";
    readingData.card_notes.forEach((note, index) => {
      fullText += `${note.slot_label}: ${note.note}\n\n`;
    });
  }
  
  if (readingData.synthesis) {
    fullText += `Synthesis: ${readingData.synthesis}\n\n`;
  }
  
  if (readingData.advice && readingData.advice.length > 0) {
    fullText += "Action steps:\n";
    readingData.advice.forEach(step => {
      fullText += `• ${step}\n`;
    });
  }
  
  if (readingData.reflection_prompt) {
    fullText += `\nReflection: ${readingData.reflection_prompt}`;
  }
  
  await speakText(fullText.trim());
}

async function loadAvailableVoices() {
  try {
    const response = await fetch("/voice/voices");
    if (response.ok) {
      const data = await response.json();
      return data.voices || [];
    }
  } catch (error) {
    console.error("Failed to load voices:", error);
  }
  return [];
}

function updateVoiceUI() {
  const voiceSelect = $("voiceSelect");
  const speakBtn = $("speakBtn");
  const micBtn = $("btnMic");
  const micStatus = $("micStatus");
  const micTimer = $("micTimer");
  
  if (voiceSelect) {
    voiceSelect.value = state.currentVoice;
  }
  
  if (speakBtn) {
    speakBtn.disabled = state.isPlaying;
    speakBtn.textContent = state.isPlaying ? "Speaking..." : "Speak Reading";
  }

  if (micBtn) {
    const busy = state.isPlaying || state.micPhase === "transcribing";
    micBtn.disabled = busy;
    micBtn.textContent = state.micPhase === "recording" ? "Stop" : "Mic";
    micBtn.classList.toggle("bg-red-600", state.micPhase === "recording");
    micBtn.classList.toggle("hover:bg-red-500", state.micPhase === "recording");
    micBtn.classList.toggle("bg-zinc-800", state.micPhase !== "recording");
    micBtn.classList.toggle("hover:bg-zinc-700", state.micPhase !== "recording");
  }

  if (micStatus) {
    micStatus.textContent =
      state.micPhase === "recording" ? "Recording" :
      state.micPhase === "transcribing" ? "Transcribing" :
      "Idle";
  }

  if (micTimer) {
    if (state.micPhase === "recording") {
      const secs = Math.floor((Date.now() - state.micStartedAtMs) / 1000);
      const mm = String(Math.floor(secs / 60)).padStart(2, "0");
      const ss = String(secs % 60).padStart(2, "0");
      micTimer.textContent = `${mm}:${ss}`;
    } else {
      micTimer.textContent = "";
    }
  }
}

// Speech-to-text (mic) functions
function _cleanupMic() {
  try { if (state.micTimerInterval) clearInterval(state.micTimerInterval); } catch (_) {}
  try { if (state.silenceInterval) clearInterval(state.silenceInterval); } catch (_) {}
  state.micTimerInterval = null;
  state.silenceInterval = null;
  state.silenceMs = 0;

  try { if (state.audioCtx) state.audioCtx.close(); } catch (_) {}
  state.audioCtx = null;
  state.analyser = null;

  try { if (state.micStream) state.micStream.getTracks().forEach(t => t.stop()); } catch (_) {}
  state.micStream = null;
  state.mediaRecorder = null;
  state.micChunks = [];
}

async function startMicRecording() {
  if (state.micPhase === "recording") return;
  if (!navigator.mediaDevices || !window.MediaRecorder) {
    setStatus("Mic not supported in this browser");
    return;
  }

  try {
    state.micChunks = [];
    state.micStream = await navigator.mediaDevices.getUserMedia({ audio: true });

    state.micStartedAtMs = Date.now();
    state.micPhase = "recording";
    updateVoiceUI();

    // Timer UI
    state.micTimerInterval = setInterval(() => updateVoiceUI(), 250);

    // Silence detection (auto-stop)
    try {
      state.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const source = state.audioCtx.createMediaStreamSource(state.micStream);
      state.analyser = state.audioCtx.createAnalyser();
      state.analyser.fftSize = 2048;
      source.connect(state.analyser);

      const data = new Uint8Array(state.analyser.fftSize);
      const SILENCE_THRESHOLD = 0.012; // tuned for speech
      const MIN_RECORD_MS = 700;
      const STOP_AFTER_SILENCE_MS = 1200;

      state.silenceInterval = setInterval(() => {
        if (state.micPhase !== "recording" || !state.analyser) return;
        state.analyser.getByteTimeDomainData(data);

        let sum = 0;
        for (let i = 0; i < data.length; i++) {
          const v = (data[i] - 128) / 128;
          sum += v * v;
        }
        const rms = Math.sqrt(sum / data.length);
        const elapsed = Date.now() - state.micStartedAtMs;

        if (rms < SILENCE_THRESHOLD) state.silenceMs += 200;
        else state.silenceMs = 0;

        if (elapsed >= MIN_RECORD_MS && state.silenceMs >= STOP_AFTER_SILENCE_MS) {
          stopMicRecording();
        }
      }, 200);
    } catch (_) {
      // If silence detection fails, recording still works.
    }

    const mr = new MediaRecorder(state.micStream, { mimeType: "audio/webm" });
    state.mediaRecorder = mr;

    mr.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) state.micChunks.push(e.data);
    };

    mr.onstop = async () => {
      try {
        state.micPhase = "transcribing";
        updateVoiceUI();
        setStatus("Transcribing...");
        const blob = new Blob(state.micChunks, { type: "audio/webm" });
        await transcribeAndFillChat(blob);
      } catch (e) {
        console.error(e);
        setStatus("Transcription failed");
      } finally {
        _cleanupMic();
        state.micPhase = "idle";
        updateVoiceUI();
      }
    };

    setStatus("Recording...");
    mr.start();
  } catch (e) {
    console.error(e);
    setStatus("Mic permission denied");
    _cleanupMic();
    state.micPhase = "idle";
    updateVoiceUI();
  }
}

function stopMicRecording() {
  if (state.micPhase !== "recording" || !state.mediaRecorder) return;
  try {
    state.mediaRecorder.stop();
  } catch (e) {
    console.error(e);
    _cleanupMic();
    state.micPhase = "idle";
    updateVoiceUI();
  }
}

async function transcribeAndFillChat(audioBlob) {
  const fd = new FormData();
  fd.append("audio", audioBlob, "mic.webm");
  const r = await fetch("/voice/transcribe", { method: "POST", body: fd });
  if (!r.ok) throw new Error("transcribe failed");
  const j = await r.json();
  const text = (j.text || "").trim();
  if (!text) {
    setStatus("No speech detected");
    return;
  }
  const input = $("chatInput");
  input.value = text;
  input.focus();
  setStatus("Transcript ready");
  if (state.autoSend) {
    await sendChat();
  }
}

async function boot() {
  state.overlayId = localStorage.getItem("tarot42_overlay") || "WIND";
  await loadDeck();
  await loadOverlays();
  
  // Load available voices and populate voice select
  const voices = await loadAvailableVoices();
  const voiceSelect = $("voiceSelect");
  if (voiceSelect && voices.length > 0) {
    voiceSelect.innerHTML = voices.map(voice => 
      `<option value="${voice.id}">${voice.name} - ${voice.description}</option>`
    ).join('');
  }
  
  // style persistence
  const savedStyle = localStorage.getItem("tarot42_style") || "seer";
  $("readerStyle").value = savedStyle;
  $("readerStyle").addEventListener("change", () => {
    localStorage.setItem("tarot42_style", $("readerStyle").value);
  });
  
  // Voice persistence and events
  const savedVoice = localStorage.getItem("tarot42_voice") || "nova";
  state.currentVoice = savedVoice;

  // Auto-send persistence
  state.autoSend = (localStorage.getItem("tarot42_autosend") || "0") === "1";
  
  // Auto-speak chat persistence
  state.autoSpeakChat = (localStorage.getItem("tarot42_autospeak_chat") || "1") === "1";
  const autoSendToggle = $("autoSendToggle");
  if (autoSendToggle) {
    autoSendToggle.checked = state.autoSend;
    autoSendToggle.addEventListener("change", () => {
      state.autoSend = !!autoSendToggle.checked;
      localStorage.setItem("tarot42_autosend", state.autoSend ? "1" : "0");
    });
  }
  
  // Auto-speak chat toggle
  const autoSpeakChatToggle = $("autoSpeakChat");
  if (autoSpeakChatToggle) {
    autoSpeakChatToggle.checked = state.autoSpeakChat;
    autoSpeakChatToggle.addEventListener("change", () => {
      state.autoSpeakChat = !!autoSpeakChatToggle.checked;
      localStorage.setItem("tarot42_autospeak_chat", state.autoSpeakChat ? "1" : "0");
    });
  }
  
  if (voiceSelect) {
    voiceSelect.addEventListener("change", () => {
      state.currentVoice = voiceSelect.value;
      localStorage.setItem("tarot42_voice", state.currentVoice);
    });
  }
  
  // Speak button event
  const speakBtn = $("speakBtn");
  if (speakBtn) {
    speakBtn.addEventListener("click", async () => {
      if (state.currentReading && !state.isPlaying) {
        try {
          await speakReading(state.currentReading);
        } catch (error) {
          console.error("Voice playback failed:", error);
          setStatus("Voice playback failed");
        }
      }
    });
  }

  // Mic button (toggle)
  const micBtn = $("btnMic");
  if (micBtn) {
    micBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      if (state.micPhase === "recording") stopMicRecording();
      else await startMicRecording();
    });
  }
  
  $("spreadSelect").addEventListener("change", async () => { await newReading(); });
  $("modeSelect").addEventListener("change", async () => { await newReading(); });
  $("btnNew").addEventListener("click", async () => { await newReading(); });

  // Clarify button event delegation
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".clarifyBtn");
    if (!btn) return;
    const slotIndex = Number(btn.getAttribute("data-slot-index"));
    setClarifyTarget(slotIndex);
  });

  $("btnStart").addEventListener("click", async () => {
    if (!state.stream) {
      await startCamera();
      $("btnScan").disabled = false;
      setStatus("📷 Camera ready - align card with guide");
      $("btnStartText").textContent = "Stop";
      $("btnStart").classList.remove("bg-zinc-800", "hover:bg-zinc-700");
      $("btnStart").classList.add("bg-red-600", "hover:bg-red-700");
    } else {
      stopCamera();
      $("btnScan").disabled = true;
      setStatus("📷 Camera stopped");
      $("btnStartText").textContent = "Start";
      $("btnStart").classList.remove("bg-red-600", "hover:bg-red-700");
      $("btnStart").classList.add("bg-zinc-800", "hover:bg-zinc-700");
    }
  });

  $("btnScan").addEventListener("click", async () => {
    try {
      const reversed = $("reversedToggle").checked;
      const card_id = await scanOnce();
      if (!card_id) return;
      placeCard(card_id, reversed);
      setStatus("Placed");
    } catch (e) {
      console.error(e);
      setStatus("Scan error");
    }
  });
}

// Mic button (toggle)
const micBtn = $("btnMic");
if (micBtn) {
  micBtn.addEventListener("click", async (e) => {
    e.preventDefault();
    if (state.micPhase === "recording") stopMicRecording();
    else await startMicRecording();
  });
}

$("btnUndo").addEventListener("click", () => undoLast());
$("btnReading").addEventListener("click", async () => {
  try { 
    await generateReading(); 
  } catch (e) { 
    console.error("Generate reading button error:", e);
    setStatus(`❌ Reading failed: ${e.message}`);
  }
});
$("btnChat").addEventListener("click", () => sendChat());
$("chatInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") debouncedSendChat();
});

// Camera event listeners
$("btnStart").addEventListener("click", async () => {
  if (!state.stream) {
    await startCamera();
    $("btnScan").disabled = false;
    setStatus("📷 Camera ready - align card with guide");
    $("btnStartText").textContent = "Stop";
    $("btnStart").classList.remove("bg-zinc-800", "hover:bg-zinc-700");
    $("btnStart").classList.add("bg-red-600", "hover:bg-red-700");
  } else {
    stopCamera();
    $("btnScan").disabled = true;
    setStatus("📷 Camera stopped");
    $("btnStartText").textContent = "Start";
    $("btnStart").classList.remove("bg-red-600", "hover:bg-red-700");
    $("btnStart").classList.add("bg-zinc-800", "hover:bg-zinc-700");
  }
});

$("btnScan").addEventListener("click", async () => {
  try {
    const reversed = $("reversedToggle").checked;
    const card_id = await scanOnce();
    if (!card_id) return;
    placeCard(card_id, reversed);
    setStatus("Placed");
  } catch (e) {
    console.error(e);
    setStatus("Scan error");
  }
});

// New event listeners
if ($('btnShuffle')) $('btnShuffle').addEventListener('click', () => performDigitalShuffle());
if ($('btnDraw1')) $('btnDraw1').addEventListener('click', () => performDigitalShuffle(1));
if ($('btnDraw3')) $('btnDraw3').addEventListener('click', () => performDigitalShuffle(3));
if ($('btnDraw7')) $('btnDraw7').addEventListener('click', () => performDigitalShuffle(7));

if ($('btnChatCollapse')) $('btnChatCollapse').addEventListener('click', () => setChatState('collapsed'));
if ($('btnChatHalf')) $('btnChatHalf').addEventListener('click', () => setChatState('half'));
if ($('btnChatExpand')) $('btnChatExpand').addEventListener('click', () => setChatState('expanded'));

if ($('btnSummarize')) $('btnSummarize').addEventListener('click', () => {
  $('chatInput').value = '/summarize';
  sendChat();
});
if ($('btnClearChat')) $('btnClearChat').addEventListener('click', () => {
  $('chatMessages').innerHTML = '';
});

if ($('jumpToLatest')) $('jumpToLatest').addEventListener('click', () => {
  const log = $('chatMessages');
  log.scrollTop = log.scrollHeight;
  $('jumpToLatest').classList.add('hidden');
});

if ($('chatMessages')) $('chatMessages').addEventListener('scroll', () => {
  const log = $('chatMessages');
  const isAtBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 80;
  if (isAtBottom) {
    $('jumpToLatest').classList.add('hidden');
  }
});

// Initial load check
document.addEventListener('DOMContentLoaded', function() {
  // Set up mode change listener using FlowState
  const modeSelect = $('modeSelect');
  if (modeSelect) {
    modeSelect.addEventListener('change', function(e) {
      FlowState.setMode(e.target.value);
      newReading();
    });
  }
  
  // Initialize FlowState with current mode
  const currentMode = modeSelect ? modeSelect.value : 'physical';
  FlowState.setMode(currentMode);
  FlowState.setStep('modeSelect');
});

newReading();
setStatus("Idle");

boot().catch((e) => {
  console.error(e);
  setStatus("Boot error");
});
