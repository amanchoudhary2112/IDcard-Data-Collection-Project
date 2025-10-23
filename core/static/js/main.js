document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('student-form');
    const photoInput = document.getElementById('photo-input');
    const preview = document.getElementById('preview');
    const submitBtn = document.getElementById('submit-btn');
    const loader = document.getElementById('loader');

    // Cropper elements
    const modal = document.getElementById('cropper-modal');
    const imageToCrop = document.getElementById('image-to-crop');
    const cropBtn = document.getElementById('crop-btn');

    let cropper;
    let croppedBlob = null;

    photoInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = (event) => {
                imageToCrop.src = event.target.result;
                modal.style.display = 'flex';
                if (cropper) {
                    cropper.destroy();
                }
                cropper = new Cropper(imageToCrop, {
                    aspectRatio: 1,
                    viewMode: 1,
                    background: false,
                    responsive: true,
                    autoCropArea: 0.9,
                    zoomable: false,
                });
            };
            reader.readAsDataURL(file);
        }
    });

    cropBtn.addEventListener('click', () => {
        if (cropper) {
            cropper.getCroppedCanvas({
                width: 512,
                height: 512,
                imageSmoothingQuality: 'high',
            }).toBlob((blob) => {
                croppedBlob = blob;
                const url = URL.createObjectURL(blob);
                preview.innerHTML = `<img src="${url}" class="w-full h-full object-cover rounded-full">`;
                modal.style.display = 'none';
                cropper.destroy();
            }, 'image/jpeg');
        }
    });

    form.addEventListener('submit', function (e) {
        e.preventDefault();

        if (!croppedBlob) {
            alert('Please choose and crop a photo.');
            return;
        }
        
        submitBtn.disabled = true;
        submitBtn.textContent = 'Submitting...';
        loader.style.display = 'block';

        const formData = new FormData(form);
        formData.append('photo', croppedBlob, 'photo.jpg');

        fetch(window.location.href, {
            method: 'POST',
            body: formData,
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                window.location.href = data.redirect_url;
            } else {
                alert('An error occurred: ' + data.message);
                submitBtn.disabled = false;
                submitBtn.textContent = 'Submit Details';
                loader.style.display = 'none';
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('A network error occurred. Please try again.');
            submitBtn.disabled = false;
            submitBtn.textContent = 'Submit Details';
            loader.style.display = 'none';
        });
    });
});