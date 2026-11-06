import { HandTracker } from "./hand-tracker.js";
import { CONFIG, PointSmoother, PinchDetector, mapToViewport } from "./gesture.js";

const uiContainer = document.querySelector("#ui");
const pageContent = document.querySelector(".page-content");
const box = document.querySelector(".box");
const cursor = document.querySelector("#cursor_master");
const buttons = document.querySelectorAll(".tool-bar button");
const demosSection = document.getElementById("demos");
const video = document.getElementById("webcam");
const canvasElement = document.getElementById("output_canvas");
const canvasCtx = canvasElement.getContext("2d");
const webcamButton = document.getElementById("webcamButton");

const pages = [
    { html: page_1, background: "#fcb8b8" },
    { html: page_2, background: "#c2ffb3" },
    { html: page_3, background: "white" },
];
buttons.forEach((btn, i) => {
    btn.addEventListener("click", () => {
        pageContent.innerHTML = pages[i].html;
        uiContainer.style.background = pages[i].background;
    });
});

cursor.style.pointerEvents = "none";
cursor.style.left = "0";
cursor.style.top = "0";
cursor.style.display = "none";

const smoother = new PointSmoother();
const pinch = new PinchDetector();
let hovered = null;
let dragOffset = null;
let cursorPos = { x: 0, y: 0 }; // viewport coordinates of the cursor center

function setHovered(el) {
    if (el === hovered) return;
    hovered?.classList.remove("btn-hovered");
    el?.classList.add("btn-hovered");
    hovered = el;
}

function moveCursor(p) {
    const rect = uiContainer.getBoundingClientRect();
    const x = rect.left + p.x * rect.width;
    const y = rect.top + p.y * rect.height;
    cursorPos = { x, y };
    cursor.style.display = "block";
    cursor.style.transform = `translate(${x - rect.left - cursor.offsetWidth / 2}px, ${y - rect.top - cursor.offsetHeight / 2}px)`;
    if (dragOffset) {
        box.style.left = x - dragOffset.x + "px";
        box.style.top = y - dragOffset.y + "px";
    }
}

function onPinch(event) {
    const { x, y } = cursorPos;
    if (event === "start") {
        cursor.classList.add("cursor-active");
        const target = document.elementFromPoint(x, y);
        if (target === box) {
            const r = box.getBoundingClientRect();
            dragOffset = { x: x - r.left, y: y - r.top };
        } else {
            target?.closest("button")?.click();
        }
    } else if (event === "end") {
        cursor.classList.remove("cursor-active");
        dragOffset = null;
    }
}

function handleLost() {
    cursor.style.display = "none";
    smoother.reset();
    setHovered(null);
    onPinch(pinch.reset());
}

function onResults(results, now) {
    const landmarks = results.landmarks?.[0];
    if (CONFIG.debugDraw) drawDebug(results.landmarks);
    if (!landmarks) {
        handleLost();
        return;
    }
    // Landmark 5 (index base) stays steady while pinching, unlike the fingertips.
    moveCursor(smoother.filter(mapToViewport(landmarks[5]), now));
    const target = document.elementFromPoint(cursorPos.x, cursorPos.y);
    setHovered(target?.closest(".tool-bar button") ?? null);
    onPinch(pinch.update(landmarks));
}

function drawDebug(hands = []) {
    canvasCtx.clearRect(0, 0, canvasElement.width, canvasElement.height);
    if (typeof drawConnectors === "undefined") return;
    for (const landmarks of hands) {
        drawConnectors(canvasCtx, landmarks, HAND_CONNECTIONS, { color: "#00FF00", lineWidth: 5 });
        drawLandmarks(canvasCtx, landmarks, { color: "#FF0000", lineWidth: 2 });
    }
}

video.addEventListener("loadedmetadata", () => {
    canvasElement.width = video.videoWidth;
    canvasElement.height = video.videoHeight;
});

const tracker = new HandTracker({ video, numHands: 1, onResults });
tracker.init().then(() => demosSection.classList.remove("invisible"));

webcamButton.addEventListener("click", async () => {
    if (tracker.running) {
        tracker.stop();
        handleLost();
        webcamButton.innerText = "ENABLE PREDICTIONS";
    } else {
        await tracker.start();
        webcamButton.innerText = "DISABLE PREDICTIONS";
    }
});
