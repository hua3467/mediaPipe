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
const pageContent = document.querySelector(".page-content");
const box = document.querySelector(".box");
const fingerTips = document.querySelectorAll(".cursor");
const cursor = document.querySelector("#cursor_master");
const btnColor = document.querySelectorAll(".tool-bar button");

btnColor[0].addEventListener("click", e => {
    pageContent.innerHTML = page_1;
});

btnColor[1].addEventListener("click", e => {
    pageContent.innerHTML = page_2;
});

btnColor[2].addEventListener("click", e => {
    pageContent.innerHTML = page_3;
});


let movingMultiplier = 2;
let cursorMovingMultiplier = 10;
let zAddition = 0;
let deciNum = 3;
let touchThreshold = 0.17;
let includePoints = [0, 4, 8, 12, 16, 20];
let smoothening = 5;

let previousX = 0;
let previousY = 0;
let currentX = 0;
let currentY = 0;

const coord_mark_5 = [0, 0];


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
        console.log(fingerMoving);
        fingerMoving = [];
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

            // coord_mark_5[0] = (0.8 - landmarks[5].x) * uiContainer.clientWidth * cursorMovingMultiplier - 2500;
            // coord_mark_5[1] = (0.8 - landmarks[5].y) * uiContainer.clientHeight * cursorMovingMultiplier - 2500;


                if (objectClicked(cursor, btnColor[0])) {
                    
                    if (isClicked(landmarks[4], landmarks[8], 0.05)) {
                        pageContent.innerHTML = page_1;
                        uiContainer.style.background = "#fcb8b8";
                    }
                    
                } else if (objectClicked(cursor, btnColor[1])) {

                    if (isClicked(landmarks[4], landmarks[8], 0.05)) {
                        pageContent.innerHTML = page_2;
                        uiContainer.style.background = "#c2ffb3";
                    }

                } else if (objectClicked(cursor, btnColor[2])) {
                    
                    if (isClicked(landmarks[4], landmarks[8], 0.05)) {
                        pageContent.innerHTML = page_3;
                        uiContainer.style.background = "white";
                    }

                } 

                if (isClicked(landmarks[4], landmarks[8], 0.05)) {
                    pickObj(cursor, box);
                }
                
            clickDetect(landmarks[8].x, [-0.005, 0.005])

            // fingerMoving.push([landmarks[8].x, landmarks[8].y, landmarks[8].z]);

            // updateFingerTip(landmarks[4],4, 0);
            // updateFingerTip(landmarks[8],8, 1);
            // updateFingerTip(landmarks[12],12, 2);
            // updateFingerTip(landmarks[16],16, 3);
            // updateFingerTip(landmarks[20],20, 4);
            updateCursor(landmarks[5], 5, 5);

            

            // updateCursorLine(landmarks[4], landmarks[8], 4, 8);

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

function updateFingerTip(landmark, markIndex, cursorIndex) {
    fingerTips[cursorIndex].style.left = smooth((0.8 - landmark.x), cursorIndex, 'x') * uiContainer.clientWidth * movingMultiplier + "px";
    fingerTips[cursorIndex].style.top = smooth((0.8 - landmark.y), cursorIndex, 'y') * uiContainer.clientHeight * movingMultiplier + "px";
}

function updateCursor(landmark, markIndex, cursorIndex) {

    let left = (0.8 - landmark.x) * uiContainer.clientWidth * cursorMovingMultiplier - 2500;
    let top = (0.8 - landmark.y) * uiContainer.clientHeight * cursorMovingMultiplier - 1800;

    currentX = previousX + (left - previousX) / smoothening;
    currentY = previousY + (top - previousY) / smoothening;

    if(currentX <= 1) {
        currentX = 1;
    } else if (currentX >= uiContainer.clientWidth) {
        currentX = uiContainer.clientWidth - 40;
    }

    if (currentY <= 1) {
        currentY = 1;
    } else if (currentY >= uiContainer.clientHeight) {
        currentY = uiContainer.clientHeight - 40;
    }

    cursor.style.left = currentX + "px";
    cursor.style.top = currentY + "px";
    
    previousX = currentX;
    previousY = currentY;
}

function objectClicked(obj, target) {
    const targetRect = target.getBoundingClientRect();
    const objRect = obj.getBoundingClientRect();
    
    let isTouched = false;

    if (objRect.x + objRect.width > targetRect.x  && objRect.x < targetRect.x + targetRect.width && objRect.y + objRect.height > targetRect.y && objRect.y < targetRect.y + targetRect.height ) {
        if (!target.classList.contains("btn-hovered")) {
            target.classList.add("btn-hovered");
        }
        isTouched = true;

    } else {
        if (target.classList.contains("btn-hovered")) {
            target.classList.remove("btn-hovered");
        }
        isTouched = false;
    }

    return isTouched;
}

function pickObj(obj, target) {

    const targetRect = target.getBoundingClientRect();  
    const objRect = obj.getBoundingClientRect();  
    if (objRect.x + objRect.width > targetRect.x  && objRect.x < targetRect.x + targetRect.width && objRect.y + objRect.height > targetRect.y && objRect.y < targetRect.y + targetRect.height ) {
        target.style.left = objRect.x + "px";
        target.style.top = objRect.y + "px";
    } 

}


// function updateCursorLine(landmark1, landmark2, cursorIndex1, cursorIndex2){
//     cursorLine.setAttribute('x1', (0.8 - landmark1.x) * uiContainer.clientWidth * movingMultiplier + 20);
//     cursorLine.setAttribute('y1', (0.8 - landmark1.y) * uiContainer.clientHeight * movingMultiplier - 40);
//     cursorLine.setAttribute('x2', (0.8 - landmark2.x) * uiContainer.clientWidth * movingMultiplier + 20);
//     cursorLine.setAttribute('y2', (0.8 - landmark2.y) * uiContainer.clientHeight * movingMultiplier - 40);
//     cursorLine.setAttribute('stroke', 'rgb(255,0,0)');
//     cursorLine.setAttribute('stroke-width', 2);
// }


function isClicked(landmark1, landmark2, threshold) {
    const a = landmark1.x - landmark2.x;
    const b = landmark1.y - landmark2.y;

    if (Math.hypot(a,b) < threshold) {

        if (!cursor.classList.contains("cursor-active")) {
            cursor.classList.add("cursor-active");
        }
        
        return (Math.hypot(a,b) < threshold);
    } else {
        if (cursor.classList.contains("cursor-active")) {
            cursor.classList.remove("cursor-active");
        }
        return false;
    }
}