// Copyright 2023 The MediaPipe Authors.
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//      http://www.apache.org/licenses/LICENSE-2.0
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { HandLandmarker, FilesetResolver } from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.0";

// const landmarkLocations = document.querySelectorAll(".landmark-location");
// const uiCanvas = document.querySelector("#ui");
// let uiContext = uiCanvas.getContext("2d");


let movingMultiplier = 2;
let zAddition = 0;
let deciNum = 3;
let touchThreshold = 0.17;

const demosSection = document.getElementById("demos");
let handLandmarker = undefined;
let runningMode = "VIDEO";
let enableWebcamButton;
let webcamRunning = false;
let includePoints = [0, 4, 8, 12, 16, 20];
let objLastPosition = { x: 0, y: 0 };

let fingerMoving = [];

createCanvas(640, 480).parent('#interactionArea');

// Before we can use HandLandmarker class we must wait for it to finish
// loading. Machine Learning models can be large and take a moment to
// get everything needed to run.
const createHandLandmarker = async () => {
    const vision = await FilesetResolver.forVisionTasks("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.0/wasm");
    handLandmarker = await HandLandmarker.createFromOptions(vision, {
        baseOptions: {
            modelAssetPath: `./shared/models/hand_landmarker.task`,
            delegate: "GPU"
        },
        runningMode: runningMode,
        numHands: 2
    });
    demosSection.classList.remove("invisible");
};


createHandLandmarker();



const video = document.getElementById("webcam");
const canvasElement = document.getElementById("output_canvas");
const canvasCtx = canvasElement.getContext("2d");
// Check if webcam access is supported.
const hasGetUserMedia = () => { var _a; return !!((_a = navigator.mediaDevices) === null || _a === void 0 ? void 0 : _a.getUserMedia); };
// If webcam supported, add event listener to button for when user
// wants to activate it.
if (hasGetUserMedia()) {
    enableWebcamButton = document.getElementById("webcamButton");
    enableWebcamButton.addEventListener("click", enableCam);
} else {
    console.warn("getUserMedia() is not supported by your browser");
}
// Enable the live webcam view and start detection.
function enableCam(event) {
    if (!handLandmarker) {
        console.log("Wait! objectDetector not loaded yet.");
        return;
    }
    if (webcamRunning === true) {
        webcamRunning = false;
        enableWebcamButton.innerText = "ENABLE PREDICTIONS";
        // console.log(fingerMoving);
        // fingerMoving = [];
    }
    else {
        webcamRunning = true;
        enableWebcamButton.innerText = "DISABLE PREDICTIONS";

    }
    // getUsermedia parameters.
    const constraints = {
        video: true
    };
    // Activate the webcam stream.
    navigator.mediaDevices.getUserMedia(constraints).then((stream) => {
        video.srcObject = stream;
        video.addEventListener("loadeddata", predictWebcam);
    });
}

let lastVideoTime = -1;
let results = undefined;

let flag = true;

console.log(video);

async function predictWebcam() {
    canvasElement.style.width = video.videoWidth;
    canvasElement.style.height = video.videoHeight;
    canvasElement.width = video.videoWidth;
    canvasElement.height = video.videoHeight;
    // Now let's start detecting the stream.
    if (runningMode === "IMAGE") {
        runningMode = "VIDEO";
        await handLandmarker.setOptions({ runningMode: "VIDEO" });
    }
    let startTimeMs = performance.now();
    if (lastVideoTime !== video.currentTime) {
        lastVideoTime = video.currentTime;
        results = handLandmarker.detectForVideo(video, startTimeMs);
    }
    canvasCtx.save();
    canvasCtx.clearRect(0, 0, canvasElement.width, canvasElement.height);

    if (results.landmarks) {
        for (const landmarks of results.landmarks) {

            uiContext.globalAlpha = 1;
            uiContext.fillStyle = "#aaaaaa";
            uiContext.fillRect(0, 0, uiCanvas.width, uiCanvas.height);

            if (distance(landmarks[4], landmarks[8]) < 0.05) {
                updateObj(true, (0.8 - landmarks[4].x) * uiCanvas.width * movingMultiplier, (0.8 - landmarks[4].y) * uiCanvas.height * movingMultiplier);
            } else {
                updateObj(false, (0.8 - landmarks[4].x) * uiCanvas.width * movingMultiplier, (0.8 - landmarks[4].y) * uiCanvas.height * movingMultiplier);
            }

            createCursor(landmarks[4], 4);
            createCursor(landmarks[8], 8);
            createCursor(landmarks[12], 12);
            createCursor(landmarks[16], 16);
            createCursor(landmarks[20], 20);

            uiContext.fillText(distance(landmarks[4], landmarks[8]).toFixed(2), 40, 40);


            drawConnectors(canvasCtx, landmarks, HAND_CONNECTIONS, {
                color: "#00FF00",
                lineWidth: 5
            });
            drawLandmarks(canvasCtx, landmarks, { color: "#FF0000", lineWidth: 2 });
        }
    }
    canvasCtx.restore();
    // Call this function again to keep predicting when the browser is ready.
    if (webcamRunning === true) {
        window.requestAnimationFrame(predictWebcam);
    }
}


function createCursor(landmark, index) {

    uiContext.globalAlpha = 1 - (zAddition - landmark.z);

    createCircle(((0.8 - landmark.x) * uiCanvas.width * movingMultiplier),
        ((0.8 - landmark.y) * uiCanvas.height * movingMultiplier),
        cursorSize[index],
        `white`);
               
}


// function createCircle(x, y, size, color) {
//     uiContext.beginPath();
//     uiContext.arc(x, y, size, 0, 2 * Math.PI, false);
//     uiContext.fillStyle = color;
//     uiContext.fill();
// }



// function updateObj(isPicked, x, y) {
//     if (isPicked) {
//         createCircle(x, y - 20, 40, 'red');
//         objLastPosition.x = x;
//         objLastPosition.y = y - 20;
//     } else {
//         createCircle(objLastPosition.x, objLastPosition.y - 20, 40, 'red');
//     }

// }
