// 1st mine

let audioBlob;

// function uploadAudio() {
//     var fileInput = document.getElementById('audioUpload');
//     var audioFile = fileInput.files[0];

//     if (!audioFile) {
//         alert('Please upload an audio file!');
//         return;
//     }

//     var formData = new FormData();
//     formData.append('file', audioFile);

//     $.ajax({
//         url: '/upload',  // Make sure this matches your Flask route
//         type: 'POST',    // Ensure it's a POST request
//         data: formData,
//         contentType: false,
//         processData: false,
//         success: function(data) {
//             console.log(data);
//             displayResults(data); // Display charts
//             displayTranscript(data.transcript); // Display transcript
//         },
//         error: function(err) {
//             console.error(err);
//             alert('Error analyzing audio: ' + err.responseText); // Show the server error
//         }
//     });
// }

let videoStream = null;

function toggleCamera() {
    const videoContainer = document.getElementById('user-video-container');
    const userAvatar = document.getElementById('user-avatar');
    const userVideo = document.getElementById('user-video');
    const cameraToggleBtn = document.getElementById('camera-toggle');

    if (!videoStream) {
        // Turn on camera
        navigator.mediaDevices.getUserMedia({ 
            video: true, 
            audio: false 
        })
        .then(stream => {
            videoStream = stream;
            userVideo.srcObject = stream;
            userVideo.style.display = 'block';
            userAvatar.style.display = 'none';
            
            // Change button icon
            cameraToggleBtn.innerHTML = '<i class="fas fa-video"></i>';
        })
        .catch(error => {
            console.error('Error accessing camera:', error);
            alert('Could not access camera. Please check permissions.');
        });
    } else {
        // Turn off camera
        videoStream.getTracks().forEach(track => track.stop());
        videoStream = null;
        userVideo.style.display = 'none';
        userAvatar.style.display = 'block';
        
        // Change button icon back
        cameraToggleBtn.innerHTML = '<i class="fas fa-video-slash"></i>';
    }
}

function displayTranscript(transcript) {
    const transcriptDiv = document.getElementById('transcript');
    if (transcriptDiv) {
        transcriptDiv.innerHTML = `<h3>Transcript</h3><p>${transcript || 'No transcript available'}</p>`;
    } else {
        console.error('Transcript container not found');
    }
}

function displayResults(data) {
    try {
        // Words Per Minute Chart
        createBarChart('wordsPerMinuteChart', 'Words Per Minute', 
            [{ label: 'WPM', value: data.words_per_minute || 0 }], 
            'rgba(75, 192, 192, 0.6)');

        // Tone Chart (using tone energy)
        createBarChart('toneChart', 'Tone Energy', 
            [{ label: 'Energy', value: data.tone?.energy || 0 }], 
            'rgba(255, 99, 132, 0.6)');

        // Pitch Chart
        createBarChart('pitchChart', 'Pitch', 
            [{ label: 'Average Pitch', value: data.pitch || 0 }], 
            'rgba(54, 162, 235, 0.6)');

        // Pace Chart
        createBarChart('paceChart', 'Pace', 
            [{ label: 'Pace', value: data.pace || 0 }], 
            'rgba(255, 206, 86, 0.6)');

        // Sentiment Chart
        createSentimentChart('sentimentChart', data.sentiment || {});

        // Ensure transcript is displayed
        if (data.transcript) {
            displayTranscript(data.transcript);
        }
    } catch (error) {
        console.error('Error displaying results:', error);
    }
}

function createBarChart(canvasId, label, dataPoints, backgroundColor) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) {
        console.error(`Canvas ${canvasId} not found`);
        return;
    }

    // Destroy existing chart if it exists
    if (ctx.chart) {
        ctx.chart.destroy();
    }

    ctx.chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: dataPoints.map(point => point.label),
            datasets: [{
                label: label,
                data: dataPoints.map(point => point.value),
                backgroundColor: backgroundColor,
                borderColor: backgroundColor.replace('0.6)', '1)'),
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: label
                    }
                }
            },
            plugins: {
                title: {
                    display: true,
                    text: label
                }
            }
        }
    });
}

function createSentimentChart(canvasId, sentimentData) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) {
        console.error(`Canvas ${canvasId} not found`);
        return;
    }

    // Destroy existing chart if it exists
    if (ctx.chart) {
        ctx.chart.destroy();
    }

    const sentimentValues = [
        { label: 'Positive', value: (sentimentData.positive * 100) || 0 },
        { label: 'Negative', value: (sentimentData.negative * 100) || 0 },
        { label: 'Neutral', value: (sentimentData.neutral * 100) || 0 }
    ];

    ctx.chart = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: sentimentValues.map(s => s.label),
            datasets: [{
                data: sentimentValues.map(s => s.value),
                backgroundColor: [
                    'rgba(75, 192, 192, 0.6)',  // Positive - teal
                    'rgba(255, 99, 132, 0.6)',  // Negative - red
                    'rgba(201, 203, 207, 0.6)' // Neutral - gray
                ]
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: 'Sentiment Analysis'
                }
            }
        }
    });
}

// Implement startRecording and stopRecording functions here as needed
let mediaRecorder;
let audioChunks = [];

function startRecording() {
    audioChunks = [];
    
    navigator.mediaDevices.getUserMedia({ audio: true })
        .then(stream => {
            mediaRecorder = new MediaRecorder(stream);
            mediaRecorder.start();

            mediaRecorder.ondataavailable = event => {
                audioChunks.push(event.data);
            };

            mediaRecorder.onstop = () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                const audioFile = new File([audioBlob], "audio.wav", { type: 'audio/wav' });
            
                const formData = new FormData();
                formData.append('file', audioFile);
            
                fetch('/analyze_real_time', {
                    method: 'POST',
                    body: formData
                })
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Network response was not ok');
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('Real-time Analysis Results:', data);
                    displayResults(data);
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('Error analyzing real-time audio: ' + error.message);
                });
            };
            
        })
        .catch(error => {
            console.error('Error accessing microphone:', error);
            alert('Could not access microphone. Please check permissions.');
        });
}

function stopRecording() {
    mediaRecorder.stop();
}