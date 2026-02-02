/**
 * Aspect Ratio Automator - Frontend JavaScript
 * Updated to fix preview image issues after adjustments
 */

// Global variables
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
const modalImage = document.getElementById('modalImage');

// ============================================================================
// 1. INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('Aspect Ratio Automator initialized');
    
    // Initialize slider event listeners
    initializeSliders();
    
    // Check if there's a previous session in localStorage
    checkPreviousSession();
});

// ============================================================================
// 2. FILE UPLOAD HANDLING
// ============================================================================

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

/**
 * Handle file upload
 */
async function handleFile(file) {
    console.log('Handling file:', file.name, `(${(file.size / 1024 / 1024).toFixed(2)} MB)`);
    
    // Validation
    if (!file.type.match('image.*')) {
        showError('Please upload an image file (JPG, PNG, TIFF)');
        return;
    }
    
    if (file.size > 50 * 1024 * 1024) {
        showError('File size exceeds 50MB limit');
        return;
    }
    
    // Warn for large files
    if (file.size > 10 * 1024 * 1024) {
        if (!confirm('Large file detected (>10MB). Free tier may have memory limitations. Continue?')) {
            return;
        }
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
            console.log('Upload successful:', data);
            
            currentSession = data.session_id;
            currentAdjustments = {};
            
            // Save session to localStorage
            saveSessionToStorage();
            
            // Show DPI warning if needed
            if (data.dpi_warning) {
                warningText.textContent = data.dpi_warning;
                dpiWarning.classList.remove('hidden');
            } else {
                dpiWarning.classList.add('hidden');
            }
            
            // Show size warning if present
            if (data.size_warning) {
                showToast(data.size_warning, 'warning');
            }
            
            // Create preview grid
            createPreviewGrid(data.previews);
            previewGrid.classList.remove('hidden');
            downloadSection.classList.remove('hidden');
            
            // Scroll to previews
            previewGrid.scrollIntoView({ behavior: 'smooth', block: 'start' });
            
        } else {
            showError('Upload failed: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Upload error:', error);
        showError('Error uploading file: ' + error.message);
    } finally {
        hideLoading();
    }
}

// ============================================================================
// 3. PREVIEW GRID MANAGEMENT
// ============================================================================

/**
 * Create the preview grid from server data
 */
function createPreviewGrid(previews) {
    console.log('Creating preview grid:', previews);
    gridContainer.innerHTML = '';
    
    // Define ratio display names
    const ratioNames = {
        '2x3': '2:3',
        '3x4': '3:4', 
        '4x5': '4:5',
        'ISO': 'ISO',
        '11x14': '11:14'
    };
    
    for (const [ratioKey, previewInfo] of Object.entries(previews)) {
        console.log(`Creating grid item for ${ratioKey}:`, previewInfo);
        
        const gridItem = document.createElement('div');
        gridItem.className = 'grid-item';
        gridItem.dataset.ratio = ratioKey;
        
        // Handle error case
        if (previewInfo.error) {
            gridItem.innerHTML = `
                <div class="preview-error">
                    <i class="fas fa-exclamation-triangle"></i>
                    <p>Preview Error</p>
                </div>
                <div class="ratio-label">${ratioNames[ratioKey] || ratioKey}</div>
                <div class="ratio-dimensions">${previewInfo.dimensions || ''}</div>
                <button class="btn btn-secondary" disabled>
                    <i class="fas fa-sliders-h"></i> Adjust
                </button>
            `;
        } else {
            gridItem.innerHTML = `
                <img src="${previewInfo.url}" alt="${ratioKey} preview" 
                     class="preview-image" data-ratio="${ratioKey}"
                     onerror="this.onerror=null; this.src='data:image/svg+xml,<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"300\" height=\"200\" viewBox=\"0 0 300 200\"><rect width=\"300\" height=\"200\" fill=\"%231e1e1e\"/><text x=\"150\" y=\"100\" font-family=\"Arial\" font-size=\"14\" fill=\"%23ffffff\" text-anchor=\"middle\">Preview Loading...</text></svg>';">
                <div class="ratio-label">${ratioNames[ratioKey] || ratioKey}</div>
                <div class="ratio-dimensions">${previewInfo.dimensions || ''}</div>
                <button class="btn btn-secondary" onclick="openAdjustment('${ratioKey}')">
                    <i class="fas fa-sliders-h"></i> Adjust
                </button>
            `;
        }
        
        gridContainer.appendChild(gridItem);
    }
    
    // Preload images for better UX
    preloadPreviewImages();
}

/**
 * Preload all preview images
 */
function preloadPreviewImages() {
    const images = document.querySelectorAll('.preview-image');
    images.forEach(img => {
        if (img.src && !img.src.startsWith('data:')) {
            const tempImg = new Image();
            tempImg.src = img.src;
        }
    });
}

