export const CONFIG = {
    // Region of the (mirrored) camera frame that maps to the whole viewport.
    activeRegion: { x0: 0.2, x1: 0.8, y0: 0.15, y1: 0.75 },
    // Pinch thresholds as a ratio of palm size, so they are independent of camera distance.
    pinchOn: 0.35,
    pinchOff: 0.5,
    oneEuro: { minCutoff: 1.2, beta: 0.02, dCutoff: 1.0 },
    flipX: true,
    flipY: true,
    debugDraw: true,
};

const alpha = (cutoff, dt) => {
    const tau = 1 / (2 * Math.PI * cutoff);
    return 1 / (1 + tau / dt);
};

// One Euro filter: smooth when moving slowly, responsive when moving fast.
export class OneEuroFilter {
    constructor({ minCutoff, beta, dCutoff }) {
        this.minCutoff = minCutoff;
        this.beta = beta;
        this.dCutoff = dCutoff;
        this.reset();
    }

    reset() {
        this.x = null;
        this.dx = 0;
        this.t = null;
    }

    filter(value, timeMs) {
        if (this.x === null) {
            this.x = value;
            this.t = timeMs;
            return value;
        }
        const dt = Math.max((timeMs - this.t) / 1000, 1e-3);
        this.t = timeMs;
        const rawDx = (value - this.x) / dt;
        this.dx += alpha(this.dCutoff, dt) * (rawDx - this.dx);
        const cutoff = this.minCutoff + this.beta * Math.abs(this.dx);
        this.x += alpha(cutoff, dt) * (value - this.x);
        return this.x;
    }
}

export class PointSmoother {
    constructor(options = CONFIG.oneEuro) {
        this.fx = new OneEuroFilter(options);
        this.fy = new OneEuroFilter(options);
    }

    reset() {
        this.fx.reset();
        this.fy.reset();
    }

    filter(p, timeMs) {
        return { x: this.fx.filter(p.x, timeMs), y: this.fy.filter(p.y, timeMs) };
    }
}

// Maps a normalized landmark to normalized viewport coordinates (0..1), with optional axis flips, and clamped.
export function mapToViewport(landmark, region = CONFIG.activeRegion) {
    const clamp = (v) => Math.min(1, Math.max(0, v));
    return {
        x: clamp(((CONFIG.flipX ? 1 - landmark.x : landmark.x) - region.x0) / (region.x1 - region.x0)),
        y: clamp(((CONFIG.flipY ? 1 - landmark.y : landmark.y) - region.y0) / (region.y1 - region.y0)),
    };
}

// Edge-triggered pinch detection with hysteresis.
export class PinchDetector {
    constructor({ on = CONFIG.pinchOn, off = CONFIG.pinchOff } = {}) {
        this.on = on;
        this.off = off;
        this.pinching = false;
    }

    // Returns "start", "end", or null.
    update(landmarks) {
        const palm = Math.hypot(landmarks[0].x - landmarks[9].x, landmarks[0].y - landmarks[9].y);
        const gap = Math.hypot(landmarks[4].x - landmarks[8].x, landmarks[4].y - landmarks[8].y);
        const ratio = gap / Math.max(palm, 1e-6);
        if (!this.pinching && ratio < this.on) {
            this.pinching = true;
            return "start";
        }
        if (this.pinching && ratio > this.off) {
            this.pinching = false;
            return "end";
        }
        return null;
    }

    reset() {
        const wasPinching = this.pinching;
        this.pinching = false;
        return wasPinching ? "end" : null;
    }
}
