"""
Aspect-Ratio Automator - Production Deployment Version
Fixed: Preview images not showing after adjustments
"""

import os
import uuid
import zipfile
import tempfile
import logging
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, jsonify, send_file, session

# Import utility modules
from utils.image_processor import ImageProcessor
from utils.dpi_checker import check_dpi

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# ============================================================================
# 1. FLASK APP INITIALIZATION
# ============================================================================

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

# ============================================================================
# 2. APPLICATION CONFIGURATION
# ============================================================================

# File upload configuration (reduced for free tier)
app.config['MAX_CONTENT_LENGTH'] = 15 * 1024 * 1024  # 15MB

# File type restrictions
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'tiff', 'tif'}

# Use /tmp directory for Render compatibility
UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'ara_uploads')
PROCESSED_FOLDER = os.path.join(tempfile.gettempdir(), 'ara_processed')

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER

# ============================================================================
# 3. LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
app.logger = logging.getLogger(__name__)
app.logger.info('Aspect-Ratio Automator starting up...')

# ============================================================================
# 4. HELPER FUNCTIONS
# ============================================================================

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def clean_filename(filename):
    """Clean filename for safe usage."""
    import re
    name = re.sub(r'[^\w\s\-_.]', '', filename)
    name = name.replace(' ', '_')
    if len(name) > 100:
        name = name[:50] + "_" + name[-50:]
    return name

def get_session_original_path(session_id):
    """Find the original uploaded file for a session."""
    if not session_id:
        return None
    
    for file in os.listdir(UPLOAD_FOLDER):
        if file.startswith(session_id):
            return os.path.join(UPLOAD_FOLDER, file)
    
    return None

# ============================================================================
# 5. ROUTES
# ============================================================================