// ============================================================================
// 4. ADJUSTMENT MODAL FUNCTIONS
// ============================================================================

/**
 * Open adjustment modal for a specific ratio
 */
function openAdjustment(ratio) {
    console.log('Opening adjustment for ratio:', ratio);
    
    currentRatio = ratio;
    
    // Get the current preview image for this ratio
    const previewImg = document.querySelector(`.preview-image[data-ratio="${ratio}"]`);
    
    if (previewImg && previewImg.src) {
        // Use cache busting to ensure fresh image
        const timestamp = new Date().getTime();
        const separator = previewImg.src.includes('?') ? '&' : '?';
        modalImage.src = previewImg.src + separator + 't=' + timestamp;
        console.log('Set modal image to:', modalImage.src);
    } else {
        // Fallback: try to load from server
        modalImage.src = `/preview/${currentSession}_${ratio}_preview.jpg?t=${Date.now()}`;
        console.log('Using fallback modal image:', modalImage.src);
    }
    
    // Set alt text
    modalImage.alt = `${ratio} adjustment preview`;
    
    // Set loading state
    modalImage.onload = () => {
        modalImage.style.opacity = '1';
        console.log('Modal image loaded successfully');
    };
    
    modalImage.onerror = () => {
        console.error('Failed to load modal image:', modalImage.src);
        modalImage.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300"><rect width="400" height="300" fill="%231e1e1e"/><text x="200" y="150" font-family="Arial" font-size="16" fill="%23ffffff" text-anchor="middle">Image not available</text></svg>';
        showToast('Could not load adjustment preview', 'error');
    };
    
    // Reset sliders to saved adjustments or center
    const savedAdj = currentAdjustments[ratio] || { x_offset: 0, y_offset: 0 };
    document.getElementById('xSlider').value = savedAdj.x_offset || 0;
    document.getElementById('ySlider').value = savedAdj.y_offset || 0;
    updateSliderValues(savedAdj.x_offset || 0, savedAdj.y_offset || 0);
    
    // Show modal
    document.getElementById('adjustmentModal').classList.remove('hidden');
    document.body.style.overflow = 'hidden'; // Prevent background scrolling
    
    console.log('Adjustment modal opened for', ratio);
}

/**
 * Close adjustment modal
 */
function closeModal() {
    document.getElementById('adjustmentModal').classList.add('hidden');
    document.body.style.overflow = ''; // Restore scrolling
    console.log('Adjustment modal closed');
}

/**
 * Reset adjustment to center
 */
function resetAdjustment() {
    document.getElementById('xSlider').value = 0;
    document.getElementById('ySlider').value = 0;
    updateSliderValues(0, 0);
    
    // Remove adjustment for this ratio
    delete currentAdjustments[currentRatio];
    
    // Reload original preview
    const modalImage = document.getElementById('modalImage');
    modalImage.src = `/preview/${currentSession}_${currentRatio}_preview.jpg?t=${Date.now()}`;
    
    // Update grid preview
    updateGridPreview(currentRatio, `/preview/${currentSession}_${currentRatio}_preview.jpg`);
    
    showToast('Adjustment reset to center', 'info');
    console.log('Adjustment reset for', currentRatio);
}

/**
 * Save adjustment changes
 */
async function saveAdjustment() {
    const xSlider = document.getElementById('xSlider');
    const ySlider = document.getElementById('ySlider');
    
    const xOffset = parseInt(xSlider.value);
    const yOffset = parseInt(ySlider.value);
    
    console.log(`Saving adjustment for ${currentRatio}: x=${xOffset}, y=${yOffset}`);
    
    // Don't save if no change
    const savedAdj = currentAdjustments[currentRatio] || { x_offset: 0, y_offset: 0 };
    if (savedAdj.x_offset === xOffset && savedAdj.y_offset === yOffset) {
        showToast('No changes to save', 'info');
        closeModal();
        return;
    }
    
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
        console.log('Adjustment response:', data);
        
        if (data.success) {
            // Save adjustment
            currentAdjustments[currentRatio] = {
                x_offset: xOffset,
                y_offset: yOffset
            };
            
            // Save to localStorage
            saveSessionToStorage();
            
            // Update grid preview with cache busting
            if (data.preview_url) {
                const previewUrl = data.preview_url + '?t=' + Date.now();
                updateGridPreview(currentRatio, previewUrl);
                
                // Also update modal image
                modalImage.src = previewUrl;
            } else {
                console.warn('No preview_url in response:', data);
                // Fallback to session-based URL
                const fallbackUrl = `/preview/${currentSession}_${currentRatio}_preview.jpg?t=${Date.now()}`;
                updateGridPreview(currentRatio, fallbackUrl);
                modalImage.src = fallbackUrl;
            }
            
            showToast('Adjustment saved successfully', 'success');
            console.log('Adjustment saved for', currentRatio);
            
            // Close modal after a short delay
            setTimeout(() => {
                closeModal();
            }, 500);
            
        } else {
            showError('Adjustment failed: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Adjustment error:', error);
        showError('Error saving adjustment: ' + error.message);
    } finally {
        hideLoading();
    }
}

