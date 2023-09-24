let cursorSize = [20,20,20,20,20,20,20,20,20,20,20,20,20,20,20,20,20,20,20,20,20];

const moves = [
    {
        x: [0,0,0,0,0],
        y: [0,0,0,0,0],
        z: [0,0,0,0,0],
    },{
        x: [0,0,0,0,0],
        y: [0,0,0,0,0],
        z: [0,0,0,0,0],
    },{
        x: [0,0,0,0,0],
        y: [0,0,0,0,0],
        z: [0,0,0,0,0],
    },{
        x: [0,0,0,0,0],
        y: [0,0,0,0,0],
        z: [0,0,0,0,0],
    },{
        x: [0,0,0,0,0],
        y: [0,0,0,0,0],
        z: [0,0,0,0,0],
    },{
        x: [0,0,0,0,0],
        y: [0,0,0,0,0],
        z: [0,0,0,0,0],
    }
]





/**
 * 
 * @param {number} newNum value of the coord
 * @param {landmark} finger 
 * @param {number} coord x, y, or z
 * @returns 
 */
// const smooth = (newNum, finger, coord) => {
//         moves[finger][coord].push(newNum);
//         moves[finger][coord].shift();
//         return moves[finger][coord].reduce((a, b) => a + b) / moves[finger][coord].length;
//     }
const smooth = (acturalValue, prevValue, currentValue, smooth=5) => {
    currentValue = prevValue + (acturalValue - prevValue) / smooth;
}



function resetBtnSelect(selector) {
    selector.forEach(btn => {
        if (btn.classList.contains("btn-hovered")) {
            btn.classList.remove("btn-hovered");
        }
    })
}



const trackArr = [0,0,0,0,0,0,0];
let down = 0;
let up = 0;
let stay = 0;

function clickDetect(num, threshold) {
    trackArr.push(num);
    trackArr.shift();

    if(trackArr[trackArr.length - 1] - trackArr[0] > threshold[0] && trackArr[trackArr.length - 1] - trackArr[0] < 0.02) {
        down++;
    } else if (trackArr[trackArr.length - 1] - trackArr[1] < threshold[1] && trackArr[trackArr.length - 1] - trackArr[1] > -0.02) {
        up++;
    } else {
        stay++;
    }

    if (stay > 30) {
        down = 0;
        up = 0;
        stay = 0;
    }

    if(down > 4 && up > 4) {
        down = 0;
        up = 0;
    }

    
}