@app.route('/')
def index():
    """Main application page"""
    app.logger.info('Home page accessed')
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file uploads"""
    app.logger.info('Upload request received')
    
    if 'file' not in request.files:
        app.logger.warning('No file in upload request')
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        app.logger.warning('Empty filename in upload')
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        app.logger.warning(f'Invalid file type: {file.filename}')
        return jsonify({'error': 'File type not allowed. Use JPG, PNG, or TIFF.'}), 400
    
    try:
        # Check file size
        file.seek(0, 2)  # Seek to end to get size
        file_size = file.tell()
        file.seek(0)  # Reset to beginning
        
        if file_size > app.config['MAX_CONTENT_LENGTH']:
            max_mb = app.config['MAX_CONTENT_LENGTH'] / 1024 / 1024
            return jsonify({'error': f'File exceeds maximum size of {max_mb}MB'}), 400
        
        # Generate session ID
        session_id = str(uuid.uuid4())
        session['session_id'] = session_id
        
        # Save file with session ID prefix
        original_filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        saved_filename = f"{session_id}_{timestamp}_{original_filename}"
        original_path = os.path.join(UPLOAD_FOLDER, saved_filename)
        
        file.save(original_path)
        app.logger.info(f'File saved: {saved_filename} ({file_size/1024/1024:.2f}MB)')
        
        # Check DPI
        dpi_warning = check_dpi(original_path)
        if dpi_warning:
            app.logger.warning(f'Low DPI detected: {original_filename}')
        
        # Process previews
        processor = ImageProcessor(original_path, session_id, PROCESSED_FOLDER)
        previews = processor.create_previews()
        
        if not previews:
            return jsonify({'error': 'Failed to create previews'}), 500
        
        response_data = {
            'success': True,
            'session_id': session_id,
            'original_filename': original_filename,
            'dpi_warning': dpi_warning,
            'previews': previews
        }
        
        # Add warning for large files
        if file_size > 10 * 1024 * 1024:
            response_data['size_warning'] = 'Large file detected. Free tier may have memory limitations.'
        
        return jsonify(response_data)
        
    except Exception as e:
        app.logger.error(f'Upload error: {str(e)}', exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/adjust', methods=['POST'])
def adjust_crop():
    """Adjust crop position with proper preview handling"""
    data = request.json
    session_id = data.get('session_id')
    ratio = data.get('ratio')
    x_offset = data.get('x_offset', 0)
    y_offset = data.get('y_offset', 0)
    
    app.logger.info(f'Adjust request: session={session_id}, ratio={ratio}, x={x_offset}, y={y_offset}')
    
    if not session_id or not ratio:
        return jsonify({'error': 'Missing parameters'}), 400
    
    # Find original file
    original_path = get_session_original_path(session_id)
    
    if not original_path or not os.path.exists(original_path):
        app.logger.warning(f'Original file not found for session: {session_id}')
        return jsonify({'error': 'File not found. Please upload again.'}), 404
    
    try:
        processor = ImageProcessor(original_path, session_id, PROCESSED_FOLDER)
        preview_filename = processor.adjust_crop(ratio, x_offset, y_offset)
        
        if preview_filename:
            app.logger.info(f'Adjustment saved successfully: {preview_filename}')
            
            # CRITICAL: Return the correct preview URL
            # This should match what the /preview/<filename> endpoint expects
            preview_url = f'/preview/{preview_filename}'
            
            return jsonify({
                'success': True,
                'preview_url': preview_url,
                'preview_filename': preview_filename  # For debugging
            })
        else:
            app.logger.error(f'Adjustment failed: processor returned None for {ratio}')
            return jsonify({'error': 'Adjustment failed - could not create preview'}), 500
            
    except Exception as e:
        app.logger.error(f'Adjustment error: {str(e)}', exc_info=True)
        return jsonify({'error': f'Adjustment failed: {str(e)}'}), 500

@app.route('/preview/<filename>')
def get_preview(filename):
    """Serve preview images with proper debugging"""
    # Security check
    if '..' in filename or filename.startswith('/'):
        return jsonify({'error': 'Invalid filename'}), 400
    
    preview_path = os.path.join(PROCESSED_FOLDER, filename)
    
    # Debug logging
    app.logger.info(f"Preview request: {filename}")
    app.logger.info(f"Looking in: {PROCESSED_FOLDER}")
    app.logger.info(f"Full path: {preview_path}")
    app.logger.info(f"File exists: {os.path.exists(preview_path)}")
    
    if os.path.exists(preview_path):
        app.logger.info(f"Serving preview: {filename} ({os.path.getsize(preview_path)} bytes)")
        return send_file(preview_path, mimetype='image/jpeg', max_age=300)
    else:
        # List available previews for debugging
        try:
            available_files = os.listdir(PROCESSED_FOLDER)
            preview_files = [f for f in available_files if f.endswith(('.jpg', '.jpeg', '.png'))]
            app.logger.warning(f"Preview not found: {filename}")
            app.logger.warning(f"Available previews: {preview_files[:10]}")
        except Exception as e:
            app.logger.error(f"Error listing files: {e}")
        
        return jsonify({'error': f'Preview not found: {filename}'}), 404

@app.route('/download', methods=['POST'])
def download_all():
    """Process all ratios and return ZIP file"""
    data = request.json
    session_id = data.get('session_id')
    adjustments = data.get('adjustments', {})
    
    app.logger.info(f'Download request for session: {session_id}')
    
    if not session_id:
        return jsonify({'error': 'Session ID required'}), 400
    
    # Find original file
    original_path = get_session_original_path(session_id)
    
    if not original_path:
        return jsonify({'error': 'Original file not found. Please upload again.'}), 404
    
    # Extract original filename from the saved file
    original_filename = None
    for file in os.listdir(UPLOAD_FOLDER):
        if file.startswith(session_id):
            # Extract original name (remove session_id_timestamp_ prefix)
            parts = file.split('_', 2)
            if len(parts) >= 3:
                original_filename = parts[2]
            else:
                original_filename = file
            break
    
    if not original_filename:
        original_filename = f"image_{session_id[:8]}"
    
    try:
        # Process all images with adjustments
        processor = ImageProcessor(original_path, session_id, PROCESSED_FOLDER)
        output_files = processor.process_all_ratios(adjustments)
        
        if not output_files:
            app.logger.error('No output files generated')
            return jsonify({'error': 'Failed to process images'}), 500
        
        # Add Printing_Guide.pdf
        pdf_path = os.path.join('static', 'Printing_Guide.pdf')
        if os.path.exists(pdf_path):
            output_files.append(pdf_path)
        else:
            app.logger.warning('Printing_Guide.pdf not found in static folder')
        
        # Create ZIP file with naming: OriginalName_printready.zip
        base_name = os.path.splitext(original_filename)[0]
        clean_base_name = clean_filename(base_name)
        zip_filename = f"{clean_base_name}_printready.zip"
        
        # Ensure ZIP filename is valid
        if not zip_filename or zip_filename == '_printready.zip':
            zip_filename = f"aspect_ratios_{session_id[:8]}.zip"
        
        zip_path = os.path.join(PROCESSED_FOLDER, zip_filename)
        
        # Create ZIP with compression
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in output_files:
                    if os.path.exists(file_path):
                        arcname = os.path.basename(file_path)
                        zipf.write(file_path, arcname)
                        app.logger.info(f'Added to ZIP: {arcname}')
            
            # Verify ZIP was created
            if not os.path.exists(zip_path):
                app.logger.error(f'ZIP file not created: {zip_path}')
                return jsonify({'error': 'Failed to create ZIP file'}), 500
                
            zip_size = os.path.getsize(zip_path)
            app.logger.info(f'ZIP created: {zip_filename} ({zip_size/1024/1024:.2f}MB)')
            
        except Exception as e:
            app.logger.error(f'ZIP creation error: {str(e)}', exc_info=True)
            return jsonify({'error': f'ZIP creation failed: {str(e)}'}), 500
        
        # Send file with new naming
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=zip_filename,
            mimetype='application/zip'
        )
        
    except Exception as e:
        app.logger.error(f'Download error: {str(e)}', exc_info=True)
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    upload_count = len([f for f in os.listdir(UPLOAD_FOLDER) if os.path.isfile(os.path.join(UPLOAD_FOLDER, f))])
    processed_count = len([f for f in os.listdir(PROCESSED_FOLDER) if os.path.isfile(os.path.join(PROCESSED_FOLDER, f))])
    
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'upload_dir': os.path.exists(UPLOAD_FOLDER),
        'processed_dir': os.path.exists(PROCESSED_FOLDER),
        'upload_files': upload_count,
        'processed_files': processed_count,
        'max_file_size_mb': app.config['MAX_CONTENT_LENGTH'] / 1024 / 1024
    })

@app.route('/debug')
def debug_info():
    """Debug endpoint to see what files exist"""
    upload_files = os.listdir(UPLOAD_FOLDER)[:20]
    processed_files = os.listdir(PROCESSED_FOLDER)[:20]
    
    return jsonify({
        'upload_folder': UPLOAD_FOLDER,
        'processed_folder': PROCESSED_FOLDER,
        'upload_files': upload_files,
        'processed_files': processed_files,
        'session_id': session.get('session_id', 'none')
    })

@app.route('/cleanup', methods=['POST'])
def cleanup_session():
    """Clean up files for a specific session"""
    data = request.json
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({'error': 'Session ID required'}), 400
    
    app.logger.info(f'Cleanup requested for session: {session_id}')
    
    files_removed = 0
    
    # Clean up files in both folders
    for folder in [UPLOAD_FOLDER, PROCESSED_FOLDER]:
        if os.path.exists(folder):
            for file in os.listdir(folder):
                if file.startswith(session_id):
                    try:
                        os.remove(os.path.join(folder, file))
                        files_removed += 1
                    except Exception as e:
                        app.logger.warning(f'Could not remove {file}: {e}')
    
    app.logger.info(f'Cleanup completed: {files_removed} files removed')
    return jsonify({'success': True, 'files_removed': files_removed})

# ============================================================================
# 6. ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    app.logger.warning(f'404 error: {request.url}')
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(413)
def too_large(error):
    """Handle file too large errors"""
    app.logger.warning(f'File too large: {request.remote_addr}')
    max_mb = app.config['MAX_CONTENT_LENGTH'] / 1024 / 1024
    return jsonify({'error': f'File size exceeds {max_mb}MB limit'}), 413

@app.errorhandler(500)
def internal_error(error):
    """Handle internal server errors"""
    app.logger.error(f'500 error: {str(error)}', exc_info=True)
    return jsonify({'error': 'Internal server error'}), 500

# ============================================================================
# 7. APPLICATION STARTUP
# ============================================================================

if __name__ == '__main__':
    # Log startup information
    app.logger.info(f'Upload folder: {UPLOAD_FOLDER}')
    app.logger.info(f'Processed folder: {PROCESSED_FOLDER}')
    app.logger.info(f'Max file size: {app.config["MAX_CONTENT_LENGTH"]/1024/1024}MB')
    
    # Get port from environment variable
    port = int(os.environ.get('PORT', 5000))
    
    # Determine environment
    is_production = os.environ.get('FLASK_ENV') == 'production'
    
    if is_production:
        # Production: Use all network interfaces
        app.logger.info(f'Starting production server on port {port}')
        app.run(host='0.0.0.0', port=port)
    else:
        # Development: Localhost with debug
        app.logger.info(f'Starting development server on port {port}')
        app.run(host='127.0.0.1', port=port, debug=True)