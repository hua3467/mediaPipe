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

const contentContainer = document.querySelector("#contentContainer");
const rectContentContainer = contentContainer.getBoundingClientRect();



const box = document.querySelector(".box");
const fingerTips = document.querySelectorAll(".cursor");
const cursor = document.querySelector("#cursor_master");
const btnColor = document.querySelectorAll(".tool-bar button");
const info = document.querySelector(".info");

const scrollBar = document.querySelector("#scrollBar");
const rectRecrollBar = scrollBar.getBoundingClientRect();

const btnPageUp = document.querySelector("#btnPageUp");
const btnPageDown = document.querySelector("#btnPageDown");


contentContainer.innerHTML = page_1;

btnColor[0].addEventListener("click", e => {
    contentContainer.innerHTML = page_1;
});

btnColor[1].addEventListener("click", e => {
    contentContainer.innerHTML = page_2;
});

btnColor[2].addEventListener("click", e => {
    contentContainer.innerHTML = page_3;
});


let movingMultiplier = 2;
let cursorMovingMultiplier = 10;
let zAddition = 0;
let deciNum = 3;
let touchThreshold = 0.17;
let includePoints = [0, 4, 8, 12, 16, 20];
let smoothening = 5;
let touchStep = [0,0];

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

    // canvasElement.style.width = video.videoWidth;
    // canvasElement.style.height = video.videoHeight;
    // canvasElement.width = video.videoWidth;
    // canvasElement.height = video.videoHeight;

    canvasElement.style.width = 320;
    canvasElement.style.height = 200;
    canvasElement.width = 320;
    canvasElement.height = 200;


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
                    contentContainer.innerHTML = page_1;
                }

            } else if (objectClicked(cursor, btnColor[1])) {

                if (isClicked(landmarks[4], landmarks[8], 0.05)) {
                    contentContainer.innerHTML = page_2;
                }

            } else if (objectClicked(cursor, btnColor[2])) {

                if (isClicked(landmarks[4], landmarks[8], 0.05)) {
                    contentContainer.innerHTML = page_3;
                }

            }

            if (isClicked(landmarks[4], landmarks[8], 0.05)) {
                pickObj(cursor, box);
            }

            if (isClicked(landmarks[4], landmarks[12], 0.05)) {
                pageContent.scrollBy({ left: 0, top: pageContent.clientHeight, behavior: "smooth" });
            }

            if (isClicked(landmarks[4], landmarks[16], 0.05)) {
                pageContent.scrollBy({ left: 0, top: pageContent.clientHeight * (-1), behavior: "smooth" });
            }

            clickDetect(landmarks[8].x, [-0.005, 0.005])

            // fingerMoving.push([landmarks[8].x, landmarks[8].y, landmarks[8].z]);

            updateFingerTip(landmarks[4], 4, 0);
            updateFingerTip(landmarks[8], 8, 1);
            updateFingerTip(landmarks[12], 12, 2);
            updateFingerTip(landmarks[16], 16, 3);
            updateFingerTip(landmarks[20], 20, 4);
            updateCursor(landmarks[5], 5, 5);



            // updateCursorLine(landmarks[4], landmarks[8], 4, 8);

            drawConnectors(canvasCtx, landmarks, HAND_CONNECTIONS, {
                color: "#00FF00",
                lineWidth: 1
            });
            drawLandmarks(canvasCtx, landmarks, { color: "#FF0000", lineWidth: 1 });
        }
    }
    canvasCtx.restore();
    // Call this function again to keep predicting when the browser is ready.
    if (webcamRunning === true) {
        window.requestAnimationFrame(predictWebcam);
    }
}




console.log(contentContainer.clientHeight);
scrollBar.addEventListener('mousemove', function (event) {

    const y = event.clientY - rectRecrollBar.top;
    const percentY = y / rectRecrollBar.height;

    pageContent.scroll({ top: contentContainer.clientHeight * percentY, left: 0 });

});



btnPageDown.addEventListener("click", e => {
    console.log(pageContent.clientHeight);
    pageContent.scrollBy({ left: 0, top: pageContent.clientHeight, behavior: "smooth" });
})

btnPageUp.addEventListener("click", e => {
    pageContent.scrollBy({ left: 0, top: pageContent.clientHeight * (-1), behavior: "smooth" });
})

function updateFingerTip(landmark, markIndex, cursorIndex) {
    fingerTips[cursorIndex].style.left = smooth((0.8 - landmark.x), cursorIndex, 'x') * uiContainer.clientWidth * movingMultiplier + "px";
    fingerTips[cursorIndex].style.top = smooth((0.8 - landmark.y), cursorIndex, 'y') * uiContainer.clientHeight * movingMultiplier + "px";
}

function updateCursor(landmark, markIndex, cursorIndex) {

    let left = (1 - landmark.x) * uiContainer.clientWidth * 1.75 - 1100;
    let top = landmark.y * uiContainer.clientHeight * 2.5 - 850;

    currentX = previousX + (left - previousX) / smoothening;
    currentY = previousY + (top - previousY) / smoothening;

    if (currentX <= 1) {
        currentX = 1;
    } else if (currentX >= 520) {
        currentX = 520;
    }

    if (currentY <= 1) {
        currentY = 1;
    } else if (currentY >= 340) {
        currentY = 340;
    }

    info.innerHTML = `x: ${left}, y: ${top}`;

    cursor.style.left = currentX * 2 + "px";
    cursor.style.top = currentY * 2 + "px";

    previousX = currentX;
    previousY = currentY;
}

function objectClicked(obj, target) {
    const targetRect = target.getBoundingClientRect();
    const objRect = obj.getBoundingClientRect();

    let isTouched = false;

    if (objRect.x + objRect.width > targetRect.x && objRect.x < targetRect.x + targetRect.width && objRect.y + objRect.height > targetRect.y && objRect.y < targetRect.y + targetRect.height) {
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
    if (objRect.x + objRect.width > targetRect.x && objRect.x < targetRect.x + targetRect.width && objRect.y + objRect.height > targetRect.y && objRect.y < targetRect.y + targetRect.height) {
        target.style.left = objRect.x + "px";
        target.style.top = objRect.y + "px";
    }

}

function scroll(cursor) {

}


function isClicked(landmark1, landmark2, threshold) {
    const a = landmark1.x - landmark2.x;
    const b = landmark1.y - landmark2.y;

    if (Math.hypot(a, b) < threshold) {

        touchStep[0] = 1;

        if (!cursor.classList.contains("cursor-active")) {
            cursor.classList.add("cursor-active");
        }

        return (Math.hypot(a, b) < threshold);
    } else if (Math.hypot(a, b) >= threshold){
        touchStep[1] = 1;
    } else {
        if (cursor.classList.contains("cursor-active")) {
            cursor.classList.remove("cursor-active");
        }
        return false;
    }
}