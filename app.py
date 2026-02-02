"""
Aspect-Ratio Automator - Production Deployment Version
Optimized for Render.com with cloud storage considerations
"""

# ============================================================================
# 1. IMPORTS & CONFIGURATION
# ============================================================================

import os
import uuid
import zipfile
import shutil
import logging
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, jsonify, send_file, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
import tempfile

# Import utility modules
from utils.image_processor import ImageProcessor
from utils.dpi_checker import check_dpi

# Load environment variables
from dotenv import load_dotenv
load_dotenv()  # Loads from .env file locally

# ============================================================================
# 2. FLASK APP INITIALIZATION
# ============================================================================

app = Flask(__name__)

# Security: Enable CORS for API requests
CORS(app)

# Rate limiting to prevent abuse
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",  # Simple in-memory storage for starters
    strategy="fixed-window"  # Rate limiting strategy
)

# ============================================================================
# 3. APPLICATION CONFIGURATION
# ============================================================================

# SECURITY: Get secret key from environment variable (CRITICAL for production)
# Render will set this as an environment variable
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

# File upload configuration
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB limit

# File type restrictions
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'tiff', 'tif'}

# Render uses ephemeral storage - we'll use /tmp directory
# This ensures files survive between requests but not between deploys
app.config['UPLOAD_FOLDER'] = os.path.join(tempfile.gettempdir(), 'ara_uploads')
app.config['PROCESSED_FOLDER'] = os.path.join(tempfile.gettempdir(), 'ara_processed')
app.config['SESSION_FOLDER'] = os.path.join(tempfile.gettempdir(), 'ara_sessions')

# Session configuration (filesystem sessions for simplicity)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = app.config['SESSION_FOLDER']
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

# ============================================================================
# 4. DIRECTORY SETUP
# ============================================================================

def setup_directories():
    """
    Create necessary directories for file storage.
    Uses /tmp on Render which is ephemeral but persists during app runtime.
    """
    directories = [
        app.config['UPLOAD_FOLDER'],
        app.config['PROCESSED_FOLDER'],
        app.config['SESSION_FOLDER']
    ]
    
    for directory in directories:
        try:
            os.makedirs(directory, exist_ok=True)
            app.logger.info(f"Directory ensured: {directory}")
        except Exception as e:
            app.logger.error(f"Failed to create directory {directory}: {e}")
            # Fallback to current directory if /tmp fails
            if directory == app.config['UPLOAD_FOLDER']:
                app.config['UPLOAD_FOLDER'] = 'uploads_fallback'
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize directories when app starts
with app.app_context():
    setup_directories()

# ============================================================================
# 5. LOGGING SETUP
# ============================================================================

# Configure logging for production
if not app.debug:
    # Basic logging to stdout (Render captures this)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # File logging (optional, for debugging)
    log_file = os.path.join(tempfile.gettempdir(), 'ara_app.log')
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    app.logger.addHandler(file_handler)

app.logger.info('Aspect-Ratio Automator starting up...')

# ============================================================================
# 6. HELPER FUNCTIONS
# ============================================================================

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def clean_filename(filename):
    """
    Clean filename for safe usage.
    Removes special characters and ensures it's filesystem-safe.
    """
    # Keep only alphanumeric, spaces, dashes, underscores, and dots
    import re
    name = re.sub(r'[^\w\s\-_.]', '', filename)
    # Replace spaces with underscores
    name = name.replace(' ', '_')
    # Truncate if too long
    if len(name) > 100:
        name = name[:50] + "_" + name[-50:]
    return name

