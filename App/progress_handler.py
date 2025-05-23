from PySide6.QtCore import QObject, QTimer

class ProgressHandler(QObject):
    """Handles progress updates from the background thread"""
    
    def __init__(self, app):
        super().__init__()
        self.app = app
        
    def handle_progress(self, message, percentage):
        """Handle progress updates from the background thread"""
        # This method is called in the main thread via signal/slot
        self.app.update_progress(message, percentage)
        
    def handle_file_update(self, file_path, is_complete):
        """Handle file updates from the background thread"""
        # This method is called in the main thread via signal/slot
        if is_complete:
            self.app.restore_title_label()
        else:
            self.app.update_thumbnail(file_path)

class ProgressUIManager:
    """Manages progress UI updates to prevent recursive repaints"""
    
    def __init__(self, progress_bar):
        self.progress_bar = progress_bar
        self.update_timer = QTimer()
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self._update_progress_ui)
        self.pending_progress_message = None
        self.pending_progress_percentage = None
    
    def update_progress(self, message, percentage=None):
        """
        Schedule progress bar update with a message and percentage.
        Uses a timer to prevent recursive repaints.
        
        Args:
            message: Message to display
            percentage: Completion percentage (0-100)
        """
        if not self.progress_bar:
            return
            
        # Store the updated values for use when the timer fires
        self.pending_progress_message = message
        self.pending_progress_percentage = percentage
        
        # Restart the timer to update UI shortly
        # If timer is already active, this will defer the update 
        # until all pending events are processed
        if not self.update_timer.isActive():
            self.update_timer.start(50)  # 50ms delay

    def _update_progress_ui(self):
        """
        Actually update the UI with the pending progress information.
        This is called by the timer to prevent recursive repaints.
        """
        if not self.progress_bar:
            return
            
        if self.pending_progress_percentage is not None:
            self.progress_bar.setValue(self.pending_progress_percentage)
            self.progress_bar.setFormat(f"{self.pending_progress_message} - %p%")
        else:
            self.progress_bar.setFormat(self.pending_progress_message)
