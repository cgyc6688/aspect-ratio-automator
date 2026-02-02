let currentSession = null;
let currentAdjustments = {};
let currentRatio = null;

// DOM Elements
const uploadZone = document.getElementById('uploadZone');
const fileInput = document.getElementById('fileInput');
const dpiWarning = document.getElementById('dpiWarning');
const warningText = document.getElementById('warningText');
const previewGrid = document.getElementById('previewGrid');
const gridContainer = document.querySelector('.grid');
const downloadSection = document.getElementById('downloadSection');
const loadingOverlay = document.getElementById('loadingOverlay');

// Drag and Drop
uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('dragover');
});

uploadZone.addEventListener('dragleave', () => {
    uploadZone.classList.remove('dragover');
});

uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('dragover');
    
    if (e.dataTransfer.files.length) {
        handleFile(e.dataTransfer.files[0]);
    }
});

// File Input Change
fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) {
        handleFile(e.target.files[0]);
    }
});

// Handle File Upload
async function handleFile(file) {
    if (!file.type.match('image.*')) {
        alert('Please upload an image file (JPG, PNG, TIFF)');
        return;
    }
    
    if (file.size > 50 * 1024 * 1024) {
        alert('File size exceeds 50MB limit');
        return;
    }
    
    showLoading();
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
            currentSession = data.session_id;
            currentAdjustments = {};
            
            // Show DPI warning if needed
            if (data.dpi_warning) {
                warningText.textContent = data.dpi_warning;
                dpiWarning.classList.remove('hidden');
            } else {
                dpiWarning.classList.add('hidden');
            }
            
            // Create preview grid
            createPreviewGrid(data.previews);
            previewGrid.classList.remove('hidden');
            downloadSection.classList.remove('hidden');
            
        } else {
            alert('Upload failed: ' + data.error);
        }
    } catch (error) {
        alert('Error uploading file: ' + error.message);
    } finally {
        hideLoading();
    }
}

// Create Preview Grid
function createPreviewGrid(previews) {
    gridContainer.innerHTML = '';
    
    for (const [ratio, info] of Object.entries(previews)) {
        const gridItem = document.createElement('div');
        gridItem.className = 'grid-item';
        gridItem.innerHTML = `
            <img src="${info.url}" alt="${ratio} preview" class="preview-image">
            <div class="ratio-label">${ratio.replace('x', ':')}</div>
            <div class="ratio-dimensions">${info.dimensions}</div>
            <button class="btn btn-secondary" onclick="openAdjustment('${ratio}')">
                <i class="fas fa-sliders-h"></i> Adjust
            </button>
        `;
        gridContainer.appendChild(gridItem);
    }
}

// Open Adjustment Modal
function openAdjustment(ratio) {
    currentRatio = ratio;
    
    // Set modal image
    const modalImage = document.getElementById('modalImage');
    modalImage.src = `/preview/${currentSession}/${ratio}?t=${Date.now()}`;
    
    // Reset sliders
    document.getElementById('xSlider').value = 0;
    document.getElementById('ySlider').value = 0;
    updateSliderValues(0, 0);
    
    // Show modal
    document.getElementById('adjustmentModal').classList.remove('hidden');
}

// Close Modal
function closeModal() {
    document.getElementById('adjustmentModal').classList.add('hidden');
}

// Update Slider Values
function updateSliderValues(x, y) {
    const xValue = document.querySelector('#xSlider + .slider-value');
    const yValue = document.querySelector('#ySlider + .slider-value');
    
    xValue.textContent = x === 0 ? 'Center' : (x > 0 ? `Right ${x}%` : `Left ${Math.abs(x)}%`);
    yValue.textContent = y === 0 ? 'Center' : (y > 0 ? `Down ${y}%` : `Up ${Math.abs(y)}%`);
}

// Reset Adjustment
function resetAdjustment() {
    document.getElementById('xSlider').value = 0;
    document.getElementById('ySlider').value = 0;
    updateSliderValues(0, 0);
    
    // Remove adjustment for this ratio
    delete currentAdjustments[currentRatio];
    
    // Reload original preview
    const modalImage = document.getElementById('modalImage');
    modalImage.src = `/preview/${currentSession}/${currentRatio}?t=${Date.now()}`;
}

// Save Adjustment
async function saveAdjustment() {
    const xSlider = document.getElementById('xSlider');
    const ySlider = document.getElementById('ySlider');
    
    const xOffset = parseInt(xSlider.value);
    const yOffset = parseInt(ySlider.value);
    
    showLoading();
    
    try {
        const response = await fetch('/adjust', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                session_id: currentSession,
                ratio: currentRatio,
                x_offset: xOffset,
                y_offset: yOffset
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Save adjustment
            currentAdjustments[currentRatio] = {
                x_offset: xOffset,
                y_offset: yOffset
            };
            
            // Update preview in grid
            const previewImage = document.querySelector(`.grid-item .preview-image[src^="/preview/${currentSession}/${currentRatio}"]`);
            if (previewImage) {
                previewImage.src = data.preview_url + `?t=${Date.now()}`;
            }
            
            closeModal();
        }
    } catch (error) {
        alert('Error saving adjustment: ' + error.message);
    } finally {
        hideLoading();
    }
}

// Download All
async function downloadAll() {
    showLoading();
    
    try {
        const response = await fetch('/download', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                session_id: currentSession,
                adjustments: currentAdjustments
            })
        });
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `aspect_ratios_${currentSession}.zip`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
        } else {
            const error = await response.json();
            alert('Download failed: ' + error.error);
        }
    } catch (error) {
        alert('Error downloading files: ' + error.message);
    } finally {
        hideLoading();
    }
}

// Event Listeners for Sliders
document.getElementById('xSlider').addEventListener('input', function() {
    const ySlider = document.getElementById('ySlider');
    updateSliderValues(parseInt(this.value), parseInt(ySlider.value));
});

document.getElementById('ySlider').addEventListener('input', function() {
    const xSlider = document.getElementById('xSlider');
    updateSliderValues(parseInt(xSlider.value), parseInt(this.value));
});

// Loading Functions
function showLoading() {
    loadingOverlay.classList.remove('hidden');
}

function hideLoading() {
    loadingOverlay.classList.add('hidden');
}

// Cleanup on page unload
window.addEventListener('beforeunload', async () => {
    if (currentSession) {
        await fetch('/cleanup', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ session_id: currentSession })
        });
    }
});

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Set up slider event listeners
    const sliders = document.querySelectorAll('.slider');
    sliders.forEach(slider => {
        slider.addEventListener('input', function() {
            const valueDisplay = this.nextElementSibling;
            if (valueDisplay && valueDisplay.classList.contains('slider-value')) {
                const value = parseInt(this.value);
                const label = this.previousElementSibling.textContent.toLowerCase();
                
                if (label.includes('horizontal')) {
                    valueDisplay.textContent = value === 0 ? 'Center' : 
                                              value > 0 ? `Right ${value}%` : `Left ${Math.abs(value)}%`;
                } else {
                    valueDisplay.textContent = value === 0 ? 'Center' : 
                                              value > 0 ? `Down ${value}%` : `Up ${Math.abs(value)}%`;
                }
            }
        });
    });
});