def get_session_file_path(session_id, original_filename):
    """
    Generate a unique file path for an uploaded file.
    Format: sessionid_timestamp_originalname
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    clean_name = clean_filename(original_filename)
    filename = f"{session_id}_{timestamp}_{clean_name}"
    return os.path.join(app.config['UPLOAD_FOLDER'], filename)

def cleanup_old_files():
    """
    Clean up files older than 24 hours to prevent disk filling.
    Called periodically or on startup.
    """
    try:
        current_time = datetime.now()
        for folder in [app.config['UPLOAD_FOLDER'], app.config['PROCESSED_FOLDER']]:
            if os.path.exists(folder):
                for filename in os.listdir(folder):
                    filepath = os.path.join(folder, filename)
                    try:
                        # Get file modification time
                        file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                        # Delete if older than 24 hours
                        if current_time - file_time > timedelta(hours=24):
                            os.remove(filepath)
                            app.logger.info(f"Cleaned up old file: {filename}")
                    except Exception as e:
                        app.logger.warning(f"Could not delete {filepath}: {e}")
    except Exception as e:
        app.logger.error(f"Error in cleanup: {e}")

# ============================================================================
# 7. ROUTES
# ============================================================================

@app.route('/')
def index():
    """Main application page"""
    app.logger.info('Home page accessed')
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
@limiter.limit("10 per minute")  # Rate limit uploads
def upload_file():
    """
    Handle file uploads with validation and processing.
    Returns preview URLs for the 5 aspect ratios.
    """
    app.logger.info('Upload request received')
    
    # Check if file was uploaded
    if 'file' not in request.files:
        app.logger.warning('No file in upload request')
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    
    # Validate file
    if file.filename == '':
        app.logger.warning('Empty filename in upload')
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        app.logger.warning(f'Invalid file type: {file.filename}')
        return jsonify({'error': 'File type not allowed. Use JPG, PNG, or TIFF.'}), 400
    
    try:
        # Generate unique session ID
        session_id = str(uuid.uuid4())
        session['session_id'] = session_id
        
        # Create secure filename with session ID
        original_filename = secure_filename(file.filename)
        original_path = get_session_file_path(session_id, original_filename)
        
        # Save file
        file.save(original_path)
        app.logger.info(f'File saved: {original_path} ({os.path.getsize(original_path)} bytes)')
        
        # Check DPI
        dpi_warning = check_dpi(original_path)
        if dpi_warning:
            app.logger.warning(f'Low DPI detected: {original_filename}')
        
        # Process image into all ratios
        processor = ImageProcessor(original_path, session_id, app.config['PROCESSED_FOLDER'])
        previews = processor.create_previews()
        
        app.logger.info(f'Previews created for session: {session_id}')
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'original_filename': original_filename,
            'dpi_warning': dpi_warning,
            'previews': previews
        })
        
    except Exception as e:
        app.logger.error(f'Upload error: {str(e)}', exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/adjust', methods=['POST'])
@limiter.limit("30 per minute")  # Rate limit adjustments
def adjust_crop():
    """
    Adjust crop position for a specific aspect ratio.
    """
    data = request.json
    session_id = data.get('session_id')
    ratio = data.get('ratio')
    x_offset = data.get('x_offset', 0)
    y_offset = data.get('y_offset', 0)
    
    app.logger.info(f'Adjust request: session={session_id}, ratio={ratio}, x={x_offset}, y={y_offset}')
    
    if not session_id or not ratio:
        return jsonify({'error': 'Missing parameters'}), 400
    
    # Find original file
    original_path = None
    for file in os.listdir(app.config['UPLOAD_FOLDER']):
        if file.startswith(session_id):
            original_path = os.path.join(app.config['UPLOAD_FOLDER'], file)
            break
    
    if not original_path or not os.path.exists(original_path):
        app.logger.warning(f'Original file not found for session: {session_id}')
        return jsonify({'error': 'File not found. Please upload again.'}), 404
    
    try:
        processor = ImageProcessor(original_path, session_id, app.config['PROCESSED_FOLDER'])
        preview_path = processor.adjust_crop(ratio, x_offset, y_offset)
        
        # Generate URL for the preview
        preview_filename = os.path.basename(preview_path)
        
        app.logger.info(f'Adjustment saved: {preview_filename}')
        
        return jsonify({
            'success': True,
            'preview_url': f'/preview/{preview_filename}'
        })
        
    except Exception as e:
        app.logger.error(f'Adjustment error: {str(e)}', exc_info=True)
        return jsonify({'error': f'Adjustment failed: {str(e)}'}), 500

@app.route('/preview/<filename>')
def get_preview(filename):
    """
    Serve preview images.
    Security: Validate filename to prevent directory traversal.
    """
    # Security check: Ensure filename is safe
    if '..' in filename or filename.startswith('/'):
        app.logger.warning(f'Potential directory traversal attempt: {filename}')
        return jsonify({'error': 'Invalid filename'}), 400
    
    preview_path = os.path.join(app.config['PROCESSED_FOLDER'], filename)
    
    if os.path.exists(preview_path):
        # Cache control for better performance
        return send_file(preview_path, mimetype='image/jpeg', 
                        max_age=3600)  # Cache for 1 hour
    else:
        app.logger.warning(f'Preview not found: {filename}')
        return jsonify({'error': 'Preview not found'}), 404

@app.route('/download', methods=['POST'])
@limiter.limit("5 per minute")  # Strict limit on downloads
def download_all():
    """
    Process all ratios and return a ZIP file.
    Uses new naming format: OriginalName_printready.zip
    """
    data = request.json
    session_id = data.get('session_id')
    adjustments = data.get('adjustments', {})
    
    app.logger.info(f'Download request for session: {session_id}')
    
    if not session_id:
        return jsonify({'error': 'Session ID required'}), 400
    
    # Find original file and extract original name
    original_path = None
    original_filename = None
    
    for file in os.listdir(app.config['UPLOAD_FOLDER']):
        if file.startswith(session_id):
            original_path = os.path.join(app.config['UPLOAD_FOLDER'], file)
            # Extract original filename (remove session_id_timestamp_ prefix)
            parts = file.split('_', 2)  # Split into [session_id, timestamp, original_name]
            if len(parts) >= 3:
                original_filename = parts[2]
            else:
                original_filename = file
            break
    
    if not original_path or not os.path.exists(original_path):
        app.logger.warning(f'Original file not found for download: {session_id}')
        return jsonify({'error': 'Original file not found. Please upload again.'}), 404
    
    try:
        # Process all images with adjustments
        processor = ImageProcessor(original_path, session_id, app.config['PROCESSED_FOLDER'])
        output_files = processor.process_all_ratios(adjustments)
        
        if not output_files:
            app.logger.error(f'No output files generated for session: {session_id}')
            return jsonify({'error': 'Failed to process images'}), 500
        
        # Add Printing_Guide.pdf if it exists
        pdf_path = os.path.join('static', 'Printing_Guide.pdf')
        if os.path.exists(pdf_path):
            output_files.append(pdf_path)
        else:
            app.logger.warning('Printing_Guide.pdf not found in static folder')
        
        # Create ZIP file with new naming format: OriginalName_printready.zip
        base_name = os.path.splitext(original_filename)[0]
        clean_base_name = clean_filename(base_name)
        zip_filename = f"{clean_base_name}_printready.zip"
        
        # Ensure ZIP filename is not empty
        if not zip_filename or zip_filename == '_printready.zip':
            zip_filename = f"aspect_ratios_{session_id[:8]}.zip"
        
        zip_path = os.path.join(app.config['PROCESSED_FOLDER'], zip_filename)
        
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
            app.logger.info(f'ZIP created: {zip_filename} ({zip_size} bytes)')
            
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
    """
    Health check endpoint for Render monitoring.
    """
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'upload_dir': os.path.exists(app.config['UPLOAD_FOLDER']),
        'processed_dir': os.path.exists(app.config['PROCESSED_FOLDER']),
        'session_count': len(os.listdir(app.config['UPLOAD_FOLDER'])) if os.path.exists(app.config['UPLOAD_FOLDER']) else 0
    })

@app.route('/cleanup', methods=['POST'])
def cleanup_session():
    """
    Clean up files for a specific session.
    Called when user leaves the page or session expires.
    """
    data = request.json
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({'error': 'Session ID required'}), 400
    
    app.logger.info(f'Cleanup requested for session: {session_id}')
    
    files_removed = 0
    
    # Clean up files in uploads and processed folders
    for folder in [app.config['UPLOAD_FOLDER'], app.config['PROCESSED_FOLDER']]:
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
# 8. ERROR HANDLERS
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
    return jsonify({'error': 'File size exceeds 50MB limit'}), 413

@app.errorhandler(429)
def rate_limit_exceeded(error):
    """Handle rate limit errors"""
    app.logger.warning(f'Rate limit exceeded: {request.remote_addr}')
    return jsonify({'error': 'Rate limit exceeded. Please wait and try again.'}), 429

@app.errorhandler(500)
def internal_error(error):
    """Handle internal server errors"""
    app.logger.error(f'500 error: {str(error)}', exc_info=True)
    return jsonify({'error': 'Internal server error'}), 500

# ============================================================================
# 9. APPLICATION STARTUP
# ============================================================================

if __name__ == '__main__':
    # Clean up old files on startup
    cleanup_old_files()
    
    # Get port from environment variable (Render sets this)
    port = int(os.environ.get('PORT', 5000))
    
    # Determine if we're in development or production
    is_production = os.environ.get('FLASK_ENV') == 'production'
    
    if is_production:
        # Production: Use all network interfaces
        app.logger.info(f'Starting production server on port {port}')
        app.run(host='0.0.0.0', port=port)
    else:
        # Development: Localhost with debug
        app.logger.info(f'Starting development server on port {port}')
        app.run(host='127.0.0.1', port=port, debug=True)