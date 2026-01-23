from PySide6.QtCore import QObject, QTimer

class ProgressHandler(QObject):
    def __init__(self, app):
        super().__init__()
        self.app = app
        
    def handle_progress(self, message, percentage):
        self.app.update_progress(message, percentage)
        
    def handle_file_update(self, file_path, is_complete):
        if is_complete:
            self.app.restore_title_label()
        else:
            self.app.update_thumbnail(file_path)

class ProgressUIManager:
    def __init__(self, progress_bar):
        self.progress_bar = progress_bar
        self.update_timer = QTimer()
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self._update_progress_ui)
        self.pending_progress_message = None
        self.pending_progress_percentage = None
    
    def update_progress(self, message, percentage=None):
        if not self.progress_bar:
            return
        self.pending_progress_message = message
        self.pending_progress_percentage = percentage
        if not self.update_timer.isActive():
            self.update_timer.start(50)

    def _update_progress_ui(self):
        if not self.progress_bar:
            return
        if self.pending_progress_percentage is not None:
            self.progress_bar.setValue(self.pending_progress_percentage)
            self.progress_bar.setFormat(f"{self.pending_progress_message} - %p%")
        else:
            self.progress_bar.setFormat(self.pending_progress_message)
