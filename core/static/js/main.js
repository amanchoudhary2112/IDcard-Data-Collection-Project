document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('student-form');
    const submitBtn = document.getElementById('submit-btn');
    const loader = document.getElementById('loader');

    // Global Modals
    const cropperModal = document.getElementById('cropper-modal');
    const imageToCrop = document.getElementById('image-to-crop');
    const cropBtn = document.getElementById('crop-btn');
    const cameraModal = document.getElementById('camera-modal');
    const cancelCameraBtn = document.getElementById('cancel-camera-btn');
    const cameraFeed = document.getElementById('camera-feed');
    const captureBtn = document.getElementById('capture-btn');

    let cropper;
    let cameraStream = null;
    
    // Store the active field elements
    let activeCropperTarget = {
        input: null,    // The file input
        preview: null   // The preview circle
    };

    // --- Cropper Logic ---
    function openCropper(imageSrc) {
        imageToCrop.src = imageSrc;
        cropperModal.style.display = 'flex';
        if (cropper) { cropper.destroy(); }
        cropper = new Cropper(imageToCrop, {
            aspectRatio: 1, viewMode: 1, background: false,
            responsive: true, autoCropArea: 0.9, zoomable: false,
        });
    }

    cropBtn.addEventListener('click', () => {
        if (cropper && activeCropperTarget.input) {
            cropper.getCroppedCanvas({
                width: 512, height: 512, imageSmoothingQuality: 'high',
            }).toBlob((blob) => {
                // Update the preview circle
                activeCropperTarget.preview.innerHTML = `<img src="${URL.createObjectURL(blob)}" class="w-full h-full object-cover rounded-full">`;
                
                // --- This is the key trick ---
                // Create a new File object from the blob
                const croppedFile = new File([blob], "cropped_photo.jpg", { type: "image/jpeg" });
                // Create a DataTransfer to hold this new file
                const dataTransfer = new DataTransfer();
                dataTransfer.items.add(croppedFile);
                // Set the .files property of the original file input to our new file
                activeCropperTarget.input.files = dataTransfer.files;
                // -----------------------------
                
                cropperModal.style.display = 'none';
                cropper.destroy();
                activeCropperTarget = { input: null, preview: null }; // Clear active target
            }, 'image/jpeg');
        }
    });

    // --- Camera Logic ---
    async function startCamera() {
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            try {
                const constraints = { video: { facingMode: 'environment' } };
                try { cameraStream = await navigator.mediaDevices.getUserMedia(constraints); }
                catch (err) { cameraStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } }); }
                cameraFeed.srcObject = cameraStream;
                cameraFeed.onloadedmetadata = () => { cameraFeed.play(); cameraModal.style.display = 'flex'; };
            } catch (err) { alert("Could not access camera. Please check permissions."); console.error(err); }
        } else { alert("Browser does not support camera access."); }
    }

    function stopCamera() {
        if (cameraStream) { cameraStream.getTracks().forEach(track => track.stop()); cameraStream = null; cameraFeed.srcObject = null; cameraModal.style.display = 'none'; }
    }

    cancelCameraBtn.addEventListener('click', stopCamera);

    captureBtn.addEventListener('click', () => {
        if (!cameraFeed.videoWidth || !cameraFeed.videoHeight) { return; }
        const canvas = document.createElement('canvas');
        canvas.width = cameraFeed.videoWidth; canvas.height = cameraFeed.videoHeight;
        const context = canvas.getContext('2d');
        context.drawImage(cameraFeed, 0, 0, canvas.width, canvas.height);
        stopCamera();
        canvas.toBlob((blob) => {
            openCropper(URL.createObjectURL(blob)); // Send captured blob to the cropper
        }, 'image/jpeg', 0.9);
    });

    // --- Main Initialization ---
    // Find ALL photo upload blocks and wire them up
    document.querySelectorAll('.photo-upload-block').forEach(block => {
        const photoInput = block.querySelector('.photo-file-input');
        const photoLabel = block.querySelector('.photo-input-label');
        const openCameraBtn = block.querySelector('.open-camera-btn');
        const preview = block.querySelector('.preview-circle');

        // Wire up the "Choose Photo" label to click the hidden input
        if (photoLabel) {
            photoLabel.addEventListener('click', (e) => {
                e.preventDefault();
                photoInput.click();
            });
        }
        
        // Wire up the file input
        if (photoInput) {
            photoInput.addEventListener('change', (e) => {
                const file = e.target.files[0];
                if (file) {
                    // Set this field as the active target
                    activeCropperTarget = { input: photoInput, preview: preview };
                    // Open the cropper
                    const reader = new FileReader();
                    reader.onload = (event) => openCropper(event.target.result);
                    reader.readAsDataURL(file);
                }
            });
        }
        
        // Wire up the camera button
        if (openCameraBtn) {
            openCameraBtn.addEventListener('click', () => {
                // Set this field as the active target
                activeCropperTarget = { input: photoInput, preview: preview };
                startCamera();
            });
        }
    });

    // --- Form Submission Logic ---
    form.addEventListener('submit', function (e) {
        e.preventDefault();
        
        submitBtn.disabled = true;
        submitBtn.style.display = 'none'; 
        loader.style.display = 'flex';

        // Create FormData FROM the form.
        // Because we updated the file inputs with the cropped blobs,
        // FormData(form) will automatically pick up ALL files:
        // - The cropped photos
        // - The regular document/file uploads
        const formData = new FormData(form);

        fetch(window.location.href, {
            method: 'POST',
            body: formData,
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                window.location.href = data.redirect_url;
            } else {
                alert('Submission Error: ' + data.message);
                submitBtn.disabled = false;
                submitBtn.style.display = 'block'; 
                loader.style.display = 'none'; 
            }
        })
        .catch(error => {
            console.error('Network Error:', error);
            alert('A network error occurred. Please check your connection and try again.');
            submitBtn.disabled = false;
            submitBtn.style.display = 'block'; 
            loader.style.display = 'none'; 
        });
    });
});