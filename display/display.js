const WS_URL = "ws://127.0.0.1:8765";
const RECONNECT_DELAY = 2000;

let socket = null;
let isConnecting = false;

const container = document.getElementById("container");
const verseText = document.getElementById("verse-text");
const verseRef = document.getElementById("verse-ref");
const verseRefText = document.getElementById("verse-ref-text");
const verseRefTranslation = document.getElementById("verse-ref-translation");

function connect() {
    if (isConnecting || (socket && socket.readyState === WebSocket.OPEN)) return;
    
    isConnecting = true;
    console.log("Attempting WebSocket connection...");
    
    socket = new WebSocket(WS_URL);
    
    socket.onopen = () => {
        console.log("WebSocket connected.");
        isConnecting = false;
    };
    
    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handlePayload(data);
        } catch (e) {
            console.error("Failed to parse WebSocket message:", e);
        }
    };
    
    socket.onclose = () => {
        console.log("WebSocket disconnected. Reconnecting in 2 seconds...");
        isConnecting = false;
        socket = null;
        setTimeout(connect, RECONNECT_DELAY);
    };
    
    socket.onerror = (err) => {
        console.error("WebSocket error observed:", err);
        socket.close();
    };
}

function applyTheme(theme) {
    if (!theme) return;
    const root = document.documentElement;
    const c = theme.container || {};
    const t = theme.text || {};
    const r = theme.reference || {};
    const tr = theme.translation || {};

    // Container
    if (c.background)   root.style.setProperty("--rc-container-bg", c.background);
    if (c.border)       root.style.setProperty("--rc-container-border", c.border);
    if (c.border_radius) root.style.setProperty("--rc-border-radius", c.border_radius);
    if (c.box_shadow)   root.style.setProperty("--rc-container-shadow", c.box_shadow);
    if (c.backdrop_filter) root.style.setProperty("--rc-backdrop-filter", c.backdrop_filter);
    if (c.padding)      root.style.setProperty("--rc-padding", c.padding);
    if (c.max_width)    root.style.setProperty("--rc-max-width", c.max_width);
    if (c.min_width)    root.style.setProperty("--rc-min-width", c.min_width);

    // Text
    if (t.color)        root.style.setProperty("--rc-text-color", t.color);
    if (t.size)         root.style.setProperty("--rc-text-size", t.size);
    if (t.weight)       root.style.setProperty("--rc-text-weight", t.weight);
    if (t.line_height)  root.style.setProperty("--rc-text-line-height", t.line_height);
    if (t.text_shadow)  root.style.setProperty("--rc-text-shadow", t.text_shadow);
    if (t.letter_spacing) root.style.setProperty("--rc-text-letter-spacing", t.letter_spacing);
    if (t.margin_bottom) root.style.setProperty("--rc-text-margin-bottom", t.margin_bottom);

    // Reference
    if (r.color)        root.style.setProperty("--rc-ref-color", r.color);
    if (r.size)         root.style.setProperty("--rc-ref-size", r.size);
    if (r.weight)       root.style.setProperty("--rc-ref-weight", r.weight);
    if (r.text_transform) root.style.setProperty("--rc-ref-text-transform", r.text_transform);
    if (r.letter_spacing) root.style.setProperty("--rc-ref-letter-spacing", r.letter_spacing);

    // Translation
    if (tr.color)       root.style.setProperty("--rc-translation-color", tr.color);
    if (tr.margin_left) root.style.setProperty("--rc-translation-margin-left", tr.margin_left);
}

function handlePayload(data) {
    if (data.action === "clear") {
        container.classList.add("hidden");
        return;
    }
    
    if (data.action === "display") {
        // Update scripture text
        if (data.text) {
            verseText.innerHTML = data.text;
        }
        
        // Update reference and translation as separate elements
        if (data.reference) {
            verseRefText.innerHTML = data.reference;
        } else if (data.book && data.chapter && data.verse) {
            verseRefText.innerHTML = `${data.book} ${data.chapter}:${data.verse}`;
        }
        
        if (data.translation) {
            verseRefTranslation.innerHTML = data.translation;
        }
        
        // Legacy: if only ref is provided (no reference/translation), parse it
        if (!data.reference && !data.translation && data.ref) {
            const match = data.ref.match(/^\[([^\]]+)\]\s*(.+)$/);
            if (match) {
                verseRefTranslation.innerHTML = match[1];
                verseRefText.innerHTML = match[2];
            } else {
                verseRefText.innerHTML = data.ref;
            }
        }
        
        // Apply theme (full theme dict or just name for CSS class fallback)
        if (data.theme_data) {
            applyTheme(data.theme_data);
            document.body.className = "";
        } else if (data.theme) {
            document.body.className = `theme-${data.theme}`;
        }
        
        // Show
        container.classList.remove("hidden");
    }
}

// Initialize connection
connect();