/**
 * Update preview image in the grid
 */
function updateGridPreview(ratio, previewUrl) {
    console.log(`Updating grid preview for ${ratio}: ${previewUrl}`);
    
    // Find all preview images for this ratio
    const previewImages = document.querySelectorAll(`.preview-image[data-ratio="${ratio}"]`);
    
    if (previewImages.length === 0) {
        console.warn(`No preview images found for ratio: ${ratio}`);
        return;
    }
    
    // Update each image
    previewImages.forEach(img => {
        // Store old src for comparison
        const oldSrc = img.src;
        
        // Update src with cache busting
        const separator = previewUrl.includes('?') ? '&' : '?';
        img.src = previewUrl + separator + 't=' + Date.now();
        
        // Handle loading
        img.style.opacity = '0.7';
        img.onload = () => {
            img.style.opacity = '1';
            console.log(`Preview updated for ${ratio}`);
        };
        
        img.onerror = () => {
            console.error(`Failed to load updated preview for ${ratio}`);
            img.src = oldSrc; // Revert to old image
            img.style.opacity = '1';
            showToast(`Could not update ${ratio} preview`, 'error');
        };
    });
}

// ============================================================================
// 5. SLIDER CONTROLS
// ============================================================================

/**
 * Initialize slider event listeners
 */
function initializeSliders() {
    const xSlider = document.getElementById('xSlider');
    const ySlider = document.getElementById('ySlider');
    
    if (!xSlider || !ySlider) {
        console.warn('Sliders not found in DOM');
        return;
    }
    
    xSlider.addEventListener('input', function() {
        const yValue = document.getElementById('ySlider').value;
        updateSliderValues(parseInt(this.value), parseInt(yValue));
        updateModalPreviewHint(this.value, yValue);
    });
    
    ySlider.addEventListener('input', function() {
        const xValue = document.getElementById('xSlider').value;
        updateSliderValues(parseInt(xValue), parseInt(this.value));
        updateModalPreviewHint(xValue, this.value);
    });
    
    console.log('Sliders initialized');
}

/**
 * Update slider value displays
 */
function updateSliderValues(x, y) {
    const xValue = document.querySelector('#xSlider + .slider-value');
    const yValue = document.querySelector('#ySlider + .slider-value');
    
    if (xValue) {
        xValue.textContent = x === 0 ? 'Center' : 
                            x > 0 ? `Right ${x}%` : `Left ${Math.abs(x)}%`;
    }
    
    if (yValue) {
        yValue.textContent = y === 0 ? 'Center' : 
                            y > 0 ? `Down ${y}%` : `Up ${Math.abs(y)}%`;
    }
}

/**
 * Show hint about preview update
 */
function updateModalPreviewHint(x, y) {
    const hintElement = document.getElementById('modalPreviewHint');
    if (!hintElement) return;
    
    if (x !== 0 || y !== 0) {
        hintElement.textContent = 'Changes will be visible after saving';
        hintElement.classList.remove('hidden');
    } else {
        hintElement.classList.add('hidden');
    }
}

// ============================================================================
// 6. DOWNLOAD FUNCTIONALITY
// ============================================================================

/**
 * Download all processed images as ZIP
 */
