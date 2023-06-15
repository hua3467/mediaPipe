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

const uiContainer = document.querySelector("#ui");
const box = document.querySelector(".box");
const cursors = document.querySelectorAll(".cursor");
const btnColor = document.querySelectorAll(".tool-bar button");

// console.log(uiContainer);

let movingMultiplier = 2;
let zAddition = 0;
let deciNum = 3;
let touchThreshold = 0.17;
let includePoints = [0, 4, 8, 12, 16, 20];

const coord_mark_4 = [0, 0];


const demosSection = document.getElementById("demos");
let handLandmarker = undefined;
let runningMode = "VIDEO";
let enableWebcamButton;
let webcamRunning = false;


let fingerMoving = [];

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
}
else {
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

async function predictWebcam() {
    canvasElement.style.width = video.videoWidth;
    ;
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

            coord_mark_4[0] = (0.8 - landmarks[4].x) * uiContainer.clientWidth * movingMultiplier;
            coord_mark_4[1] = (0.8 - landmarks[4].y) * uiContainer.clientHeight * movingMultiplier;

            if (distance(landmarks[4], landmarks[8]) < 0.04) {

                if (touchDetect(coord_mark_4[0], coord_mark_4[1], btnColor[0])) {
                    uiContainer.style.background = "red";
                } else if (touchDetect(coord_mark_4[0], coord_mark_4[1], btnColor[1])) {
                    uiContainer.style.background = "green";
                } else if (touchDetect(coord_mark_4[0], coord_mark_4[1], btnColor[2])) {
                    uiContainer.style.background = "white";
                } 

                pickObj(coord_mark_4[0], coord_mark_4[1], box);
            }

            updateCursor(landmarks[4], 0);
            updateCursor(landmarks[8], 1);
            updateCursor(landmarks[12], 2);
            updateCursor(landmarks[16], 3);
            updateCursor(landmarks[20], 4);

            // drawConnectors(canvasCtx, landmarks, HAND_CONNECTIONS, {
            //     color: "#00FF00",
            //     lineWidth: 5
            // });
            // drawLandmarks(canvasCtx, landmarks, { color: "#FF0000", lineWidth: 2 });
        }
    }
    canvasCtx.restore();
    // Call this function again to keep predicting when the browser is ready.
    if (webcamRunning === true) {
        window.requestAnimationFrame(predictWebcam);
    }
}

function updateCursor(landmark, cursorIndex) {
    cursors[cursorIndex].style.left = (0.8 - landmark.x) * uiContainer.clientWidth * movingMultiplier + "px";
    cursors[cursorIndex].style.top = (0.8 - landmark.y) * uiContainer.clientHeight * movingMultiplier + "px";
}

// console.log(btnColor[1].getBoundingClientRect());
// console.log(box.getBoundingClientRect());

function touchDetect(landmarkX, landmarkY, target) {
    const targetRect = target.getBoundingClientRect();
    
    let isTouched = false;
    if (landmarkX > targetRect.x - targetRect.width / 2 && landmarkX < targetRect.x + targetRect.width / 2 && landmarkY > targetRect.y - targetRect.height && landmarkY < targetRect.y ) {
        isTouched = true;
    } else {
        isTouched = false;
    }

    return isTouched;
}

function pickObj(landmarkX, landmarkY, target) {
    const targetRect = target.getBoundingClientRect();    
    if (landmarkX > targetRect.x - targetRect.width / 2 && landmarkX < (targetRect.x + targetRect.width) && landmarkY > targetRect.y - targetRect.height / 2 && landmarkY < (targetRect.y + targetRect.height) ) {
        target.style.left = landmarkX + "px";
        target.style.top = landmarkY + "px";
    } 

}





