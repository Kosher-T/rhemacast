const WS_URL = "ws://127.0.0.1:8765";
const RECONNECT_DELAY = 2000;

let socket = null;
let isConnecting = false;

const container = document.getElementById("container");
const verseText = document.getElementById("verse-text");
const verseRef = document.getElementById("verse-ref");

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

function handlePayload(data) {
    if (data.action === "clear") {
        container.classList.add("hidden");
        return;
    }
    
    if (data.action === "display") {
        // Update text
        if (data.text) {
            verseText.innerHTML = data.text; // Note: Payload is pre-sanitized in Python
        }
        
        // Update ref
        if (data.ref) {
            verseRef.innerHTML = data.ref;
        } else if (data.translation && data.book) {
            verseRef.innerHTML = `[${data.translation}] ${data.book} ${data.chapter}:${data.verse}`;
        }
        
        // Update Theme
        if (data.theme) {
            document.body.className = `theme-${data.theme}`;
        } else {
            document.body.className = "theme-default";
        }
        
        // Show
        container.classList.remove("hidden");
    }
}

// Initialize connection
connect();