async function downloadAll() {
    console.log('Download requested for session:', currentSession);
    
    if (!currentSession) {
        showError('Please upload an image first');
        return;
    }
    
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
            // Extract filename from response headers
            const contentDisposition = response.headers.get('Content-Disposition');
            let filename = `aspect_ratios_${currentSession}.zip`; // fallback
            
            if (contentDisposition) {
                const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(contentDisposition);
                if (matches != null && matches[1]) {
                    filename = matches[1].replace(/['"]/g, '');
                }
            }
            
            // Create blob and download
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
            
            console.log(`Downloaded: ${filename} (${(blob.size / 1024 / 1024).toFixed(2)} MB)`);
            showToast('Download started! Check your downloads folder.', 'success');
            
        } else {
            const error = await response.json();
            showError('Download failed: ' + (error.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Download error:', error);
        showError('Error downloading files: ' + error.message);
    } finally {
        hideLoading();
    }
}

// ============================================================================
// 7. SESSION MANAGEMENT
// ============================================================================

/**
 * Save current session to localStorage
 */
function saveSessionToStorage() {
    if (!currentSession) return;
    
    const sessionData = {
        session_id: currentSession,
        adjustments: currentAdjustments,
        timestamp: new Date().toISOString()
    };
    
    localStorage.setItem('aspectRatioAutomatorSession', JSON.stringify(sessionData));
    console.log('Session saved to localStorage');
}

/**
 * Check for previous session in localStorage
 */
function checkPreviousSession() {
    try {
        const savedSession = localStorage.getItem('aspectRatioAutomatorSession');
        if (savedSession) {
            const sessionData = JSON.parse(savedSession);
            const sessionAge = new Date() - new Date(sessionData.timestamp);
            const maxAge = 30 * 60 * 1000; // 30 minutes
            
            if (sessionAge < maxAge) {
                console.log('Found previous session:', sessionData.session_id);
                // Could implement session restoration here
            } else {
                localStorage.removeItem('aspectRatioAutomatorSession');
            }
        }
    } catch (error) {
        console.warn('Error checking previous session:', error);
        localStorage.removeItem('aspectRatioAutomatorSession');
    }
}

/**
 * Clean up session files on server
 */
async function cleanupSession() {
    if (!currentSession) return;
    
    try {
        await fetch('/cleanup', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ session_id: currentSession })
        });
        
        console.log('Session cleanup requested');
    } catch (error) {
        console.warn('Cleanup error:', error);
    }
}

// ============================================================================
// 8. UI UTILITY FUNCTIONS
// ============================================================================

/**
 * Show loading overlay
 */
function showLoading() {
    if (loadingOverlay) {
        loadingOverlay.classList.remove('hidden');
    }
}

/**
 * Hide loading overlay
 */
function hideLoading() {
    if (loadingOverlay) {
        loadingOverlay.classList.add('hidden');
    }
}

/**
 * Show error message
 */
function showError(message) {
    console.error('Error:', message);
    alert('Error: ' + message);
}

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
    // Remove existing toasts
    const existingToasts = document.querySelectorAll('.toast');
    existingToasts.forEach(toast => toast.remove());
    
    // Create toast
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span>${message}</span>
        <button onclick="this.parentElement.remove()">&times;</button>
    `;
    
    // Add styles if not already present
    if (!document.querySelector('#toast-styles')) {
        const style = document.createElement('style');
        style.id = 'toast-styles';
        style.textContent = `
            .toast {
                position: fixed;
                top: 20px;
                right: 20px;
                padding: 12px 20px;
                border-radius: 8px;
                color: white;
                font-weight: 500;
                z-index: 10000;
                display: flex;
                align-items: center;
                gap: 10px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                animation: slideIn 0.3s ease;
            }
            .toast-success { background-color: #10b981; }
            .toast-error { background-color: #ef4444; }
            .toast-warning { background-color: #f59e0b; }
            .toast-info { background-color: #3b82f6; }
            .toast button {
                background: none;
                border: none;
                color: white;
                font-size: 20px;
                cursor: pointer;
                padding: 0;
                line-height: 1;
            }
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
        `;
        document.head.appendChild(style);
    }
    
    document.body.appendChild(toast);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (toast.parentElement) {
            toast.remove();
        }
    }, 5000);
    
    console.log(`Toast: ${message} (${type})`);
}

// ============================================================================
// 9. EVENT LISTENERS & CLEANUP
// ============================================================================

// Close modal when clicking outside
document.addEventListener('click', (e) => {
    const modal = document.getElementById('adjustmentModal');
    if (modal && !modal.contains(e.target) && !e.target.closest('.grid-item')) {
        if (!modal.classList.contains('hidden')) {
            closeModal();
        }
    }
});

// Close modal with Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const modal = document.getElementById('adjustmentModal');
        if (modal && !modal.classList.contains('hidden')) {
            closeModal();
        }
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', async (e) => {
    // Only cleanup if we have a session
    if (currentSession) {
        // Save current state
        saveSessionToStorage();
        
        // Optional: cleanup server files (commented for now as it might interrupt downloads)
        // await cleanupSession();
    }
});

// ============================================================================
// 10. DEBUG FUNCTIONS (Optional)
// ============================================================================

/**
 * Debug function to check current state
 */
function debugState() {
    console.log('=== DEBUG STATE ===');
    console.log('Current Session:', currentSession);
    console.log('Current Adjustments:', currentAdjustments);
    console.log('Current Ratio:', currentRatio);
    
    // Check preview images
    const previews = document.querySelectorAll('.preview-image');
    console.log(`Found ${previews.length} preview images`);
    previews.forEach((img, i) => {
        console.log(`Preview ${i}:`, {
            src: img.src,
            complete: img.complete,
            naturalWidth: img.naturalWidth,
            naturalHeight: img.naturalHeight
        });
    });
}

// Make debug function available globally
window.debugState = debugState;

console.log('Aspect Ratio Automator script loaded successfully!');