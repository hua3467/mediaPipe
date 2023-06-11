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

const landmarkLocations = document.querySelectorAll(".landmark-location");
const uiCanvas = document.querySelector("#ui");
let uiContext = uiCanvas.getContext("2d");

let movingMultiplier = 3;
let zAddition = 0;
let deciNum = 3;
let touchThreshold = 0.17;

const demosSection = document.getElementById("demos");
let handLandmarker = undefined;
let runningMode = "VIDEO";
let enableWebcamButton;
let webcamRunning = false;
let includePoints = [0, 4, 8, 12, 16, 20];

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
/********************************************************************
// Demo 1: Grab a bunch of images from the page and detection them
// upon click.
********************************************************************/
// In this demo, we have put all our clickable images in divs with the
// CSS class 'detectionOnClick'. Lets get all the elements that have
// this class.
const imageContainers = document.getElementsByClassName("detectOnClick");
// Now let's go through all of these and add a click event listener.
for (let i = 0; i < imageContainers.length; i++) {
    // Add event listener to the child element whichis the img element.
    imageContainers[i].children[0].addEventListener("click", handleClick);
}


// // When an image is clicked, let's detect it and display results!
// async function handleClick(event) {
//     if (!handLandmarker) {
//         console.log("Wait for handLandmarker to load before clicking!");
//         return;
//     }
//     if (runningMode === "VIDEO") {
//         runningMode = "IMAGE";
//         await handLandmarker.setOptions({ runningMode: "IMAGE" });
//     }
//     // Remove all landmarks drawed before
//     const allCanvas = event.target.parentNode.getElementsByClassName("canvas");
//     for (var i = allCanvas.length - 1; i >= 0; i--) {
//         const n = allCanvas[i];
//         n.parentNode.removeChild(n);
//     }
//     // We can call handLandmarker.detect as many times as we like with
//     // different image data each time. This returns a promise
//     // which we wait to complete and then call a function to
//     // print out the results of the prediction.
//     const handLandmarkerResult = handLandmarker.detect(event.target);
//     const canvas = document.createElement("canvas");
//     canvas.setAttribute("class", "canvas");
//     canvas.setAttribute("width", event.target.naturalWidth + "px");
//     canvas.setAttribute("height", event.target.naturalHeight + "px");
//     canvas.style =
//         "left: 0px;" +
//         "top: 0px;" +
//         "width: " +
//         event.target.width +
//         "px;" +
//         "height: " +
//         event.target.height +
//         "px;";

//     event.target.parentNode.appendChild(canvas);
//     const cxt = canvas.getContext("2d");

//     for (const landmarks of handLandmarkerResult.landmarks) {
//         landmarkLocations[0].innerHTML = landmarks;
//         drawConnectors(cxt, landmarks, HAND_CONNECTIONS, {
//             color: "#00FF00",
//             lineWidth: 5
//         });
//         drawLandmarks(cxt, landmarks, { color: "#FF0000", lineWidth: 1 });
//     }
// }
/********************************************************************
// Demo 2: Continuously grab image from webcam stream and detect it.
********************************************************************/
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

console.log(video);

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

            uiContext.globalAlpha = 1;
            uiContext.fillStyle = "#aaaaaa";
            uiContext.fillRect(0,0,uiCanvas.width, uiCanvas.height);

            createCursor(landmarks[4], 4);
            createCursor(landmarks[8], 8);
            createCursor(landmarks[12], 12);
            createCursor(landmarks[16], 16);
            createCursor(landmarks[20], 20);




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

    uiContext.globalAlpha = 1-(zAddition - landmark.z); 

    if (landmark.z < touchThreshold) {
        cursorSize[index] = 25;
    } else {
        cursorSize[index] = 20;
    }

    createCircle(((1-smooth(landmark.x, index, 'x'))*uiCanvas.width*movingMultiplier), 
                ((1-smooth(landmark.y, index, 'y'))*uiCanvas.width*movingMultiplier),
                cursorSize[index],
                `white`);
    // uiCanvas.fillText((1-(zAddition - landmark.z)).toString(), ((1-smooth(landmark.x, index, 'x'))*uiCanvas.width*movingMultiplier), ((1-smooth(landmark.y, index, 'y'))*uiCanvas.width*movingMultiplier))                  
}


function createCircle(x, y, size, color){
    uiContext.beginPath();
    uiContext.arc(x, y, size, 0, 2 * Math.PI, false);
    uiContext.fillStyle = color;
    uiContext.fill();
}


