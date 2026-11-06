import { HandLandmarker, FilesetResolver } from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.0";

// Wraps webcam + HandLandmarker and calls onResults only for new video frames.
export class HandTracker {
    constructor({ video, modelPath = "./shared/models/hand_landmarker.task", numHands = 1, onResults }) {
        this.video = video;
        this.modelPath = modelPath;
        this.numHands = numHands;
        this.onResults = onResults;
        this.landmarker = null;
        this.stream = null;
        this.running = false;
        this.lastVideoTime = -1;
    }

    async init() {
        const vision = await FilesetResolver.forVisionTasks(
            "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.0/wasm"
        );
        this.landmarker = await HandLandmarker.createFromOptions(vision, {
            baseOptions: { modelAssetPath: this.modelPath, delegate: "GPU" },
            runningMode: "VIDEO",
            numHands: this.numHands,
        });
    }

    async start() {
        if (this.running || !this.landmarker) return;
        this.stream = await navigator.mediaDevices.getUserMedia({
            video: { width: 640, height: 480, frameRate: 30 },
        });
        this.video.srcObject = this.stream;
        await new Promise((resolve) => {
            if (this.video.readyState >= 2) resolve();
            else this.video.addEventListener("loadeddata", resolve, { once: true });
        });
        this.running = true;
        this.schedule();
    }

    stop() {
        this.running = false;
        this.stream?.getTracks().forEach((t) => t.stop());
        this.stream = null;
        this.video.srcObject = null;
        this.lastVideoTime = -1;
    }

    schedule() {
        if (!this.running) return;
        if ("requestVideoFrameCallback" in this.video) {
            this.video.requestVideoFrameCallback((now) => this.tick(now));
        } else {
            requestAnimationFrame((now) => this.tick(now));
        }
    }

    tick(now) {
        if (!this.running) return;
        if (this.video.currentTime !== this.lastVideoTime) {
            this.lastVideoTime = this.video.currentTime;
            const results = this.landmarker.detectForVideo(this.video, performance.now());
            this.onResults(results, now);
        }
        this.schedule();
    }
}
